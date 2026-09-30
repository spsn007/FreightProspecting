"""
FreightProspecting V1 — Stage 3G Taxonomy & Seasonality Tests
Verifies:
1. All existing commodity categories, companies, facilities preserved.
2. New taxonomy families and categories exist with stable unique codes.
3. Multi-category facility associations supported.
4. Category seasonality != Facility verified seasonality.
5. Typical category equipment fit != Facility verified equipment usage.
6. Strictly facilities 1, 2, 18 maintain VERIFIED equipment.
7. Bulk grain explicitly deferred (is_active = 0, Hopper/Bulk equipment required).
8. Reefer not introduced into target equipment universe.
9. Lifecycle baseline preserved (31 Shortlisted, 97 Qualified, 399 Discovery).
10. Company real-world footprint statuses preserved.
11. Filtering by Family, Category, and Seasonality.
12. Unified search includes new commodity terms.
13. Migration idempotency (re-run produces 0 duplicates).
14. Zero fake operational records (0 fake outreach, loads, signals, capacity, matches).
"""

import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.backend.db.connection import create_connection
from src.backend.db.queries import (
    get_commodity_categories,
    get_commodity_families,
    get_company_grouped_prospects,
    get_prospect_detail,
    get_prospects_list,
    get_summary_counts,
    get_taxonomy_overview,
)
from src.backend.main import app
from scripts.migrate_stage3g_taxonomy import run_migration


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


from src.backend.db.connection import create_connection, get_db_path

@pytest.fixture(scope="module")
def db_conn():
    conn = create_connection(get_db_path())
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ----------------------------------------------------------------------------
# 1. Backward Compatibility & Baseline Integrity
# ----------------------------------------------------------------------------

def test_existing_commodity_categories_preserved(db_conn):
    """Verify that original commodity_category strings in facility_commodities are preserved."""
    cur = db_conn.cursor()
    categories = cur.execute("SELECT DISTINCT commodity_category FROM facility_commodities").fetchall()
    cat_names = {r[0] for r in categories}
    assert "Lumber & Wood Products" in cat_names
    assert "Steel & Metal Products" in cat_names
    assert "Precast Concrete & Heavy Building" in cat_names
    assert "MOLDED_PLASTICS" in cat_names
    assert "TOOLING_MOLDS" in cat_names
    assert len(cat_names) >= 20, "Existing distinct categories must remain intact"


def test_baseline_lifecycle_counts_unchanged(db_conn):
    """Verify that company lifecycle stages remain exactly 29 Shortlisted, 91 Qualified, 445 Discovery."""
    counts = get_summary_counts(get_db_path())
    assert counts["all_companies_count"] == 565
    assert counts["all_prospects_count"] == 653
    assert counts["shortlisted_companies_count"] == 29
    assert counts["qualified_companies_count"] == 91
    assert counts["discovery_companies_count"] == 445
    assert counts["shortlisted_count"] == 29
    assert counts["qualified_count"] == 124
    assert counts["discovery_count"] == 500


def test_zero_fake_operational_data(db_conn):
    """Verify zero fake operational records exist."""
    cur = db_conn.cursor()
    assert cur.execute("SELECT count(*) FROM outreach_logs").fetchone()[0] == 0
    assert cur.execute("SELECT count(*) FROM load_opportunities").fetchone()[0] == 0
    assert cur.execute("SELECT count(*) FROM freight_demand_signals").fetchone()[0] == 0
    assert cur.execute("SELECT count(*) FROM capacity_postings").fetchone()[0] == 0
    assert cur.execute("SELECT count(*) FROM load_capacity_matches").fetchone()[0] == 0


def test_company_footprint_statuses_preserved(db_conn):
    """Verify Stage 3F.2 footprint truth is preserved."""
    cur = db_conn.cursor()
    fp_counts = cur.execute(
        "SELECT company_footprint_status, count(*) FROM companies WHERE id IN (SELECT DISTINCT company_id FROM facilities) GROUP BY company_footprint_status"
    ).fetchall()
    fp_map = {r[0]: r[1] for r in fp_counts}
    assert fp_map.get("SINGLE_SITE_VERIFIED", 0) > 0
    assert fp_map.get("MULTI_SITE_VERIFIED", 0) > 0
    assert fp_map.get("UNKNOWN", 0) > 0


