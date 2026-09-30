"""
FreightProspecting V1 — Stage 2 Schema & Integrity Automated Tests
Covers points 1-22 of Stage 2 verification requirements.
"""

from datetime import datetime
import sqlite3
import pytest

from src.backend.db.connection import create_connection, get_db_connection
from src.backend.db.schema import init_db
from src.backend.db.validators import (
    calculate_gross_margin,
    validate_date_string,
    validate_iso_timestamp,
)
from src.backend.db.claims_engine import record_claim, validate_single_subject


@pytest.fixture
def memory_db():
    """Provides an isolated, in-memory SQLite database initialized with the full schema."""
    conn = create_connection(":memory:")
    init_db(":memory:")
    # Initialize in the active connection
    from src.backend.db.schema import SCHEMA_DDL
    conn.executescript(SCHEMA_DDL)
    yield conn
    conn.close()


@pytest.fixture
def file_db(tmp_path):
    """Provides a temporary file-based SQLite database to test WAL mode."""
    db_file = tmp_path / "test_prospects.db"
    conn = create_connection(db_file, create_if_missing=True)
    init_db(db_file)
    yield conn, db_file
    conn.close()


# ============================================================================
# 1. Database Initialization & Connection PRAGMAs
# ============================================================================
def test_database_initializes_successfully(memory_db):
    """Test 1: Verify database initializes without errors."""
    assert memory_db is not None
    cur = memory_db.execute("SELECT 1")
    assert cur.fetchone()[0] == 1


def test_foreign_keys_are_enabled(memory_db):
    """Test 2: Verify PRAGMA foreign_keys = ON is enforced."""
    cur = memory_db.execute("PRAGMA foreign_keys;")
    result = cur.fetchone()[0]
    assert result == 1, "Foreign keys must be ON"


def test_wal_configured_for_production_db(file_db):
    """Test 3: Verify WAL mode is configured on file-based databases."""
    conn, _ = file_db
    cur = conn.execute("PRAGMA journal_mode;")
    mode = cur.fetchone()[0].upper()
    assert mode == "WAL", f"Expected WAL journal mode, got {mode}"


# ============================================================================
# 4. Expected Tables & Views Exist
# ============================================================================
def test_expected_tables_exist(memory_db):
    """Test 4: Verify all 17 physical tables from docs/ARCHITECTURE.md exist."""
    cur = memory_db.execute(
        "SELECT name, type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%';"
    )
    objects = {row["name"]: row["type"] for row in cur.fetchall()}

    expected_tables = {
        "companies",
        "company_relationships",
        "facilities",
        "facility_commodities",
        "contacts",
        "claims",
        "evidence_sources",
        "claim_evidence",
        "freight_demand_signals",
        "load_opportunities",
        "carriers",
        "carrier_lane_activity",
        "capacity_postings",
        "load_capacity_matches",
        "suppressions",
        "outreach_logs",
        "settings",
    }
    missing = expected_tables - set(objects.keys())
    assert not missing, f"Missing required tables: {missing}"

    for t in expected_tables:
        assert objects[t] == "table", f"Expected '{t}' to be a physical table, but got {objects[t]}"

    # Verify accidental name does not exist
    assert "suppression_status_records" not in objects, "suppression_status_records must NOT exist in schema"
    # Verify no view alias exists
    views = [name for name, otype in objects.items() if otype == "view"]
    assert len(views) == 0, f"Expected 0 views, found views: {views}"


# ============================================================================
# 5. Important Indexes Exist
# ============================================================================
def test_important_indexes_exist(memory_db):
    """Test 5: Verify the 10 partial unique indexes on claims and foreign key indexes exist."""
    cur = memory_db.execute("SELECT name FROM sqlite_master WHERE type = 'index';")
    indexes = {row["name"] for row in cur.fetchall()}

    expected_indexes = {
        "uq_current_claim_company",
        "uq_current_claim_comp_rel",
        "uq_current_claim_facility",
        "uq_current_claim_commodity",
        "uq_current_claim_contact",
        "uq_current_claim_fgt_sig",
        "uq_current_claim_load",
        "uq_current_claim_carrier",
        "uq_current_claim_lane_act",
        "uq_current_claim_capacity",
        "idx_facilities_company",
        "idx_contacts_company",
        "idx_demand_signals_facility",
        "idx_load_opps_facility",
        "idx_capacity_carrier",
    }
    missing = expected_indexes - indexes
    assert not missing, f"Missing required indexes: {missing}"


