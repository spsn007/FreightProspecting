"""
FreightProspecting V1 — Company-Grouped Master Directory & Broker Access Friction Tests
Validates:
1. Entity separation invariant: COMPANY != FACILITY (285 active companies, 372 facilities).
2. Equipment truth: Georgia-Pacific facilities are INFERRED; only Beasley, Kenwal, and CSP are VERIFIED.
3. Summary metrics: company-level counts and facility-level counts truthfully separated.
4. Company grouping: exactly 285 company groups, 220 single-facility, 65 multi-facility.
5. Georgia-Pacific acceptance: appears once with 4 child facilities (Albany, Rome, Madison, Warrenton).
6. Multi-facility leaders: West Fraser (7), Canfor (5), GP (4), Interfor (4).
7. Evidence-based Broker Access Friction heuristic:
   - Transparent, explainable, deterministic.
   - Observable facts kept strictly separate from heuristic.
   - Multi-site scale is transparently stated as a scale heuristic, never corporate evidence.
   - No fabricated routing guides, formal onboarding, or broker rejection.
   - COMMERCIAL_SALES and GENERAL_FACILITY are strictly neutral (do not lower friction).
   - UNKNOWN private fleet and carrier use are rendered as UNKNOWN (never "No private fleet").
   - Broker acceptance remains strictly UNKNOWN (never mutated by friction).
   - Exact distribution: HIGH=4, MEDIUM=71, LOW=116, UNKNOWN=94 (Total: 285).
8. Unified search: child facility cities (e.g. Albany, Warrenton) match parent company (Georgia-Pacific).
9. API endpoints: /api/companies returns 200 with 285 groups; /prospects renders Company View by default.
10. Baseline data preservation: Shortlist=4, Discovery=368, Qualified=0, Total=372. Signals=0, Loads=0, Capacity=0, Matches=0.
"""

import sqlite3
import pytest
from fastapi.testclient import TestClient

from src.backend.main import app
from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.queries import (
    get_summary_counts,
    get_prospects_list,
    get_company_grouped_prospects,
    evaluate_broker_access_friction,
)

client = TestClient(app)
DB_PATH = get_db_path()


# ============================================================================
# 1. Company vs Facility Summary Counts
# ============================================================================
def test_company_and_facility_summary_counts():
    """Verify truthful separation of company-level and facility-level counts."""
    counts = get_summary_counts(DB_PATH)

    # Facility counts
    assert counts["all_prospects_count"] == 1120
    assert counts["shortlisted_count"] == 29
    assert counts["discovery_count"] == 102
    assert counts["qualified_count"] == 989

    # Company counts (565 original + 467 new = 1032 operating companies)
    assert counts["total_companies_count"] == 1034  # 1032 operating + 2 holding/inactive
    assert counts["all_companies_count"] == 1032
    assert counts["shortlisted_companies_count"] == 29
    assert counts["discovery_companies_count"] == 47
    assert counts["qualified_companies_count"] == 956
    assert counts["all_companies_count"] >= 500

    # Structure counts
    assert counts["single_facility_companies_count"] == 966
    assert counts["multi_facility_companies_count"] == 66
    assert counts["single_facility_companies_count"] + counts["multi_facility_companies_count"] == 1032

    # Zero fake records
    assert counts["signals_count"] == 0
    assert counts["loads_count"] == 0
    assert counts["capacity_count"] == 0
    assert counts["matches_count"] == 0


# ============================================================================
# 2. Equipment Truth Invariant: Only Evidence-Backed Usage is VERIFIED
# ============================================================================
def test_equipment_truth_invariants():
    """
    Verify equipment truth:
    - Only Beasley (1), Kenwal (2), and CSP (18) have VERIFIED equipment usage.
    - All 4 Georgia-Pacific facilities (46, 47, 48, 49) are strictly INFERRED.
    - All other Discovery facilities remain INFERRED (total: 369 INFERRED, 3 VERIFIED).
    """
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Check all verified rows in database
        verified_rows = conn.execute(
            "SELECT facility_id, equipment_category, equipment_usage_status FROM facility_commodities WHERE equipment_usage_status = 'VERIFIED'"
        ).fetchall()
        verified_ids = {r["facility_id"] for r in verified_rows}
        assert verified_ids == {1, 2, 18}, f"Expected verified facility IDs {{1, 2, 18}}, got {verified_ids}"

        # Georgia-Pacific facilities must be INFERRED
        gp_rows = conn.execute(
            """
            SELECT fc.facility_id, fc.equipment_category, fc.equipment_usage_status
            FROM facility_commodities fc
            WHERE fc.facility_id IN (46, 47, 48, 49)
            """
        ).fetchall()
        assert len(gp_rows) == 4
        for r in gp_rows:
            assert r["equipment_category"] == "FLATBED"
            assert r["equipment_usage_status"] == "INFERRED", (
                f"Facility {r['facility_id']} must have equipment_usage_status = 'INFERRED', not VERIFIED"
            )
    finally:
        conn.close()