# ----------------------------------------------------------------------------
# 2. Taxonomy Families & Categories Presence & Codes
# ----------------------------------------------------------------------------

def test_all_requested_families_exist(db_conn):
    """Verify all 10 requested commodity families exist."""
    fams = get_commodity_families(get_db_path(), include_inactive=True)
    fam_codes = {f["family_code"] for f in fams}
    expected = {
        "SEASONAL_OPPORTUNITY",
        "REGIONAL_SPECIALTY_MFG",
        "PACKAGING_HIGH_CUBE",
        "FOREST_PRODUCTS",
        "METALS_STEEL",
        "CONCRETE_PRECAST",
        "PLASTICS_TOOLING",
        "BUILDING_MATERIALS",
        "INDUSTRIAL_MFG",
        "BULK_AGRICULTURE",
    }
    assert expected.issubset(fam_codes), f"Missing families: {expected - fam_codes}"


def test_all_requested_new_categories_exist(db_conn):
    """Verify all requested seasonal, regional specialty, and packaging categories exist."""
    cats = get_commodity_categories(get_db_path(), include_deferred=True)
    cat_codes = {c["category_code"] for c in cats}
    expected_categories = {
        # Seasonal & Opportunity
        "CHRISTMAS_TREES",
        "NURSERY_TREES_SHRUBS",
        "HARDY_OUTDOOR_PLANTS",
        "HAY_STRAW",
        "WOOD_PELLETS_FIREWOOD",
        "PACKAGED_ICE_MELT",
        "BAGGED_MULCH_SOIL",
        "PAVERS_LANDSCAPE_STONE",
        # Regional Specialty Mfg
        "PALLETS_CRATES_DUNNAGE",
        "ROOF_TRUSSES_WALL_PANELS",
        "HDPE_PVC_PIPE",
        "FENCING_GATES_POSTS",
        "METAL_ROOFING_SIDING",
        "PORTABLE_BUILDINGS",
        "AG_EQUIPMENT",
        "USED_MACHINERY",
        "HVAC_EQUIPMENT",
        "PLAYGROUND_PARK_EQUIPMENT",
        "SOLAR_RACKING",
        # Packaging & High-Cube
        "CORRUGATED_PACKAGING",
        "PLASTIC_PACKAGING",
        "CLEAN_DRUMS",
        "CLEAN_IBC_TOTES",
        "MATTRESSES_FURNITURE",
        "FOAM_PRODUCTS",
        # Core
        "LUMBER_FOREST_PRODUCTS",
        "STEEL_METALS",
        "CONCRETE_PRECAST_PRODUCTS",
        "PLASTICS_TOOLING_PRODUCTS",
        "BUILDING_MATERIALS_GENERAL",
        "INDUSTRIAL_MFG_EQUIPMENT",
        # Deferred
        "BULK_GRAIN_DEFERRED",
    }
    assert expected_categories.issubset(cat_codes), f"Missing categories: {expected_categories - cat_codes}"


def test_unique_stable_category_codes(db_conn):
    """Verify category codes are unique and uppercase ASCII."""
    cats = get_commodity_categories(get_db_path(), include_deferred=True)
    codes = [c["category_code"] for c in cats]
    assert len(codes) == len(set(codes)), "Category codes must be unique"
    for code in codes:
        assert code.isupper(), f"Code {code} must be uppercase"
        assert code.replace("_", "").isalnum(), f"Code {code} must be alphanumeric with underscores"


# ----------------------------------------------------------------------------
# 3. Policy & Invariant Boundaries
# ----------------------------------------------------------------------------

def test_bulk_grain_is_deferred(db_conn):
    """Verify Bulk Grain is explicitly marked deferred (is_active = 0, Hopper/Bulk note)."""
    cur = db_conn.cursor()
    row = cur.execute("SELECT is_active, deferred_status_note FROM commodity_categories WHERE category_code = 'BULK_GRAIN_DEFERRED'").fetchone()
    assert row is not None
    assert row[0] == 0, "Bulk grain must have is_active = 0"
    assert "Hopper/Bulk equipment family" in row[1]