# ============================================================================
# 6, 7, 8. Exactly-One-Subject Claim CHECK Constraint
# ============================================================================
def test_claim_check_rejects_zero_subject_claims(memory_db):
    """Test 6: Verify inserting a claim with 0 subject foreign keys fails."""
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            """
            INSERT INTO claims (claim_field, claimed_value, verification_status, is_current_accepted)
            VALUES ('test_field', 'val', 'VERIFIED', 1)
            """
        )


def test_claim_check_rejects_multi_subject_claims(memory_db):
    """Test 7: Verify inserting a claim with >1 subject foreign keys fails."""
    # Insert prerequisite company and facility
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Brand A')")
    comp_id = cur.lastrowid
    cur = memory_db.execute(
        "INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country) "
        "VALUES (?, 'Fac A', 'SAWMILL', '123 St', 'Town', 'GA', 'US')",
        (comp_id,)
    )
    fac_id = cur.lastrowid

    # Attempt inserting with both company_id and facility_id
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            """
            INSERT INTO claims (company_id, facility_id, claim_field, claimed_value, verification_status, is_current_accepted)
            VALUES (?, ?, 'operating_brand', 'Brand A', 'VERIFIED', 1)
            """,
            (comp_id, fac_id)
        )


def test_valid_single_subject_claim_succeeds(memory_db):
    """Test 8: Verify inserting a claim with exactly one subject FK succeeds."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Brand B')")
    comp_id = cur.lastrowid

    claim_id = record_claim(
        conn=memory_db,
        claim_field="operating_brand",
        claimed_value="Brand B",
        verification_status="VERIFIED",
        is_current_accepted=True,
        company_id=comp_id,
    )
    assert claim_id > 0


# ============================================================================
# 9, 10. Single Current Accepted Claim Invariant & Historical Preservation
# ============================================================================
def test_duplicate_current_accepted_claim_is_rejected(memory_db):
    """Test 9: Verify partial unique index rejects two claims with is_current_accepted = 1 for same subject + field."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Brand C')")
    comp_id = cur.lastrowid

    memory_db.execute(
        """
        INSERT INTO claims (company_id, claim_field, claimed_value, verification_status, is_current_accepted)
        VALUES (?, 'website_url', 'https://c1.com', 'VERIFIED', 1)
        """,
        (comp_id,)
    )

    # Attempt direct insert of duplicate current accepted claim
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            """
            INSERT INTO claims (company_id, claim_field, claimed_value, verification_status, is_current_accepted)
            VALUES (?, 'website_url', 'https://c2.com', 'VERIFIED', 1)
            """,
            (comp_id,)
        )


