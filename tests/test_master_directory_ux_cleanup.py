"""
Comprehensive Test Suite: Master Directory UX & Multi-Select Filter Architecture Cleanup.
Tests Matrix Requirements A through M:
- A: Navigation Canonicalization (GET / -> 302 -> /prospects, query preservation, sidebar)
- B: Legacy Filter Removal (Lifecycle stage / friction removed from normal UX)
- C: Opportunity Multi-Select (OR within group)
- D: Outreach Multi-Select (OR within group)
- E: Equipment Multi-Select (OR within group)
- F: Seasonality Multi-Select (OR within group)
- G: Cross-Filter Composition (AND across different groups, OR within same group)
- H: Search + Filter Composition
- I: Sort + Filter Composition
- J: Pagination + Filter Composition
- K: URL State Serialization & Query Param Parsing
- L: Dynamic Universe Truth (1,032 companies, 1,120 facilities, no stale 565/653)
- M: Sidebar Shortcuts & CRM Workflow Routing
"""

import pytest
from fastapi.testclient import TestClient
from src.backend.main import app
from src.backend.db.queries import (
    get_universe_metadata,
    get_summary_counts,
    get_company_grouped_prospects,
    get_prospects_list,
    _parse_filter_list,
)

client = TestClient(app)


# ============================================================================
# A. Navigation Matrix
# ============================================================================