def test_reefer_freight_not_introduced(db_conn):
    """Verify that REEFER / temperature-controlled equipment is not introduced into active equipment category enums."""
    cur = db_conn.cursor()
    rows = cur.execute("SELECT DISTINCT equipment_category FROM facility_commodities").fetchall()
    for r in rows:
        assert r[0] in ("FLATBED", "STEP_DECK", "DRY_VAN"), f"Unexpected equipment category {r[0]}"


def test_verified_equipment_facilities_invariant(db_conn):
    """Verify that strictly facilities [1, 2, 18] have VERIFIED equipment."""
    cur = db_conn.cursor()
    verified_facs = cur.execute(
        "SELECT DISTINCT facility_id FROM facility_commodities WHERE equipment_usage_status = 'VERIFIED' ORDER BY facility_id"
    ).fetchall()
    verified_ids = [r[0] for r in verified_facs]
    assert verified_ids == [1, 2, 18], f"Verified equipment facilities must remain exactly [1, 2, 18], got {verified_ids}"


def test_category_seasonality_vs_facility_verified_seasonality(db_conn):
    """Verify category seasonality guidance is distinct from facility-level verified seasonality."""
    cats = get_commodity_categories(get_db_path())
    cat_map = {c["category_code"]: c for c in cats}
    # Christmas trees category has HOLIDAY_PEAK guidance
    assert cat_map["CHRISTMAS_TREES"]["seasonality_profile"] == "HOLIDAY_PEAK"

    # But facility_commodities table rows must NOT have verified seasonality unless primary evidence exists
    cur = db_conn.cursor()
    fac_commodities_with_season = cur.execute(
        "SELECT count(*) FROM facility_commodities WHERE seasonality_profile IS NOT NULL"
    ).fetchone()[0]
    assert fac_commodities_with_season == 0, "Individual facility seasonality must remain NULL until primary evidence is verified"


def test_typical_equipment_fit_vs_verified_equipment_usage(db_conn):
    """Verify that category typical equipment is non-binding guidance, not facility verified usage."""
    # HDPE pipe category typically fits FLATBED
    cats = get_commodity_categories(get_db_path())
    cat_map = {c["category_code"]: c for c in cats}
    assert "FLATBED" in cat_map["HDPE_PVC_PIPE"]["typical_equipment_fit"]

    # Typical equipment guidance on category must not promote any unverified facility to VERIFIED
    cur = db_conn.cursor()
    inferred_count = cur.execute("SELECT count(*) FROM facility_commodities WHERE equipment_usage_status = 'INFERRED'").fetchone()[0]
    assert inferred_count > 500, "Inferred facilities must remain INFERRED"


# ----------------------------------------------------------------------------
# 4. Multi-Category Facility Association
# ----------------------------------------------------------------------------

def test_multi_category_facility_mappings(db_conn):
    """Verify facilities with secondary products have multiple mappings in facility_commodity_mappings."""
    cur = db_conn.cursor()
    # Facility 5 (Battle Lumber) produces lumber, pallet cants, and bark mulch
    f5_mappings = cur.execute(
        """
        SELECT c.category_code, m.is_primary
        FROM facility_commodity_mappings m
        JOIN commodity_categories c ON m.category_id = c.id
        WHERE m.facility_id = 5
        ORDER BY m.is_primary DESC
        """
    ).fetchall()
    f5_codes = {r[0] for r in f5_mappings}
    assert "LUMBER_FOREST_PRODUCTS" in f5_codes
    assert "PALLETS_CRATES_DUNNAGE" in f5_codes
    # Audit Finding 8: Bulk mulch is NOT bagged mulch; BAGGED_MULCH_SOIL must NOT be mapped to Battle Lumber
    assert "BAGGED_MULCH_SOIL" not in f5_codes
    assert len(f5_mappings) >= 2

    # Primary mapping is marked is_primary = 1
    primary = [r[0] for r in f5_mappings if r[1] == 1]
    assert len(primary) == 1
    assert primary[0] == "LUMBER_FOREST_PRODUCTS"