def test_historical_non_current_claims_can_coexist(memory_db):
    """Test 10: Verify multiple claims with is_current_accepted = 0 can coexist for audit history."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Brand D')")
    comp_id = cur.lastrowid

    # Insert three historical claims (is_current_accepted = 0)
    for i in range(3):
        memory_db.execute(
            """
            INSERT INTO claims (company_id, claim_field, claimed_value, verification_status, is_current_accepted)
            VALUES (?, 'website_url', ?, 'INFERRED', 0)
            """,
            (comp_id, f"https://old{i}.com")
        )

    # And one accepted claim (is_current_accepted = 1)
    memory_db.execute(
        """
        INSERT INTO claims (company_id, claim_field, claimed_value, verification_status, is_current_accepted)
        VALUES (?, 'website_url', 'https://current.com', 'VERIFIED', 1)
        """,
        (comp_id,)
    )

    cur = memory_db.execute(
        "SELECT count(*) FROM claims WHERE company_id = ? AND claim_field = 'website_url'",
        (comp_id,)
    )
    assert cur.fetchone()[0] == 4


# ============================================================================
# 11, 12. Nullable-Enum Constraints & Rejection of Invalid Values
# ============================================================================
def test_nullable_enum_constraints_accept_null(memory_db):
    """Test 11: Verify CHECK(col IS NULL OR col IN (...)) correctly accepts NULL."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Brand E')")
    comp_id = cur.lastrowid
    cur = memory_db.execute(
        "INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country) "
        "VALUES (?, 'Fac E', 'SAWMILL', '123 St', 'Town', 'GA', 'US')",
        (comp_id,)
    )
    fac_id = cur.lastrowid

    # freight_demand_signals has nullable origin_country, dest_country, equipment_indication
    cur = memory_db.execute(
        """
        INSERT INTO freight_demand_signals (
            facility_id, signal_type, signal_status, observed_at,
            origin_country, dest_country, equipment_indication
        ) VALUES (?, 'RFP', 'HISTORICAL_SIGNAL', '2026-09-26T12:00:00Z', NULL, NULL, NULL)
        """,
        (fac_id,)
    )
    assert cur.lastrowid > 0


def test_invalid_enum_values_are_rejected(memory_db):
    """Test 12: Verify invalid enum strings are strictly rejected by CHECK constraints."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Brand F')")
    comp_id = cur.lastrowid

    with pytest.raises(sqlite3.IntegrityError):
        # Invalid country code 'XX'
        memory_db.execute(
            """
            INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country)
            VALUES (?, 'Fac F', 'SAWMILL', '123 St', 'Town', 'GA', 'XX')
            """,
            (comp_id,)
        )


# ============================================================================
# 13. Timestamp & Placeholder String Rejection
# ============================================================================
@pytest.mark.parametrize("placeholder", ["Active", "Current", "Recent", "N/A", "Unknown", "None", "TBD"])
def test_timestamp_validator_rejects_placeholders(placeholder):
    """Test 13: Verify timestamp validation rejects text placeholder strings."""
    with pytest.raises(ValueError, match="Invalid timestamp placeholder"):
        validate_iso_timestamp(placeholder)

    with pytest.raises(ValueError, match="Invalid date placeholder"):
        validate_date_string(placeholder)


def test_timestamp_validator_accepts_canonical_iso():
    """Verify valid ISO-8601 strings pass validation."""
    valid_ts = "2026-09-26T14:30:00Z"
    assert validate_iso_timestamp(valid_ts) == valid_ts


# ============================================================================
# 14, 15, 16. Entity Separation Invariants
# ============================================================================
def test_facility_can_exist_without_freight_demand_signal(memory_db):
    """Test 14: A facility exists independently without active freight demand."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Brand G')")
    comp_id = cur.lastrowid
    cur = memory_db.execute(
        """
        INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country)
        VALUES (?, 'Fac G', 'STEEL_SERVICE_CENTER', '456 Steel Rd', 'Detroit', 'MI', 'US')
        """,
        (comp_id,)
    )
    fac_id = cur.lastrowid

    # Verify no demand signals exist
    cur = memory_db.execute("SELECT count(*) FROM freight_demand_signals WHERE facility_id = ?", (fac_id,))
    assert cur.fetchone()[0] == 0


