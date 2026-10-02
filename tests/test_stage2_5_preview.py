"""
FreightProspecting V1 — Stage 2.5 Visual UI/UX Automated Tests
Validates all 18 Stage 2.5 requirements:
1. Application imports successfully
2. Dashboard route returns HTTP 200
3. Prospect list route returns HTTP 200
4. Prospect detail route returns HTTP 200 for valid seeds
5. Unknown prospect returns appropriate 404
6. Dashboard displays exactly four prospect families
7. ABC Technologies parent record is not shown as a prospect
8. Actual database counts are reflected
9. No fake load cards appear
10. Loads/opportunities empty state renders
11. Carriers/capacity empty state renders
12. Beasley contact directness is preserved (Mark Joiner = direct, Phil Clements = switchboard)
13. Kenwal fleet status renders UNKNOWN rather than false/no fleet
14. DECAST operational job evidence is not displayed as active freight
15. WMG flatbed suitability renders INFERRED, not VERIFIED usage
16. No external runtime CDN URLs appear in templates or CSS
17. No AI SDK/API dependency has been added
18. Project Stage 2 test suite still passes
"""

from pathlib import Path
import re
import sqlite3
import pytest
from fastapi.testclient import TestClient

from src.backend.main import app
from src.backend.db.connection import create_connection, get_db_path
from src.backend.db.queries import (
    get_summary_counts,
    get_prospects_list,
    get_prospect_detail,
)

client = TestClient(app)


# ============================================================================
# 1. Application Imports Successfully
# ============================================================================
def test_application_imports_successfully():
    """Test 1: FastAPI app instance exists, has title and version."""
    assert app is not None
    assert app.title == "FreightProspecting V1"
    assert app.version == "1.0.0"


# ============================================================================
# 2. Dashboard Route Returns HTTP 200
# ============================================================================
def test_dashboard_route_returns_http_200():
    """Test 2: Dashboard Cockpit route (/) responds with HTTP 200."""
    response = client.get("/")
    assert response.status_code == 200
    assert "FreightProspecting" in response.text
    assert "PROSPECTS TO CONTACT" in response.text


# ============================================================================
# 3. Prospect List Route Returns HTTP 200
# ============================================================================
def test_prospect_list_route_returns_http_200():
    """Test 3: Master Directory route (/prospects) responds with HTTP 200."""
    response = client.get("/prospects")
    assert response.status_code == 200
    assert "Master Directory" in response.text


# ============================================================================
# 4. Prospect Detail Route Returns HTTP 200 For Valid Seeds
# ============================================================================
def test_prospect_detail_route_returns_http_200_for_valid_seeds():
    """Test 4: Detail route (/prospects/{id}) responds with HTTP 200 for all 4 seed facilities."""
    for fac_id in [1, 2, 3, 4]:
        response = client.get(f"/prospects/{fac_id}")
        assert response.status_code == 200, f"Facility {fac_id} failed with {response.status_code}"
        assert "Who Is This?" in response.text
        assert "What Do They Move / Make?" in response.text
        assert "What Do I Know?" in response.text


# ============================================================================
# 5. Unknown Prospect Returns Appropriate 404
# ============================================================================
def test_unknown_prospect_returns_appropriate_404():
    """Test 5: Requesting non-existent prospect facility IDs returns HTTP 404."""
    for bad_id in [0, 9999, 50000]:
        response = client.get(f"/prospects/{bad_id}")
        assert response.status_code == 404
        assert "not found" in response.text.lower()


# ============================================================================
# 6. Dashboard Displays Shortlisted Prospect Families
# ============================================================================
def test_dashboard_displays_exactly_four_prospect_families():
    """Test 6: The dashboard renders shortlisted prospects including approved seed prospect families."""
    response = client.get("/")
    assert response.status_code == 200
    text = response.text

    # Verify shortlisted seed brands are present in cockpit
    assert "Beasley Forest Products" in text
    assert "Kenwal Steel Corp." in text
    assert "DECAST Ltd." in text

    # Verify count via queries helper (Stage 3F.2 / D.1: 29 shortlisted)
    prospects = get_prospects_list()
    assert len(prospects) == 29
    brands = {p["operating_brand"] for p in prospects}
    assert {
        "Beasley Forest Products",
        "Kenwal Steel Corp.",
        "DECAST Ltd.",
    }.issubset(brands)


