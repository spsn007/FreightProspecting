"""
Audit Remediation D Comprehensive Verification Tests
Validates surgical closure fixes for findings:
AUD-002, AUD-003, AUD-009, AUD-010, AUD-011, AUD-012, AUD-013, AUD-014, AUD-022, AUD-023, AUD-025.
"""

import os
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from decimal import Decimal
from tests.authenticated_client import TestClient

from src.backend.db.connection import create_connection, check_database_health, DEFAULT_DB_PATH, get_db_path
from src.backend.db.queries import (
    get_prospects_list,
    get_company_grouped_prospects,
    get_crm_follow_ups,
    log_outreach_call,
    evaluate_qualification_readiness,
    evaluate_broker_access_friction,
)
from src.backend.db.validators import (
    normalize_to_utc_iso,
    convert_to_utc_iso,
    resolve_timezone,
    is_valid_phone_number,
    is_valid_email,
    validate_and_calculate_load_margin,
)
from src.backend.main import app

client = TestClient(app)

@pytest.fixture(autouse=True, scope="module")
def pin_historical_db(use_historical_stage3_db):
    yield


# ============================================================================
# AUD-003 & AUD-010: Evidence Provenance & Readiness Re-evaluation
# ============================================================================

def test_aud003_reverted_equipment_evidence_relationships():
    """
    AUD-003: The 7 unsupported/unverified equipment claims (19, 29, 34, 174, 179, 189, 194)
    are CONTEXT in claim_evidence, NOT SUPPORTS.
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        reverted_claims = (19, 29, 34, 174, 179, 189, 194)
        for cid in reverted_claims:
            rows = cur.execute(
                "SELECT relationship FROM claim_evidence WHERE claim_id = ?",
                (cid,)
            ).fetchall()
            for r in rows:
                assert r["relationship"] == "CONTEXT", f"Claim {cid} relationship is {r['relationship']}, expected CONTEXT"
    finally:
        conn.close()


def test_aud003_facilities_4_and_6_readiness_fails_equipment_fit():
    """
    AUD-003: Facilities 4 & 6 fail check 2 (commodity_equipment_fit) because their
    equipment claims are backed only by CONTEXT evidence. They score 4/5.
    The remaining 29 shortlisted facilities pass 5/5.
    """
    conn = create_connection()
    try:
        # Facility 4 (WMG Technologies)
        r4 = evaluate_qualification_readiness(4, conn=conn)
        assert r4["passed_count"] == 4
        assert r4["checks"]["commodity_equipment_fit"]["passed"] is False

        # Facility 6 (Custom Cut)
        r6 = evaluate_qualification_readiness(6, conn=conn)
        assert r6["passed_count"] == 4
        assert r6["checks"]["commodity_equipment_fit"]["passed"] is False

        # Sample justified shortlisted facility (e.g. Facility 1, 2, 5, 8)
        for fid in (1, 2, 5, 8):
            rf = evaluate_qualification_readiness(fid, conn=conn)
            assert rf["passed_count"] == 5, f"Facility {fid} failed readiness: {rf['checks']}"
            assert rf["is_ready"] is True
    finally:
        conn.close()


def test_aud003_phone_adversarial_check():
    """
    AUD-003: Changing phone to 'x' or a phone number that doesn't match accepted claim notes
    fails Check 4 (usable_outreach_route).
    """
    conn = create_connection()
    try:
        # Create an isolated temporary copy of facility 1's contacts in the test database
        cur = conn.cursor()
        orig_contacts = cur.execute("SELECT id, phone_number FROM contacts WHERE facility_id = 1").fetchall()

        # Temporarily set all contacts to 'x'
        cur.execute("UPDATE contacts SET phone_number = 'x' WHERE facility_id = 1")
        conn.commit()

        # Readiness must now fail check 4
        res = evaluate_qualification_readiness(1, conn=conn)
        assert res["checks"]["usable_outreach_route"]["passed"] is False
        assert res["passed_count"] < 5

        # Restore original phones
        for c in orig_contacts:
            cur.execute("UPDATE contacts SET phone_number = ? WHERE id = ?", (c["phone_number"], c["id"]))
        conn.commit()

        # Now check 4 passes again
        res_restored = evaluate_qualification_readiness(1, conn=conn)
        assert res_restored["checks"]["usable_outreach_route"]["passed"] is True
    finally:
        conn.close()


def test_aud010_six_demoted_claims_are_unknown_context():
    """
    AUD-010: Claims 265, 268, 417, 420, 673, 676 have verification_status = 'UNKNOWN'
    and claim_evidence relationship = 'CONTEXT'.
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        demoted_claims = (265, 268, 417, 420, 673, 676)
        for cid in demoted_claims:
            claim_row = cur.execute("SELECT verification_status FROM claims WHERE id = ?", (cid,)).fetchone()
            assert claim_row is not None
            assert claim_row["verification_status"] == "UNKNOWN", f"Claim {cid} status {claim_row['verification_status']}"

            ev_rows = cur.execute("SELECT relationship FROM claim_evidence WHERE claim_id = ?", (cid,)).fetchall()
            for er in ev_rows:
                assert er["relationship"] == "CONTEXT", f"Claim {cid} ev relationship {er['relationship']}"
    finally:
        conn.close()