def test_company_can_exist_without_load_opportunity(memory_db):
    """Test 15: A prospect company does not require discrete load opportunity rows."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Brand H')")
    comp_id = cur.lastrowid

    cur = memory_db.execute(
        """
        SELECT count(*) FROM load_opportunities lo
        JOIN facilities f ON lo.facility_id = f.id
        WHERE f.company_id = ?
        """,
        (comp_id,)
    )
    assert cur.fetchone()[0] == 0


def test_carrier_can_exist_without_capacity_posting(memory_db):
    """Test 16: Carrier directory record does not require active capacity posting."""
    cur = memory_db.execute(
        """
        INSERT INTO carriers (legal_name, country, operating_status)
        VALUES ('Ace Trucking LLC', 'US', 'UNKNOWN')
        """
    )
    carrier_id = cur.lastrowid

    cur = memory_db.execute("SELECT count(*) FROM capacity_postings WHERE carrier_id = ?", (carrier_id,))
    assert cur.fetchone()[0] == 0


# ============================================================================
# 17, 18. Demand Signals != Loads, Lane Activity != Capacity
# ============================================================================
def test_demand_signal_does_not_automatically_create_load(memory_db):
    """Test 17: Freight demand signal row does not create load_opportunity."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Brand I')")
    comp_id = cur.lastrowid
    cur = memory_db.execute(
        "INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country) "
        "VALUES (?, 'Fac I', 'SAWMILL', '789 Wood Ln', 'Atlanta', 'GA', 'US')",
        (comp_id,)
    )
    fac_id = cur.lastrowid

    cur = memory_db.execute(
        """
        INSERT INTO freight_demand_signals (
            facility_id, signal_type, signal_status, observed_at, event_at
        ) VALUES (?, 'RFP', 'SIGNAL_LAST_30_DAYS', '2026-09-26T12:00:00Z', '2026-09-20T10:00:00Z')
        """,
        (fac_id,)
    )
    signal_id = cur.lastrowid
    assert signal_id > 0

    cur = memory_db.execute("SELECT count(*) FROM load_opportunities WHERE facility_id = ?", (fac_id,))
    assert cur.fetchone()[0] == 0


def test_carrier_lane_activity_does_not_create_capacity(memory_db):
    """Test 18: Historical carrier lane activity does not create capacity_posting."""
    cur = memory_db.execute(
        "INSERT INTO carriers (legal_name, country) VALUES ('Beta Transport Inc.', 'CA')"
    )
    carrier_id = cur.lastrowid

    cur = memory_db.execute(
        """
        INSERT INTO carrier_lane_activity (
            carrier_id, origin_country, origin_region, dest_country, dest_region, activity_type, observed_at
        ) VALUES (?, 'CA', 'ON', 'US', 'MI', 'HISTORICAL_MOVE', '2026-09-26T12:00:00Z')
        """,
        (carrier_id,)
    )
    act_id = cur.lastrowid
    assert act_id > 0

    cur = memory_db.execute("SELECT count(*) FROM capacity_postings WHERE carrier_id = ?", (carrier_id,))
    assert cur.fetchone()[0] == 0


# ============================================================================
# 19, 20. UNKNOWN States & Private Fleet Visibility
# ============================================================================
def test_unknown_states_remain_valid(memory_db):
    """Test 19: UNKNOWN verification status and operating statuses are valid defaults."""
    cur = memory_db.execute(
        "INSERT INTO carriers (legal_name, country) VALUES ('Gamma Freight Ltd.', 'US')"
    )
    carrier_id = cur.lastrowid

    cur = memory_db.execute("SELECT operating_status, safety_rating FROM carriers WHERE id = ?", (carrier_id,))
    row = cur.fetchone()
    assert row["operating_status"] == "UNKNOWN"
    assert row["safety_rating"] == "UNKNOWN"