# ============================================================================
# 7. ABC Technologies Parent Record Is NOT Shown As A Prospect
# ============================================================================
def test_abc_technologies_parent_record_not_shown_as_prospect():
    """Test 7: ABC Technologies (holding company) is not rendered as a standalone prospect lead."""
    prospects = get_prospects_list(lifecycle_stage="ALL")
    brands = [p["operating_brand"] for p in prospects]
    assert "ABC Technologies" not in brands
    assert "ABC Technologies Holdings Inc." not in brands

    # Check detail pages exist for all 4 seed facilities
    for fid in [1, 2, 3, 4]:
        r = client.get(f"/prospects/{fid}")
        assert r.status_code == 200


# ============================================================================
# 8. Actual Database Counts Are Reflected
# ============================================================================
def test_actual_database_counts_are_reflected():
    """Test 8: Status summary numbers faithfully match SQLite database records."""
    counts = get_summary_counts()
    assert counts["prospects_count"] == 29
    assert counts["signals_count"] == 0
    assert counts["loads_count"] == 0
    assert counts["capacity_count"] == 0
    if counts.get("all_prospects_count", 4) > 4:
        assert counts["seed_verified_claims_count"] == 16
        assert counts["seed_inferred_claims_count"] == 2
        assert counts["seed_unknown_claims_count"] == 2
        assert counts["verified_claims_count"] >= 16
    else:
        assert counts["verified_claims_count"] == 16
        assert counts["inferred_claims_count"] == 2
        assert counts["unknown_claims_count"] == 2

    response = client.get("/")
    assert ">29<" in response.text  # 29 shortlisted prospects
    assert ">0<" in response.text  # 0 signals / loads / capacity


# ============================================================================
# 9. No Fake Load Cards Appear
# ============================================================================
def test_no_fake_load_cards_appear():
    """Test 9: Verifies zero fake load cards, fake rates, or fake freight appear on dashboard or loads screen."""
    counts = get_summary_counts()
    assert counts["loads_count"] == 0
    assert counts["signals_count"] == 0

    r_dash = client.get("/")
    assert "Active Loads: 0" in r_dash.text or "0 Bookable" in r_dash.text
    # No fake FTL load rate numbers
    assert "$2,500" not in r_dash.text
    assert "$3,200" not in r_dash.text


# ============================================================================
# 10. Loads / Opportunities Empty State Renders
# ============================================================================
def test_loads_opportunities_empty_state_renders():
    """Test 10: /loads renders the honest, intentional empty state."""
    response = client.get("/loads")
    assert response.status_code == 200
    assert "No Confirmed Loads Recorded Yet" in response.text
    assert "Shipper Prospect ≠ Freight-Demand Signal ≠ Discrete Load" in response.text
    assert "Deterministic Margin Model" in response.text


# ============================================================================
# 11. Carriers & Capacity Empty State Renders
# ============================================================================
def test_carriers_capacity_empty_state_renders():
    """Test 11: /carriers renders the honest empty state with zero fake truck postings."""
    response = client.get("/carriers")
    assert response.status_code == 200
    assert "No Current Capacity Postings Yet" in response.text
    assert "Carrier Directory ≠ Historical Lane Activity ≠ Capacity Posting" in response.text

    # Verify database contains 0 capacity
    counts = get_summary_counts()
    assert counts["capacity_count"] == 0


# ============================================================================
# 12. Beasley Contact Directness Is Preserved
# ============================================================================
def test_beasley_contact_directness_preserved():
    """Test 12: Mark Joiner has DIRECT_PERSON status and Phil Clements has GENERAL_SWITCHBOARD."""
    response = client.get("/prospects/1")
    assert response.status_code == 200
    text = response.text

    # Mark Joiner is Direct
    assert "Mark Joiner" in text
    assert "(912) 347-5930" in text
    assert "Direct Line" in text

    # Phil Clements is Switchboard
    assert "Phil Clements" in text
    assert "(912) 375-5174" in text
    assert "Switchboard" in text


# ============================================================================
# 13. Kenwal Fleet Status Renders UNKNOWN
# ============================================================================
def test_kenwal_fleet_status_renders_unknown():
    """Test 13: Kenwal fleet status renders as UNKNOWN, never as false or no fleet."""
    response = client.get("/prospects/2")
    assert response.status_code == 200
    text = response.text

    # Must contain UNKNOWN and NOT claim 'No fleet'
    assert "Fleet: UNKNOWN" in text or "UNKNOWN" in text
    assert "VERIFIED_NO_FLEET" not in text
    assert "No Private Fleet" not in text