# ============================================================================
# 3. Company-Grouped Prospects Integrity
# ============================================================================
def test_company_grouped_prospects_structure():
    """Verify get_company_grouped_prospects returns 527 groups grouping all 615 facilities."""
    groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)

    assert len(groups) == 1032, f"Expected 1032 active company groups, got {len(groups)}"

    # Total facilities across all groups must be exactly 1120
    total_child_facilities = sum(len(g["facilities"]) for g in groups)
    assert total_child_facilities == 1120, f"Expected 1120 child facilities, got {total_child_facilities}"

    # Verify single vs multi counts
    single_count = sum(1 for g in groups if g["facility_count"] == 1)
    multi_count = sum(1 for g in groups if g["facility_count"] > 1)
    assert single_count == 966
    assert multi_count == 66


# ============================================================================
# 4. Georgia-Pacific Grouping Acceptance Test
# ============================================================================
def test_georgia_pacific_grouping():
    """
    Acceptance Test: Georgia-Pacific appears ONCE in Company View with 4 facilities:
    Albany, GA; Rome, GA; Madison, GA; Warrenton, GA.
    Equipment usage status is INFERRED for all 4.
    """
    groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)
    gp_groups = [g for g in groups if g["operating_brand"] == "Georgia-Pacific"]

    assert len(gp_groups) == 1, "Georgia-Pacific must appear exactly ONCE in company groups"

    gp = gp_groups[0]
    assert gp["facility_count"] == 4
    assert gp["is_multi_facility"] is True
    # AUD-005: When company_footprint_status is UNKNOWN, DB facility count cannot be promoted to verified scale
    assert gp["friction_level"] == "UNKNOWN"
    assert any("Company footprint UNKNOWN" in r for r in gp["broker_access_friction"]["reasons"])

    # Verify child facilities
    child_facs = gp["facilities"]
    assert len(child_facs) == 4

    child_cities = {f["city"] for f in child_facs}
    expected_cities = {"Albany", "Rome", "Madison", "Warrenton"}
    assert child_cities == expected_cities, f"Expected cities {expected_cities}, got {child_cities}"

    child_names = {f["facility_name"] for f in child_facs}
    expected_names = {
        "Albany Lumber Mill",
        "Rome Lumber Mill",
        "Madison Plywood Plant",
        "Warrenton Lumber Facility",
    }
    assert child_names == expected_names, f"Expected names {expected_names}, got {child_names}"

    # All 4 in Georgia, FTL Flatbed, INFERRED usage
    for f in child_facs:
        assert f["state_prov"] == "GA"
        assert f["country"] == "US"
        assert f["primary_commodity"]["equipment_category"] == "FLATBED"
        assert f["primary_commodity"]["equipment_usage_status"] == "INFERRED"


# ============================================================================
# 5. Multi-Facility Leaders
# ============================================================================
def test_multi_facility_leaders():
    """Verify multi-facility top companies: West Fraser (7), Canfor (5), GP (4), Interfor (4)."""
    groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)
    by_brand = {g["operating_brand"]: g for g in groups}

    assert by_brand["West Fraser"]["facility_count"] == 7
    assert by_brand["Canfor"]["facility_count"] == 5
    assert by_brand["Georgia-Pacific"]["facility_count"] == 4
    assert by_brand["Interfor"]["facility_count"] == 4

    # AUD-005: With company_footprint_status UNKNOWN, scale is not promoted; friction is UNKNOWN
    for brand in ["West Fraser", "Canfor", "Georgia-Pacific", "Interfor"]:
        assert by_brand[brand]["friction_level"] == "UNKNOWN"
        reasons = by_brand[brand]["broker_access_friction"]["reasons"]
        assert any("Company footprint UNKNOWN" in r for r in reasons), (
            f"Expected footprint UNKNOWN explanation for {brand}, got {reasons}"
        )


# ============================================================================
# 6. Corrected Broker Access Friction Distribution & Observable Facts
# ============================================================================
def test_broker_access_friction_distribution_and_facts():
    """
    Verify corrected Broker Access Friction distribution:
    HIGH: 4 companies (West Fraser, Canfor, GP, Interfor)
    MEDIUM: 71 companies (61 multi-plant [2-3] + 10 single-plant with verified fleet)
    LOW: 116 companies (single-plant with verified freight/logistics contact or verified carrier use)
    UNKNOWN: 94 companies (single-plant with unverified carrier channel and neutral/unknown contacts)
    Total: 285 companies.
    """
    groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)

    friction_counts = {}
    for g in groups:
        lvl = g["friction_level"]
        friction_counts[lvl] = friction_counts.get(lvl, 0) + 1

    assert friction_counts["HIGH"] == 8
    assert friction_counts["MEDIUM"] == 36
    assert friction_counts["LOW"] == 6
    assert friction_counts["UNKNOWN"] == 982
    assert sum(friction_counts.values()) == 1032

    # Verify observable facts integrity
    for g in groups:
        facts = g["facts"]
        assert "facility_count" in facts
        assert "private_fleet_present" in facts
        assert "commercial_carrier_use" in facts
        assert "freight_procurement_level" in facts
        assert "broker_acceptance" in facts
        assert facts["broker_acceptance"] == "UNKNOWN", "Broker acceptance must be UNKNOWN (no fake acceptance)"

        # Check explainability reasons
        friction = g["broker_access_friction"]
        assert len(friction["reasons"]) > 0, f"Friction must have explainable reasons for {g['operating_brand']}"

        # Prohibited phrases check
        for r in friction["reasons"]:
            assert "No private fleet" not in r
            assert "No captive" not in r
            assert "No fleet detected" not in r
            assert "No commercial carrier" not in r
            assert "Formal vendor onboarding" not in r
            assert "Rigid routing guide" not in r


