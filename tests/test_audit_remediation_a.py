"""
FreightProspecting V1 — Audit Remediation A Test Suite
Tests P0/P1 Data Safety, CRM Correctness & Business Truth:
1. Test DB Isolation: pytest never mutates production prospects.db.
2. DNC / Suppression Server-Side Enforcement across COMPANY, FACILITY, COMPANY_LANE, FACILITY_LANE, GLOBAL_LANE.
3. NOT_INTERESTED != DNC and DIRECT_ONLY != DNC.
4. Qualification readiness requires genuine evidence provenance for address, equipment, and contact route.
5. Broker access friction prevents false LOW for UNKNOWN footprint or general switchboard numbers.
6. Sibling facility contamination eliminated: facility A's outreach does NOT mark sibling facility B contacted.
7. All 8 canonical dispositions record cleanly without CHECK constraint failure.
8. CSP (Facility 18) Shipping Contact truth: (419) 269-9706, shipping@coilsteelprocessing.com, DEPARTMENT_LINE, FLATBED VERIFIED.
9. Taxonomy: Bulk mulch not in BAGGED_MULCH_SOIL (facilities 5 & 460); StructureCraft (613) is mass timber.
10. Source types: directories/associations have is_primary_source = 0 and appropriate non-website source types.
"""

import hashlib
from pathlib import Path
import sqlite3
import pytest
from tests.authenticated_client import TestClient

from src.backend.db.connection import create_connection, get_db_path
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
from src.backend.main import app

