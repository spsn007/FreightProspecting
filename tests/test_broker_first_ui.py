"""
FreightProspecting V1 — Broker-First UI/UX Verification Tests
Validates:
1. Master directory full-universe metadata counts (565 companies, 653 facilities, 29/91/445 split).
2. Server-side search pushdown (single-char 'S', beyond-page-1 'Scott', 'Steel').
3. Broker-first card fields (best_phone, best_phone_clean, best_phone_label, best_email, broker_status_label, why_bullets).
4. HTML templates integration (endpoints /prospects and / render cleanly with metadata).
5. Dark mode CSS contrast tokens (active tab text #ffffff on #0284c7, hero-banner dark gradient).
"""

from pathlib import Path
import re
import pytest
from tests.authenticated_client import TestClient

from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.queries import (
    get_summary_counts,
    get_universe_metadata,
    get_company_grouped_prospects,
    get_prospects_list,
)
from src.backend.main import app

DB_PATH = get_db_path()
client = TestClient(app)


def test_universe_metadata_counts():
    """Verify universe metadata accurately captures full non-overlapping company and facility lifecycle pools."""
    meta = get_universe_metadata(db_path=DB_PATH)
    assert meta["universe_companies"] == 1032
    assert meta["universe_facilities"] == 1120

    # Company lifecycle breakdown
    comp_lc = meta["lifecycle_counts"]
    assert comp_lc["ALL"] == 1032
    assert comp_lc["SHORTLISTED"] == 29
    assert comp_lc["QUALIFIED"] == 956
    assert comp_lc["DISCOVERY"] == 47
    assert comp_lc["SHORTLISTED"] + comp_lc["QUALIFIED"] + comp_lc["DISCOVERY"] == 1032

    # Facility lifecycle breakdown
    fac_lc = meta["facility_lifecycle_counts"]
    assert fac_lc["ALL"] == 1120
    assert fac_lc["SHORTLISTED"] == 29
    assert fac_lc["QUALIFIED"] == 989
    assert fac_lc["DISCOVERY"] == 102
    assert fac_lc["SHORTLISTED"] + fac_lc["QUALIFIED"] + fac_lc["DISCOVERY"] == 1120


def test_paginated_company_grouped_prospects_metadata():
    """Verify get_company_grouped_prospects returns rich metadata dictionary alongside hydrated items."""
    res = get_company_grouped_prospects(lifecycle_stage="ALL", page=1, page_size=25, db_path=DB_PATH)
    assert isinstance(res, dict)
    assert len(res["items"]) == 25
    assert res["total_count"] == 1032
    assert "metadata" in res

    meta = res["metadata"]
    assert meta["total_companies"] == 1032
    assert meta["total_facilities"] == 1120
    assert meta["page"] == 1
    assert meta["page_size"] == 25
    assert meta["total_pages"] == 42
    assert meta["page_start"] == 1
    assert meta["page_end"] == 25
    assert meta["lifecycle_counts"]["SHORTLISTED"] == 29
    assert meta["lifecycle_counts"]["QUALIFIED"] == 956
    assert meta["lifecycle_counts"]["DISCOVERY"] == 47


def test_server_side_search_single_char():
    """Verify server-side single-char search 'S' matches across the full universe without pagination limitation."""
    res = get_company_grouped_prospects(search="S", page=1, page_size=25, db_path=DB_PATH)
    assert res["total_count"] > 25
    assert len(res["items"]) == 25
    assert res["metadata"]["total_companies"] == res["total_count"]


def test_server_side_search_beyond_page_one_scott():
    """Verify search finds Scott Steel (which is normally beyond page 1 alphabetically)."""
    res = get_company_grouped_prospects(search="Scott", page=1, page_size=25, db_path=DB_PATH)
    assert res["total_count"] >= 1
    brands = [item["operating_brand"] for item in res["items"]]
    assert any("Scott Steel" in b for b in brands)
    assert res["metadata"]["total_companies"] == res["total_count"]


def test_server_side_search_steel_universe_totals():
    """Verify search 'Steel' computes accurate matching companies and child facilities."""
    res = get_company_grouped_prospects(search="Steel", page=1, page_size=25, db_path=DB_PATH)
    assert res["total_count"] == 267
    assert res["metadata"]["total_companies"] == 267
    assert res["metadata"]["total_facilities"] == 306
    assert res["metadata"]["universe_companies"] == 1032
    assert res["metadata"]["universe_facilities"] == 1120