def test_private_fleet_company_remains_active_and_visible(memory_db):
    """Test 20: Having a private fleet is an operational attribute and does NOT suppress/hide the company."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Fleet Shipper Corp')")
    comp_id = cur.lastrowid
    cur = memory_db.execute(
        """
        INSERT INTO facilities (
            company_id, facility_name, facility_type, physical_address, city, state_prov, country,
            private_fleet_present
        ) VALUES (?, 'Main Plant', 'SAWMILL', '100 Mill Rd', 'Macon', 'GA', 'US', 'VERIFIED_PRESENT')
        """,
        (comp_id,)
    )
    fac_id = cur.lastrowid

    # Verify query for active prospects returns the facility regardless of private fleet
    cur = memory_db.execute(
        """
        SELECT f.id, f.private_fleet_present FROM facilities f
        LEFT JOIN suppressions s ON f.id = s.facility_id
        WHERE s.id IS NULL AND f.id = ?
        """,
        (fac_id,)
    )
    result = cur.fetchone()
    assert result is not None
    assert result["private_fleet_present"] == "VERIFIED_PRESENT"


# ============================================================================
# 21, 22. DIRECT_ONLY vs DO_NOT_CONTACT & Margin Calculation
# ============================================================================
def test_direct_only_does_not_equal_do_not_contact(memory_db):
    """Test 21: Direct-only broker policy is distinct from DO_NOT_CONTACT suppression."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Asset Only Corp')")
    comp_id = cur.lastrowid
    cur = memory_db.execute(
        """
        INSERT INTO facilities (
            company_id, facility_name, facility_type, physical_address, city, state_prov, country,
            broker_friendly_status
        ) VALUES (?, 'Facility 1', 'STEEL_SERVICE_CENTER', '200 Coil St', 'Gary', 'IN', 'US', 'VERIFIED_DIRECT_ONLY')
        """,
        (comp_id,)
    )
    fac_id = cur.lastrowid

    # Facility has broker_friendly_status = 'VERIFIED_DIRECT_ONLY'
    cur = memory_db.execute("SELECT broker_friendly_status FROM facilities WHERE id = ?", (fac_id,))
    assert cur.fetchone()["broker_friendly_status"] == "VERIFIED_DIRECT_ONLY"

    # Verify no suppression record exists
    cur = memory_db.execute("SELECT count(*) FROM suppressions WHERE facility_id = ?", (fac_id,))
    assert cur.fetchone()[0] == 0


def test_margin_can_remain_unknown_when_rates_are_missing():
    """Test 22: If either rate is missing, gross margin is UNKNOWN (None, None)."""
    assert calculate_gross_margin(None, 2000.0) == (None, None)
    assert calculate_gross_margin(2500.0, None) == (None, None)
    assert calculate_gross_margin(None, None) == (None, None)

    # When both are present
    spread, pct = calculate_gross_margin(2500.0, 2000.0)
    assert spread == 500.0
    assert pct == 20.0


# ============================================================================
# Stage 2.1 Specific Tests: Physical `suppressions` Table & Scope Verification
# ============================================================================
def test_suppressions_physical_table_and_no_legacy_records_table(memory_db):
    """Stage 2.1: Verify suppressions is a physical TABLE and suppression_status_records does not exist."""
    cur = memory_db.execute(
        "SELECT name, type FROM sqlite_master WHERE name IN ('suppressions', 'suppression_status_records')"
    )
    objs = {r["name"]: r["type"] for r in cur.fetchall()}
    assert "suppressions" in objs, "'suppressions' must exist in sqlite_master"
    assert objs["suppressions"] == "table", f"'suppressions' must be a physical table, got {objs['suppressions']}"
    assert "suppression_status_records" not in objs, "'suppression_status_records' must NOT exist"


def test_fresh_initialization_creates_suppressions_directly(tmp_path):
    """Stage 2.1: Fresh database initialization directly creates suppressions as a table."""
    fresh_db = tmp_path / "fresh_init.db"
    init_db(fresh_db)

    conn = create_connection(fresh_db)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT name, type FROM sqlite_master WHERE name IN ('suppressions', 'suppression_status_records')")
    objs = {r["name"]: r["type"] for r in cur.fetchall()}
    assert objs.get("suppressions") == "table"
    assert "suppression_status_records" not in objs

    # Idempotent re-initialization
    init_db(fresh_db)
    cur = conn.execute("SELECT name, type FROM sqlite_master WHERE name IN ('suppressions', 'suppression_status_records')")
    objs_reinit = {r["name"]: r["type"] for r in cur.fetchall()}
    assert objs_reinit.get("suppressions") == "table"
    assert "suppression_status_records" not in objs_reinit
    conn.close()