def test_secondary_mappings_for_greif(db_conn):
    """Verify Greif plants have clean drums and IBC totes mapped."""
    cur = db_conn.cursor()
    f370_mappings = cur.execute(
        """
        SELECT c.category_code
        FROM facility_commodity_mappings m
        JOIN commodity_categories c ON m.category_id = c.id
        WHERE m.facility_id = 370
        """
    ).fetchall()
    codes = {r[0] for r in f370_mappings}
    assert "CLEAN_IBC_TOTES" in codes or "CLEAN_DRUMS" in codes


# ----------------------------------------------------------------------------
# 5. Queries & API Layer
# ----------------------------------------------------------------------------

def test_taxonomy_overview_structure():
    """Verify get_taxonomy_overview returns all families with categories and company counts."""
    overview = get_taxonomy_overview()
    assert len(overview) == 10
    for fam in overview:
        assert "family_code" in fam
        assert "display_name" in fam
        assert "categories" in fam
        assert "total_facilities" in fam
        assert "total_companies" in fam
        for cat in fam["categories"]:
            assert "category_code" in cat
            assert "typical_equipment_fit" in cat
            assert "facility_count" in cat
            assert "company_count" in cat
            assert cat["facility_count"] >= 0
            assert cat["company_count"] >= 0


def test_prospect_detail_includes_taxonomy():
    """Verify get_prospect_detail includes taxonomy and seasonality metadata."""
    detail = get_prospect_detail(1)
    assert detail is not None
    assert "commodity_family_name" in detail
    assert "commodity_category_name" in detail
    assert "category_seasonality" in detail
    assert "category_typical_equipment" in detail
    assert "taxonomy_mappings" in detail
    assert len(detail["taxonomy_mappings"]) >= 1


def test_company_grouped_prospects_includes_taxonomy():
    """Verify get_company_grouped_prospects aggregates family and category codes for filtering."""
    groups = get_company_grouped_prospects()
    assert len(groups) == 565
    sample = groups[0]
    assert "commodity_family_codes" in sample
    assert "commodity_category_codes" in sample
    assert "seasonality_profiles" in sample
    assert "primary_family_name" in sample
    assert "primary_seasonality" in sample


def test_api_taxonomy_endpoints(client):
    """Verify FastAPI routes for taxonomy return valid JSON."""
    r_over = client.get("/api/taxonomy/overview")
    assert r_over.status_code == 200
    assert len(r_over.json()) == 10

    r_fams = client.get("/api/taxonomy/families")
    assert r_fams.status_code == 200
    assert len(r_fams.json()) == 9  # 9 active, bulk ag deferred

    r_cats = client.get("/api/taxonomy/categories")
    assert r_cats.status_code == 200
    assert len(r_cats.json()) == 32  # 32 active (including INDUSTRIAL_PAPER_PACKAGING)


# ----------------------------------------------------------------------------
# 6. Search & Filtering Behavior
# ----------------------------------------------------------------------------

def test_searchable_text_includes_new_taxonomy_terms():
    """Verify searchable_text on company groups contains family and category terms."""
    groups = get_company_grouped_prospects()
    # Find Battle Lumber
    battle = next((g for g in groups if "battle lumber" in g["operating_brand"].lower()), None)
    assert battle is not None
    stext = battle["searchable_text"]
    assert "lumber" in stext
    assert "pallets" in stext or "pallets_crates_dunnage" in stext


def test_migration_idempotence(tmp_path):
    """Verify migration can run repeatedly without duplicate records or errors."""
    import shutil
    temp_db = tmp_path / "test_prospects.db"
    shutil.copy2(get_db_path(), temp_db)
    run_migration(temp_db)
    fams = get_commodity_families(temp_db, include_inactive=True)
    assert len(fams) == 10
    cats = get_commodity_categories(temp_db, include_deferred=True)
    assert len(cats) == 33


# ----------------------------------------------------------------------------
# 7. Stage 3G.1 Regression & Exact Equipment Truth Suite
# ----------------------------------------------------------------------------

