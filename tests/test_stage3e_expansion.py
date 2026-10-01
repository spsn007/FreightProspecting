import re
import sqlite3
import pytest
from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.queries import get_summary_counts, get_company_grouped_prospects

DB_PATH = get_db_path()

@pytest.fixture(autouse=True, scope="module")
def pin_historical_db(use_historical_stage3_db):
    global DB_PATH
    DB_PATH = use_historical_stage3_db
    yield
    DB_PATH = get_db_path()

# ============================================================================
# 1. Target Invariants Post-Audit & Deduplication
# ============================================================================
def test_stage3e_company_expansion_targets():
    """Verify that Stage 3E meets the >= 500 unique operating companies goal, partitioned by Stage 3F lifecycle."""
    counts = get_summary_counts(DB_PATH)
    assert counts["all_companies_count"] >= 500, f"Expected >= 500 operating companies, got {counts['all_companies_count']}"
    assert counts["all_companies_count"] == 565
    assert counts["total_companies_count"] == 567  # 565 operating + 2 holding/inactive
    assert counts["shortlisted_companies_count"] == 29
    assert counts["qualified_companies_count"] == 91
    assert counts["discovery_companies_count"] == 445
    assert counts["shortlisted_count"] == 29
    assert counts["qualified_count"] == 124
    assert counts["discovery_count"] == 500
    assert counts["all_prospects_count"] == 653


def test_stage3e_zero_fake_operational_data():
    """Verify zero fake operational data or outreach pollution across the entire database."""
    counts = get_summary_counts(DB_PATH)
    assert counts["loads_count"] == 0
    assert counts["capacity_count"] == 0
    assert counts["signals_count"] == 0
    assert counts["carriers_count"] == 0
    assert counts["matches_count"] == 0
    assert counts["crm_total_calls"] == 0
    assert counts["crm_uncontacted"] == 567