def test_existing_production_migration_preserves_suppression_data(tmp_path):
    """Stage 2.1: Migration correctly moves existing rows from suppression_status_records to suppressions."""
    mig_db = tmp_path / "legacy_migration.db"
    conn = create_connection(mig_db, create_if_missing=True)

    # Manually create legacy schema with suppression_status_records and view suppressions
    conn.executescript("""
        CREATE TABLE companies (id INTEGER PRIMARY KEY, operating_brand TEXT);
        CREATE TABLE facilities (id INTEGER PRIMARY KEY, company_id INTEGER, facility_name TEXT);
        CREATE TABLE suppression_status_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope_type TEXT NOT NULL,
            company_id INTEGER,
            facility_id INTEGER,
            origin_country TEXT,
            origin_state_prov TEXT,
            origin_city TEXT,
            dest_country TEXT,
            dest_state_prov TEXT,
            dest_city TEXT,
            suppression_status TEXT NOT NULL,
            reason_notes TEXT NOT NULL,
            assigned_by TEXT NOT NULL DEFAULT 'USER',
            effective_date DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE VIEW suppressions AS SELECT * FROM suppression_status_records;
    """)

    conn.execute("INSERT INTO companies VALUES (1, 'Test Corp')")
    conn.execute("INSERT INTO facilities VALUES (1, 1, 'Plant A')")

    # Insert 3 legacy rows across different scopes
    conn.execute(
        """
        INSERT INTO suppression_status_records (
            id, scope_type, company_id, facility_id, origin_country, origin_state_prov,
            dest_country, dest_state_prov, suppression_status, reason_notes
        ) VALUES
        (10, 'COMPANY', 1, NULL, NULL, NULL, NULL, NULL, 'DO_NOT_CONTACT', 'Credit issue'),
        (11, 'FACILITY', NULL, 1, NULL, NULL, NULL, NULL, 'EXISTING_CUSTOMER', 'Dedicated contract'),
        (12, 'GLOBAL_LANE', NULL, NULL, 'US', 'FL', 'US', 'GA', 'ALREADY_ROUTED', 'Internal lane')
        """
    )
    conn.commit()
    conn.close()

    # Run init_db which triggers _migrate_legacy_suppressions_if_needed
    init_db(mig_db)

    # Verify migration results
    conn = create_connection(mig_db)
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT name, type FROM sqlite_master WHERE name IN ('suppressions', 'suppression_status_records')")
    objs = {r["name"]: r["type"] for r in cur.fetchall()}
    assert objs.get("suppressions") == "table"
    assert "suppression_status_records" not in objs

    # Verify all 3 rows migrated with exact fields preserved
    cur = conn.execute("SELECT * FROM suppressions ORDER BY id")
    rows = cur.fetchall()
    assert len(rows) == 3

    assert rows[0]["id"] == 10
    assert rows[0]["scope_type"] == "COMPANY"
    assert rows[0]["company_id"] == 1
    assert rows[0]["suppression_status"] == "DO_NOT_CONTACT"
    assert rows[0]["reason_notes"] == "Credit issue"

    assert rows[1]["id"] == 11
    assert rows[1]["scope_type"] == "FACILITY"
    assert rows[1]["facility_id"] == 1
    assert rows[1]["suppression_status"] == "EXISTING_CUSTOMER"

    assert rows[2]["id"] == 12
    assert rows[2]["scope_type"] == "GLOBAL_LANE"
    assert rows[2]["origin_state_prov"] == "FL"
    assert rows[2]["dest_state_prov"] == "GA"
    assert rows[2]["suppression_status"] == "ALREADY_ROUTED"

    conn.close()