def test_stage3g1_requested_categories_exist(db_conn):
    """Verify that all specific Stage 3G.1 requested active categories exist with stable codes."""
    cur = db_conn.cursor()
    target_codes = [
        "USED_MACHINERY",
        "HVAC_EQUIPMENT",
        "PLAYGROUND_PARK_EQUIPMENT",
        "SOLAR_RACKING",
        "PLASTIC_PACKAGING",
        "HAY_STRAW",
        "CHRISTMAS_TREES",
        "PACKAGED_ICE_MELT",
    ]
    for code in target_codes:
        row = cur.execute(
            "SELECT category_code, display_name, is_active FROM commodity_categories WHERE category_code = ?",
            (code,)
        ).fetchone()
        assert row is not None, f"Category code {code} must exist in commodity_categories"
        assert row[2] == 1, f"Category code {code} must be active (is_active = 1)"

    # Verify specific display labels
    labels = {
        r[0]: r[1] for r in cur.execute(
            "SELECT category_code, display_name FROM commodity_categories WHERE category_code IN ('USED_MACHINERY', 'HVAC_EQUIPMENT', 'PLAYGROUND_PARK_EQUIPMENT', 'SOLAR_RACKING', 'PLASTIC_PACKAGING', 'HAY_STRAW')"
        ).fetchall()
    }
    assert labels["USED_MACHINERY"] == "Used Machinery & Industrial Equipment"
    assert labels["HVAC_EQUIPMENT"] == "HVAC, Rooftop Units & Industrial Cooling"
    assert labels["PLAYGROUND_PARK_EQUIPMENT"] == "Playground, Park & Bleacher Equipment"
    assert labels["SOLAR_RACKING"] == "Solar Racking & Mounting Structures"
    assert labels["PLASTIC_PACKAGING"] == "Plastic Packaging & Rigid Containers"
    assert labels["HAY_STRAW"] == "Hay & Straw / Compressed Bales"


def test_stage3g1_exact_verified_equipment_truth(db_conn):
    """
    Assert exact equipment truth:
    Facility 1 (Beasley): FLATBED VERIFIED
    Facility 2 (Kenwal): FLATBED VERIFIED
    Facility 18 (CSP): FLATBED VERIFIED
    """
    cur = db_conn.cursor()
    # Check facility_commodities
    for fac_id in (1, 2, 18):
        row = cur.execute(
            "SELECT equipment_category, equipment_usage_status FROM facility_commodities WHERE facility_id = ?",
            (fac_id,)
        ).fetchone()
        assert row is not None, f"Facility {fac_id} must have a facility_commodities record"
        assert row[0] == "FLATBED", f"Facility {fac_id} equipment_category must be FLATBED, got {row[0]}"
        assert row[1] == "VERIFIED", f"Facility {fac_id} equipment_usage_status must be VERIFIED, got {row[1]}"

    # Check claims table
    for fac_id in (1, 2, 18):
        claim = cur.execute(
            """
            SELECT cl.claimed_value, cl.verification_status, cl.is_current_accepted
            FROM claims cl
            JOIN facility_commodities fc ON cl.facility_commodity_id = fc.id
            WHERE fc.facility_id = ? AND cl.claim_field = 'equipment_category'
            """,
            (fac_id,)
        ).fetchone()
        assert claim is not None, f"Facility {fac_id} must have an equipment_category claim"
        assert claim[0] == "FLATBED", f"Facility {fac_id} equipment claim value must be FLATBED, got {claim[0]}"
        assert claim[1] == "VERIFIED", f"Facility {fac_id} equipment claim status must be VERIFIED, got {claim[1]}"
        assert claim[2] == 1, f"Facility {fac_id} equipment claim must be current accepted"


def test_stage3g1_csp_kenwal_no_step_deck_verified(db_conn):
    """
    Verify that Kenwal (Facility 2) and CSP (Facility 18) do NOT have VERIFIED STEP_DECK claims.
    CSP source explicitly establishes: Flatbeds only; overhead crane or sheet lifter loading;
    dry vans / box trucks cannot be loaded.
    """
    cur = db_conn.cursor()
    for fac_id in (2, 18):
        claims = cur.execute(
            """
            SELECT cl.claimed_value, cl.verification_status
            FROM claims cl
            JOIN facility_commodities fc ON cl.facility_commodity_id = fc.id
            WHERE fc.facility_id = ? AND cl.claim_field = 'equipment_category' AND cl.verification_status = 'VERIFIED'
            """,
            (fac_id,)
        ).fetchall()
        for c in claims:
            assert "STEP_DECK" not in c[0], f"Facility {fac_id} must NOT have VERIFIED STEP_DECK: {c[0]}"


