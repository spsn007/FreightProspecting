"""
Audit Remediation B Verification Tests
Validates performance optimizations, security hardening, input validation,
canonical timestamps, trigger protections, and UI/accessibility fixes
for findings AUD-011 through AUD-026.
"""

import os
import sqlite3
import pytest
from pathlib import Path
from decimal import Decimal
from fastapi.testclient import TestClient

from src.backend.db.connection import create_connection, check_database_health
from src.backend.db.queries import (
    get_prospects_list,
    get_company_grouped_prospects,
    log_outreach_call,
)
from src.backend.db.validators import (
    normalize_to_utc_iso,
    sanitize_url,
    validate_and_calculate_load_margin,
)
from src.backend.main import app

client = TestClient(app)


class StatementCounter:
    """SQLite trace callback counter to measure exact SQL execution count."""
    def __init__(self):
        self.count = 0
        self.statements = []

    def __call__(self, statement):
        self.count += 1
        self.statements.append(statement)


def test_aud011_directory_query_reduction_benchmark():
    """
    AUD-011: Master Directory query count must be reduced from 5,539+
    down to fewer than 35 SQL statements for get_prospects_list(ALL).
    """
    conn = create_connection()
    counter = StatementCounter()
    conn.set_trace_callback(counter)

    try:
        prospects = get_prospects_list("ALL", conn=conn)
        assert len(prospects) == 1120, f"Expected 1120 facilities, got {len(prospects)}"
        assert counter.count < 35, f"Expected < 35 SQL queries, executed {counter.count}"
    finally:
        conn.close()


def test_aud011_company_grouped_prospects_query_reduction():
    """
    AUD-011: Grouped directory query count must be reduced from 5,542+
    down to fewer than 40 SQL statements.
    """
    conn = create_connection()
    counter = StatementCounter()
    conn.set_trace_callback(counter)

    try:
        groups = get_company_grouped_prospects("ALL", conn=conn)
        assert len(groups) == 1032, f"Expected 1032 operating company groups, got {len(groups)}"
        assert counter.count < 40, f"Expected < 40 SQL queries, executed {counter.count}"
    finally:
        conn.close()


def test_aud012_timestamp_normalization_and_validation():
    """
    AUD-012: normalize_to_utc_iso strictly validates and normalizes timestamps,
    rejecting non-parseable and placeholder text.
    """
    # Valid ISO formats
    assert normalize_to_utc_iso("2026-09-28T09:00:00Z") == "2026-09-28T09:00:00Z"
    assert normalize_to_utc_iso("2026-09-28 09:00:00") == "2026-09-28T09:00:00Z"
    assert normalize_to_utc_iso("2026-09-28") == "2026-09-28T00:00:00Z"

    # Invalid / placeholder strings must raise ValueError
    with pytest.raises(ValueError):
        normalize_to_utc_iso("bad-time")

    with pytest.raises(ValueError):
        normalize_to_utc_iso("not-a-date")

    with pytest.raises(ValueError):
        normalize_to_utc_iso("Active")

    assert normalize_to_utc_iso(None) is None


def test_aud012_crm_log_call_rejects_malformed_timestamps():
    """
    AUD-012: log_outreach_call rejects malformed timestamps with ValueError.
    """
    conn = create_connection()
    try:
        with pytest.raises(ValueError, match="not a valid ISO-8601 timestamp string"):
            log_outreach_call(
                company_id=1,
                disposition="NO_ANSWER",
                contacted_at="bad-time",
                conn=conn
            )

        with pytest.raises(ValueError, match="not a valid ISO-8601 timestamp string"):
            log_outreach_call(
                company_id=1,
                disposition="CALL_BACK",
                follow_up_at="invalid-date",
                conn=conn
            )
    finally:
        conn.close()


def test_aud013_origin_verification_blocks_unauthorized_origins():
    """
    AUD-013: Mutating endpoints block requests from untrusted external origins.
    """
    # External origin with POST /api/outreach
    res = client.post(
        "/api/outreach",
        json={"company_id": 1, "disposition": "NO_ANSWER"},
        headers={"Origin": "https://attacker-site.com"}
    )
    assert res.status_code == 403
    assert "Cross-origin request rejected" in res.json().get("detail", "")

    # External origin with POST /api/viewed/1
    res = client.post(
        "/api/viewed/1",
        headers={"Origin": "https://attacker-site.com"}
    )
    assert res.status_code == 403
    assert "Cross-origin request rejected" in res.json().get("detail", "")


def test_aud014_load_rate_and_margin_validation():
    """
    AUD-014: validate_and_calculate_load_margin uses Decimal arithmetic,
    enforces non-negative rates, and preserves UNKNOWN when either rate is missing.
    """
    # Complete valid rates
    margin, pct = validate_and_calculate_load_margin("2500.00", "2000.00")
    assert margin == Decimal("500.00")
    assert pct == Decimal("20.00")

    # Missing shipper rate -> UNKNOWN margin
    margin, pct = validate_and_calculate_load_margin(None, "2000.00")
    assert margin is None
    assert pct is None

    # Missing carrier cost -> UNKNOWN margin
    margin, pct = validate_and_calculate_load_margin("2500.00", None)
    assert margin is None
    assert pct is None

    # Zero shipper rate
    margin, pct = validate_and_calculate_load_margin("0.00", "0.00")
    assert margin == Decimal("0.00")
    assert pct is None  # Avoid division by zero

    # Negative rate must raise ValueError
    with pytest.raises(ValueError, match="cannot be negative"):
        validate_and_calculate_load_margin("-100.00", "50.00")

    with pytest.raises(ValueError, match="cannot be negative"):
        validate_and_calculate_load_margin("100.00", "-50.00")