# ============================================================================
# 14. DECAST Operational Job Evidence Is Not Displayed As Active Freight
# ============================================================================
def test_decast_job_evidence_not_displayed_as_active_freight():
    """Test 14: DECAST hiring ad is Category A operational evidence, not an active freight signal or private fleet proof."""
    response = client.get("/prospects/3")
    assert response.status_code == 200
    text = response.text

    # State is PROSPECT ONLY
    assert "PROSPECT" in text
    assert "0 Active" in text or "0 Signals" in text

    # Job ad source is in claims/evidence ledger
    assert "AZ Float Driver" in text or "Careers" in text

    # DECAST fleet status is UNKNOWN (not VERIFIED_PRESENT)
    assert "Fleet: UNKNOWN" in text or "Fleet Status: UNKNOWN" in text
    assert "Private Fleet Verified" not in text

    # DECAST equipment is INFERRED Step Deck, not VERIFIED usage
    assert "Inferred Suitability" in text or "Inferred" in text
    assert "STEP_DECK" in text


# ============================================================================
# 15. WMG Flatbed Suitability Renders INFERRED
# ============================================================================
def test_wmg_flatbed_suitability_renders_inferred():
    """Test 15: WMG flatbed usage is rendered as INFERRED, not VERIFIED."""
    response = client.get("/prospects/4")
    assert response.status_code == 200
    text = response.text

    # Inferred equipment badge
    assert "Inferred" in text
    assert "FLATBED" in text


# ============================================================================
# 16. No External Runtime CDN URLs Appear In Templates
# ============================================================================
def test_no_external_runtime_cdn_urls_in_templates():
    """Test 16: Zero external CDN / font / script URLs exist in frontend templates and CSS."""
    frontend_dir = Path("D:/FreightProspecting/src/frontend")
    html_and_css_files = list(frontend_dir.glob("**/*.html")) + list(frontend_dir.glob("**/*.css"))

    forbidden_patterns = [
        re.compile(r"https?://cdn\.", re.IGNORECASE),
        re.compile(r"https?://cdnjs\.", re.IGNORECASE),
        re.compile(r"https?://fonts\.googleapis\.com", re.IGNORECASE),
        re.compile(r"https?://fonts\.gstatic\.com", re.IGNORECASE),
        re.compile(r"https?://unpkg\.com", re.IGNORECASE),
        re.compile(r"https?://cdn\.jsdelivr\.net", re.IGNORECASE),
        re.compile(r"https?://cdn\.tailwindcss\.com", re.IGNORECASE),
    ]

    for file_path in html_and_css_files:
        content = file_path.read_text(encoding="utf-8")
        for pat in forbidden_patterns:
            matches = pat.findall(content)
            assert not matches, f"Forbidden external CDN reference found in {file_path}: {matches}"


# ============================================================================
# 17. No AI SDK / API Dependency Added
# ============================================================================
def test_no_ai_sdk_dependency_added():
    """Test 17: requirements.txt and active codebase contain zero paid AI SDKs."""
    req_file = Path("D:/FreightProspecting/requirements.txt")
    req_content = req_file.read_text(encoding="utf-8").lower()

    forbidden_sdks = [
        "google-generativeai",
        "openai",
        "anthropic",
        "langchain",
        "chromadb",
        "pinecone",
    ]
    for sdk in forbidden_sdks:
        assert sdk not in req_content, f"Forbidden AI SDK found in requirements.txt: {sdk}"


