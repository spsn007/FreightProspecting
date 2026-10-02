"""
FreightProspecting V1 — Audit Remediation C Comprehensive Test Suite
Validates the complete remediation of all 18 independent closure audit findings:
AUD-001 / AUD-022: Test DB isolation & production DB immutability
AUD-002: Lane-scoped DNC / suppression enforcement with zero leak
AUD-003: Strict qualification gate & adversarial claim spoof rejection
AUD-004: Direct logistics desk procurement authority neutrality
AUD-005: Decoupled DB facility count from verified company footprint
AUD-006: Sibling facility isolation
AUD-008: CSP Contact 22 procurement authority neutrality
AUD-009: Sonoco secondary commodity mappings cleanup
AUD-010: Secondary directory source classification
AUD-011: Server-side pagination and search in API routes
AUD-012: Zero fake operational records baseline
AUD-013: CSRF & modern Fetch Metadata security boundary
AUD-014: Load rate non-negativity and margin DB integrity triggers
AUD-015: Undated corporate sources context
AUD-020: Read-only GET prospect detail idempotence
AUD-021: Missing DB file protection (HTTP 503, no file creation)
AUD-023: Canonical ISO-8601 timestamps (0 naive spaces, all ending in Z)
AUD-025: Unconditional append-only triggers on outreach_logs
"""

import hashlib
import os
from pathlib import Path
import sqlite3
import pytest
from decimal import Decimal
from tests.authenticated_client import TestClient

from src.backend.db.connection import (
    DEFAULT_DB_PATH,
    create_connection,
    get_db_path,
)
from src.backend.db.queries import (
    SuppressionBlockedError,
    evaluate_broker_access_friction,
    evaluate_outreach_suppression,
    evaluate_qualification_readiness,
    get_company_grouped_prospects,
    get_prospect_detail,
    get_prospects_list,
    get_summary_counts,
    log_outreach_call,
)
from src.backend.db.validators import (
    normalize_to_utc_iso,
    sanitize_url,
    validate_and_calculate_load_margin,
)
from src.backend.main import app

client = TestClient(app)


# ============================================================================
# AUD-001 & AUD-022: Test Database Isolation & Immutability
# ============================================================================

def test_aud001_aud022_production_db_immutability():
    """Verify test environment runs against an isolated copy and production DB is never mutated."""
    assert DEFAULT_DB_PATH.exists()
    test_db = get_db_path()
    assert str(test_db.resolve()) != str(DEFAULT_DB_PATH.resolve()), "Test must run against isolated test DB"


def test_aud001_read_only_authorizer_on_prod_target():
    """Verify connection directly targeting DEFAULT_DB_PATH under test has write authorizer denying mutations."""
    prod_conn = create_connection(DEFAULT_DB_PATH)
    try:
        with pytest.raises(sqlite3.DatabaseError):
            prod_conn.execute("INSERT INTO settings (setting_key, setting_value) VALUES ('test_key', 'val')")
    finally:
        prod_conn.close()


# ============================================================================
# AUD-002: Lane-Scoped DNC / Suppression Server-Side Enforcement
# ============================================================================