def test_aud015_sources_13_and_14_published_context():
    """
    AUD-015: Sources 13 & 14 are undated corporate web pages; in accordance with
    zero-hallucination standards, source_published_at must be NULL (never fabricated).
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, source_published_at FROM evidence_sources WHERE id IN (13, 14)")
        rows = cur.fetchall()
        assert len(rows) == 2
        for r in rows:
            assert r["source_published_at"] is None
    finally:
        conn.close()


def test_aud016_discovery_readiness_explanation_truth():
    """
    AUD-016: Discovery prospects meeting all 5 readiness checks display
    honest explanation that they are ready for qualification review.
    """
    conn = create_connection()
    try:
        prospects = get_prospects_list("DISCOVERY", conn=conn)
        ready_prospects = [p for p in prospects if p.get("qualification_readiness", {}).get("is_ready")]
        assert len(ready_prospects) > 0
        for p in ready_prospects:
            assert "Meets all 5 qualification checks" in p.get("stage_explanation", "")
            assert "ready for qualification review" in p.get("stage_explanation", "")
    finally:
        conn.close()


def test_aud021_health_check_does_not_create_empty_database(tmp_path):
    """
    AUD-021: check_database_health uses read-only URI mode and does not
    silently create an empty database file when the path is missing.
    """
    missing_path = tmp_path / "non_existent_dir" / "missing.db"
    assert not missing_path.exists()

    health = check_database_health(missing_path)
    assert health["healthy"] is False
    assert health["exists"] is False
    assert "not found" in health["error"]
    # File must NOT have been created
    assert not missing_path.exists()


def test_aud022_url_sanitization():
    """
    AUD-022: sanitize_url allows http/https and blocks dangerous schemes.
    """
    assert sanitize_url("https://example.com/shipping") == "https://example.com/shipping"
    assert sanitize_url("http://example.com/shipping") == "http://example.com/shipping"
    assert sanitize_url("javascript:alert(1)") is None
    assert sanitize_url("data:text/html,<script>alert(1)</script>") is None
    assert sanitize_url("vbscript:msgbox(1)") is None
    assert sanitize_url(None) is None


def test_aud023_canonical_timestamps_across_tables():
    """
    AUD-023: Timestamps in companies, facilities, claims, and contacts
    must strictly conform to ISO-8601 UTC (ending in 'Z').
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        for tbl, col in [
            ("companies", "created_at"),
            ("facilities", "created_at"),
            ("claims", "created_at"),
            ("contacts", "created_at"),
            ("evidence_sources", "created_at"),
        ]:
            cur.execute(f"SELECT count(*) FROM {tbl} WHERE {col} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:*'")
            naive_count = cur.fetchone()[0]
            assert naive_count == 0, f"Found {naive_count} naive space timestamps in {tbl}.{col}"
    finally:
        conn.close()


def test_aud024_csp_source_38_url_canonical():
    """
    AUD-024: CSP Source 38 has canonical URL for shipping and receiving.
    """
    conn = create_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT source_url FROM evidence_sources WHERE id = 38")
        row = cur.fetchone()
        assert row is not None
        assert row["source_url"] == "https://coilsteelprocessing.com/shipping-and-receiving/"
    finally:
        conn.close()


def test_aud025_outreach_logs_append_only_triggers(tmp_path):
    """
    AUD-025: outreach_logs triggers strictly block direct UPDATE and DELETE
    unless the test bypass setting is explicitly enabled.
    """
    import shutil
    temp_db = tmp_path / "trigger_test.db"
    shutil.copy2("data/prospects.db", temp_db)
    conn = create_connection(temp_db)
    try:
        # Insert a test call
        conn.execute("INSERT INTO outreach_logs (company_id, outcome, disposition) VALUES (1, 'NO_ANSWER', 'NO_ANSWER')")
        log_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # UPDATE must be rejected
        with pytest.raises(sqlite3.IntegrityError, match="outreach_logs is append-only"):
            conn.execute("UPDATE outreach_logs SET notes = 'illegal update' WHERE id = ?", (log_id,))

        # DELETE must be rejected
        with pytest.raises(sqlite3.IntegrityError, match="outreach_logs is append-only"):
            conn.execute("DELETE FROM outreach_logs WHERE id = ?", (log_id,))

        # AUD-025: Unconditional trigger test - setting 'allow_outreach_mutation' must NOT bypass append-only protection
        conn.execute("INSERT OR REPLACE INTO settings (setting_key, setting_value, value_type, description) VALUES ('allow_outreach_mutation', 'true', 'BOOLEAN', 'Test override')")
        with pytest.raises(sqlite3.IntegrityError, match="outreach_logs is append-only"):
            conn.execute("DELETE FROM outreach_logs WHERE id = ?", (log_id,))
        with pytest.raises(sqlite3.IntegrityError, match="outreach_logs is append-only"):
            conn.execute("UPDATE outreach_logs SET notes = 'illegal' WHERE id = ?", (log_id,))
        conn.execute("DELETE FROM settings WHERE setting_key = 'allow_outreach_mutation'")
    finally:
        conn.close()


def test_aud026_prospect_detail_legal_name_fallback():
    """
    AUD-026: Detail page handles null legal_name cleanly without displaying 'None'.
    Facility 18 has legal_name NULL.
    """
    res = client.get("/prospects/18")
    assert res.status_code == 200
    html = res.text
    # Must not contain "Legal Entity Name</span> <span class="kv-val">None"
    assert '<span class="kv-key">Legal Entity Name</span>\n          <span class="kv-val">None</span>' not in html
    assert "Not specified" in html
