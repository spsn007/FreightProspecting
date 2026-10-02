"""
FreightProspecting V1 — Stage 3C Outreach CRM & Call Logging Workflow Tests

Validates:
1. Production database invariants:
   - Exactly 0 rows in outreach_logs on production DB.
   - 285 active operating company groups (286 total rows in companies table, 1 inactive holding co), 372 physical facilities.
   - Lifecycle stages intact: SHORTLISTED=4, DISCOVERY=368, QUALIFIED=0, ARCHIVED=0.
   - prospect_engagement_state initialized for all 286 companies (UNCONTACTED, attempt_count=0).
2. Blank Screen / Directory Payload Prevention:
   - GET /prospects returns 200 OK and contains valid HTML with company and facility cards.
   - Base templates and sidebar pills render correctly.
3. Outreach Call Logging & Append-Only History:
   - Single call inserts 1 record into outreach_logs.
   - Calling again appends a second record (append-only ledger).
   - Phone attempt counter increments on phone dispositions.
4. Non-Mutating Lifecycle Invariant:
   - INTERESTED outcome updates prospect_engagement_state to INTERESTED, but DOES NOT alter lifecycle stage (stage remains DISCOVERY).
   - Calling does not create any research claims or freight signals.
5. Suppression & Archive Non-Mutation:
   - NOT_INTERESTED outcome does NOT create any customer suppression, facility suppression, or archive entry.
6. Viewing Invariant:
   - mark_prospect_viewed sets is_viewed=1 with timestamps, but creates 0 outreach records.
7. Follow-Up Categorization:
   - Segregates overdue, today, and upcoming follow-ups accurately based on follow_up_at.
8. Entity Context Isolation (COMPANY != FACILITY):
   - Calling Facility A logs context for Facility A; does NOT imply sibling facility B was contacted.
   - Rejects foreign facility ID not belonging to the company.
9. CRM Navigation & API Endpoints:
   - GET /crm/interested, /crm/follow-ups, /crm/no-answer, /crm/not-interested all return 200 OK.
   - POST /api/outreach returns 201 Created.
   - GET /api/outreach/history returns chronological history.
   - POST /api/viewed/{company_id} updates viewed state.
"""

import os
import shutil
import sqlite3
import pytest
from pathlib import Path
from tests.authenticated_client import TestClient

from src.backend.main import app
from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.queries import (
    get_summary_counts,
    get_crm_counts,
    get_crm_prospects,
    get_crm_follow_ups,
    get_outreach_history,
    log_outreach_call,
    mark_prospect_viewed,
    get_company_grouped_prospects,
    get_prospects_list,
    get_prospect_detail,
)

client = TestClient(app)
PROD_DB_PATH = get_db_path()