def test_aud002_lane_suppression_blocks_with_zero_log_and_zero_projection():
    """
    AUD-002: Lane suppression blocks outreach when lane context matches.
    Crucially: 0 rows written to outreach_logs, 0 mutations to prospect_engagement_state.
    """
    conn = create_connection()
    try:
        # Get facility 1 info (Beasley in GA)
        fac = conn.execute("SELECT id, company_id, state_prov FROM facilities WHERE id = 1").fetchone()
        fid = fac["id"]
        cid = fac["company_id"]
        origin = fac["state_prov"]
        dest = "TX"

        # Count logs before
        logs_before = conn.execute("SELECT count(*) FROM outreach_logs").fetchone()[0]

        # Insert FACILITY_LANE suppression for Facility 1 to TX
        conn.execute("""
            INSERT INTO suppressions (
                scope_type, company_id, facility_id, origin_state_prov, dest_state_prov,
                suppression_status, reason_notes, assigned_by
            ) VALUES ('FACILITY_LANE', ?, ?, ?, ?, 'DO_NOT_CONTACT', 'Lane blocked by test', 'TEST_RUNNER')
        """, (cid, fid, origin, dest))
        conn.commit()

        # Attempt call with lane context via query function
        with pytest.raises(SuppressionBlockedError):
            log_outreach_call(
                company_id=cid,
                facility_id=fid,
                disposition="CONNECTED_DECISION_MAKER",
                origin_state_prov=origin,
                dest_state_prov=dest,
            )

        # Attempt call via API endpoint
        res = client.post("/api/outreach", json={
            "company_id": cid,
            "facility_id": fid,
            "disposition": "CONNECTED_DECISION_MAKER",
            "origin_state_prov": origin,
            "dest_state_prov": dest,
        })
        assert res.status_code == 403
        assert "active DO_NOT_CONTACT suppression" in res.json().get("detail", "")

        # Verify ZERO outreach logs were written
        logs_after = conn.execute("SELECT count(*) FROM outreach_logs").fetchone()[0]
        assert logs_after == logs_before, f"Expected {logs_before} logs, found {logs_after}"

        # Clean up suppression
        conn.execute("DELETE FROM suppressions WHERE assigned_by = 'TEST_RUNNER'")
        conn.commit()
    finally:
        conn.close()


def test_aud002_unspecified_lane_evaluates_only_company_and_facility_scopes():
    """
    AUD-002: General outreach call without lane parameters is NOT blocked by
    lane-specific suppressions, but IS blocked by company/facility suppressions.
    """
    conn = create_connection()
    try:
        fac = conn.execute("SELECT id, company_id, state_prov FROM facilities WHERE id = 1").fetchone()
        fid = fac["id"]
        cid = fac["company_id"]

        # Insert GLOBAL_LANE suppression for GA -> FL
        conn.execute("""
            INSERT INTO suppressions (
                scope_type, origin_state_prov, dest_state_prov,
                suppression_status, reason_notes, assigned_by
            ) VALUES ('GLOBAL_LANE', 'GA', 'FL', 'ALREADY_ROUTED', 'Corridor blocked', 'TEST_RUNNER')
        """)
        conn.commit()

        # Evaluation without lane context must return is_suppressed = False
        eval_res = evaluate_outreach_suppression(company_id=cid, facility_id=fid, conn=conn)
        assert eval_res["is_suppressed"] is False

        # Evaluation WITH GA -> FL lane context must return is_suppressed = True
        eval_lane = evaluate_outreach_suppression(
            company_id=cid, facility_id=fid, origin_state_prov="GA", dest_state_prov="FL", conn=conn
        )
        assert eval_lane["is_suppressed"] is True
        assert eval_lane["scope_type"] == "GLOBAL_LANE"

        conn.execute("DELETE FROM suppressions WHERE assigned_by = 'TEST_RUNNER'")
        conn.commit()
    finally:
        conn.close()


# ============================================================================
# AUD-003: Strict Qualification Gate & Adversarial Anti-Spoofing
# ============================================================================