def test_root_canonically_redirects_to_prospects():
    """Verify GET / returns HTTP 302 redirect to /prospects."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/prospects"


def test_root_redirect_preserves_query_string():
    """Verify GET /?tier=TIER_A_PRIORITY redirects to /prospects?tier=TIER_A_PRIORITY."""
    response = client.get("/?tier=TIER_A_PRIORITY", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/prospects?tier=TIER_A_PRIORITY"

    # Multi-param preservation
    resp_multi = client.get("/?tier=TIER_A_PRIORITY&equipment=FLATBED&q=steel", follow_redirects=False)
    assert resp_multi.status_code == 302
    assert "tier=TIER_A_PRIORITY" in resp_multi.headers["location"]
    assert "equipment=FLATBED" in resp_multi.headers["location"]
    assert "q=steel" in resp_multi.headers["location"]


def test_cockpit_absent_from_sidebar_navigation():
    """Verify 'Shortlist Cockpit' is retired from sidebar navigation."""
    response = client.get("/prospects")
    assert response.status_code == 200
    html = response.text
    assert "Shortlist Cockpit" not in html
    assert "Master Directory" in html


def test_master_directory_is_primary_entry_point():
    """Verify Master Directory is marked active in the sidebar on /prospects."""
    response = client.get("/prospects")
    assert response.status_code == 200
    assert 'sidebar-link active' in response.text
    assert 'Master Directory' in response.text


# ============================================================================
# B. Legacy Filter Removal Matrix
# ============================================================================

def test_legacy_stage_filters_removed_from_user_toolbar():
    """Verify 'All Stages (565)', Shortlisted, Qualified, Discovery dropdown is removed from toolbar."""
    response = client.get("/prospects")
    assert response.status_code == 200
    html = response.text
    assert "All Stages (565)" not in html
    assert "All Stages (1032)" not in html
    assert 'name="stage"' not in html
    assert 'id="stageFilter"' not in html


def test_legacy_friction_filter_removed_from_user_toolbar():
    """Verify Broker Access Friction filter is removed from normal user toolbar."""
    response = client.get("/prospects")
    assert response.status_code == 200
    html = response.text
    assert 'id="frictionFilter"' not in html
    assert 'name="friction"' not in html


def test_summary_grid_has_three_clean_cards():
    """Verify summary metrics grid contains Operating Companies, Physical Facilities, and Company Structure."""
    response = client.get("/prospects")
    assert response.status_code == 200
    html = response.text
    assert "Operating Companies" in html
    assert "Physical Shipping Facilities" in html
    assert "Company Structure" in html
    # Active visible friction card is retired
    assert "metric-label\">Broker Access Friction" not in html


# ============================================================================
# C. Opportunity Multi-Select Matrix (OR within group)
# ============================================================================

def test_opportunity_single_tier_a():
    """Verify selecting only Priority Prospect (TIER_A_PRIORITY) returns exactly 19 companies."""
    res = get_company_grouped_prospects(opportunity_tier="TIER_A_PRIORITY")
    assert len(res) == 19
    for c in res:
        assert c["opportunity_tier"] == "TIER_A_PRIORITY"


def test_opportunity_single_tier_b():
    """Verify selecting only Worth Calling (TIER_B_WORTH_CALLING) returns exactly 956 companies."""
    res = get_company_grouped_prospects(opportunity_tier="TIER_B_WORTH_CALLING")
    assert len(res) == 956
    for c in res:
        assert c["opportunity_tier"] == "TIER_B_WORTH_CALLING"


def test_opportunity_single_tier_c():
    """Verify selecting only Secondary Prospect (TIER_C_SECONDARY) returns exactly 10 companies."""
    res = get_company_grouped_prospects(opportunity_tier="TIER_C_SECONDARY")
    assert len(res) == 10
    for c in res:
        assert c["opportunity_tier"] == "TIER_C_SECONDARY"


def test_opportunity_single_tier_d():
    """Verify selecting only Needs More Research (TIER_D_RESEARCH_NEEDED) returns exactly 47 companies."""
    res = get_company_grouped_prospects(opportunity_tier="TIER_D_RESEARCH_NEEDED")
    assert len(res) == 47
    for c in res:
        assert c["opportunity_tier"] == "TIER_D_RESEARCH_NEEDED"


def test_opportunity_multi_select_or_a_plus_b():
    """Verify multi-selecting Priority + Worth Calling returns 19 + 956 = 975 companies."""
    res = get_company_grouped_prospects(opportunity_tier=["TIER_A_PRIORITY", "TIER_B_WORTH_CALLING"])
    assert len(res) == 975
    tiers = {c["opportunity_tier"] for c in res}
    assert tiers.issubset({"TIER_A_PRIORITY", "TIER_B_WORTH_CALLING"})


def test_opportunity_multi_select_or_b_plus_c():
    """Verify multi-selecting Worth Calling + Secondary returns 956 + 10 = 966 companies."""
    res = get_company_grouped_prospects(opportunity_tier="TIER_B_WORTH_CALLING,TIER_C_SECONDARY")
    assert len(res) == 966
    tiers = {c["opportunity_tier"] for c in res}
    assert tiers.issubset({"TIER_B_WORTH_CALLING", "TIER_C_SECONDARY"})


def test_opportunity_multi_select_all_four_tiers():
    """Verify multi-selecting all 4 tiers returns all 1,032 operating companies."""
    res = get_company_grouped_prospects(opportunity_tier=[
        "TIER_A_PRIORITY", "TIER_B_WORTH_CALLING", "TIER_C_SECONDARY", "TIER_D_RESEARCH_NEEDED"
    ])
    assert len(res) == 1032


# ============================================================================
# D. Outreach Multi-Select Matrix (OR within group)
# ============================================================================

def test_outreach_multi_select_or():
    """Verify multi-select outreach filtering works via list and CSV."""
    # Test UNCONTACTED
    res_unc = get_company_grouped_prospects(outreach_filter="UNCONTACTED")
    count_unc = len(res_unc)

    # Test NO_ANSWER
    res_na = get_company_grouped_prospects(outreach_filter="NO_ANSWER")
    count_na = len(res_na)

    # Test UNCONTACTED + NO_ANSWER (OR logic)
    res_combined = get_company_grouped_prospects(outreach_filter=["UNCONTACTED", "NO_ANSWER"])
    assert len(res_combined) == count_unc + count_na


# ============================================================================
# E. Equipment Multi-Select Matrix (OR within group)
# ============================================================================

def test_equipment_multi_select_or():
    """Verify multi-select equipment filtering uses OR within group."""
    res_fb = get_company_grouped_prospects(equipment="FLATBED")
    count_fb = len(res_fb)

    res_sd = get_company_grouped_prospects(equipment="STEP_DECK")
    count_sd = len(res_sd)

    res_both = get_company_grouped_prospects(equipment=["FLATBED", "STEP_DECK"])
    # Combined OR should be at least max of individual and <= sum
    assert len(res_both) >= max(count_fb, count_sd)
    assert len(res_both) <= count_fb + count_sd


# ============================================================================
# F. Seasonality Multi-Select Matrix (OR within group)
# ============================================================================

def test_seasonality_multi_select_or():
    """Verify multi-select seasonality filtering uses OR within group."""
    res_spring = get_company_grouped_prospects(seasonality="SPRING_PEAK")
    count_spring = len(res_spring)

    res_fall = get_company_grouped_prospects(seasonality="FALL_HARVEST")
    count_fall = len(res_fall)

    res_both = get_company_grouped_prospects(seasonality=["SPRING_PEAK", "FALL_HARVEST"])
    assert len(res_both) >= max(count_spring, count_fall)


# ============================================================================
# G. Cross-Filter Composition Matrix (AND across groups, OR within group)
# ============================================================================

def test_cross_filter_opportunity_and_equipment():
    """Verify Opportunity (Tier A or Tier B) AND Equipment (Flatbed) composition."""
    res = get_company_grouped_prospects(
        opportunity_tier=["TIER_A_PRIORITY", "TIER_B_WORTH_CALLING"],
        equipment="FLATBED",
    )
    assert len(res) > 0
    for c in res:
        assert c["opportunity_tier"] in ("TIER_A_PRIORITY", "TIER_B_WORTH_CALLING")


def test_cross_filter_opportunity_equipment_family():
    """Verify composite composition across Tier, Equipment, and Family."""
    res = get_company_grouped_prospects(
        opportunity_tier=["TIER_A_PRIORITY", "TIER_B_WORTH_CALLING"],
        equipment=["FLATBED", "STEP_DECK"],
        family="METALS_STEEL",
    )
    assert len(res) > 0
    for c in res:
        assert c["opportunity_tier"] in ("TIER_A_PRIORITY", "TIER_B_WORTH_CALLING")


# ============================================================================
# H. Search + Filter Composition Matrix
# ============================================================================

def test_search_composed_with_tier_filter():
    """Verify search query composed with opportunity tier filter."""
    res = get_company_grouped_prospects(
        search="Steel",
        opportunity_tier="TIER_A_PRIORITY",
    )
    assert len(res) > 0
    for c in res:
        assert c["opportunity_tier"] == "TIER_A_PRIORITY"
        assert "steel" in c["searchable_text"].lower()


# ============================================================================
# I. Sort + Filter Composition Matrix
# ============================================================================

def test_html_sort_and_filters_preservation():
    """Verify /prospects preserves sort selection with multi-select filters."""
    response = client.get("/prospects?tier=TIER_A_PRIORITY&equipment=FLATBED&sort=fac_desc")
    assert response.status_code == 200
    html = response.text
    assert 'value="fac_desc"' in html
    # Friction sort options removed from select
    assert 'value="friction_asc"' not in html
    assert 'value="friction_desc"' not in html


# ============================================================================
# J. Pagination + Filter Composition Matrix
# ============================================================================

def test_pagination_metadata_with_filters():
    """Verify pagination correctly calculates pages for filtered sets."""
    res = get_company_grouped_prospects(
        opportunity_tier="TIER_A_PRIORITY",
        page=1,
        page_size=10,
    )
    assert res["total_count"] == 19
    assert res["total_pages"] == 2
    assert len(res["items"]) == 10

    res_p2 = get_company_grouped_prospects(
        opportunity_tier="TIER_A_PRIORITY",
        page=2,
        page_size=10,
    )
    assert len(res_p2["items"]) == 9


# ============================================================================
# K. URL State Serialization & Query Param Parsing Matrix
# ============================================================================

def test_parse_filter_list_helper():
    """Verify _parse_filter_list handles lists, comma-separated strings, None, and empty."""
    assert _parse_filter_list(None) == []
    assert _parse_filter_list("") == []
    assert _parse_filter_list([]) == []
    assert _parse_filter_list(["A", "B"]) == ["A", "B"]
    assert _parse_filter_list("A,B") == ["A", "B"]
    assert _parse_filter_list(["A,B", "C"]) == ["A", "B", "C"]
    assert _parse_filter_list("  A ,  B  ") == ["A", "B"]


def test_api_companies_multi_select_query_params():
    """Verify /api/companies accepts repeated query params and CSV."""
    # Repeated params: ?tier=TIER_A_PRIORITY&tier=TIER_B_WORTH_CALLING
    resp = client.get("/api/companies?tier=TIER_A_PRIORITY&tier=TIER_B_WORTH_CALLING")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 975

    # CSV param: ?tier=TIER_A_PRIORITY,TIER_B_WORTH_CALLING
    resp_csv = client.get("/api/companies?tier=TIER_A_PRIORITY,TIER_B_WORTH_CALLING")
    assert resp_csv.status_code == 200
    data_csv = resp_csv.json()
    assert len(data_csv) == 975


# ============================================================================
# L. Dynamic Universe Truth (Zero Stale Hardcoded Counts)
# ============================================================================

def test_authoritative_universe_numbers():
    """Verify database truth is 1,032 companies, 1,120 facilities, 19/956/10/47/0."""
    meta = get_universe_metadata()
    assert meta["universe_companies"] == 1032
    assert meta["universe_facilities"] == 1120
    assert meta["opportunity_counts"]["TIER_A_PRIORITY"] == 19
    assert meta["opportunity_counts"]["TIER_B_WORTH_CALLING"] == 956
    assert meta["opportunity_counts"]["TIER_C_SECONDARY"] == 10
    assert meta["opportunity_counts"]["TIER_D_RESEARCH_NEEDED"] == 47
    assert meta["opportunity_counts"]["RESTRICTED"] == 0


def test_no_stale_counts_in_master_directory_html():
    """Verify Master Directory HTML does not contain stale 565 or 653 lead universe counts."""
    response = client.get("/prospects")
    assert response.status_code == 200
    html = response.text
    assert "1,032" in html or "1032" in html
    assert "1,120" in html or "1120" in html
    assert "565 Active" not in html
    assert "All Stages (565)" not in html


# ============================================================================
# M. Sidebar Shortcuts & CRM Workflow Routing Matrix
# ============================================================================

def test_crm_views_redirect_to_prospects_with_outreach_filter():
    """Verify /crm/* routes redirect with 302 to /prospects?outreach=..."""
    r_int = client.get("/crm/interested", follow_redirects=False)
    assert r_int.status_code == 302
    assert r_int.headers["location"] == "/prospects?outreach=INTERESTED"

    r_fu = client.get("/crm/follow-ups", follow_redirects=False)
    assert r_fu.status_code == 302
    assert r_fu.headers["location"] == "/prospects?outreach=FOLLOW_UP"

    r_na = client.get("/crm/no-answer", follow_redirects=False)
    assert r_na.status_code == 302
    assert r_na.headers["location"] == "/prospects?outreach=NO_ANSWER"

    r_ni = client.get("/crm/not-interested", follow_redirects=False)
    assert r_ni.status_code == 302
    assert r_ni.headers["location"] == "/prospects?outreach=NOT_INTERESTED"


def test_sidebar_highlighting_for_crm_routes():
    """Verify sidebar menu item is highlighted when accessing /prospects with outreach param."""
    r_int = client.get("/prospects?outreach=INTERESTED")
    assert r_int.status_code == 200
    assert 'active_nav == \'crm_interested\'' not in r_int.text  # rendered by Jinja
    assert 'class="sidebar-link active"' in r_int.text
    assert 'Interested' in r_int.text
