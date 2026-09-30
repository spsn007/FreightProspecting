"""
FreightProspecting V1 — Stage 2 Seed & Provenance Automated Tests
Covers points 23-30 of Stage 2 verification requirements.
"""

from pathlib import Path
import sqlite3
import pytest

from src.backend.db.connection import create_connection
from src.backend.db.schema import init_db
from src.backend.db.seed import seed_database


@pytest.fixture
def seeded_db(tmp_path):
    """Provides a fresh, isolated SQLite database with audited seed data ingested."""
    db_file = tmp_path / "test_seeded_prospects.db"
    conn = create_connection(db_file, create_if_missing=True)
    init_db(db_file)
    seed_database(db_file)
    yield conn, db_file
    conn.close()


# ============================================================================
# 23. Seed Operation Idempotency
# ============================================================================
def test_seed_operation_is_idempotent(seeded_db):
    """Test 23: Verify running seed_database twice does not duplicate companies or records."""
    conn, db_file = seeded_db

    initial_companies = conn.execute("SELECT count(*) FROM companies;").fetchone()[0]
    initial_facilities = conn.execute("SELECT count(*) FROM facilities;").fetchone()[0]
    initial_claims = conn.execute("SELECT count(*) FROM claims;").fetchone()[0]

    # Run seed again
    seed_database(db_file)

    reseeded_companies = conn.execute("SELECT count(*) FROM companies;").fetchone()[0]
    reseeded_facilities = conn.execute("SELECT count(*) FROM facilities;").fetchone()[0]
    reseeded_claims = conn.execute("SELECT count(*) FROM claims;").fetchone()[0]

    assert initial_companies == reseeded_companies, "Company count must not duplicate"
    assert initial_facilities == reseeded_facilities, "Facility count must not duplicate"
    assert initial_claims == reseeded_claims, "Claims count must not duplicate"


# ============================================================================
# 24. Exactly Four Approved Seed Families Inserted
# ============================================================================
def test_exactly_four_approved_seed_families(seeded_db):
    """Test 24: Verify exactly the four approved audited seed entities are present."""
    conn, _ = seeded_db

    cur = conn.execute("SELECT operating_brand FROM companies ORDER BY id ASC;")
    brands = [row["operating_brand"] for row in cur.fetchall()]

    # Expected: Beasley Forest Products, Kenwal Steel Corp., DECAST Ltd., WMG Technologies, plus parent ABC Technologies
    assert "Beasley Forest Products" in brands
    assert "Kenwal Steel Corp." in brands
    assert "DECAST Ltd." in brands
    assert "WMG Technologies" in brands

    # Ensure no unauthorized companies exist
    allowed = {"Beasley Forest Products", "Kenwal Steel Corp.", "DECAST Ltd.", "WMG Technologies", "ABC Technologies"}
    for b in brands:
        assert b in allowed, f"Unexpected company '{b}' found in seed database"


# ============================================================================
# 25, 26. Zero Fake Loads & Zero Fake Capacity
# ============================================================================
def test_no_fake_load_rows_are_introduced(seeded_db):
    """Test 25: Discrete loads must NOT be faked or placeholder-seeded for prospects."""
    conn, _ = seeded_db
    cur = conn.execute("SELECT count(*) FROM load_opportunities;")
    count = cur.fetchone()[0]
    assert count == 0, f"Expected 0 fake load opportunities, found {count}"


def test_no_fake_capacity_postings_are_introduced(seeded_db):
    """Test 26: Available capacity must NOT be faked or placeholder-seeded."""
    conn, _ = seeded_db
    cur = conn.execute("SELECT count(*) FROM capacity_postings;")
    count = cur.fetchone()[0]
    assert count == 0, f"Expected 0 fake capacity postings, found {count}"