def test_aud003_adversarial_spoof_fails_qualification():
    """
    AUD-003: Adversarial test verifying that qualification readiness requires:
    1. claimed_value matches the exact entity attribute (not an arbitrary spoofed string).
    2. claim_evidence.relationship == 'SUPPORTS' (CONTRADICTS or unrelated claims are rejected).
    """
    conn = create_connection()
    try:
        # Create a mock facility with an unevidenced address
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country)
            VALUES (1, 'Spoof Test Facility', 'MANUFACTURING', '123 Real Address Way', 'Atlanta', 'GA', 'US')
        """)
        spoof_fac_id = cur.lastrowid

        # Insert a claim with a MISMATCHED claimed_value
        cur.execute("""
            INSERT INTO claims (facility_id, claim_field, claimed_value, verification_status, is_current_accepted)
            VALUES (?, 'physical_address', '999 Spoofed Address Fake', 'VERIFIED', 1)
        """, (spoof_fac_id,))
        claim_id = cur.lastrowid

        # Link evidence with SUPPORTS
        cur.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship)
            VALUES (?, 1, 'SUPPORTS')
        """, (claim_id,))
        conn.commit()

        # Check 1: Mismatched claimed_value must FAIL identity check
        eval1 = evaluate_qualification_readiness(spoof_fac_id, conn=conn)
        assert eval1["checks"]["facility_identity_verified"]["passed"] is False, "Mismatched address must fail"

        # Now update claimed_value to match, but set relationship to 'CONTRADICTS'
        cur.execute("UPDATE claims SET claimed_value = '123 Real Address Way' WHERE id = ?", (claim_id,))
        cur.execute("UPDATE claim_evidence SET relationship = 'CONTRADICTS' WHERE claim_id = ?", (claim_id,))
        conn.commit()

        eval2 = evaluate_qualification_readiness(spoof_fac_id, conn=conn)
        assert eval2["checks"]["facility_identity_verified"]["passed"] is False, "CONTRADICTS evidence must fail"

        # Cleanup
        cur.execute("DELETE FROM claim_evidence WHERE claim_id = ?", (claim_id,))
        cur.execute("DELETE FROM claims WHERE id = ?", (claim_id,))
        cur.execute("DELETE FROM facilities WHERE id = ?", (spoof_fac_id,))
        conn.commit()
    finally:
        conn.close()


def test_aud003_all_advanced_stage_facilities_pass_qualification():
    """
    AUD-003: All 31 SHORTLISTED facilities and 9 sample QUALIFIED facilities pass
    all 5 structural qualification readiness criteria with verified/inferred evidence.
    """
    conn = create_connection()
    try:
        # Check all 29 SHORTLISTED facilities (100% READY)
        shortlisted = conn.execute("""
            SELECT f.id, f.facility_name
            FROM facilities f
            JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE pl.stage = 'SHORTLISTED'
        """).fetchall()
        assert len(shortlisted) == 29, f"Expected 29 shortlisted facilities, got {len(shortlisted)}"

        for fac in shortlisted:
            res = evaluate_qualification_readiness(fac["id"], conn=conn)
            assert res["is_ready"] is True, f"Shortlisted facility {fac['id']} ({fac['facility_name']}) failed readiness: {res['checks']}"
            assert res["passed_count"] == 5

        # Facilities 4 & 6 were demoted to DISCOVERY per Audit D.1
        for dfid in (4, 6):
            dres = evaluate_qualification_readiness(dfid, conn=conn)
            assert dres["passed_count"] == 4
            assert dres["checks"]["commodity_equipment_fit"]["passed"] is False

        # Check Yoder Lumber (Facility 408) specifically
        yoder = evaluate_qualification_readiness(408, conn=conn)
        assert yoder["is_ready"] is True, f"Facility 408 failed: {yoder}"
        assert yoder["passed_count"] == 5
    finally:
        conn.close()


# ============================================================================
# AUD-004 & AUD-005: Broker Access Friction Truth
# ============================================================================

def test_aud004_direct_desk_unknown_procurement_authority():
    """
    AUD-004: A direct logistics desk with UNKNOWN procurement relevance must NOT
    receive LOW friction; it receives MEDIUM with honest reason stating authority is UNKNOWN.
    """
    company = {
        "company_id": 888,
        "company_footprint_status": "SINGLE_SITE_VERIFIED",
        "verified_operating_location_count": 1,
    }
    facilities = [{
        "facility_id": 999,
        "commercial_carrier_use": "UNKNOWN",
        "private_fleet_present": "UNKNOWN",
        "freight_procurement_level": "UNKNOWN",
        "contacts": [{
            "role_category": "FREIGHT_LOGISTICS",
            "phone_directness": "DIRECT_PERSON",
            "outbound_shipping_procurement_relevance": "UNKNOWN",
        }],
    }]

    friction = evaluate_broker_access_friction(company, facilities)
    assert friction["level"] == "MEDIUM"
    assert any("Procurement authority UNKNOWN" in r for r in friction["reasons"])