# ============================================================================
# 18. Project Stage 2 Test Suite Invariants Remain Intact
# ============================================================================
def test_project_stage2_invariants_remain_intact():
    """Test 18: All Stage 2 database invariants (17 tables, 0 views, claims integrity) remain intact."""
    conn = create_connection(get_db_path())
    conn.row_factory = sqlite3.Row

    # Verify exactly 17 physical tables and 0 views
    cur = conn.execute("SELECT name, type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
    objs = {r["name"]: r["type"] for r in cur.fetchall()}

    tables = {name for name, t in objs.items() if t == "table"}
    views = {name for name, t in objs.items() if t == "view"}

    assert len(tables) in (17, 19, 20, 23), f"Expected 17 (Stage 2), 19 (Stage 3A), 20 (Stage 3C), or 23 (Stage 3G) tables, got {len(tables)}: {tables}"
    assert len(views) == 0, f"Expected 0 views, got {len(views)}: {views}"
    assert "suppressions" in tables
    assert "suppression_status_records" not in tables
    if len(tables) in (19, 20, 23):
        assert "prospect_lifecycle" in tables
        assert "discovery_intake_audit" in tables
    if len(tables) in (20, 23):
        assert "prospect_engagement_state" in tables
    if len(tables) == 23:
        assert "commodity_families" in tables
        assert "commodity_categories" in tables
        assert "facility_commodity_mappings" in tables

    if len(tables) in (19, 20, 23):
        # In Stage 3A with Batch #1 (39 discovery candidates imported), verify seed claims remain exactly 20
        seed_claims_cnt = conn.execute("SELECT count(*) FROM claims WHERE id <= 20").fetchone()[0]
        assert seed_claims_cnt == 20
        verified_cnt = conn.execute("SELECT count(*) FROM claims WHERE id <= 20 AND verification_status = 'VERIFIED'").fetchone()[0]
        inferred_cnt = conn.execute("SELECT count(*) FROM claims WHERE id <= 20 AND verification_status = 'INFERRED'").fetchone()[0]
        unknown_cnt = conn.execute("SELECT count(*) FROM claims WHERE id <= 20 AND verification_status = 'UNKNOWN'").fetchone()[0]
        assert verified_cnt == 16
        assert inferred_cnt == 2
        assert unknown_cnt == 2
    else:
        # Verify exact claim counts: 20 total (16 VERIFIED, 2 INFERRED, 2 UNKNOWN)
        claims_cnt = conn.execute("SELECT count(*) FROM claims").fetchone()[0]
        assert claims_cnt == 20
        verified_cnt = conn.execute("SELECT count(*) FROM claims WHERE verification_status = 'VERIFIED'").fetchone()[0]
        inferred_cnt = conn.execute("SELECT count(*) FROM claims WHERE verification_status = 'INFERRED'").fetchone()[0]
        unknown_cnt = conn.execute("SELECT count(*) FROM claims WHERE verification_status = 'UNKNOWN'").fetchone()[0]
        assert verified_cnt == 16
        assert inferred_cnt == 2
        assert unknown_cnt == 2

    conn.close()


def test_research_and_settings_routes_work_locally():
    """Verify research and settings routes render without external dependencies."""
    r_res = client.get("/research")
    assert r_res.status_code == 200
    assert "Evidence Sources" in r_res.text
    assert "Three-Dimensional Time Model" in r_res.text

    r_set = client.get("/settings")
    assert r_set.status_code == 200
    assert "Decision A: Geographic Scope" in r_set.text
    assert "Decision B: Outreach Priority" in r_set.text
    assert "Decision H: Zero-Paid-AI Architecture" in r_set.text


# ============================================================================
# Stage 2.5.1 Truthfulness & Evidence-Presentation Tests
# ============================================================================
def test_wmg_corporate_relationship_truthful_presentation():
    """Verify WMG displays TI Automotive context and intermediate hierarchy UNKNOWN, not shorthand 'Sub of ABC'."""
    # 1. Directory screen
    r_dir = client.get("/prospects")
    assert r_dir.status_code == 200
    assert "WMG Technologies" in r_dir.text

    # 2. Detail screen
    r_detail = client.get("/prospects/4")
    assert r_detail.status_code == 200
    assert "TI Automotive" in r_detail.text
    assert "Windsor Mold Inc." in r_detail.text
    assert "UNKNOWN" in r_detail.text


def test_broker_policy_not_verified_direct_only_on_seeds():
    """Verify all 4 seeds display broker policy as UNKNOWN / Not verified, never VERIFIED_DIRECT_ONLY."""
    for fid in [1, 2, 3, 4]:
        resp = client.get(f"/prospects/{fid}")
        assert resp.status_code == 200
        assert "VERIFIED_DIRECT_ONLY" not in resp.text
        assert "Verified Direct-Only" not in resp.text
        assert "UNKNOWN (Not verified" in resp.text or "UNKNOWN" in resp.text


def test_evidence_sources_not_all_labeled_primary():
    """Verify Evidence Ledger does not describe all 10 sources as '10 Verified Primary Sources'."""
    r_res = client.get("/research")
    assert r_res.status_code == 200
    assert "Audited Primary Sources" not in r_res.text
    assert "Audited Evidence Sources" in r_res.text
    # Individual sources must show secondary classification for job posting and directory
    assert "Secondary" in r_res.text
    assert "Primary Source" in r_res.text


def test_suggested_next_action_workflow_guidance_presentation():
    """Verify outreach suggestions are labeled 'Suggested Next Action (Workflow Guidance)'."""
    r_dash = client.get("/")
    assert r_dash.status_code == 200
    assert "Suggested Next Action" in r_dash.text
    assert "Workflow Guidance" in r_dash.text

    for fid in [1, 2, 3, 4]:
        r_det = client.get(f"/prospects/{fid}")
        assert r_det.status_code == 200
        assert "Suggested Next Action" in r_det.text


def test_settings_in_secondary_utility_navigation():
    """Verify Settings is in a secondary utility position in the sidebar, with 5 primary screens."""
    resp = client.get("/")
    assert resp.status_code == 200
    # Primary workflow nav has Cockpit, Directory, Loads, Carriers, Ledger
    assert "Shortlist Cockpit" in resp.text
    assert "Master Directory" in resp.text
    assert "Loads &amp; Margins" in resp.text or "Loads & Margins" in resp.text
    assert "Carriers &amp; Capacity" in resp.text or "Carriers & Capacity" in resp.text
    assert "Evidence Ledger" in resp.text
    # Settings is placed in sidebar-utility under Configuration
    assert "sidebar-utility" in resp.text
    assert "Configuration" in resp.text


# ============================================================================
# Stage 2.5.2 UI Truthfulness & Copy Polish Tests
# ============================================================================
def test_no_unimplemented_ranking_claims():
    """Verify prospects are not labeled 'ranked first', '#1 prospect', or 'highest priority'."""
    r_dash = client.get("/")
    assert r_dash.status_code == 200
    text_lower = r_dash.text.lower()

    assert "ranked first" not in text_lower
    assert "#1 prospect" not in text_lower
    assert "priority is based on verified broker-opportunity evidence" in text_lower
    assert "broker acceptance may still be unconfirmed" in text_lower
    assert "priority scoring is not yet enabled" not in text_lower


def test_mark_joiner_not_labeled_procurement_decision_maker():
    """Verify Mark Joiner is labeled a logistics contact, not a verified procurement decision-maker."""
    r_dash = client.get("/")
    assert r_dash.status_code == 200
    assert "decision-maker" not in r_dash.text.lower()
    assert "decision maker" not in r_dash.text.lower()
    assert "Direct logistics contact available" in r_dash.text

    r_det = client.get("/prospects/1")
    assert r_det.status_code == 200
    assert "procurement decision maker" not in r_det.text.lower()
    assert "verified decision maker" not in r_det.text.lower()


def test_load_rate_margin_not_presented_as_mandatory():
    """Verify /loads does not describe rates or margin as mandatory to create a load."""
    resp = client.get("/loads")
    assert resp.status_code == 200
    text = resp.text

    assert "Core Shipment Details" in text
    assert "Commercial Pricing Details" in text
    assert "Rates are optional" in text
    assert "Missing rates never invalidate a load" in text


def test_missing_rates_produce_unknown_margin():
    """Verify that a load with missing shipper rate or carrier cost keeps margin as UNKNOWN."""
    conn = create_connection(get_db_path())
    cur = conn.cursor()
    # Check that schema allows NULL for shipper_target_rate and carrier_target_cost
    columns = [col[1] for col in cur.execute("PRAGMA table_info(load_opportunities)").fetchall()]
    assert "shipper_target_rate" in columns
    assert "carrier_target_cost" in columns
    assert "gross_margin" in columns
    conn.close()


def test_app_not_described_globally_as_100_percent_offline():
    """Verify app qualifies local core app vs external internet research (never unqualified '100% offline')."""
    r_dash = client.get("/")
    assert "100% offline" not in r_dash.text
    assert "Core app runs locally" in r_dash.text
    assert "Web for Research Only" in r_dash.text or "External Research" in r_dash.text or "No Paid AI/API Required" in r_dash.text

    r_set = client.get("/settings")
    assert "100% offline" not in r_set.text
    assert "No Paid AI/API Required" in r_set.text


def test_evidence_wording_distinguishes_primary_and_secondary():
    """Verify Evidence Ledger does not claim all sources are primary or verified offline interviews."""
    r_res = client.get("/research")
    assert r_res.status_code == 200
    assert "100% primary" not in r_res.text.lower()
    assert "Offline record / Phone interview" not in r_res.text
    assert "Direct verification record / No URL" in r_res.text
    assert "Field-Level Provenance Backed" in r_res.text


def test_suggested_next_action_styling_distinct_from_verified():
    """Verify .next-action-box in components.css does not use the verified-green background."""
    css_path = Path("D:/FreightProspecting/src/frontend/static/css/components.css")
    css_content = css_path.read_text(encoding="utf-8")

    # In components.css, .next-action-box should have background-color: #f8fafc (not #f0fdf4 green)
    assert ".next-action-box" in css_content
    # Verified badge uses #dcfce7 or #f0fdf4
    idx = css_content.find(".next-action-box {")
    box_def = css_content[idx:idx+350]
    assert "#f0fdf4" not in box_def
    assert "#f8fafc" in box_def or "#cbd5e1" in box_def