def test_broker_card_fields_shortlisted_sample():
    """Verify broker-first card attributes for Beasley Forest Products (Priority prospect due to verified outside carrier use) and Cole Hardwood (Secondary prospect due to private fleet)."""
    res = get_company_grouped_prospects(search="Beasley Forest Products", page=1, page_size=10, db_path=DB_PATH)
    item = next((i for i in res["items"] if "Beasley Forest Products" in i["operating_brand"]), None)
    assert item is not None

    assert item["broker_status_label"] == "Priority Prospect"
    assert item["opportunity_tier"] == "TIER_A_PRIORITY"
    assert "outside transportation capacity" in item["broker_status_desc"].lower()
    assert item["best_phone"] == "(912) 347-5930"
    assert item["best_phone_clean"] == "9123475930"
    assert "Direct: Mark Joiner" in item["best_phone_label"]
    assert item["best_location"] == "Hazlehurst, GA"
    assert item["primary_facility_id"] == 1

    bullets = item["broker_why_bullets"]
    assert len(bullets) >= 2
    assert any("Outside carrier use confirmed" in b for b in bullets)
    assert any("Mark Joiner" in b for b in bullets)

    # Verify a true Secondary Prospect: Cole Hardwood Inc.
    res_sec = get_company_grouped_prospects(search="Cole Hardwood", page=1, page_size=10, db_path=DB_PATH)
    sec_item = next((i for i in res_sec["items"] if "Cole Hardwood" in i["operating_brand"]), None)
    assert sec_item is not None
    assert sec_item["broker_status_label"] == "Secondary Prospect"
    assert sec_item["opportunity_tier"] == "TIER_C_SECONDARY"
    assert "Own trucks confirmed" in sec_item["broker_status_desc"]

    # Also verify a true Priority Prospect: Battle Lumber Company
    res_pri = get_company_grouped_prospects(search="Battle Lumber", page=1, page_size=10, db_path=DB_PATH)
    pri_item = next((i for i in res_pri["items"] if "Battle Lumber" in i["operating_brand"]), None)
    assert pri_item is not None
    assert pri_item["broker_status_label"] == "Priority Prospect"
    assert pri_item["opportunity_tier"] == "TIER_A_PRIORITY"
    assert "outside transportation capacity" in pri_item["broker_status_desc"].lower()
    assert any("Target FLATBED equipment fit" in b for b in pri_item["broker_why_bullets"])


def test_broker_card_fields_discovery_sample():
    """Verify broker-first card attributes for WMG Technologies (Discovery prospect)."""
    res = get_company_grouped_prospects(search="WMG Technologies", page=1, page_size=10, db_path=DB_PATH)
    item = next((i for i in res["items"] if "WMG Technologies" in i["operating_brand"]), None)
    assert item is not None

    assert item["broker_status_label"] == "Needs More Research"
    assert item["opportunity_tier"] == "TIER_D_RESEARCH_NEEDED"
    assert item["best_phone"] == "(519) 972-9032"
    assert item["best_phone_clean"] == "5199729032"
    assert len(item["discovery_what_we_know"]) >= 2
    assert "Windsor, ON" in item["discovery_what_we_know"][0]
    assert item["discovery_still_checking"] == "Direct shipping contact still needs confirmation"


def test_html_endpoints_render_metadata():
    """Verify /prospects returns 200 and embeds metadata JSON and broker UI elements."""
    response = client.get("/prospects")
    assert response.status_code == 200
    html = response.text

    assert '<script id="metadata-data" type="application/json">' in html
    assert "master-search-input" in html
    assert "applySearch()" in html
    assert "company-card-grid-broker" in html
    assert "broker-phone-link" in html