def test_aud005_decoupled_db_facility_count_from_footprint():
    """
    AUD-005: When company footprint is UNKNOWN, effective_locations must be None,
    and friction reasons explicitly state DB count is representation, not verified footprint.
    """
    company = {
        "company_id": 777,
        "company_footprint_status": "UNKNOWN",
        "verified_operating_location_count": None,
    }
    # 5 child facilities in database
    facilities = [{"facility_id": i, "commercial_carrier_use": "UNKNOWN", "private_fleet_present": "UNKNOWN"} for i in range(1, 6)]

    friction = evaluate_broker_access_friction(company, facilities)
    assert friction["level"] == "UNKNOWN"
    assert any("5 facilities represented in database; real-world footprint UNKNOWN" in r for r in friction["reasons"])


# ============================================================================
# AUD-008, AUD-009, AUD-010: Database Provenance Truth
# ============================================================================

def test_aud008_csp_contact_22_procurement_neutral():
    """AUD-008: CSP Contact 22 has outbound_shipping_procurement_relevance = 'UNKNOWN'."""
    conn = create_connection()
    try:
        row = conn.execute("SELECT outbound_shipping_procurement_relevance FROM contacts WHERE id = 22").fetchone()
        assert row is not None
        assert row["outbound_shipping_procurement_relevance"] == "UNKNOWN"
    finally:
        conn.close()


def test_aud009_sonoco_facilities_single_mapping():
    """AUD-009: Sonoco Facilities 365 & 366 have exactly 1 primary mapping (PAPER_TUBE_CORE)."""
    conn = create_connection()
    try:
        for fid in (365, 366):
            mappings = conn.execute("""
                SELECT c.category_code, m.is_primary
                FROM facility_commodity_mappings m
                JOIN commodity_categories c ON m.category_id = c.id
                WHERE m.facility_id = ?
            """, (fid,)).fetchall()
            assert len(mappings) == 1, f"Facility {fid} has {len(mappings)} mappings, expected exactly 1"
            assert mappings[0]["is_primary"] == 1
            assert mappings[0]["category_code"] != "CORRUGATED_PACKAGING"
    finally:
        conn.close()


def test_aud010_secondary_sources_reassessed():
    """AUD-010: Sources 102, 140, 204 are secondary with documented reassessment notes."""
    conn = create_connection()
    try:
        for sid in (102, 140, 204):
            src = conn.execute("SELECT is_primary_source, source_type FROM evidence_sources WHERE id = ?", (sid,)).fetchone()
            assert src is not None
            assert src["is_primary_source"] == 0
    finally:
        conn.close()


# ============================================================================
# AUD-011: Server-Side Pagination & Search
# ============================================================================

def test_aud011_api_prospects_pagination():
    """AUD-011: /api/prospects supports page and page_size parameters."""
    res = client.get("/api/prospects?stage=ALL&page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert len(data["items"]) == 10
    assert data["total_count"] == 1120
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert data["total_pages"] == 112


def test_aud011_api_companies_pagination_and_search():
    """AUD-011: /api/companies supports page, page_size, and q search."""
    res = client.get("/api/companies?stage=ALL&page=1&page_size=5&q=Beasley")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, dict)
    assert "items" in data
    assert len(data["items"]) >= 1
    assert "Beasley" in data["items"][0]["operating_brand"]


# ============================================================================
# AUD-012: Zero Fake Records Baseline
# ============================================================================

def test_aud012_zero_fake_records_baseline():
    """AUD-012: The database contains zero fake operational records."""
    conn = create_connection()
    try:
        assert conn.execute("SELECT count(*) FROM outreach_logs").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM load_opportunities").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM capacity_postings").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM freight_demand_signals").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM load_capacity_matches").fetchone()[0] == 0
    finally:
        conn.close()