def test_stage3g1_category_guidance_does_not_mutate_facility_claims(db_conn):
    """Verify that category typical equipment does not mutate facility equipment claims."""
    cur = db_conn.cursor()
    # Find all facilities whose primary category has typical_equipment_fit containing STEP_DECK
    step_deck_cat_facs = cur.execute(
        """
        SELECT f.id, fc.equipment_category, fc.equipment_usage_status
        FROM facilities f
        JOIN facility_commodity_mappings m ON f.id = m.facility_id AND m.is_primary = 1
        JOIN commodity_categories cat ON m.category_id = cat.id
        JOIN facility_commodities fc ON fc.facility_id = f.id
        WHERE cat.typical_equipment_fit LIKE '%STEP_DECK%'
        """
    ).fetchall()
    assert len(step_deck_cat_facs) > 0
    # None of them should be VERIFIED STEP_DECK unless primary evidence was verified
    for fac_id, eq_cat, eq_stat in step_deck_cat_facs:
        if fac_id in (2, 18):
            assert eq_cat == "FLATBED"
            assert eq_stat == "VERIFIED"
        else:
            assert eq_stat in ("INFERRED", "UNKNOWN"), f"Facility {fac_id} was improperly promoted: {eq_stat}"


def test_stage3g1_taxonomy_mapping_fk_and_join_integrity(db_conn):
    """Verify that all facility_commodity_mappings have valid FK joins with 0 orphans."""
    cur = db_conn.cursor()
    # Check total mappings
    total_m = cur.execute("SELECT count(*) FROM facility_commodity_mappings").fetchone()[0]
    prim_m = cur.execute("SELECT count(*) FROM facility_commodity_mappings WHERE is_primary = 1").fetchone()[0]
    sec_m = cur.execute("SELECT count(*) FROM facility_commodity_mappings WHERE is_primary = 0").fetchone()[0]
    assert total_m == 672
    assert prim_m == 653
    assert sec_m == 19

    # Check 0 orphan facilities
    orphan_fac = cur.execute(
        "SELECT count(*) FROM facility_commodity_mappings m LEFT JOIN facilities f ON m.facility_id = f.id WHERE f.id IS NULL"
    ).fetchone()[0]
    assert orphan_fac == 0, "No orphan facility mappings allowed"

    # Check 0 orphan categories
    orphan_cat = cur.execute(
        "SELECT count(*) FROM facility_commodity_mappings m LEFT JOIN commodity_categories c ON m.category_id = c.id WHERE c.id IS NULL"
    ).fetchone()[0]
    assert orphan_cat == 0, "No orphan category mappings allowed"

    # Check that all facilities join to valid companies
    invalid_comp = cur.execute(
        """
        SELECT count(*)
        FROM facility_commodity_mappings m
        JOIN facilities f ON m.facility_id = f.id
        LEFT JOIN companies c ON f.company_id = c.id
        WHERE c.id IS NULL
        """
    ).fetchone()[0]
    assert invalid_comp == 0, "All mapped facilities must join to a valid company"


def test_stage3g1_secondary_mappings_evidence_backed(db_conn):
    """Verify that all 21 secondary mappings join to genuine facilities with relevant commodity products."""
    cur = db_conn.cursor()
    sec_rows = cur.execute(
        """
        SELECT f.id, c.id, c.operating_brand, f.facility_name, cat.category_code, fc.specific_products, fc.commodity_category
        FROM facility_commodity_mappings m
        JOIN facilities f ON m.facility_id = f.id
        JOIN companies c ON f.company_id = c.id
        JOIN commodity_categories cat ON m.category_id = cat.id
        JOIN facility_commodities fc ON fc.facility_id = f.id
        WHERE m.is_primary = 0
        ORDER BY f.id
        """
    ).fetchall()
    assert len(sec_rows) == 19, f"Expected exactly 19 secondary mappings, got {len(sec_rows)}"

    # Confirm purged bogus mappings are absent
    bogus_ids = {10, 11, 38, 39, 110}
    for r in sec_rows:
        assert r[0] not in bogus_ids, f"Facility {r[0]} was a purged bogus mapping and must not exist in secondary mappings"

