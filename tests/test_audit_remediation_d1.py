"""
Audit Remediation D.1 Verification Test Suite
============================================
Validates the four technical closure blockers and polish items:
1. Advanced-stage readiness / lifecycle reconciliation & promotion guard
2. Append-only ledger REPLACE bypass prevention trigger
3. Two-phase backend/database pagination pushdown
4. Lane-context operator workflow & suppression warning
5. Symmetric phone digit comparison normalization
6. Safe URL sanitization (no href="None")
"""

import os
import shutil
import sqlite3
import pytest
from pathlib import Path
from tests.authenticated_client import TestClient

from src.backend.db.connection import create_connection, get_db_path
from src.backend.db.queries import (
    get_summary_counts,
    get_prospects_list,
    get_company_grouped_prospects,
    evaluate_qualification_readiness,
    promote_prospect_stage,
    check_lane_suppression_warning,
    log_outreach_call,
)
from src.backend.db.validators import (
    normalize_phone_digits,
    sanitize_url,
)
from src.backend.main import app

client = TestClient(app)
DB_PATH = get_db_path()

@pytest.fixture(autouse=True, scope="module")
def pin_historical_db(use_historical_stage3_db):
    global DB_PATH
    DB_PATH = use_historical_stage3_db
    yield
    DB_PATH = get_db_path()


@pytest.fixture
def isolated_db(tmp_path):
    """Creates a temporary, isolated copy of the database for safe mutation testing."""
    temp_db_path = tmp_path / "prospects_d1_test.db"
    shutil.copy2(DB_PATH, temp_db_path)
    return temp_db_path


# ============================================================================
# 1. Advanced-Stage Readiness & Lifecycle Reconciliation
# ============================================================================

def test_shortlisted_facilities_100_percent_ready():
    """Verify that all 29 SHORTLISTED facilities pass all 5 readiness gates with 0 FAIL."""
    conn = create_connection(DB_PATH)
    rows = conn.execute("""
        SELECT f.id, f.company_id
        FROM facilities f
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE pl.stage = 'SHORTLISTED'
    """).fetchall()

    assert len(rows) == 29, f"Expected 29 shortlisted facilities, got {len(rows)}"

    for row in rows:
        fid = row["id"]
        readiness = evaluate_qualification_readiness(fid, conn=conn)
        assert readiness["is_ready"] is True, (
            f"Shortlisted facility {fid} failed readiness: {readiness['checks']}"
        )
        assert readiness["status"] == "READY"
        assert readiness["passed_count"] == 5
    conn.close()


def test_qualified_facilities_100_percent_ready():
    """Verify that all 124 QUALIFIED facilities pass all 5 readiness gates with 0 FAIL."""
    conn = create_connection(DB_PATH)
    rows = conn.execute("""
        SELECT f.id, f.company_id
        FROM facilities f
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE pl.stage = 'QUALIFIED'
    """).fetchall()

    assert len(rows) == 124, f"Expected 124 qualified facilities, got {len(rows)}"

    for row in rows:
        fid = row["id"]
        readiness = evaluate_qualification_readiness(fid, conn=conn)
        assert readiness["is_ready"] is True, (
            f"Qualified facility {fid} failed readiness: {readiness['checks']}"
        )
        assert readiness["status"] == "READY"
        assert readiness["passed_count"] == 5
    conn.close()


def test_demoted_facilities_are_in_discovery():
    """Verify that the 9 demoted non-passing facilities are now in DISCOVERY."""
    demoted_fids = [4, 6, 7, 35, 36, 38, 39, 48, 150]
    conn = create_connection(DB_PATH)
    placeholders = ",".join("?" for _ in demoted_fids)
    rows = conn.execute(f"""
        SELECT f.id, pl.stage
        FROM facilities f
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE f.id IN ({placeholders})
    """, demoted_fids).fetchall()
    conn.close()

    assert len(rows) == len(demoted_fids)
    for r in rows:
        assert r["stage"] == "DISCOVERY", f"Facility {r['id']} must be DISCOVERY, got {r['stage']}"


def test_promotion_guard_rejects_failing_facility(isolated_db):
    """Verify promote_prospect_stage rejects promoting a failing facility with ValueError and reasons."""
    # Facility 4 (WMG Technologies) has failing readiness gates
    with pytest.raises(ValueError) as excinfo:
        promote_prospect_stage(4, "SHORTLISTED", db_path=isolated_db)
    assert "Promotion to SHORTLISTED blocked" in str(excinfo.value)
    assert "commodity_equipment_fit" in str(excinfo.value)