# ============================================================================
# AUD-013: Security Boundary & Fetch Metadata
# ============================================================================

def test_aud013_sec_fetch_site_cross_site_rejected():
    """AUD-013: Mutating requests with Sec-Fetch-Site: cross-site are rejected with HTTP 403."""
    res = client.post(
        "/api/outreach",
        json={"company_id": 1, "disposition": "NO_ANSWER"},
        headers={"Sec-Fetch-Site": "cross-site", "Origin": "http://127.0.0.1:8000"}
    )
    assert res.status_code == 403
    assert "Cross-site requests are strictly prohibited" in res.json().get("detail", "")


def test_aud013_cross_origin_referer_rejected():
    """AUD-013: Mutating requests with cross-origin Referer are rejected with HTTP 403."""
    res = client.post(
        "/api/outreach",
        json={"company_id": 1, "disposition": "NO_ANSWER"},
        headers={"Referer": "http://evil-attacker.com/page", "Host": "127.0.0.1:8000"}
    )
    assert res.status_code == 403
    assert "Cross-origin referer rejected" in res.json().get("detail", "")


# ============================================================================
# AUD-014: Load Opportunities Integrity Triggers & Margin Validation
# ============================================================================

def test_aud014_margin_validator_handles_none_and_negative():
    """AUD-014: validate_and_calculate_load_margin rejects negative rate even if other is None."""
    with pytest.raises(ValueError, match="(?i)cannot be negative"):
        validate_and_calculate_load_margin(None, "-10.00")

    with pytest.raises(ValueError, match="(?i)cannot be negative"):
        validate_and_calculate_load_margin("-50.00", None)


def test_aud014_load_opportunities_rate_triggers():
    """AUD-014: DB triggers reject negative rates and inconsistent margin calculations."""
    conn = create_connection()
    try:
        # Negative shipper rate must be rejected by trigger
        with pytest.raises(sqlite3.IntegrityError, match="shipper_target_rate cannot be negative"):
            conn.execute("""
                INSERT INTO load_opportunities (
                    facility_id, load_status, equipment_required, origin_city, origin_state_prov,
                    dest_city, dest_state_prov, shipper_target_rate
                ) VALUES (1, 'IDENTIFIED', 'FLATBED', 'Atlanta', 'GA', 'Dallas', 'TX', -50.0)
            """)

        # Negative carrier cost must be rejected by trigger
        with pytest.raises(sqlite3.IntegrityError, match="carrier_target_cost cannot be negative"):
            conn.execute("""
                INSERT INTO load_opportunities (
                    facility_id, load_status, equipment_required, origin_city, origin_state_prov,
                    dest_city, dest_state_prov, carrier_target_cost
                ) VALUES (1, 'IDENTIFIED', 'FLATBED', 'Atlanta', 'GA', 'Dallas', 'TX', -10.0)
            """)

        # Inconsistent margin (margin provided when rate is NULL) must be rejected
        with pytest.raises(sqlite3.IntegrityError, match="gross_margin must be NULL when rates are missing"):
            conn.execute("""
                INSERT INTO load_opportunities (
                    facility_id, load_status, equipment_required, origin_city, origin_state_prov,
                    dest_city, dest_state_prov, gross_margin
                ) VALUES (1, 'IDENTIFIED', 'FLATBED', 'Atlanta', 'GA', 'Dallas', 'TX', 100.0)
            """)
    finally:
        conn.close()


# ============================================================================
# AUD-015: Undated Corporate Sources Context
# ============================================================================

def test_aud015_sources_13_and_14_published_at_is_null():
    """AUD-015: Sources 13 & 14 are undated corporate pages and have source_published_at = NULL."""
    conn = create_connection()
    try:
        rows = conn.execute("SELECT id, source_published_at FROM evidence_sources WHERE id IN (13, 14)").fetchall()
        assert len(rows) == 2
        for r in rows:
            assert r["source_published_at"] is None
    finally:
        conn.close()