def test_all_five_suppression_scopes_are_valid(memory_db):
    """Stage 2.1: Verify all 5 suppression scopes can be inserted into the physical suppressions table."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Shipper X')")
    comp_id = cur.lastrowid
    cur = memory_db.execute(
        """
        INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country)
        VALUES (?, 'Plant X', 'SAWMILL', '123 Pine St', 'Savannah', 'GA', 'US')
        """,
        (comp_id,)
    )
    fac_id = cur.lastrowid

    # 1. COMPANY scope
    memory_db.execute(
        """
        INSERT INTO suppressions (scope_type, company_id, suppression_status, reason_notes)
        VALUES ('COMPANY', ?, 'DO_NOT_CONTACT', 'Legal hold')
        """,
        (comp_id,)
    )

    # 2. FACILITY scope
    memory_db.execute(
        """
        INSERT INTO suppressions (scope_type, facility_id, suppression_status, reason_notes)
        VALUES ('FACILITY', ?, 'EXISTING_CUSTOMER', 'Direct house account')
        """,
        (fac_id,)
    )

    # 3. COMPANY_LANE scope
    memory_db.execute(
        """
        INSERT INTO suppressions (
            scope_type, company_id, origin_country, origin_state_prov, dest_country, dest_state_prov,
            suppression_status, reason_notes
        ) VALUES ('COMPANY_LANE', ?, 'US', 'GA', 'US', 'NC', 'ALREADY_ROUTED', 'Contracted to private fleet')
        """,
        (comp_id,)
    )

    # 4. FACILITY_LANE scope
    memory_db.execute(
        """
        INSERT INTO suppressions (
            scope_type, facility_id, origin_country, origin_state_prov, dest_country, dest_state_prov,
            suppression_status, reason_notes
        ) VALUES ('FACILITY_LANE', ?, 'US', 'GA', 'US', 'FL', 'ALREADY_ROUTED', 'Local drayage only')
        """,
        (fac_id,)
    )

    # 5. GLOBAL_LANE scope
    memory_db.execute(
        """
        INSERT INTO suppressions (
            scope_type, origin_country, origin_state_prov, dest_country, dest_state_prov,
            suppression_status, reason_notes
        ) VALUES ('GLOBAL_LANE', 'US', 'TX', 'US', 'CA', 'NORMAL_PROSPECT', 'High deadhead risk corridor')
        """
    )

    cur = memory_db.execute("SELECT count(*) FROM suppressions")
    assert cur.fetchone()[0] == 5


def test_invalid_suppression_scopes_and_violations_rejected(memory_db):
    """Stage 2.1: Verify CHECK constraints reject invalid scope configurations and enum values."""
    cur = memory_db.execute("INSERT INTO companies (operating_brand) VALUES ('Shipper Y')")
    comp_id = cur.lastrowid
    cur = memory_db.execute(
        """
        INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country)
        VALUES (?, 'Plant Y', 'SAWMILL', '456 Oak St', 'Atlanta', 'GA', 'US')
        """,
        (comp_id,)
    )
    fac_id = cur.lastrowid

    # COMPANY scope without company_id
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            "INSERT INTO suppressions (scope_type, suppression_status, reason_notes) VALUES ('COMPANY', 'DO_NOT_CONTACT', 'Missing company')"
        )

    # COMPANY scope with facility_id
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            "INSERT INTO suppressions (scope_type, company_id, facility_id, suppression_status, reason_notes) "
            "VALUES ('COMPANY', ?, ?, 'DO_NOT_CONTACT', 'Both set')",
            (comp_id, fac_id)
        )

    # GLOBAL_LANE scope with company_id set
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            "INSERT INTO suppressions (scope_type, company_id, origin_state_prov, dest_state_prov, suppression_status, reason_notes) "
            "VALUES ('GLOBAL_LANE', ?, 'GA', 'FL', 'DO_NOT_CONTACT', 'Global lane cannot have company')",
            (comp_id,)
        )

    # Invalid scope_type enum
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            "INSERT INTO suppressions (scope_type, company_id, suppression_status, reason_notes) "
            "VALUES ('INVALID_SCOPE', ?, 'DO_NOT_CONTACT', 'Invalid scope')",
            (comp_id,)
        )

    # Invalid suppression_status enum
    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute(
            "INSERT INTO suppressions (scope_type, company_id, suppression_status, reason_notes) "
            "VALUES ('COMPANY', ?, 'BLACKLISTED', 'Invalid status')",
            (comp_id,)
        )