def test_html_cockpit_renders():
    """Verify Cockpit root endpoint / canonically 302 redirects to Master Directory."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/prospects"
    # When following redirects, lands on Master Directory
    res_followed = client.get("/")
    assert res_followed.status_code == 200
    assert "Master Directory" in res_followed.text


def test_dark_mode_css_tokens():
    """Verify CSS files contain required dark mode tokens for WCAG-compliant contrast."""
    app_css = Path("src/frontend/static/css/app.css").read_text(encoding="utf-8")
    assert '[data-theme="dark"] .hero-banner' in app_css
    assert '[data-theme="dark"] .tab-btn.active' in app_css
    assert "background-color: #0284c7" in app_css
    assert "color: #ffffff !important" in app_css

    comp_css = Path("src/frontend/static/css/components.css").read_text(encoding="utf-8")
    assert ".company-card-grid-broker" in comp_css
    assert ".broker-phone-card" in comp_css
    assert ".search-clear-btn" in comp_css


def test_regression_template_renders_without_metadata_or_none():
    """
    REGRESSION AUDIT:
    Verifies that prospects.html renders safely even if 'metadata' is completely
    omitted from context, or set to None, preventing 'TypeError: Object of type Undefined is not JSON serializable'.
    """
    from src.backend.main import templates

    tmpl = templates.get_template("prospects.html")

    # 1. Test with completely omitted metadata
    ctx_without_meta = {
        "request": None,
        "counts": {},
        "prospects": [],
        "company_groups": [],
        "pagination": {"page": 1, "page_size": 25, "total_items": 0, "total_pages": 1},
        "filters": {},
        "active_nav": "prospects",
    }
    rendered_1 = tmpl.render(ctx_without_meta)
    assert '<script id="metadata-data" type="application/json">{}</script>' in rendered_1

    # 2. Test with metadata=None
    ctx_with_none_meta = dict(ctx_without_meta)
    ctx_with_none_meta["metadata"] = None
    rendered_2 = tmpl.render(ctx_with_none_meta)
    assert '<script id="metadata-data" type="application/json">{}</script>' in rendered_2


def test_regression_card_null_field_tolerance():
    """
    Verifies that company card template handles missing phone, email, contacts,
    commodities, and bullets gracefully without crashing or throwing exceptions.
    """
    from src.backend.main import templates

    tmpl = templates.get_template("prospects.html")
    synthetic_company = {
        "company_id": 99999,
        "operating_brand": "Null Field Test Corp",
        "legal_name": None,
        "website": None,
        "clean_domain": None,
        "lifecycle_stage": "DISCOVERY",
        "outreach_status": None,
        "is_viewed": 0,
        "attempt_count": 0,
        "facility_count": 1,
        "best_phone": None,
        "best_phone_clean": None,
        "best_phone_label": None,
        "best_email": None,
        "best_location": None,
        "primary_facility_id": None,
        "broker_status_label": "Still Being Researched",
        "broker_status_desc": "Basic operational entity identified.",
        "broker_why_bullets": [],
        "discovery_what_we_know": [],
        "discovery_still_checking": None,
        "facilities": [
            {
                "facility_id": 99999,
                "facility_name": "Test Plant",
                "city": None,
                "state_province": None,
                "phone_number": None,
                "commodities": [],
                "equipment_types": [],
                "contacts": [],
            }
        ],
    }

    ctx = {
        "request": None,
        "counts": {},
        "prospects": [],
        "company_groups": [synthetic_company],
        "pagination": {"page": 1, "page_size": 25, "total_items": 1, "total_pages": 1},
        "metadata": {"total_companies": 1, "total_facilities": 1},
        "filters": {},
        "active_nav": "prospects",
    }
    rendered = tmpl.render(ctx)
    assert "Null Field Test Corp" in rendered


def test_live_prospects_routes_and_filters():
    """Verify live HTTP 200 responses across all tabs, views, search queries, and pagination."""
    endpoints = [
        "/prospects",
        "/prospects?stage=QUALIFIED",
        "/prospects?stage=SHORTLISTED",
        "/prospects?stage=DISCOVERY",
        "/prospects?q=S",
        "/prospects?q=Steel",
        "/prospects?page=2",
        "/prospects?page=23",
    ]
    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 200, f"Endpoint {ep} failed with {res.status_code}"
        assert "Master Directory" in res.text


def test_cockpit_redesigned_broker_card_elements():
    """Verify Master Directory endpoint /prospects contains Phase 2 broker-first layout elements."""
    response = client.get("/prospects")
    assert response.status_code == 200
    html = response.text

    # Priority Prospect badge & card structure
    assert "Priority Prospect" in html
    assert "company-card-grid-broker" in html
    assert "broker-phone-card" in html
    assert "broker-phone-link" in html
    assert "btn-call" in html
    assert "Log Call" in html
    assert "openLogCall" in html

    # Broker insights & action guidance
    assert "Why Shortlisted" in html
    assert "Review Prospect" in html


def test_prospect_detail_hero_briefing_and_glance_grid():
    """Verify redesigned Prospect Detail contains top briefing, 2-col insights, glance grid, readiness, and technical accordion."""
    # Test with Beasley Forest Products (facility 1) and AmeriSteel (facility 23)
    for fid in [1, 23]:
        response = client.get(f"/prospects/{fid}")
        assert response.status_code == 200
        html = response.text

        # Top briefing card & freight fit
        assert "prospect-hero-briefing" in html
        assert "briefing-do-box" in html
        assert "Likely Freight Fit" in html

        # 2-column broker insights
        assert "broker-insights-grid" in html
        assert "insights-col-why" in html
        assert "insights-col-unconfirmed" in html
        assert "Why it may be worth contacting" in html
        assert "What is still not confirmed" in html

        # At a glance operational facts grid
        assert "broker-glance-grid" in html
        assert "glance-card" in html
        assert ("Goods &amp; Products" in html) or ("Goods & Products" in html)
        assert "Likely Equipment" in html

        # Simplified qualification readiness
        assert "readiness-simple-container" in html
        assert "readiness-simple-row" in html

        # Collapsible technical research section
        assert "tech-research-card" in html
        assert "tech-accordion-btn" in html
        assert ("Research &amp; Evidence Ledger" in html) or ("Research & Evidence Ledger" in html)


def test_dark_mode_tokens_phase2():
    """Verify Phase 2 dark mode tokens in CSS and settings template consistency."""
    comp_css = Path("src/frontend/static/css/components.css").read_text(encoding="utf-8")
    assert '[data-theme="dark"] .prospect-hero-briefing' in comp_css
    assert '[data-theme="dark"] .briefing-do-box' in comp_css
    assert '[data-theme="dark"] .insights-col' in comp_css
    assert '[data-theme="dark"] .insights-col-why' in comp_css
    assert '[data-theme="dark"] .glance-card' in comp_css
    assert '[data-theme="dark"] .readiness-simple-container' in comp_css
    assert '[data-theme="dark"] .tech-research-card' in comp_css
    assert '[data-theme="dark"] .disposition-pill.selected-interested' in comp_css

    team_css = Path("src/frontend/static/css/team.css").read_text(encoding="utf-8")
    assert "var(--color-surface-inset)" in team_css
    assert ".settings-card" in team_css

    settings_html = Path("src/frontend/templates/settings.html").read_text(encoding="utf-8")
    assert "#f8fafc" not in settings_html
    assert "toggleTheme()" in settings_html or "data-theme-toggle" in settings_html


def test_search_relevance_ranking():
    """Verify search relevance prioritizes exact and prefix matches over secondary fields."""
    # Query 'S': top results must all begin with 'S'
    res_s = get_company_grouped_prospects(search="S", page=1, page_size=10, db_path=DB_PATH)
    assert res_s["total_count"] > 0
    top_brands_s = [item["operating_brand"] for item in res_s["items"][:5]]
    for b in top_brands_s:
        assert b.upper().startswith("S"), f"Expected brand starting with 'S', got {b}"

    # Query 'Ameri': top results must match Ameri brands
    res_ameri = get_company_grouped_prospects(search="Ameri", page=1, page_size=5, db_path=DB_PATH)
    assert res_ameri["total_count"] >= 1
    assert any("AmeriSteel" in item["operating_brand"] for item in res_ameri["items"])

    # Query 'Battle': #1 result must be Battle Lumber Company
    res_battle = get_company_grouped_prospects(search="Battle", page=1, page_size=5, db_path=DB_PATH)
    assert res_battle["total_count"] >= 1
    assert "Battle Lumber" in res_battle["items"][0]["operating_brand"]

    # Query 'Scott': #1 result must be Scott Steel
    res_scott = get_company_grouped_prospects(search="Scott", page=1, page_size=5, db_path=DB_PATH)
    assert res_scott["total_count"] >= 1
    assert res_scott["items"][0]["operating_brand"] == "Scott Steel"

    # Query 'St': top results must start with 'St'
    res_st = get_company_grouped_prospects(search="St", page=1, page_size=5, db_path=DB_PATH)
    for item in res_st["items"]:
        assert item["operating_brand"].upper().startswith("ST"), f"Expected brand starting with 'St', got {item['operating_brand']}"

    # Query 'Steel': brand prefix matches outrank secondary matches
    res_steel = get_company_grouped_prospects(search="Steel", page=1, page_size=5, db_path=DB_PATH)
    assert res_steel["total_count"] == 267
    for item in res_steel["items"]:
        assert item["operating_brand"].upper().startswith("STEEL"), f"Expected top brand to start with 'Steel', got {item['operating_brand']}"


def test_card_structural_symmetry_and_tokens():
    """Verify structural grid dimensions, column classes, and alignment hardening."""
    comp_css = Path("src/frontend/static/css/components.css").read_text(encoding="utf-8")
    assert "minmax(0, 1fr) 280px 210px" in comp_css
    assert ".broker-card-col-info" in comp_css
    assert ".broker-card-col-contact" in comp_css
    assert "text-overflow: ellipsis" in comp_css
    assert "width: 100% !important" in comp_css

    prospects_html = Path("src/frontend/templates/prospects.html").read_text(encoding="utf-8")
    assert "broker-card-col-info" in prospects_html
    assert "broker-card-col-contact" in prospects_html
    assert "Sort: Best Match (Relevance)" in prospects_html
    assert "found)</span>" in prospects_html

    index_html = Path("src/frontend/templates/index.html").read_text(encoding="utf-8")
    assert "broker-card-col-info" in index_html
    assert "broker-card-col-contact" in index_html