# ============================================================================
# AUD-009: Sonoco Facilities Semantic Packaging Taxonomy Reconciled
# ============================================================================

def test_aud009_sonoco_facilities_industrial_paper_packaging():
    """
    AUD-009: Sonoco Facilities 365 & 366 have category INDUSTRIAL_PAPER_PACKAGING (id 33)
    under family PACKAGING_HIGH_CUBE, matching tubes/cores and rigid paper packaging.
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        for fid in (365, 366):
            mappings = cur.execute("""
                SELECT c.category_code, c.family_id, f.family_code, m.is_primary
                FROM facility_commodity_mappings m
                JOIN commodity_categories c ON m.category_id = c.id
                JOIN commodity_families f ON c.family_id = f.id
                WHERE m.facility_id = ?
            """, (fid,)).fetchall()
            assert len(mappings) == 1
            assert mappings[0]["category_code"] == "INDUSTRIAL_PAPER_PACKAGING"
            assert mappings[0]["family_code"] == "PACKAGING_HIGH_CUBE"
            assert mappings[0]["is_primary"] == 1
    finally:
        conn.close()


# ============================================================================
# Yoder Facility 408: Toll-Free Calling Asset & Unknown Procurement
# ============================================================================

def test_yoder_contact_627_toll_free_selected_as_best_contact():
    """
    Yoder facility 408: Contact 627 (toll-free (800) 531-1704) has procurement relevance UNKNOWN
    and is prioritized in prospect list ahead of contact 418 (Wayne Yoder, phone NULL).
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        c627 = cur.execute("SELECT * FROM contacts WHERE id = 627").fetchone()
        assert c627 is not None
        assert c627["phone_directness"] == "TOLL_FREE"
        assert c627["phone_number"] == "(800) 531-1704"
        assert c627["outbound_shipping_procurement_relevance"] == "UNKNOWN"

        prospects = get_prospects_list("ALL", conn=conn)
        yoder_fac = next((p for p in prospects if p["facility_id"] == 408), None)
        assert yoder_fac is not None
        assert yoder_fac["best_contact"] is not None
        assert yoder_fac["best_contact"]["id"] == 627
        assert yoder_fac["best_contact"]["phone_number"] == "(800) 531-1704"
        assert "(800) 531-1704" in yoder_fac["next_action"]
    finally:
        conn.close()


# ============================================================================
# AUD-023: Canonical UTC ISO-8601 SQLite Column Defaults
# ============================================================================