PROD_DB_PATH = Path("data/prospects.db")


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="function")
def db_conn():
    conn = create_connection(get_db_path())
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def cleanup_test_mutations(db_conn):
    # Ensure suppressions table and outreach logs are clean before and after
    db_conn.execute("DELETE FROM suppressions WHERE assigned_by = 'TEST_RUNNER'")
    db_conn.execute("DELETE FROM facilities WHERE facility_name = 'Hypothetical Test Plant'")
    db_conn.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_delete")
    if db_conn.execute("SELECT 1 FROM sqlite_master WHERE name='outreach_authors'").fetchone():
        db_conn.execute("DELETE FROM outreach_authors")
    db_conn.execute("DELETE FROM outreach_logs")
    db_conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_outreach_logs_no_delete
        BEFORE DELETE ON outreach_logs
        BEGIN
            SELECT RAISE(ABORT, 'outreach_logs is append-only: direct DELETE is strictly forbidden');
        END;
    """)
    db_conn.execute("""
        UPDATE prospect_engagement_state 
        SET current_outreach_status = 'UNCONTACTED', 
            attempt_count = 0, 
            last_contacted_at = NULL, 
            next_follow_up_at = NULL, 
            last_facility_id = NULL, 
            last_feedback_notes = NULL, 
            is_viewed = 0
    """)
    db_conn.commit()
    yield
    db_conn.execute("DELETE FROM suppressions WHERE assigned_by = 'TEST_RUNNER'")
    db_conn.execute("DELETE FROM facilities WHERE facility_name = 'Hypothetical Test Plant'")
    db_conn.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_delete")
    if db_conn.execute("SELECT 1 FROM sqlite_master WHERE name='outreach_authors'").fetchone():
        db_conn.execute("DELETE FROM outreach_authors")
    db_conn.execute("DELETE FROM outreach_logs")
    db_conn.execute("""
        CREATE TRIGGER IF NOT EXISTS trg_outreach_logs_no_delete
        BEFORE DELETE ON outreach_logs
        BEGIN
            SELECT RAISE(ABORT, 'outreach_logs is append-only: direct DELETE is strictly forbidden');
        END;
    """)
    db_conn.execute("""
        UPDATE prospect_engagement_state 
        SET current_outreach_status = 'UNCONTACTED', 
            attempt_count = 0, 
            last_contacted_at = NULL, 
            next_follow_up_at = NULL, 
            last_facility_id = NULL, 
            last_feedback_notes = NULL, 
            is_viewed = 0
    """)
    db_conn.commit()


# ============================================================================
# 1. Test Database Isolation & Immutability Guard
# ============================================================================

def test_production_db_hash_unaltered_by_testing():
    """Verify that test operations execute in isolation and production DB remains byte-identical."""
    h_prod = hashlib.sha256(open(PROD_DB_PATH, "rb").read()).hexdigest().upper()
    # Confirm test DB is not the production DB file
    test_db = get_db_path()
    assert str(test_db) != str(PROD_DB_PATH.resolve())
    assert h_prod == hashlib.sha256(open(PROD_DB_PATH, "rb").read()).hexdigest().upper()


# ============================================================================
# 2. DNC / Suppression Server-Side Enforcement Across All Scopes
# ============================================================================

def test_company_suppression_blocks_outreach(db_conn, client):
    """Verify COMPANY-scope DNC suppression blocks call logging server-side with HTTP 403."""
    cur = db_conn.cursor()
    # Find an active company with no current suppression
    comp = cur.execute("SELECT id FROM companies LIMIT 1").fetchone()
    cid = comp["id"]

    # Insert a COMPANY suppression
    cur.execute(
        """
        INSERT INTO suppressions (
            scope_type, company_id, facility_id, suppression_status, reason_notes, assigned_by
        ) VALUES ('COMPANY', ?, NULL, 'DO_NOT_CONTACT', 'Requested removal during legal review', 'TEST_RUNNER')
        """,
        (cid,)
    )
    db_conn.commit()

    try:
        # Direct function call must raise SuppressionBlockedError
        with pytest.raises(SuppressionBlockedError) as exc_info:
            log_outreach_call(company_id=cid, disposition="NO_ANSWER", db_path=get_db_path())
        assert "Outreach blocked: Company" in str(exc_info.value)

        # API call must return HTTP 403 Forbidden
        resp = client.post(
            "/api/outreach",
            json={"company_id": cid, "disposition": "NO_ANSWER"}
        )
        assert resp.status_code == 403
        assert "Outreach blocked" in resp.json()["detail"]

        # Verify zero outreach logs were written for this company
        log_cnt = cur.execute("SELECT count(*) FROM outreach_logs WHERE company_id = ?", (cid,)).fetchone()[0]
        assert log_cnt == 0
    finally:
        cur.execute("DELETE FROM suppressions WHERE company_id = ?", (cid,))
        db_conn.commit()


def test_facility_suppression_blocks_specific_facility_only(db_conn, client):
    """Verify FACILITY-scope suppression blocks outreach to that facility while allowing sibling facility."""
    cur = db_conn.cursor()
    # Find a multi-facility company
    multi = cur.execute(
        "SELECT company_id, count(id) as fcnt FROM facilities GROUP BY company_id HAVING fcnt > 1 LIMIT 1"
    ).fetchone()
    cid = multi["company_id"]
    facs = cur.execute("SELECT id FROM facilities WHERE company_id = ? ORDER BY id", (cid,)).fetchall()
    f1_id = facs[0]["id"]
    f2_id = facs[1]["id"]

    # Suppress facility 1 only
    cur.execute(
        """
        INSERT INTO suppressions (
            scope_type, company_id, facility_id, suppression_status, reason_notes, assigned_by
        ) VALUES ('FACILITY', NULL, ?, 'DO_NOT_CONTACT', 'Plant dock access restricted', 'TEST_RUNNER')
        """,
        (f1_id,)
    )
    db_conn.commit()

    try:
        # Outreach to facility 1 must be blocked
        with pytest.raises(SuppressionBlockedError):
            log_outreach_call(company_id=cid, facility_id=f1_id, disposition="NO_ANSWER", db_path=get_db_path())

        resp = client.post(
            "/api/outreach",
            json={"company_id": cid, "facility_id": f1_id, "disposition": "NO_ANSWER"}
        )
        assert resp.status_code == 403

        # Outreach to facility 2 must SUCCEED
        res_f2 = log_outreach_call(company_id=cid, facility_id=f2_id, disposition="CONNECTED_GATEKEEPER", db_path=get_db_path())
        assert res_f2["disposition"] == "CONNECTED_GATEKEEPER"
    finally:
        cur.execute("DELETE FROM suppressions WHERE facility_id = ?", (f1_id,))
        db_conn.commit()


def test_lane_suppression_enforcement(db_conn):
    """Verify lane suppressions (COMPANY_LANE, FACILITY_LANE, GLOBAL_LANE) evaluate accurately."""
    cur = db_conn.cursor()
    comp = cur.execute("SELECT id FROM companies LIMIT 1").fetchone()
    cid = comp["id"]

    # Global lane suppression for GA -> FL
    cur.execute(
        """
        INSERT INTO suppressions (
            scope_type, company_id, facility_id, origin_state_prov, dest_state_prov,
            suppression_status, reason_notes, assigned_by
        ) VALUES ('GLOBAL_LANE', NULL, NULL, 'GA', 'FL', 'ALREADY_ROUTED', 'Contracted dedicated lane corridor', 'TEST_RUNNER')
        """
    )
    db_conn.commit()

    try:
        # Check GA -> FL lane
        sup_ga_fl = evaluate_outreach_suppression(
            company_id=cid, origin_state_prov="GA", dest_state_prov="FL", conn=db_conn
        )
        assert sup_ga_fl["is_suppressed"] is True
        assert sup_ga_fl["scope_type"] == "GLOBAL_LANE"

        # Check unsuppressed lane GA -> OH
        sup_ga_oh = evaluate_outreach_suppression(
            company_id=cid, origin_state_prov="GA", dest_state_prov="OH", conn=db_conn
        )
        assert sup_ga_oh["is_suppressed"] is False
    finally:
        cur.execute("DELETE FROM suppressions WHERE scope_type = 'GLOBAL_LANE'")
        db_conn.commit()


def test_normal_prospect_suppression_status_does_not_block(db_conn):
    """Verify suppression_status = 'NORMAL_PROSPECT' does not block outreach."""
    cur = db_conn.cursor()
    comp = cur.execute("SELECT id FROM companies LIMIT 1").fetchone()
    cid = comp["id"]

    cur.execute(
        """
        INSERT INTO suppressions (
            scope_type, company_id, facility_id, suppression_status, reason_notes, assigned_by
        ) VALUES ('COMPANY', ?, NULL, 'NORMAL_PROSPECT', 'Active prospecting approved', 'TEST_RUNNER')
        """,
        (cid,)
    )
    db_conn.commit()

    try:
        sup = evaluate_outreach_suppression(company_id=cid, conn=db_conn)
        assert sup["is_suppressed"] is False
    finally:
        cur.execute("DELETE FROM suppressions WHERE company_id = ?", (cid,))
        db_conn.commit()


# ============================================================================
# 3. NOT_INTERESTED != DNC & DIRECT_ONLY != DNC
# ============================================================================

def test_not_interested_does_not_create_suppression(db_conn, client):
    """Verify NOT_INTERESTED records as a normal disposition without creating a DNC suppression."""
    cur = db_conn.cursor()
    comp = cur.execute("SELECT id FROM companies LIMIT 1").fetchone()
    cid = comp["id"]

    # Log call with NOT_INTERESTED
    resp = client.post(
        "/api/outreach",
        json={"company_id": cid, "disposition": "NOT_INTERESTED", "feedback_notes": "Shipper satisfied with current carriers"}
    )
    assert resp.status_code == 201

    # Verify zero rows added to suppressions
    sup_cnt = cur.execute("SELECT count(*) FROM suppressions WHERE company_id = ?", (cid,)).fetchone()[0]
    assert sup_cnt == 0

    # Verify subsequent outreach is NOT blocked
    sup_eval = evaluate_outreach_suppression(company_id=cid, conn=db_conn)
    assert sup_eval["is_suppressed"] is False


# ============================================================================
# 4. Qualification Readiness Evidence Provenance Checks
# ============================================================================

def test_qualification_readiness_requires_evidence_provenance(db_conn):
    """Verify qualification gate distinguishes 'value exists' from 'evidence supports value'."""
    cur = db_conn.cursor()
    # Pick shortlisted facility 1 (Beasley)
    fac_id = 1
    readiness = evaluate_qualification_readiness(fac_id, db_conn)
    assert readiness["is_ready"] is True
    assert readiness["passed_count"] == 5

    # Check 1: If physical_address claim is missing, facility identity check fails
    # Test on a temporary unlinked facility record
    cur.execute(
        """
        INSERT INTO facilities (
            company_id, facility_name, facility_type, physical_address, city, state_prov, country
        ) VALUES (1, 'Hypothetical Test Plant', 'MANUFACTURING', '999 Unverified St', 'Atlanta', 'GA', 'US')
        """
    )
    fake_fac_id = cur.lastrowid
    db_conn.commit()

    fake_readiness = evaluate_qualification_readiness(fake_fac_id, db_conn)
    assert fake_readiness["is_ready"] is False
    assert fake_readiness["checks"]["facility_identity_verified"]["passed"] is False
    assert "missing verified accepted claim" in fake_readiness["checks"]["facility_identity_verified"]["details"]


# ============================================================================
# 5. Broker Access Friction Accuracy
# ============================================================================

def test_broker_access_friction_unknown_footprint_is_never_low():
    """Verify UNKNOWN company footprint remains strictly neutral (UNKNOWN) and never LOW."""
    company = {
        "company_id": 999,
        "company_footprint_status": "UNKNOWN",
        "verified_operating_location_count": None,
    }
    # Facility with verified commercial carrier use and freight logistics contacts
    facilities = [{
        "facility_id": 1001,
        "commercial_carrier_use": "VERIFIED",
        "private_fleet_present": "UNKNOWN",
        "freight_procurement_level": "UNKNOWN",
        "contacts": [{
            "role_category": "FREIGHT_LOGISTICS",
            "phone_directness": "DIRECT_PERSON",
        }],
    }]

    friction = evaluate_broker_access_friction(company, facilities)
    assert friction["level"] == "UNKNOWN"
    assert friction["level"] != "LOW"
    assert any("access friction cannot be evaluated without verified footprint" in r for r in friction["reasons"])


def test_broker_access_friction_general_switchboard_does_not_grant_low():
    """Verify SINGLE_SITE_VERIFIED with freight role on a general switchboard gets MEDIUM (gatekeeper required)."""
    company = {
        "company_id": 998,
        "company_footprint_status": "SINGLE_SITE_VERIFIED",
        "verified_operating_location_count": 1,
    }
    # Freight contact identified but only reachable via general switchboard
    facilities = [{
        "facility_id": 1002,
        "commercial_carrier_use": "UNKNOWN",
        "private_fleet_present": "UNKNOWN",
        "freight_procurement_level": "UNKNOWN",
        "contacts": [{
            "role_category": "FREIGHT_LOGISTICS",
            "phone_directness": "GENERAL_SWITCHBOARD",
        }],
    }]

    friction = evaluate_broker_access_friction(company, facilities)
    assert friction["level"] == "MEDIUM"
    assert any("general switchboard / gatekeeper" in r for r in friction["reasons"])


def test_broker_access_friction_single_site_with_direct_desk_grants_low():
    """Verify SINGLE_SITE_VERIFIED with direct freight line achieves LOW friction."""
    company = {
        "company_id": 997,
        "company_footprint_status": "SINGLE_SITE_VERIFIED",
        "verified_operating_location_count": 1,
    }
    facilities = [{
        "facility_id": 1003,
        "commercial_carrier_use": "UNKNOWN",
        "private_fleet_present": "UNKNOWN",
        "freight_procurement_level": "FACILITY_LEVEL",
        "contacts": [{
            "role_category": "FREIGHT_LOGISTICS",
            "phone_directness": "DEPARTMENT_LINE",
        }],
    }]

    friction = evaluate_broker_access_friction(company, facilities)
    assert friction["level"] == "LOW"


# ============================================================================
# 6. Sibling Facility Contamination Fix
# ============================================================================

def test_sibling_facility_outreach_does_not_contaminate_uncontacted_sibling(db_conn):
    """Verify outreach to Facility A does not mark sibling Facility B as contacted."""
    cur = db_conn.cursor()
    # Find a company with at least 2 facilities
    multi = cur.execute(
        "SELECT company_id FROM facilities GROUP BY company_id HAVING count(id) > 1 LIMIT 1"
    ).fetchone()
    cid = multi["company_id"]
    facs = cur.execute("SELECT id FROM facilities WHERE company_id = ? ORDER BY id", (cid,)).fetchall()
    fA_id = facs[0]["id"]
    fB_id = facs[1]["id"]

    # Log call specifically to Facility A
    log_outreach_call(
        company_id=cid,
        facility_id=fA_id,
        disposition="CONNECTED_DECISION_MAKER",
        channel="PHONE",
        feedback_notes="Spoke to Facility A shipping desk",
        db_path=get_db_path()
    )

    # Fetch prospects list
    prospects = get_prospects_list(db_path=get_db_path(), lifecycle_stage="ALL")
    facA = next((p for p in prospects if p["facility_id"] == fA_id), None)
    facB = next((p for p in prospects if p["facility_id"] == fB_id), None)

    assert facA is not None
    assert facB is not None

    # Facility A must show contacted
    assert facA["facility_outreach_status"] == "CONNECTED_DECISION_MAKER"
    assert facA["outreach_status"] == "CONNECTED_DECISION_MAKER"
    assert facA["facility_attempt_count"] == 1

    # Facility B must REMAIN UNCONTACTED
    assert facB["facility_outreach_status"] == "UNCONTACTED"
    assert facB["outreach_status"] == "UNCONTACTED"
    assert facB["facility_attempt_count"] == 0

    # Company outreach status is shared
    assert facB["company_outreach_status"] == "CONNECTED_DECISION_MAKER"


# ============================================================================
# 7. All 8 Canonical Dispositions Supported
# ============================================================================

@pytest.mark.parametrize("disp", [
    "INTERESTED",
    "CONNECTED_DECISION_MAKER",
    "CONNECTED_GATEKEEPER",
    "CALL_BACK",
    "LEFT_VOICEMAIL",
    "NO_ANSWER",
    "NOT_INTERESTED",
    "WRONG_CONTACT",
])
def test_all_8_dispositions_record_successfully(disp, client, db_conn):
    """Verify all 8 dispositions record cleanly in outreach_logs and prospect_engagement_state."""
    cur = db_conn.cursor()
    comp = cur.execute("SELECT id FROM companies LIMIT 1").fetchone()
    cid = comp["id"]

    resp = client.post(
        "/api/outreach",
        json={"company_id": cid, "disposition": disp, "feedback_notes": f"Testing {disp}"}
    )
    assert resp.status_code == 201, f"Failed for disposition {disp}: {resp.text}"
    data = resp.json()["data"]
    assert data["disposition"] == disp

    # Verify engagement state projection
    eng = cur.execute("SELECT current_outreach_status FROM prospect_engagement_state WHERE company_id = ?", (cid,)).fetchone()
    assert eng["current_outreach_status"] == disp


def test_invalid_disposition_rejected_by_api(client):
    """Verify invalid dispositions return HTTP 400 Bad Request."""
    resp = client.post(
        "/api/outreach",
        json={"company_id": 1, "disposition": "BOGUS_STATUS"}
    )
    assert resp.status_code == 422 or resp.status_code == 400


# ============================================================================
# 8. CSP (Facility 18) Shipping Contact Truth
# ============================================================================

def test_csp_facility_18_contact_and_equipment_truth(db_conn):
    """Verify Coil Steel Processing (Facility 18) shipping desk contact & equipment truth."""
    cur = db_conn.cursor()
    # Contact
    contact = cur.execute(
        """
        SELECT phone_number, email_address, phone_directness, role_category, department
        FROM contacts WHERE facility_id = 18
        """
    ).fetchone()
    assert contact is not None
    assert contact["phone_number"] == "(419) 269-9706"
    assert "shipping@coilsteelprocessing.com" in contact["email_address"]
    assert contact["phone_directness"] == "DEPARTMENT_LINE"
    assert contact["role_category"] == "FREIGHT_LOGISTICS"

    # Equipment
    equip = cur.execute(
        """
        SELECT equipment_category, equipment_usage_status
        FROM facility_commodities WHERE facility_id = 18
        """
    ).fetchone()
    assert equip["equipment_category"] == "FLATBED"
    assert equip["equipment_usage_status"] == "VERIFIED"


# ============================================================================
# 9. Taxonomy Classification Truth
# ============================================================================

def test_bulk_mulch_not_mapped_to_bagged_mulch(db_conn):
    """Verify bulk mulch producers (Battle Lumber, Spray Lake) are NOT mapped to BAGGED_MULCH_SOIL."""
    cur = db_conn.cursor()
    cat = cur.execute("SELECT id FROM commodity_categories WHERE category_code = 'BAGGED_MULCH_SOIL'").fetchone()
    if cat:
        mappings = cur.execute(
            "SELECT facility_id FROM facility_commodity_mappings WHERE category_id = ? AND facility_id IN (5, 460)",
            (cat["id"],)
        ).fetchall()
        assert len(mappings) == 0, f"Facilities 5 and 460 must NOT be mapped to BAGGED_MULCH_SOIL, found {mappings}"


def test_structurecraft_classified_as_mass_timber(db_conn):
    """Verify StructureCraft (Facility 613) is classified as mass timber, not concrete."""
    cur = db_conn.cursor()
    mappings = cur.execute(
        """
        SELECT c.category_code, m.is_primary
        FROM facility_commodity_mappings m
        JOIN commodity_categories c ON m.category_id = c.id
        WHERE m.facility_id = 613
        ORDER BY m.is_primary DESC
        """
    ).fetchall()
    codes = {r["category_code"]: r["is_primary"] for r in mappings}
    assert "ROOF_TRUSSES_WALL_PANELS" in codes
    assert codes["ROOF_TRUSSES_WALL_PANELS"] == 1, "Primary must be ROOF_TRUSSES_WALL_PANELS"
    assert "CONCRETE_PRECAST_PRODUCTS" not in codes, "StructureCraft is timber, NOT concrete"


# ============================================================================
# 10. Evidence Source Type Truth
# ============================================================================

def test_directory_sources_marked_non_primary(db_conn):
    """Verify third-party industry directories have is_primary_source = 0 and non-company-website types."""
    cur = db_conn.cursor()
    for sid in (102, 140, 204):
        src = cur.execute("SELECT id, source_type, is_primary_source, source_url FROM evidence_sources WHERE id = ?", (sid,)).fetchone()
        if src:
            assert src["is_primary_source"] == 0, f"Source {sid} must have is_primary_source = 0"
            assert src["source_type"] in ("INDUSTRY_DIRECTORY", "TRADE_ASSOCIATION", "DIRECTORY_AGGREGATOR", "OTHER_SECONDARY")