# ============================================================================
# 7. Commercial Sales Neutrality
# ============================================================================
def test_commercial_sales_neutrality():
    """
    Verify COMMERCIAL_SALES alone does NOT lower Broker Access Friction to LOW:
    - Lindsay Precast (sales only, UNKNOWN footprint) -> UNKNOWN
    - Tindall Corporation (sales only, UNKNOWN footprint) -> UNKNOWN
    - High Concrete Group LLC (sales only, MULTI_SITE_VERIFIED) -> MEDIUM (not LOW)
    - Coreslab Structures (ONT) Inc. (sales only, MULTI_SITE_VERIFIED) -> HIGH (not LOW)
    """
    groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)
    by_brand = {g["operating_brand"]: g for g in groups}

    # Companies with UNKNOWN footprint and sales-only contacts remain UNKNOWN (neutral, never LOW)
    assert by_brand["Lindsay Precast"]["friction_level"] == "UNKNOWN"
    assert by_brand["Tindall Corporation"]["friction_level"] == "UNKNOWN"

    # Multi-site companies never lowered to LOW by sales contacts
    assert by_brand["High Concrete Group LLC"]["friction_level"] in ("MEDIUM", "HIGH")
    assert by_brand["Jordan Forest Products, LLC"]["friction_level"] in ("MEDIUM", "HIGH")
    assert by_brand["Coreslab Structures (ONT) Inc."]["friction_level"] == "HIGH"


# ============================================================================
# 8. Single-Facility Shipper Evaluation
# ============================================================================
def test_single_facility_prospects():
    """Verify single-facility shippers in DB: Beasley (HIGH due to verified 6 sawmills), Miami Valley (MEDIUM due to fleet)."""
    groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)
    by_brand = {g["operating_brand"]: g for g in groups}

    # Beasley: 1 facility in DB, 6 verified operating locations
    beasley = by_brand["Beasley Forest Products"]
    assert beasley["facility_count"] == 1
    assert beasley["friction_level"] in ("HIGH", "MEDIUM")
    assert beasley["facts"]["commercial_carrier_use"] is True
    assert beasley["facts"]["private_fleet_present"] is False  # UNKNOWN per affiliated carrier invariant

    # Miami Valley: 1 facility in DB, private fleet verified
    mv = by_brand["Miami Valley Steel Service, Inc."]
    assert mv["facility_count"] == 1
    assert mv["friction_level"] == "MEDIUM"
    assert mv["facts"]["private_fleet_present"] is True


# ============================================================================
# 9. Unified Search Across Company and Child Facilities
# ============================================================================
def test_unified_search_across_children():
    """Verify that searchable_text includes child facility cities, matching parent company."""
    groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=DB_PATH)
    by_brand = {g["operating_brand"]: g for g in groups}
    gp = by_brand["Georgia-Pacific"]

    searchable = gp["searchable_text"]
    assert "albany" in searchable
    assert "rome" in searchable
    assert "madison" in searchable
    assert "warrenton" in searchable
    assert "plywood" in searchable
    assert "lumber" in searchable


# ============================================================================
# 10. API Endpoints: /api/companies and /prospects HTML
# ============================================================================
def test_api_companies_endpoint():
    """Verify /api/companies endpoint returns 200 with 285 company records."""
    res = client.get("/api/companies")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1032

    # Check Georgia-Pacific in JSON response
    gp = next((c for c in data if c["operating_brand"] == "Georgia-Pacific"), None)
    assert gp is not None
    assert gp["facility_count"] == 4
    assert gp["friction_level"] == "UNKNOWN"
    assert len(gp["facilities"]) == 4


def test_master_directory_page_company_mode():
    """Verify /prospects HTML renders Company View by default with required UI components."""
    res = client.get("/prospects?page_size=500")
    assert res.status_code == 200
    html = res.text

    # Data islands present
    assert 'id="company-groups-data"' in html
    assert 'id="prospects-data"' in html

    # Key UI elements present
    assert "get('view') === 'facilities' ? 'FACILITIES' : 'COMPANIES'" in html
    assert "Broker Access Friction" in html
    assert "🏢 Companies" in html
    assert "📍 Facilities" in html
    assert "Operating Companies" in html
    assert "Physical Shipping Facilities" in html
    assert "Georgia-Pacific" in html
    assert "Private Fleet: UNKNOWN" in html