def test_no_fake_freight_demand_signals(seeded_db):
    """Verify zero fake freight demand signals are introduced for seed facilities."""
    conn, _ = seeded_db
    cur = conn.execute("SELECT count(*) FROM freight_demand_signals;")
    count = cur.fetchone()[0]
    assert count == 0, f"Expected 0 freight demand signals for seeds without active RFPs/tenders, found {count}"


# ============================================================================
# 27. Beasley Named-Person vs Switchboard Distinction
# ============================================================================
def test_beasley_named_person_and_switchboard_distinction(seeded_db):
    """Test 27: Verify Phil Clements is switchboard, Mark Joiner is direct person."""
    conn, _ = seeded_db

    # Check Phil Clements
    cur = conn.execute(
        "SELECT phone_number, phone_directness, broker_procurement_relevance "
        "FROM contacts WHERE person_name = 'Phil Clements';"
    )
    phil = cur.fetchone()
    assert phil is not None
    assert phil["phone_number"] == "(912) 375-5174"
    assert phil["phone_directness"] == "GENERAL_SWITCHBOARD"
    assert phil["broker_procurement_relevance"] == "UNKNOWN"

    # Check Mark Joiner
    cur = conn.execute(
        "SELECT phone_number, phone_directness, outbound_shipping_procurement_relevance, broker_procurement_relevance "
        "FROM contacts WHERE person_name = 'Mark Joiner';"
    )
    mark = cur.fetchone()
    assert mark is not None
    assert mark["phone_number"] == "(912) 347-5930"
    assert mark["phone_directness"] == "DIRECT_PERSON"
    assert mark["outbound_shipping_procurement_relevance"] == "VERIFIED"
    assert mark["broker_procurement_relevance"] == "UNKNOWN"


# ============================================================================
# 28. Kenwal Fleet Status Remains UNKNOWN
# ============================================================================
def test_kenwal_fleet_status_remains_unknown(seeded_db):
    """Test 28: Absence of FMCSA record does NOT prove no fleet; must remain UNKNOWN."""
    conn, _ = seeded_db

    cur = conn.execute(
        """
        SELECT f.private_fleet_present, f.broker_friendly_status
        FROM facilities f
        JOIN companies c ON f.company_id = c.id
        WHERE c.operating_brand = 'Kenwal Steel Corp.';
        """
    )
    row = cur.fetchone()
    assert row is not None
    assert row["private_fleet_present"] == "UNKNOWN", "Absence of FMCSA data must remain UNKNOWN"
    assert row["broker_friendly_status"] == "UNKNOWN", "Broker policy must remain UNKNOWN"


# ============================================================================
# 29. DECAST Job Evidence Does Not Become Demand Signal
# ============================================================================
def test_decast_job_evidence_does_not_become_demand_signal(seeded_db):
    """Test 29: AZ Float Driver job ad is operational Category A evidence, not a demand signal."""
    conn, _ = seeded_db

    # Confirm zero demand signals for DECAST
    cur = conn.execute(
        """
        SELECT count(*) FROM freight_demand_signals fds
        JOIN facilities f ON fds.facility_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE c.operating_brand = 'DECAST Ltd.';
        """
    )
    assert cur.fetchone()[0] == 0, "Job ad must NOT create a freight_demand_signal"

    # Confirm operational evidence is stored as evidence_source and claim
    cur = conn.execute(
        """
        SELECT es.source_type, es.notes, c.claimed_value
        FROM evidence_sources es
        JOIN claim_evidence ce ON es.id = ce.evidence_source_id
        JOIN claims c ON ce.claim_id = c.id
        WHERE es.source_type = 'JOB_POSTING';
        """
    )
    row = cur.fetchone()
    assert row is not None
    assert "Category A operational evidence" in row["notes"]