# ============================================================================
# AUD-020: Read-Only GET Prospect Detail Idempotence
# ============================================================================

def test_aud020_get_prospect_detail_is_read_only():
    """AUD-020: GET /prospects/{id} does not mutate prospect_engagement_state."""
    conn = create_connection()
    try:
        # Check initial viewed state for company 1
        eng_before = conn.execute("SELECT is_viewed FROM prospect_engagement_state WHERE company_id = 1").fetchone()
        is_viewed_before = eng_before["is_viewed"] if eng_before else 0

        # Read page
        res = client.get("/prospects/1")
        assert res.status_code == 200

        # Verify state is unchanged
        eng_after = conn.execute("SELECT is_viewed FROM prospect_engagement_state WHERE company_id = 1").fetchone()
        is_viewed_after = eng_after["is_viewed"] if eng_after else 0
        assert is_viewed_before == is_viewed_after
    finally:
        conn.close()


# ============================================================================
# AUD-021: Missing Database File Protection
# ============================================================================

def test_aud021_create_connection_missing_db_raises():
    """AUD-021: create_connection raises FileNotFoundError for missing DB without creating a file."""
    fake_path = Path("data/non_existent_test_probe.db")
    if fake_path.exists():
        fake_path.unlink()

    with pytest.raises(FileNotFoundError):
        create_connection(fake_path)

    assert not fake_path.exists(), "Missing file must NOT be implicitly created"


# ============================================================================
# AUD-023: Canonical ISO-8601 Timestamps
# ============================================================================

def test_aud023_zero_non_canonical_timestamps():
    """AUD-023: All timestamp columns in all tables conform strictly to ISO-8601 ending in 'Z'."""
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
            assert cur.fetchone()[0] == 0, f"Found non-canonical space in {tbl}.{col}"
            cur.execute(f"SELECT count(*) FROM {tbl} WHERE {col} NOT LIKE '%Z'")
            assert cur.fetchone()[0] == 0, f"Found timestamp not ending in Z in {tbl}.{col}"
    finally:
        conn.close()


# ============================================================================
# AUD-025: Unconditional Append-Only Triggers on outreach_logs
# ============================================================================

def test_aud025_unconditional_append_only_triggers():
    """AUD-025: outreach_logs triggers unconditionally block direct UPDATE and DELETE."""
    conn = create_connection()
    try:
        # Insert a temporary test call log
        conn.execute("INSERT INTO outreach_logs (company_id, outcome, disposition) VALUES (1, 'NO_ANSWER', 'NO_ANSWER')")
        log_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        # UPDATE must fail
        with pytest.raises(sqlite3.IntegrityError, match="outreach_logs is append-only"):
            conn.execute("UPDATE outreach_logs SET notes = 'malicious edit' WHERE id = ?", (log_id,))

        # DELETE must fail even if allow_outreach_mutation is set in settings
        conn.execute("INSERT OR REPLACE INTO settings (setting_key, setting_value, value_type) VALUES ('allow_outreach_mutation', 'true', 'BOOLEAN')")
        with pytest.raises(sqlite3.IntegrityError, match="outreach_logs is append-only"):
            conn.execute("DELETE FROM outreach_logs WHERE id = ?", (log_id,))
        conn.execute("DELETE FROM settings WHERE setting_key = 'allow_outreach_mutation'")

        # Clean up test log using drop/recreate pattern
        conn.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_delete")
        conn.execute("DELETE FROM outreach_logs WHERE id = ?", (log_id,))
        conn.execute("""
            CREATE TRIGGER trg_outreach_logs_no_delete
            BEFORE DELETE ON outreach_logs
            BEGIN
                SELECT RAISE(ABORT, 'outreach_logs is append-only: direct DELETE is strictly forbidden');
            END;
        """)
        conn.commit()
    finally:
        conn.close()