def test_promotion_api_endpoint_rejects_failing_facility():
    """Verify POST /api/prospects/{id}/stage rejects promotion with HTTP 400 and detail."""
    resp = client.post(
        "/api/prospects/4/stage",
        json={"stage": "SHORTLISTED"},
        headers={"Origin": "http://testserver"}
    )
    assert resp.status_code == 400
    data = resp.json()
    assert "Promotion to SHORTLISTED blocked" in data["detail"]


def test_promotion_api_endpoint_verifies_origin():
    """Verify POST /api/prospects/{id}/stage blocks cross-origin requests without approved Origin/Referer."""
    resp = client.post(
        "/api/prospects/4/stage",
        json={"stage": "SHORTLISTED"},
        headers={"Origin": "https://malicious-external-site.com"}
    )
    assert resp.status_code == 403


# ============================================================================
# 2. Append-Only Ledger REPLACE Bypass Prevention Trigger
# ============================================================================

def test_outreach_logs_trigger_blocks_insert_or_replace():
    """Verify trg_outreach_logs_no_replace aborts INSERT OR REPLACE on an existing row."""
    # Test on an in-memory database with the exact schema
    test_conn = sqlite3.connect(":memory:")
    test_conn.execute("PRAGMA foreign_keys = ON")
    test_conn.execute("""
        CREATE TABLE outreach_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            disposition TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    test_conn.execute("""
        CREATE TRIGGER trg_outreach_logs_no_replace
        BEFORE INSERT ON outreach_logs
        WHEN EXISTS (SELECT 1 FROM outreach_logs WHERE id = NEW.id)
        BEGIN
            SELECT RAISE(ABORT, 'outreach_logs is append-only: replacing or reusing existing id is strictly forbidden');
        END;
    """)

    # Initial append works
    test_conn.execute("INSERT INTO outreach_logs (id, company_id, channel, disposition) VALUES (1, 10, 'PHONE', 'NO_ANSWER')")

    # Second normal append works
    test_conn.execute("INSERT INTO outreach_logs (id, company_id, channel, disposition) VALUES (2, 10, 'PHONE', 'INTERESTED')")

    # INSERT OR REPLACE attempting to overwrite id=1 MUST fail with RAISE(ABORT)
    with pytest.raises(sqlite3.IntegrityError) as excinfo:
        test_conn.execute("INSERT OR REPLACE INTO outreach_logs (id, company_id, channel, disposition) VALUES (1, 10, 'PHONE', 'NOT_INTERESTED')")

    assert "outreach_logs is append-only" in str(excinfo.value)
    test_conn.close()


def test_production_db_has_outreach_logs_trigger():
    """Verify production database has the trg_outreach_logs_no_replace trigger installed."""
    conn = create_connection(DB_PATH)
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'trg_outreach_logs_no_replace'").fetchone()
    conn.close()
    assert row is not None
    assert "outreach_logs is append-only" in row[0]


# ============================================================================
# 3. Two-Phase Backend/Database Pagination Pushdown
# ============================================================================

def test_flat_facility_two_phase_pagination():
    """Verify two-phase pushdown pagination on flat facility list returns 25 items out of 653."""
    res = get_prospects_list(lifecycle_stage="ALL", page=1, page_size=25, db_path=DB_PATH)
    assert isinstance(res, dict)
    assert len(res["items"]) == 25
    assert res["total_count"] == 653
    assert res["page"] == 1
    assert res["page_size"] == 25
    assert res["total_pages"] == 27  # ceil(653 / 25) = 27


def test_company_grouped_two_phase_pagination():
    """Verify two-phase pushdown pagination on company-grouped view returns 25 groups out of 565."""
    res = get_company_grouped_prospects(lifecycle_stage="ALL", page=1, page_size=25, db_path=DB_PATH)
    assert isinstance(res, dict)
    assert len(res["items"]) == 25
    assert res["total_count"] == 565
    assert res["page"] == 1
    assert res["page_size"] == 25
    assert res["total_pages"] == 23  # ceil(565 / 25) = 23


# ============================================================================
# 4. Lane-Context Operator Workflow & Suppression Warning
# ============================================================================

def test_lane_suppression_warning_check():
    """Verify check_lane_suppression_warning detects active suppression on restricted lanes."""
    test_conn = sqlite3.connect(":memory:")
    test_conn.row_factory = sqlite3.Row
    test_conn.execute("""
        CREATE TABLE suppressions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            facility_id INTEGER,
            scope_type TEXT NOT NULL,
            origin_state_prov TEXT,
            dest_state_prov TEXT,
            suppression_status TEXT NOT NULL,
            reason_notes TEXT
        )
    """)
    test_conn.execute("""
        INSERT INTO suppressions (company_id, scope_type, origin_state_prov, dest_state_prov, suppression_status, reason_notes)
        VALUES (10, 'COMPANY_LANE', 'GA', 'FL', 'SUPPRESSED', 'Restricted corridor by shipper policy')
    """)

    # Suppressed lane GA -> FL for company 10
    check = check_lane_suppression_warning(10, None, 'GA', 'FL', conn=test_conn)
    assert check["is_lane_suppressed"] is True
    assert check["is_suppressed"] is True
    assert "Restricted corridor" in check["message"]

    # Non-suppressed lane GA -> NC for company 10
    check_ok = check_lane_suppression_warning(10, None, 'GA', 'NC', conn=test_conn)
    assert check_ok["is_lane_suppressed"] is False

    test_conn.close()


def test_suppression_check_api_endpoint():
    """Verify /api/suppressions/check endpoint handles clean queries."""
    resp = client.get("/api/suppressions/check?company_id=1&origin=GA&destination=FL")
    assert resp.status_code == 200
    data = resp.json()
    assert "is_suppressed" in data


def test_log_outreach_call_preserves_lane_in_notes(isolated_db):
    """Verify log_outreach_call formats [Lane: ORIGIN -> DEST] in feedback notes."""
    conn = create_connection(isolated_db)
    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    fid = fac["id"]
    cid = fac["company_id"]
    conn.close()

    res = log_outreach_call(
        company_id=cid,
        facility_id=fid,
        disposition="INTERESTED",
        feedback_notes="Discussed upcoming backhauls.",
        channel="PHONE",
        origin_state_prov="GA",
        dest_state_prov="FL",
        db_path=isolated_db,
    )

    conn2 = create_connection(isolated_db)
    row = conn2.execute("SELECT feedback_notes FROM outreach_logs WHERE id = ?", (res["outreach_log_id"],)).fetchone()
    conn2.close()

    assert "[Lane: GA -> FL]" in row["feedback_notes"]
    assert "Discussed upcoming backhauls." in row["feedback_notes"]


# ============================================================================
# 5. Symmetric Phone Digit Comparison Normalization
# ============================================================================

def test_normalize_phone_digits():
    """Verify normalize_phone_digits strips formatting and leading 1 for US/CA numbers."""
    assert normalize_phone_digits("(800) 555-1212") == "8005551212"
    assert normalize_phone_digits("1-800-555-1212") == "8005551212"
    assert normalize_phone_digits("+1 (800) 555-1212") == "8005551212"
    assert normalize_phone_digits("800.555.1212") == "8005551212"
    assert normalize_phone_digits("8005551212") == "8005551212"
    assert normalize_phone_digits("18005551212") == "8005551212"
    assert normalize_phone_digits(None) == ""
    assert normalize_phone_digits("") == ""


# ============================================================================
# 6. Safe URL Sanitization (No href="None")
# ============================================================================

def test_safe_url_sanitization():
    """Verify sanitize_url permits only http/https and filters malicious or null URLs."""
    assert sanitize_url("https://example.com/facility") == "https://example.com/facility"
    assert sanitize_url("http://example.com") == "http://example.com"
    assert sanitize_url(None) is None
    assert sanitize_url("") is None
    assert sanitize_url("None") is None
    assert sanitize_url("javascript:alert(1)") is None
    assert sanitize_url("data:text/html,<script>alert(1)</script>") is None


# ============================================================================
# 7. Production Database Invariants & Zero Pollution
# ============================================================================

def test_production_db_zero_fake_operational_data():
    """Verify production database has zero fake operational records."""
    counts = get_summary_counts(DB_PATH)
    assert counts["crm_total_calls"] == 0
    assert counts["loads_count"] == 0
    assert counts["capacity_count"] == 0
    assert counts["signals_count"] == 0
    assert counts["matches_count"] == 0