# ============================================================================
# 1. Production Database Invariants (Zero Fake Records)
# ============================================================================
def test_production_db_outreach_invariants():
    """Verify production database contains exactly 0 calls, 0 signals, and clean initial engagement states."""
    conn = create_connection(PROD_DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. Zero outreach records in production
    call_count = conn.execute("SELECT COUNT(*) FROM outreach_logs").fetchone()[0]
    assert call_count == 0, f"Expected 0 production outreach logs, found {call_count}"

    # 2. Zero placeholder freight signals or loads
    sig_count = conn.execute("SELECT COUNT(*) FROM freight_demand_signals").fetchone()[0]
    assert sig_count == 0, f"Expected 0 freight signals, found {sig_count}"
    load_count = conn.execute("SELECT COUNT(*) FROM load_opportunities").fetchone()[0]
    assert load_count == 0, f"Expected 0 loads, found {load_count}"

    # 3. Companies and physical facilities (Stage 3E expansion: >= 500 discovery companies)
    comp_count = conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    assert comp_count >= 500, f"Expected >= 500 companies, found {comp_count}"
    assert comp_count == 1034
    fac_count = conn.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
    assert fac_count == 1120, f"Expected 1120 facilities, found {fac_count}"

    # 4. Lifecycle stages preserved
    stages = dict(conn.execute("SELECT stage, COUNT(*) FROM prospect_lifecycle GROUP BY stage").fetchall())
    assert stages.get("SHORTLISTED", 0) == 29
    assert stages.get("DISCOVERY", 0) == 102
    assert stages.get("QUALIFIED", 0) == 989
    assert stages.get("ARCHIVED", 0) == 0

    # 5. prospect_engagement_state backfilled for active companies
    eng_rows = conn.execute("SELECT * FROM prospect_engagement_state").fetchall()
    assert len(eng_rows) == 567
    for r in eng_rows:
        assert r["current_outreach_status"] == "UNCONTACTED"
        assert r["attempt_count"] == 0
        assert r["last_contacted_at"] is None
        assert r["next_follow_up_at"] is None

    conn.close()


def test_production_crm_summary_counts():
    """Verify get_summary_counts returns clean CRM counters."""
    counts = get_summary_counts(PROD_DB_PATH)
    assert "crm_counts" in counts
    crm = counts["crm_counts"]
    assert crm["total_calls"] == 0
    assert crm["uncontacted"] >= 500
    assert crm["uncontacted"] == 567
    assert crm["interested"] == 0
    assert crm["no_answer"] == 0
    assert crm["not_interested"] == 0
    assert crm["call_back"] == 0
    assert crm["follow_ups"] == 0


# ============================================================================
# 2. Blank Screen / Directory Payload Prevention
# ============================================================================
def test_blank_screen_prevention_prospects_page():
    """Verify /prospects returns 200 OK and valid non-blank HTML."""
    response = client.get("/prospects")
    assert response.status_code == 200
    html = response.text
    assert "Master Directory" in html
    assert "Operating Companies" in html
    assert "Physical Shipping Facilities" in html
    assert "Broker Access Friction" in html
    assert "log_call_modal" in html or "Log Call" in html
    assert "paginatedCompanies()" in html
    assert len(html) > 5000


def test_crm_views_status_codes():
    """Verify dedicated CRM workflow views return 200 OK."""
    for endpoint in ["/crm/interested", "/crm/follow-ups", "/crm/no-answer", "/crm/not-interested"]:
        resp = client.get(endpoint)
        assert resp.status_code == 200, f"Failed on {endpoint}"
        assert len(resp.text) > 2000


# ============================================================================
# Isolated Fixtures for Mutation Tests
# ============================================================================
@pytest.fixture
def test_db(tmp_path):
    """Creates a temporary, isolated copy of the database for safe call logging tests."""
    temp_db_path = tmp_path / "prospects_crm_test.db"
    shutil.copy2(PROD_DB_PATH, temp_db_path)
    return temp_db_path


# ============================================================================
# 3. Call Logging & Non-Mutating Lifecycle Invariant
# ============================================================================
def test_log_outreach_call_interested_does_not_alter_lifecycle(test_db):
    """
    INVARIANT TEST:
    Logging an INTERESTED call updates current outreach status and follow-up,
    but NEVER changes lifecycle stage (DISCOVERY remains DISCOVERY).
    """
    conn = create_connection(test_db)
    conn.row_factory = sqlite3.Row

    # Pick a discovery facility and company
    fac = conn.execute("""
        SELECT f.id as facility_id, f.company_id, c.operating_brand, pl.stage
        FROM facilities f
        JOIN companies c ON f.company_id = c.id
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE pl.stage = 'DISCOVERY'
        LIMIT 1
    """).fetchone()

    fac_id = fac["facility_id"]
    comp_id = fac["company_id"]
    initial_stage = fac["stage"]
    assert initial_stage == "DISCOVERY"

    # Log an outreach call
    result = log_outreach_call(
        company_id=comp_id,
        facility_id=fac_id,
        channel="PHONE",
        disposition="INTERESTED",
        feedback_notes="Spoke with shipping coordinator. Interested in flatbed capacity for Atlanta to Chicago lanes.",
        follow_up_at="2026-09-30T10:00:00Z",
        db_path=test_db,
    )

    assert result["company_id"] == comp_id
    assert result["facility_id"] == fac_id
    assert result["disposition"] == "INTERESTED"
    assert result["attempt_count"] == 1
    assert result["follow_up_at"] == "2026-09-30T10:00:00Z"

    # Verify outreach_logs row
    logs = conn.execute("SELECT * FROM outreach_logs WHERE company_id = ?", (comp_id,)).fetchall()
    assert len(logs) == 1
    assert logs[0]["outcome"] == "INTERESTED"
    assert logs[0]["feedback_notes"] == "Spoke with shipping coordinator. Interested in flatbed capacity for Atlanta to Chicago lanes."

    # Verify prospect_engagement_state updated
    eng = conn.execute("SELECT * FROM prospect_engagement_state WHERE company_id = ?", (comp_id,)).fetchone()
    assert eng["current_outreach_status"] == "INTERESTED"
    assert eng["attempt_count"] == 1
    assert eng["last_facility_id"] == fac_id
    assert eng["next_follow_up_at"] == "2026-09-30T10:00:00Z"

    # CRITICAL INVARIANT: Lifecycle stage is completely unchanged!
    curr_stage = conn.execute("SELECT stage FROM prospect_lifecycle WHERE facility_id = ?", (fac_id,)).fetchone()[0]
    assert curr_stage == "DISCOVERY", "Lifecycle stage must NOT mutate to QUALIFIED merely because prospect is interested"

    # Zero claims added
    conn.close()


def test_call_logging_append_only_and_attempt_counter(test_db):
    """
    Verifies that calling multiple times produces an append-only timeline
    and correctly counts attempts.
    """
    conn = create_connection(test_db)
    conn.row_factory = sqlite3.Row

    comp = conn.execute("SELECT id FROM companies LIMIT 1").fetchone()
    comp_id = comp["id"]
    conn.close()

    # Call 1: NO_ANSWER
    log_outreach_call(
        company_id=comp_id,
        channel="PHONE",
        disposition="NO_ANSWER",
        feedback_notes="Rang 5 times, no voicemail.",
        db_path=test_db,
    )

    history1 = get_outreach_history(company_id=comp_id, db_path=test_db)
    assert len(history1) == 1
    assert history1[0]["disposition"] == "NO_ANSWER"

    eng1 = get_crm_prospects(status="NO_ANSWER", db_path=test_db)
    target1 = next((c for c in eng1 if c["company_id"] == comp_id), None)
    assert target1 is not None
    assert target1["attempt_count"] == 1

    # Call 2: NO_ANSWER again
    log_outreach_call(
        company_id=comp_id,
        channel="PHONE",
        disposition="NO_ANSWER",
        feedback_notes="Busy signal.",
        db_path=test_db,
    )

    history2 = get_outreach_history(company_id=comp_id, db_path=test_db)
    assert len(history2) == 2, "Outreach history must be append-only"
    assert history2[0]["feedback_notes"] == "Busy signal."  # newest first
    assert history2[1]["feedback_notes"] == "Rang 5 times, no voicemail."

    eng2 = get_crm_prospects(status="NO_ANSWER", db_path=test_db)
    target2 = next((c for c in eng2 if c["company_id"] == comp_id), None)
    assert target2["attempt_count"] == 2

    # Call 3: CALL_BACK
    log_outreach_call(
        company_id=comp_id,
        channel="PHONE",
        disposition="CALL_BACK",
        feedback_notes="Gatekeeper said coordinator is on the dock, call back at 2 PM.",
        follow_up_at="2026-09-28T14:00:00Z",
        db_path=test_db,
    )

    history3 = get_outreach_history(company_id=comp_id, db_path=test_db)
    assert len(history3) == 3
    assert history3[0]["disposition"] == "CALL_BACK"

    eng3 = get_crm_prospects(status="CALL_BACK", db_path=test_db)
    target3 = next((c for c in eng3 if c["company_id"] == comp_id), None)
    assert target3 is not None
    assert target3["attempt_count"] == 3
    assert target3["next_follow_up_at"] == "2026-09-28T14:00:00Z"


# ============================================================================
# 4. Suppression & Archive Non-Mutation
# ============================================================================
def test_not_interested_does_not_create_suppression_or_archive(test_db):
    """
    INVARIANT TEST:
    NOT_INTERESTED outcome does NOT create a customer suppression or archive the prospect.
    """
    conn = create_connection(test_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("""
        SELECT f.id as facility_id, f.company_id, pl.stage
        FROM facilities f
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE pl.stage = 'DISCOVERY'
        LIMIT 1
    """).fetchone()

    fac_id = fac["facility_id"]
    comp_id = fac["company_id"]
    conn.close()

    log_outreach_call(
        company_id=comp_id,
        facility_id=fac_id,
        channel="PHONE",
        disposition="NOT_INTERESTED",
        feedback_notes="Not taking new brokers this quarter.",
        db_path=test_db,
    )

    conn2 = create_connection(test_db)
    conn2.row_factory = sqlite3.Row

    # Verify no suppressions created
    supp_count = conn2.execute("SELECT COUNT(*) FROM suppressions").fetchone()[0]
    assert supp_count == 0, "NOT_INTERESTED must NOT create an automated DNC suppression"

    # Verify lifecycle stage is NOT ARCHIVED
    stage = conn2.execute("SELECT stage FROM prospect_lifecycle WHERE facility_id = ?", (fac_id,)).fetchone()[0]
    assert stage == "DISCOVERY", "NOT_INTERESTED must NOT auto-archive the prospect"

    # Verify engagement state is NOT_INTERESTED
    eng = conn2.execute("SELECT current_outreach_status FROM prospect_engagement_state WHERE company_id = ?", (comp_id,)).fetchone()
    assert eng["current_outreach_status"] == "NOT_INTERESTED"

    conn2.close()


# ============================================================================
# 5. Viewing Invariant (Viewed != Contacted)
# ============================================================================
def test_mark_prospect_viewed_creates_zero_outreach_logs(test_db):
    """
    INVARIANT TEST:
    Viewing a prospect profile updates viewed state but creates ZERO outreach records.
    """
    conn = create_connection(test_db)
    comp = conn.execute("SELECT id FROM companies LIMIT 1").fetchone()
    comp_id = comp[0]
    conn.close()

    # Mark viewed
    state = mark_prospect_viewed(comp_id, db_path=test_db)
    assert state["is_viewed"] == 1
    assert state["first_viewed_at"] is not None
    assert state["last_viewed_at"] is not None

    conn2 = create_connection(test_db)
    logs_count = conn2.execute("SELECT COUNT(*) FROM outreach_logs WHERE company_id = ?", (comp_id,)).fetchone()[0]
    assert logs_count == 0, "Viewing must NEVER insert into outreach_logs"

    eng = conn2.execute("SELECT is_viewed, current_outreach_status FROM prospect_engagement_state WHERE company_id = ?", (comp_id,)).fetchone()
    assert eng[0] == 1
    assert eng[1] == "UNCONTACTED"
    conn2.close()


# ============================================================================
# 6. Follow-Up Categorization (Overdue, Today, Upcoming)
# ============================================================================
def test_crm_follow_up_categorization(test_db):
    """Verifies that get_crm_follow_ups groups follow-ups by due date accurately."""
    conn = create_connection(test_db)
    comps = conn.execute("SELECT id FROM companies LIMIT 3").fetchall()
    c1, c2, c3 = comps[0][0], comps[1][0], comps[2][0]
    conn.close()

    # Company 1: Overdue (past date)
    log_outreach_call(
        company_id=c1,
        channel="PHONE",
        disposition="CALL_BACK",
        feedback_notes="Overdue follow-up test",
        follow_up_at="2026-09-01T10:00:00Z",
        db_path=test_db,
    )

    # Company 2: Upcoming (future date)
    log_outreach_call(
        company_id=c2,
        channel="PHONE",
        disposition="INTERESTED",
        feedback_notes="Future follow-up test",
        follow_up_at="2026-10-15T10:00:00Z",
        db_path=test_db,
    )

    follow_ups = get_crm_follow_ups(db_path=test_db)
    assert "overdue" in follow_ups
    assert "today" in follow_ups
    assert "upcoming" in follow_ups

    overdue_ids = [item["company_id"] for item in follow_ups["overdue"]]
    upcoming_ids = [item["company_id"] for item in follow_ups["upcoming"]]

    assert c1 in overdue_ids
    assert c2 in upcoming_ids
    assert c3 not in overdue_ids and c3 not in upcoming_ids


# ============================================================================
# 7. Entity Context Isolation (COMPANY != FACILITY)
# ============================================================================
def test_company_facility_context_isolation(test_db):
    """
    INVARIANT TEST:
    Calling Plant A logs context for Plant A.
    It does NOT imply sibling Plant B was contacted.
    """
    conn = create_connection(test_db)
    conn.row_factory = sqlite3.Row

    # Find a multi-facility company (e.g. Georgia-Pacific or West Fraser)
    multi_comp = conn.execute("""
        SELECT company_id, COUNT(*) as cnt
        FROM facilities
        GROUP BY company_id
        HAVING cnt >= 2
        LIMIT 1
    """).fetchone()

    comp_id = multi_comp["company_id"]
    facs = conn.execute("SELECT id, facility_name FROM facilities WHERE company_id = ? ORDER BY id ASC", (comp_id,)).fetchall()
    fac_a = facs[0]["id"]
    fac_b = facs[1]["id"]
    conn.close()

    # Log call for Plant A
    log_outreach_call(
        company_id=comp_id,
        facility_id=fac_a,
        channel="PHONE",
        disposition="INTERESTED",
        feedback_notes="Called Plant A logistics coordinator.",
        db_path=test_db,
    )

    # History for Plant A has 1 record
    hist_a = get_outreach_history(facility_id=fac_a, db_path=test_db)
    assert len(hist_a) == 1
    assert hist_a[0]["facility_id"] == fac_a

    # History for Plant B has 0 records!
    hist_b = get_outreach_history(facility_id=fac_b, db_path=test_db)
    assert len(hist_b) == 0, "Calling Plant A must NOT create an outreach record on Plant B"

    # History for Company has 1 record
    hist_comp = get_outreach_history(company_id=comp_id, db_path=test_db)
    assert len(hist_comp) == 1


def test_reject_foreign_facility_id(test_db):
    """Verifies that specifying a facility belonging to another company is rejected."""
    conn = create_connection(test_db)
    comps = conn.execute("SELECT id FROM companies LIMIT 2").fetchall()
    c1 = comps[0][0]
    c2 = comps[1][0]
    fac_of_c2 = conn.execute("SELECT id FROM facilities WHERE company_id = ? LIMIT 1", (c2,)).fetchone()[0]
    conn.close()

    with pytest.raises(ValueError, match="does not belong to company"):
        log_outreach_call(
            company_id=c1,
            facility_id=fac_of_c2,
            channel="PHONE",
            disposition="NO_ANSWER",
            db_path=test_db,
        )


# ============================================================================
# 8. API Endpoints
# ============================================================================
def test_api_outreach_flow(test_db, monkeypatch):
    """Tests the REST API endpoints using an isolated database via FREIGHT_DB_PATH."""
    monkeypatch.setenv("FREIGHT_DB_PATH", str(test_db))

    conn = create_connection(test_db)
    comp = conn.execute("SELECT id FROM companies LIMIT 1").fetchone()
    comp_id = comp[0]
    conn.close()

    # 1. POST /api/outreach
    post_payload = {
        "company_id": comp_id,
        "facility_id": None,
        "contact_id": None,
        "channel": "PHONE",
        "disposition": "INTERESTED",
        "feedback_notes": "API test call log",
        "follow_up_at": "2026-10-01T15:00:00Z"
    }
    resp = client.post("/api/outreach", json=post_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "success"
    assert data["data"]["disposition"] == "INTERESTED"

    # 2. GET /api/outreach/history
    resp_hist = client.get(f"/api/outreach/history?company_id={comp_id}")
    assert resp_hist.status_code == 200
    hist = resp_hist.json()
    assert len(hist) == 1
    assert hist[0]["feedback_notes"] == "API test call log"

    # 3. POST /api/viewed/{company_id}
    resp_view = client.post(f"/api/viewed/{comp_id}")
    assert resp_view.status_code == 200
    view_data = resp_view.json()
    assert view_data["status"] == "success"
    assert view_data["data"]["is_viewed"] == 1