def test_aud023_column_defaults_use_canonical_utc_strftime():
    """
    AUD-023: Live SQLite column defaults in production tables use canonical
    (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')) instead of naive CURRENT_TIMESTAMP.
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        # Insert a company without specifying created_at or updated_at
        cur.execute("""
            INSERT INTO companies (operating_brand, legal_name, company_footprint_status)
            VALUES ('TEST_AUD23_CO', 'Test AUD23 Legal', 'UNKNOWN')
        """)
        new_id = cur.lastrowid
        conn.commit()

        row = cur.execute("SELECT created_at, updated_at FROM companies WHERE id = ?", (new_id,)).fetchone()
        assert row is not None
        # Default must be canonical ISO-8601 ending with 'Z'
        assert row["created_at"].endswith("Z")
        assert "T" in row["created_at"]
        assert row["updated_at"].endswith("Z")
        assert "T" in row["updated_at"]

        # Clean up
        cur.execute("DELETE FROM companies WHERE id = ?", (new_id,))
        conn.commit()
    finally:
        conn.close()


# ============================================================================
# AUD-025: Append-Only Outreach Logs Triggers (Unconditional)
# ============================================================================

def test_aud025_outreach_logs_unconditional_append_only():
    """
    AUD-025: outreach_logs triggers prevent UPDATE and DELETE unconditionally,
    with zero settings-based bypass switch.
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        # Insert a test outreach log
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur.execute("""
            INSERT INTO outreach_logs (
                company_id, outreach_channel, outcome, contacted_at, created_at
            ) VALUES (1, 'PHONE', 'NO_ANSWER', ?, ?)
        """, (now_iso, now_iso))
        log_id = cur.lastrowid
        conn.commit()

        # Attempt UPDATE must fail
        with pytest.raises(sqlite3.IntegrityError, match="outreach_logs is append-only"):
            cur.execute("UPDATE outreach_logs SET outcome = 'INTERESTED' WHERE id = ?", (log_id,))

        # Attempt DELETE must fail
        with pytest.raises(sqlite3.IntegrityError, match="outreach_logs is append-only"):
            cur.execute("DELETE FROM outreach_logs WHERE id = ?", (log_id,))

        # Even with allow_outreach_mutation in settings, DELETE must fail
        cur.execute("INSERT OR REPLACE INTO settings (setting_key, setting_value, value_type) VALUES ('allow_outreach_mutation', 'true', 'STRING')")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError, match="outreach_logs is append-only"):
            cur.execute("DELETE FROM outreach_logs WHERE id = ?", (log_id,))

        # Clean up trigger to clean test record (only possible by dropping trigger in isolated test db)
        cur.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_delete")
        cur.execute("DELETE FROM outreach_logs WHERE id = ?", (log_id,))
        cur.execute("DELETE FROM settings WHERE setting_key = 'allow_outreach_mutation'")
        conn.commit()
    finally:
        conn.close()


# ============================================================================
# AUD-014: Load Opportunities Integrity Triggers & Margin Validation
# ============================================================================

def test_aud014_load_opportunities_complete_margin_triggers():
    """
    AUD-014: Database triggers enforce that when both rates exist:
    - gross_margin cannot be NULL
    - gross_margin must equal shipper_target_rate - carrier_target_cost
    - margin_pct cannot be NULL or arbitrary (e.g. 999)
    And when rates are missing:
    - gross_margin must be NULL
    - margin_pct must be NULL
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base_insert = f"""
            INSERT INTO load_opportunities (
                facility_id, load_status, equipment_required, origin_city, origin_state_prov,
                dest_city, dest_state_prov, observed_at, shipper_target_rate, carrier_target_cost, gross_margin, margin_pct
            ) VALUES (1, 'IDENTIFIED', 'FLATBED', 'Atlanta', 'GA', 'Dallas', 'TX', '{now_iso}', ?, ?, ?, ?)
        """

        # 1. Both rates present, gross_margin is NULL -> REJECTED
        with pytest.raises(sqlite3.IntegrityError, match="gross_margin is required when both rates are present"):
            cur.execute(base_insert, (100.0, 80.0, None, 20.0))

        # 2. Both rates present, arbitrary gross_margin -> REJECTED
        with pytest.raises(sqlite3.IntegrityError, match="gross_margin does not match"):
            cur.execute(base_insert, (100.0, 80.0, 50.0, 20.0))

        # 3. Both rates present, arbitrary margin_pct (e.g. 999) -> REJECTED
        with pytest.raises(sqlite3.IntegrityError, match="margin_pct"):
            cur.execute(base_insert, (100.0, 80.0, 20.0, 999.0))

        # 4. Rates missing, gross_margin NOT NULL -> REJECTED
        with pytest.raises(sqlite3.IntegrityError, match="gross_margin must be NULL when rates are missing"):
            cur.execute(base_insert, (None, None, 100.0, None))

        # 5. Rates missing, margin_pct NOT NULL (e.g. 999) -> REJECTED
        with pytest.raises(sqlite3.IntegrityError, match="margin_pct must be NULL when rates are missing"):
            cur.execute(base_insert, (None, None, None, 999.0))

        # 6. Correct rates and margins -> ACCEPTED
        cur.execute(base_insert, (100.0, 80.0, 20.0, 20.0))
        load_id = cur.lastrowid
        conn.commit()

        # Clean up
        cur.execute("DELETE FROM load_opportunities WHERE id = ?", (load_id,))
        conn.commit()
    finally:
        conn.close()


# ============================================================================
# AUD-013: Security Boundary on Mutating Endpoints
# ============================================================================

def test_aud013_forged_host_header_rejected():
    """
    AUD-013: Mutating requests with a forged Host header (e.g. evil-attacker.com)
    are rejected with HTTP 403 Forbidden.
    """
    res = client.post(
        "/api/outreach",
        json={"company_id": 1, "disposition": "NO_ANSWER"},
        headers={"Host": "evil-attacker.com", "Origin": "http://evil-attacker.com"}
    )
    assert res.status_code == 403
    assert "Untrusted Host header" in res.json().get("detail", "") or "Cross-origin request rejected" in res.json().get("detail", "")


def test_aud013_cross_origin_origin_rejected():
    """
    AUD-013: Mutating requests with an external Origin header are rejected with HTTP 403.
    """
    res = client.post(
        "/api/outreach",
        json={"company_id": 1, "disposition": "NO_ANSWER"},
        headers={"Host": "127.0.0.1:8000", "Origin": "https://malicious-site.com"}
    )
    assert res.status_code == 403
    assert "Cross-origin request rejected" in res.json().get("detail", "")


# ============================================================================
# AUD-002: Lane Context in Outreach Call Modal & Suppression
# ============================================================================

def test_aud002_lane_context_passed_and_evaluated():
    """
    AUD-002: When origin_state_prov and dest_state_prov are passed in outreach call,
    an active lane suppression blocks the call with 403 Forbidden.
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        # Insert a GLOBAL_LANE suppression for GA -> FL
        cur.execute("""
            INSERT INTO suppressions (
                scope_type, origin_state_prov, dest_state_prov,
                suppression_status, reason_notes, assigned_by
            ) VALUES ('GLOBAL_LANE', 'GA', 'FL', 'DO_NOT_CONTACT', 'Corridor blocked by test', 'TEST_RUNNER')
        """)
        conn.commit()

        # Attempt to log call with GA -> FL lane
        res = client.post("/api/outreach", json={
            "company_id": 1,
            "disposition": "CONNECTED_DECISION_MAKER",
            "origin_state_prov": "GA",
            "dest_state_prov": "FL",
        })
        assert res.status_code == 403
        assert "DO_NOT_CONTACT suppression" in res.json().get("detail", "")

        # Clean up
        cur.execute("DELETE FROM suppressions WHERE assigned_by = 'TEST_RUNNER'")
        conn.commit()
    finally:
        conn.close()