def test_stage3e_equipment_truth_invariants():
    """Verify that only the 3 audited facilities have VERIFIED equipment usage."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        verified_rows = conn.execute(
            "SELECT facility_id, equipment_category, equipment_usage_status FROM facility_commodities WHERE equipment_usage_status = 'VERIFIED'"
        ).fetchall()
        verified_ids = {r["facility_id"] for r in verified_rows}
        assert verified_ids == {1, 2, 18}, f"Expected verified facility IDs {{1, 2, 18}}, got {verified_ids}"

        # All newly added facilities must have INFERRED equipment usage
        inferred_rows = conn.execute(
            "SELECT COUNT(*) FROM facility_commodities WHERE equipment_usage_status = 'INFERRED'"
        ).fetchone()
        assert inferred_rows[0] >= 610
    finally:
        conn.close()


def test_stage3e_facility_distribution():
    """Verify single-facility vs multi-facility distribution."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT c.id, COUNT(f.id) as fac_count
        FROM companies c
        JOIN facilities f ON f.company_id = c.id
        GROUP BY c.id
    """)
    fac_counts = c.fetchall()
    single_fac = [r for r in fac_counts if r[1] == 1]
    multi_fac = [r for r in fac_counts if r[1] > 1]

    assert len(single_fac) == 499
    assert len(multi_fac) == 66
    assert len(single_fac) + len(multi_fac) == 565

    conn.close()


# ============================================================================
# 2. Deduplication & Corporate Identity Audits
# ============================================================================
def test_no_duplicate_normalized_company_identities():
    """Verify zero duplicate normalized operating brands among operating companies."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT c.id, c.operating_brand, c.website_url
            FROM companies c
            JOIN facilities f ON f.company_id = c.id
            GROUP BY c.id
        """).fetchall()

        SUFFIXES = [
            r"\binc\b\.?", r"\bllc\b\.?", r"\bcorp\b\.?", r"\bcorporation\b",
            r"\bltd\b\.?", r"\blimited\b", r"\bco\b\.?", r"\bcompany\b", r"\bgroup\b"
        ]
        norm_map = {}
        for r in rows:
            brand = r["operating_brand"].lower()
            brand = re.sub(r"[^\w\s]", " ", brand)
            for s in SUFFIXES:
                brand = re.sub(s, " ", brand)
            clean = re.sub(r"\s+", " ", brand).strip()
            if clean:
                norm_map.setdefault(clean, []).append(r["id"])

        collisions = {k: v for k, v in norm_map.items() if len(v) > 1}
        assert len(collisions) == 0, f"Found normalized brand collisions: {collisions}"
    finally:
        conn.close()


def test_same_company_multiple_plants_counts_once():
    """Verify multi-plant companies (e.g., GP, West Fraser, Canfor, Interfor) count as exactly 1 company."""
    groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)
    brands = [g["operating_brand"] for g in groups]
    assert len(brands) == len(set(brands)), "Every company group operating_brand must appear exactly once"
    
    # Georgia Pacific appears once with 4 facilities
    gp = next(g for g in groups if g["operating_brand"] == "Georgia-Pacific")
    assert gp["facility_count"] == 4


def test_stage3e_delta_reconciliation():
    """
    Verify the exact delta: 244 facility candidates produced 243 new companies
    because Facility 389 (Owensboro Stave & Hardwood Mill) was recognized as
    belonging to pre-existing Company 186 (Robinson Lumber Co.).
    """
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rob_facs = conn.execute("SELECT id, facility_name, city, state_prov FROM facilities WHERE company_id = 186 ORDER BY id").fetchall()
        assert len(rob_facs) == 2
        fac_ids = [f["id"] for f in rob_facs]
        assert 220 in fac_ids  # Pre-Stage-3E facility (New Albany, IN)
        assert 389 in fac_ids  # Stage 3E facility (Owensboro, KY)
    finally:
        conn.close()


# ============================================================================
# 3. Contact Truth & Evidence Invariants
# ============================================================================
def test_stage3e_contact_truth_classification():
    """
    Verify contacts truth classification for Stage 3E imports (contact IDs >= 383):
    - Wayne Yoder (Yoder Lumber): published Shipping Manager, DIRECT_PERSON phone.
    - Somerset Flooring: published shipping@ email -> FREIGHT_LOGISTICS Shipping Department.
    - sales@ emails: strictly COMMERCIAL_SALES.
    - info@/general emails: strictly GENERAL_FACILITY.
    - No generic coordinator/manager filler strings stored as person_name.
    """
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # 1. Wayne Yoder (330-893-3031 was verified as fax; personal direct phone is UNKNOWN, fax recorded in fax_number)
        yoder = conn.execute("SELECT * FROM contacts WHERE id = 418").fetchone()
        assert yoder["person_name"] == "Wayne Yoder"
        assert yoder["exact_published_title"] == "Shipping Manager"
        assert yoder["department"] == "Shipping"
        assert yoder["phone_number"] is None
        assert yoder["phone_directness"] == "UNKNOWN"
        assert yoder["fax_number"] == "(330) 893-3031"
        assert yoder["role_category"] == "FREIGHT_LOGISTICS"

        # 2. Somerset Flooring
        somerset = conn.execute("SELECT * FROM contacts WHERE id = 400").fetchone()
        assert somerset["email_address"] == "shipping@somersetflooring.com"
        assert somerset["role_category"] == "FREIGHT_LOGISTICS"
        assert somerset["person_name"] is None

        # 3. Cole Hardwood (sales@ unverified per Codex batch 1 final closure; main phone retained)
        cole = conn.execute("SELECT * FROM contacts WHERE id = 396").fetchone()
        assert cole["email_address"] is None
        assert cole["exact_published_title"] == "General main line"
        assert cole["person_name"] is None

        # 4. Check all other Stage 3E contacts: zero invented person names
        contacts = conn.execute("SELECT * FROM contacts WHERE id >= 383 AND id <= 626 AND id NOT IN (418)").fetchall()
        for ct in contacts:
            assert ct["person_name"] is None, f"Contact {ct['id']} has unsupported person_name '{ct['person_name']}'"
            if ct["email_address"] and any(ct["email_address"].lower().startswith(p) for p in ["sales@", "ventes@", "sales.", "salespa@", "salesfs@", "torontosales@"]):
                assert ct["role_category"] == "COMMERCIAL_SALES", f"Contact {ct['id']} ({ct['email_address']}) should be COMMERCIAL_SALES"
            elif ct["id"] != 400:
                assert ct["role_category"] == "GENERAL_FACILITY", f"Contact {ct['id']} ({ct['email_address']}) should be GENERAL_FACILITY"
    finally:
        conn.close()


def test_facility_18_identity_truth():
    """Verify Facility 18 is Coil Steel Processing (CSP) Toledo, never Custom Steel Processing."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        fac = conn.execute("SELECT f.*, c.operating_brand FROM facilities f JOIN companies c ON f.company_id = c.id WHERE f.id = 18").fetchone()
        assert fac["operating_brand"] == "Coil Steel Processing (CSP)"
        assert fac["facility_name"] == "Toledo Stretcher Leveling & Processing Plant"
        assert fac["city"] == "Toledo"
        assert fac["state_prov"] == "OH"
        assert fac["postal_code"] == "43612"
    finally:
        conn.close()


def test_evidence_sources_schema_integrity():
    """Verify evidence_sources table references outreach_logs(id) and has zero stale temporary tables."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        stale = conn.execute("SELECT name FROM sqlite_master WHERE name LIKE '%_old%' OR name LIKE '%_new%'").fetchall()
        assert len(stale) == 0, f"Found stale tables: {stale}"

        fk_errs = list(conn.execute("PRAGMA foreign_key_check;"))
        assert len(fk_errs) == 0, f"FK errors: {fk_errs}"

        integ = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        assert integ == "ok"
    finally:
        conn.close()