# ============================================================================
# 30. WMG Hierarchy Fields Remain UNKNOWN Rather Than Fabricated
# ============================================================================
def test_wmg_unresolved_hierarchy_fields_remain_unknown(seeded_db):
    """Test 30: Verified acquisition is recorded, but unverified intermediate holding tiers remain UNKNOWN."""
    conn, _ = seeded_db

    # Check company legal name vs brand name
    cur = conn.execute(
        "SELECT operating_brand, legal_name FROM companies WHERE operating_brand = 'WMG Technologies';"
    )
    wmg = cur.fetchone()
    assert wmg is not None
    assert wmg["operating_brand"] == "WMG Technologies"
    assert wmg["legal_name"] == "Windsor Mold Inc."  # Verified contracting entity

    # Check company relationship
    cur = conn.execute(
        """
        SELECT cr.relationship_type, cr.verification_status, cr.notes
        FROM company_relationships cr
        JOIN companies parent ON cr.parent_company_id = parent.id
        JOIN companies child ON cr.child_company_id = child.id
        WHERE child.operating_brand = 'WMG Technologies';
        """
    )
    rel = cur.fetchone()
    assert rel is not None
    assert rel["relationship_type"] == "ACQUISITION"
    assert rel["verification_status"] == "VERIFIED"
    assert "UNKNOWN" in rel["notes"], "Unresolved present-day intermediate tier must be noted as UNKNOWN"

    # Verify WMG facility equipment status is INFERRED, not VERIFIED
    cur = conn.execute(
        """
        SELECT fc.equipment_category, fc.equipment_usage_status
        FROM facility_commodities fc
        JOIN facilities f ON fc.facility_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE c.operating_brand = 'WMG Technologies';
        """
    )
    comm = cur.fetchone()
    assert comm is not None
    assert comm["equipment_usage_status"] == "INFERRED", "Suitability inference must not be VERIFIED usage"


# ============================================================================
# 31. DECAST Fleet Is UNKNOWN and Equipment Is INFERRED
# ============================================================================
def test_decast_fleet_unknown_and_equipment_inferred(seeded_db):
    """Test 31: Driver recruitment proves internal float operational activity, not fleet asset ownership."""
    conn, _ = seeded_db

    # 1. Facility Fleet Status must be UNKNOWN
    cur = conn.execute(
        """
        SELECT f.private_fleet_present, f.broker_friendly_status
        FROM facilities f
        JOIN companies c ON f.company_id = c.id
        WHERE c.operating_brand = 'DECAST Ltd.';
        """
    )
    fac = cur.fetchone()
    assert fac is not None
    assert fac["private_fleet_present"] == "UNKNOWN", "Driver job posting does not prove fleet asset ownership; must be UNKNOWN"
    assert fac["broker_friendly_status"] == "UNKNOWN"

    # 2. Commodity Equipment Usage must be INFERRED
    cur = conn.execute(
        """
        SELECT fc.equipment_category, fc.equipment_usage_status
        FROM facility_commodities fc
        JOIN facilities f ON fc.facility_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE c.operating_brand = 'DECAST Ltd.';
        """
    )
    comm = cur.fetchone()
    assert comm is not None
    assert comm["equipment_category"] == "STEP_DECK"
    assert comm["equipment_usage_status"] == "INFERRED", "Step deck suitability inference must be INFERRED, not VERIFIED"

    # 3. Claims verification statuses
    cur = conn.execute(
        """
        SELECT cl.claim_field, cl.claimed_value, cl.verification_status
        FROM claims cl
        JOIN facilities f ON cl.facility_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE c.operating_brand = 'DECAST Ltd.' AND cl.claim_field = 'private_fleet_present';
        """
    )
    fleet_claim = cur.fetchone()
    assert fleet_claim is not None
    assert fleet_claim["claimed_value"] == "UNKNOWN"
    assert fleet_claim["verification_status"] == "UNKNOWN"

    # 4. Job posting source is secondary (not primary)
    cur = conn.execute(
        """
        SELECT is_primary_source, source_type
        FROM evidence_sources
        WHERE source_title_publisher LIKE '%AZ Float Driver%';
        """
    )
    job_src = cur.fetchone()
    assert job_src is not None
    assert job_src["is_primary_source"] == 0, "Job recruitment posting must be classified as secondary source"