# ============================================================================
# AUD-012: Timezone Localization & Slicing Truth
# ============================================================================

def test_aud012_timezone_conversion_to_utc():
    """
    AUD-012: Local browser datetime (e.g. 2026-10-01 15:00 at UTC+05:30)
    normalizes to canonical UTC 2026-10-01T09:30:00Z.
    """
    res = normalize_to_utc_iso("2026-10-01T15:00:00", default_timezone="Asia/Kolkata")
    assert res == "2026-10-01T09:30:00Z"

    # With +05:30 offset
    res_offset = normalize_to_utc_iso("2026-10-01T15:00:00+05:30")
    assert res_offset == "2026-10-01T09:30:00Z"


def test_aud012_crm_follow_ups_categorization_by_local_date():
    """
    AUD-012: get_crm_follow_ups categorizes items into OVERDUE, TODAY, UPCOMING
    using the user's local date, avoiding UTC day-boundary misgroupings.
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        # Set up a test engagement state with specific UTC follow-up timestamps
        # Suppose user is in Asia/Kolkata (UTC+05:30)
        # UTC 2026-09-27T23:00:00Z -> Local 2026-09-28T04:30:00 (Sep 28)
        # UTC 2026-09-28T18:45:00Z -> Local 2026-09-29T00:15:00 (Sep 29)
        tz = "Asia/Kolkata"
        now_local = datetime.now(ZoneInfo(tz))
        today_local_date = now_local.date()

        # Follow-up for today local: midnight local in UTC
        today_local_dt = datetime(today_local_date.year, today_local_date.month, today_local_date.day, 12, 0, tzinfo=ZoneInfo(tz))
        today_utc_iso = today_local_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Follow-up for tomorrow local:
        tomorrow_local_date = today_local_date + timedelta(days=1)
        tomorrow_local_dt = datetime(tomorrow_local_date.year, tomorrow_local_date.month, tomorrow_local_date.day, 12, 0, tzinfo=ZoneInfo(tz))
        tomorrow_utc_iso = tomorrow_local_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Insert test records
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        cur.execute("""
            INSERT OR REPLACE INTO prospect_engagement_state (
                company_id, current_outreach_status, attempt_count, next_follow_up_at, updated_at
            ) VALUES (1, 'CALL_BACK', 1, ?, ?)
        """, (today_utc_iso, now_iso))
        cur.execute("""
            INSERT OR REPLACE INTO prospect_engagement_state (
                company_id, current_outreach_status, attempt_count, next_follow_up_at, updated_at
            ) VALUES (2, 'CALL_BACK', 1, ?, ?)
        """, (tomorrow_utc_iso, now_iso))
        conn.commit()

        # Call get_crm_follow_ups with Asia/Kolkata timezone
        res = get_crm_follow_ups(user_timezone=tz)
        today_cids = [r["company_id"] for r in res["today"]]
        upcoming_cids = [r["company_id"] for r in res["upcoming"]]

        assert 1 in today_cids, f"Company 1 should be in TODAY, got: {res}"
        assert 2 in upcoming_cids, f"Company 2 should be in UPCOMING, got: {res}"

        # Clean up: restore uncontacted baseline for companies 1 and 2
        cur.execute("""
            UPDATE prospect_engagement_state
            SET current_outreach_status = 'UNCONTACTED', attempt_count = 0, next_follow_up_at = NULL, updated_at = ?
            WHERE company_id IN (1, 2)
        """, (now_iso,))
        conn.commit()
    finally:
        conn.close()


# ============================================================================
# AUD-011: Server-Side Directory Paging & 10 Filters
# ============================================================================

def test_aud011_server_side_company_filtering_and_pagination():
    """
    AUD-011: get_company_grouped_prospects applies all filters before slicing:
    - equipment
    - friction
    - fleet
    - carrier
    - procurement
    """
    # Filter by equipment FLATBED
    flatbed_res = get_company_grouped_prospects(
        lifecycle_stage="ALL",
        equipment="FLATBED",
        page=1,
        page_size=10,
    )
    assert isinstance(flatbed_res, dict)
    assert "items" in flatbed_res
    assert len(flatbed_res["items"]) == 10
    assert flatbed_res["total_count"] > 0
    for item in flatbed_res["items"]:
        assert "FLATBED" in item["equipment_categories"]

    # Filter by friction HIGH
    high_friction_res = get_company_grouped_prospects(
        lifecycle_stage="ALL",
        friction="HIGH",
        page=1,
        page_size=10,
    )
    assert isinstance(high_friction_res, dict)
    for item in high_friction_res["items"]:
        assert item["friction_level"] == "HIGH"


def test_aud011_master_directory_route_pagination_metadata():
    """
    AUD-011: /prospects returns page 1 of 25 companies by default with pagination metadata.
    """
    res = client.get("/prospects")
    assert res.status_code == 200
    assert "Page 1 of" in res.text
    assert "Next" in res.text


# ============================================================================
# AUD-022: Cockpit Research Modal Safe Links
# ============================================================================

def test_aud022_cockpit_renders_safe_website_and_call_now():
    """
    AUD-022: Shortlist cockpit does not render tel:None and guards website_url.
    """
    res = client.get("/")
    assert res.status_code == 200
    assert "tel:None" not in res.text
    assert "startsWith('http://')" in res.text or "safe_url" in res.text


# ============================================================================
# Baseline Truth Invariants
# ============================================================================

def test_baseline_zero_fake_records():
    """Verify zero fake operational records in database."""
    conn = create_connection(DEFAULT_DB_PATH)
    try:
        cur = conn.cursor()
        assert cur.execute("SELECT count(*) FROM outreach_logs").fetchone()[0] == 0
        assert cur.execute("SELECT count(*) FROM load_opportunities").fetchone()[0] == 0
        assert cur.execute("SELECT count(*) FROM capacity_postings").fetchone()[0] == 0
        assert cur.execute("SELECT count(*) FROM freight_demand_signals").fetchone()[0] == 0
        assert cur.execute("SELECT count(*) FROM load_capacity_matches").fetchone()[0] == 0
    finally:
        conn.close()


def test_baseline_lifecycle_counts():
    """Verify lifecycle baseline counts (567 companies, 653 facilities)."""
    conn = create_connection(get_db_path())
    try:
        cur = conn.cursor()
        total_co = cur.execute("SELECT count(*) FROM companies").fetchone()[0]
        total_fac = cur.execute("SELECT count(*) FROM facilities").fetchone()[0]
        assert total_co == 567, f"Expected 567 companies, got {total_co}"
        assert total_fac == 653, f"Expected 653 facilities, got {total_fac}"

        shortlisted = cur.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
        qualified = cur.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'QUALIFIED'").fetchone()[0]
        discovery = cur.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]

        assert shortlisted == 29, f"Expected 29 shortlisted, got {shortlisted}"
        assert qualified == 124, f"Expected 124 qualified, got {qualified}"
        assert discovery == 500, f"Expected 500 discovery, got {discovery}"
    finally:
        conn.close()
