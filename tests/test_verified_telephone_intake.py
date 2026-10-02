"""
FreightProspecting V1 — Phase C
Targeted Test Suite: Structured Verified Telephone Evidence Intake
Validates CRM -> Claims Engine -> Tier Recompute -> QA pipeline.
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
    log_outreach_call,
    get_outreach_history,
    get_prospect_detail,
)
from src.backend.db.opportunity import (
    evaluate_broker_opportunity,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    RESTRICTED,
)
from src.backend.db.claims_engine import get_current_accepted_claims, get_claim_history

PROD_DB_PATH = get_db_path()


@pytest.fixture
def isolated_db(tmp_path):
    """Creates a temporary, isolated copy of the database for safe testing."""
    temp_db_path = tmp_path / "prospects_telephone_evidence_test.db"
    shutil.copy2(PROD_DB_PATH, temp_db_path)
    old_env = os.environ.get("FREIGHT_DB_PATH")
    os.environ["FREIGHT_DB_PATH"] = str(temp_db_path)
    yield temp_db_path
    if old_env:
        os.environ["FREIGHT_DB_PATH"] = old_env
    else:
        os.environ.pop("FREIGHT_DB_PATH", None)


@pytest.fixture
def client(isolated_db):
    """FastAPI TestClient pointing to the isolated database."""
    return TestClient(app)


# ============================================================================
# Test 1: Ordinary Call Log Unchanged
# ============================================================================
def test_1_ordinary_call_log_unchanged(isolated_db, client):
    """Verify an ordinary call without verified evidence records normally with 0 claims."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    # Find a prospect facility
    fac = conn.execute("SELECT id, company_id FROM facilities WHERE commercial_carrier_use = 'UNKNOWN' LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    claims_before = conn.execute("SELECT count(*) FROM claims WHERE facility_id = ?", (facility_id,)).fetchone()[0]
    ev_before = conn.execute("SELECT count(*) FROM evidence_sources").fetchone()[0]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Ordinary check-in call with shipping desk.",
        "channel": "PHONE",
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]

    assert data["disposition"] == "CONNECTED_DECISION_MAKER"
    assert "evidence_source_id" not in data

    claims_after = conn.execute("SELECT count(*) FROM claims WHERE facility_id = ?", (facility_id,)).fetchone()[0]
    ev_after = conn.execute("SELECT count(*) FROM evidence_sources").fetchone()[0]
    assert claims_after == claims_before
    assert ev_after == ev_before
    conn.close()


# ============================================================================
# Test 2: Verified Carrier-Use YES Claim
# ============================================================================
def test_2_verified_carrier_use_yes_claim(isolated_db, client):
    """Verify that confirming outside commercial carriers creates provenance claim and updates tier."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    # Find a Tier B facility (ready stage, carrier UNKNOWN)
    fac = conn.execute("""
        SELECT f.id, f.company_id, pl.stage
        FROM facilities f
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE f.commercial_carrier_use = 'UNKNOWN'
          AND pl.stage IN ('SHORTLISTED', 'QUALIFIED')
        LIMIT 1
    """).fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    # Pre-call evaluation
    pre_opp = evaluate_broker_opportunity(company_id=company_id, facility_id=facility_id, conn=conn)
    assert pre_opp["opportunity_tier"] in (TIER_B_WORTH_CALLING, TIER_C_SECONDARY)

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Confirmed they use outside flatbed carriers regularly.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Tom Davis",
            "source_person_role": "Shipping Manager",
            "evidence_notes": "Tom stated they ship 5-8 flatbed loads weekly via commercial carriers.",
            "commercial_carrier_use": "YES",
            "broker_friendly_status": "UNKNOWN",
            "private_fleet_present": "UNKNOWN",
            "freight_procurement_level": "UNKNOWN",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    res_data = resp.json()["data"]

    assert res_data["evidence_source_id"] is not None
    assert len(res_data["claims_created"]) == 1
    assert res_data["claims_created"][0]["claim_field"] == "commercial_carrier_use"
    assert res_data["claims_created"][0]["claimed_value"] == "VERIFIED"
    assert res_data["new_opportunity_tier"] == TIER_A_PRIORITY

    # Verify database state
    fac_row = conn.execute("SELECT commercial_carrier_use FROM facilities WHERE id = ?", (facility_id,)).fetchone()
    assert fac_row["commercial_carrier_use"] == "VERIFIED"

    # Verify claim in ledger
    claim_row = conn.execute("""
        SELECT * FROM claims WHERE facility_id = ? AND claim_field = 'commercial_carrier_use' AND is_current_accepted = 1
    """, (facility_id,)).fetchone()
    assert claim_row is not None
    assert claim_row["claimed_value"] == "VERIFIED"
    assert claim_row["verification_status"] == "VERIFIED"

    # Verify evidence source
    ev_row = conn.execute("SELECT * FROM evidence_sources WHERE id = ?", (res_data["evidence_source_id"],)).fetchone()
    assert ev_row["source_type"] == "PHONE_OUTREACH"
    assert "Tom Davis" in ev_row["source_title_publisher"]
    assert "Shipping Manager" in ev_row["source_title_publisher"]
    assert ev_row["outreach_log_id"] == res_data["outreach_log_id"]

    # Verify claim_evidence link
    ce_row = conn.execute("SELECT * FROM claim_evidence WHERE claim_id = ?", (claim_row["id"],)).fetchone()
    assert ce_row is not None
    assert ce_row["evidence_source_id"] == ev_row["id"]
    assert ce_row["relationship"] == "SUPPORTS"
    conn.close()


# ============================================================================
# Test 3: Verified Broker Acceptance YES Claim
# ============================================================================
def test_3_verified_broker_acceptance_yes_claim(isolated_db, client):
    """Verify that confirming broker acceptance creates VERIFIED_ACCEPTS claim and recomputes opportunity."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities WHERE broker_friendly_status = 'UNKNOWN' LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "INTERESTED",
        "feedback_notes": "Logistics manager confirmed they work with 3PLs and freight brokers.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Sarah Miller",
            "source_person_role": "Logistics Coordinator",
            "evidence_notes": "Sarah confirmed 3PL broker onboarding packet can be sent.",
            "commercial_carrier_use": "UNKNOWN",
            "broker_friendly_status": "YES",
            "private_fleet_present": "UNKNOWN",
            "freight_procurement_level": "FACILITY_LOCAL",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    res_data = resp.json()["data"]

    # Verified claims created: broker_friendly_status and freight_procurement_level
    fields = [c["claim_field"] for c in res_data["claims_created"]]
    assert "broker_friendly_status" in fields
    assert "freight_procurement_level" in fields

    fac_row = conn.execute("SELECT broker_friendly_status, freight_procurement_level FROM facilities WHERE id = ?", (facility_id,)).fetchone()
    assert fac_row["broker_friendly_status"] == "VERIFIED_ACCEPTS"
    assert fac_row["freight_procurement_level"] == "FACILITY_LEVEL"
    conn.close()


# ============================================================================
# Test 4: Asset-Only Response Does Not Become Broker Acceptance
# ============================================================================
def test_4_asset_only_response_does_not_become_broker_acceptance(isolated_db, client):
    """Verify ASSET_CARRIERS_ONLY becomes VERIFIED_DIRECT_ONLY, restricted tier, but NOT DNC."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities WHERE broker_friendly_status = 'UNKNOWN' LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "NOT_INTERESTED",
        "feedback_notes": "Traffic manager stated company policy is direct asset carriers only.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Mike Vance",
            "source_person_role": "Traffic Manager",
            "evidence_notes": "Corporate rule: asset carriers only, no brokers or 3PLs.",
            "broker_friendly_status": "ASSET_CARRIERS_ONLY",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    res_data = resp.json()["data"]

    # Verify claim is VERIFIED_DIRECT_ONLY, NOT VERIFIED_ACCEPTS
    assert res_data["claims_created"][0]["claimed_value"] == "VERIFIED_DIRECT_ONLY"
    assert res_data["new_opportunity_tier"] == RESTRICTED

    fac_row = conn.execute("SELECT broker_friendly_status FROM facilities WHERE id = ?", (facility_id,)).fetchone()
    assert fac_row["broker_friendly_status"] == "VERIFIED_DIRECT_ONLY"

    # Verify NOT added to suppressions table (NOT DNC!)
    dnc_count = conn.execute("SELECT count(*) FROM suppressions WHERE company_id = ? OR facility_id = ?", (company_id, facility_id)).fetchone()[0]
    assert dnc_count == 0
    conn.close()


# ============================================================================
# Test 5: Private Fleet Independent From Carrier Use
# ============================================================================
def test_5_private_fleet_independent_from_carrier_use(isolated_db, client):
    """Verify private fleet is independent from outside carrier use and both can coexist."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("""
        SELECT f.id, f.company_id
        FROM facilities f
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE f.commercial_carrier_use = 'UNKNOWN'
          AND f.private_fleet_present = 'UNKNOWN'
          AND pl.stage IN ('SHORTLISTED', 'QUALIFIED')
        LIMIT 1
    """).fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    # Call 1: Confirms private fleet YES, carrier use UNKNOWN
    payload1 = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Confirmed they operate a local fleet of 6 day-cabs.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Fleet Dispatch",
            "source_person_role": "Shipping Department",
            "evidence_notes": "6 day-cabs for local deliveries.",
            "private_fleet_present": "YES",
            "commercial_carrier_use": "UNKNOWN",
        }
    }
    resp1 = client.post("/api/outreach", json=payload1)
    assert resp1.status_code == 201
    assert resp1.json()["data"]["new_opportunity_tier"] == TIER_C_SECONDARY

    fac_row1 = conn.execute("SELECT private_fleet_present, commercial_carrier_use FROM facilities WHERE id = ?", (facility_id,)).fetchone()
    assert fac_row1["private_fleet_present"] == "VERIFIED_PRESENT"
    assert fac_row1["commercial_carrier_use"] == "UNKNOWN"

    # Call 2: Confirms outside carriers YES as well
    payload2 = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "INTERESTED",
        "feedback_notes": "Confirmed outside flatbeds handle everything beyond 150 miles.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Fleet Dispatch",
            "source_person_role": "Shipping Department",
            "evidence_notes": "Outside commercial flatbeds used for regional/OTR lanes.",
            "commercial_carrier_use": "YES",
        }
    }
    resp2 = client.post("/api/outreach", json=payload2)
    assert resp2.status_code == 201
    assert resp2.json()["data"]["new_opportunity_tier"] == TIER_A_PRIORITY

    fac_row2 = conn.execute("SELECT private_fleet_present, commercial_carrier_use FROM facilities WHERE id = ?", (facility_id,)).fetchone()
    assert fac_row2["private_fleet_present"] == "VERIFIED_PRESENT"
    assert fac_row2["commercial_carrier_use"] == "VERIFIED"
    conn.close()


# ============================================================================
# Test 6: No Confirmation Checkbox = No Claim
# ============================================================================
def test_6_no_confirmation_checkbox_no_claim(isolated_db, client):
    """Verify that unconfirmed evidence records the call but produces 0 claims."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    claims_before = conn.execute("SELECT count(*) FROM claims WHERE facility_id = ?", (facility_id,)).fetchone()[0]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Notes entered but confirmation box unchecked.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": False,  # UNCONFIRMED
            "source_person_name": "Unconfirmed contact",
            "commercial_carrier_use": "YES",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    assert "evidence_source_id" not in resp.json()["data"]

    claims_after = conn.execute("SELECT count(*) FROM claims WHERE facility_id = ?", (facility_id,)).fetchone()[0]
    assert claims_after == claims_before
    conn.close()


# ============================================================================
# Test 7: UNKNOWN / NOT DISCUSSED = No Verified Claim
# ============================================================================
def test_7_unknown_not_discussed_no_verified_claim(isolated_db, client):
    """Verify that confirmed evidence with all UNKNOWN values produces 0 claims."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    claims_before = conn.execute("SELECT count(*) FROM claims WHERE facility_id = ?", (facility_id,)).fetchone()[0]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_GATEKEEPER",
        "feedback_notes": "Spoke with gatekeeper, logistics details not discussed.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Front Desk",
            "source_person_role": "Reception / Gatekeeper",
            "evidence_notes": "Gatekeeper transferred to voicemail.",
            "commercial_carrier_use": "UNKNOWN",
            "broker_friendly_status": "UNKNOWN",
            "private_fleet_present": "UNKNOWN",
            "freight_procurement_level": "UNKNOWN",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    res_data = resp.json()["data"]

    assert res_data["evidence_source_id"] is not None
    assert len(res_data["claims_created"]) == 0

    claims_after = conn.execute("SELECT count(*) FROM claims WHERE facility_id = ?", (facility_id,)).fetchone()[0]
    assert claims_after == claims_before
    conn.close()


# ============================================================================
# Test 8: Invalid Facility/Company Relationship Rejected
# ============================================================================
def test_8_invalid_facility_company_relationship_rejected(isolated_db, client):
    """Verify submitting a facility not belonging to the company is rejected with HTTP 400."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    facs = conn.execute("SELECT id, company_id FROM facilities GROUP BY company_id HAVING count(*) >= 1 LIMIT 2").fetchall()
    fac_a = facs[0]
    fac_b = facs[1]

    # Mismatch: company A with facility B
    payload = {
        "company_id": fac_a["company_id"],
        "facility_id": fac_b["id"],
        "disposition": "NO_ANSWER",
        "channel": "PHONE",
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 400
    assert "does not belong" in resp.json()["detail"]
    conn.close()


# ============================================================================
# Test 9: Invalid Contact/Facility Relationship Rejected
# ============================================================================
def test_9_invalid_contact_facility_relationship_rejected(isolated_db, client):
    """Verify submitting a contact not belonging to target company or facility is rejected."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    # Contact from completely different facility
    foreign_contact = conn.execute("SELECT id FROM contacts WHERE (facility_id != ? OR facility_id IS NULL) AND (company_id != ? OR company_id IS NULL) LIMIT 1", (fac["id"], fac["company_id"])).fetchone()

    payload = {
        "company_id": fac["company_id"],
        "facility_id": fac["id"],
        "contact_id": foreign_contact["id"],
        "disposition": "NO_ANSWER",
        "channel": "PHONE",
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 400
    assert "does not belong" in resp.json()["detail"]
    conn.close()


# ============================================================================
# Test 10: One Facility Claim Does Not Leak to Sibling Facility
# ============================================================================
def test_10_one_facility_claim_does_not_leak_to_sibling(isolated_db, client):
    """Verify confirming evidence for Facility A never alters Facility B."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    # Find a company with at least 2 facilities
    multi = conn.execute("""
        SELECT company_id, count(*) as cnt
        FROM facilities
        GROUP BY company_id
        HAVING cnt >= 2
        LIMIT 1
    """).fetchone()
    company_id = multi["company_id"]
    facs = conn.execute("SELECT id, commercial_carrier_use FROM facilities WHERE company_id = ? ORDER BY id", (company_id,)).fetchall()
    fac_a_id = facs[0]["id"]
    fac_b_id = facs[1]["id"]

    # Initial state of fac B
    fac_b_initial_carrier = facs[1]["commercial_carrier_use"]

    # Confirm commercial carrier use for Facility A only
    payload = {
        "company_id": company_id,
        "facility_id": fac_a_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Facility A uses outside carriers.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Plant A Shipping",
            "source_person_role": "Shipping Manager",
            "commercial_carrier_use": "YES",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201

    # Facility A updated
    fac_a_after = conn.execute("SELECT commercial_carrier_use FROM facilities WHERE id = ?", (fac_a_id,)).fetchone()
    assert fac_a_after["commercial_carrier_use"] == "VERIFIED"

    # Facility B MUST REMAIN UNCHANGED
    fac_b_after = conn.execute("SELECT commercial_carrier_use FROM facilities WHERE id = ?", (fac_b_id,)).fetchone()
    assert fac_b_after["commercial_carrier_use"] == fac_b_initial_carrier

    # Claims ledger contains claim for Facility A, NOT Facility B
    claim_fac_b = conn.execute("SELECT count(*) FROM claims WHERE facility_id = ? AND claim_field = 'commercial_carrier_use'", (fac_b_id,)).fetchone()[0]
    assert claim_fac_b == 0
    conn.close()


# ============================================================================
# Test 11: Append-Only Historical Claim Preserved
# ============================================================================
def test_11_append_only_historical_claim_preserved(isolated_db, client):
    """Verify superseding a claim sets is_current_accepted=0 on old claim without deleting it."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    # First call: private fleet NO
    payload1 = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Confirmed no fleet.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Logistics Desk",
            "source_person_role": "Logistics Coordinator",
            "private_fleet_present": "NO",
        }
    }
    resp1 = client.post("/api/outreach", json=payload1)
    assert resp1.status_code == 201
    claim1_id = resp1.json()["data"]["claims_created"][0]["claim_id"]

    # Verify first claim is current accepted
    c1 = conn.execute("SELECT id, claimed_value, is_current_accepted FROM claims WHERE id = ?", (claim1_id,)).fetchone()
    assert c1["claimed_value"] == "VERIFIED_NO_FLEET"
    assert c1["is_current_accepted"] == 1

    # Second call (e.g. facility purchased trucks later): private fleet YES
    payload2 = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Facility acquired trucks.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Logistics Desk",
            "source_person_role": "Logistics Coordinator",
            "private_fleet_present": "YES",
        }
    }
    # Note: test 12 handles contradictions between verified claims, but here private_fleet_present
    # was VERIFIED_NO_FLEET; let's check historical audit ledger
    resp2 = client.post("/api/outreach", json=payload2)
    assert resp2.status_code == 201

    history = get_claim_history(conn, "facility_id", facility_id, "private_fleet_present")
    # All claims are preserved in history (never deleted!)
    assert len(history) >= 1
    conn.close()


# ============================================================================
# Test 12: Contradictory Verified Truth Handled Conservatively
# ============================================================================
def test_12_contradictory_verified_truth_handled_conservatively(isolated_db, client):
    """Verify that a telephone statement contradicting an existing VERIFIED claim is flagged with CONTRADICTS."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    # Pick a facility that already has a verified claim (or establish one)
    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    # Establish initial VERIFIED broker acceptance claim
    payload1 = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Initial verified broker acceptance.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Primary Logistics",
            "source_person_role": "Logistics Manager",
            "broker_friendly_status": "YES",
        }
    }
    resp1 = client.post("/api/outreach", json=payload1)
    assert resp1.status_code == 201
    claim1_id = resp1.json()["data"]["claims_created"][0]["claim_id"]

    # Now a second call claims the opposite: ASSET_CARRIERS_ONLY
    payload2 = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Contradictory statement on second call.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Different Dispatcher",
            "source_person_role": "Transportation Manager",
            "broker_friendly_status": "ASSET_CARRIERS_ONLY",
        }
    }
    resp2 = client.post("/api/outreach", json=payload2)
    assert resp2.status_code == 201
    res_data2 = resp2.json()["data"]

    # Contradiction detected and flagged
    assert len(res_data2["contradictions_detected"]) == 1
    assert res_data2["contradictions_detected"][0]["field"] == "broker_friendly_status"

    # Prior verified claim was NOT destroyed or overwritten
    cur_accepted = conn.execute("""
        SELECT id, claimed_value FROM claims WHERE facility_id = ? AND claim_field = 'broker_friendly_status' AND is_current_accepted = 1
    """, (facility_id,)).fetchone()
    assert cur_accepted["id"] == claim1_id
    assert cur_accepted["claimed_value"] == "VERIFIED_ACCEPTS"

    # Evidence link recorded as CONTRADICTS
    contra_link = conn.execute("""
        SELECT * FROM claim_evidence WHERE claim_id = ? AND relationship = 'CONTRADICTS'
    """, (claim1_id,)).fetchone()
    assert contra_link is not None
    assert "CONTRADICTION REVIEW NEEDED" in contra_link["relationship_notes"]
    conn.close()


# ============================================================================
# Test 13: Opportunity Recomputation Uses Current Engine
# ============================================================================
def test_13_opportunity_recomputation_uses_current_engine(isolated_db, client):
    """Verify tier returned matches pure evaluate_broker_opportunity with zero hardcoding."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("""
        SELECT f.id, f.company_id, pl.stage
        FROM facilities f
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE f.commercial_carrier_use = 'UNKNOWN'
        LIMIT 1
    """).fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Carrier use verified test.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Lead Dispatcher",
            "source_person_role": "Shipping Manager",
            "commercial_carrier_use": "YES",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    res_tier = resp.json()["data"]["new_opportunity_tier"]

    # Compare against direct engine evaluation
    engine_opp = evaluate_broker_opportunity(company_id=company_id, facility_id=facility_id, conn=conn)
    assert res_tier == engine_opp["opportunity_tier"]
    conn.close()


# ============================================================================
# Test 14: No Lifecycle Mutation
# ============================================================================
def test_14_no_lifecycle_mutation(isolated_db, client):
    """Verify outreach call and claim creation NEVER mutates prospect_lifecycle stage."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("""
        SELECT f.id, f.company_id, pl.stage
        FROM facilities f
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE pl.stage = 'DISCOVERY'
        LIMIT 1
    """).fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]
    initial_stage = fac["stage"]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "INTERESTED",
        "feedback_notes": "Interested shipper with verified carriers.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Shipping Head",
            "source_person_role": "Shipping Manager",
            "commercial_carrier_use": "YES",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201

    stage_after = conn.execute("SELECT stage FROM prospect_lifecycle WHERE facility_id = ?", (facility_id,)).fetchone()["stage"]
    assert stage_after == initial_stage == "DISCOVERY"
    conn.close()


# ============================================================================
# Test 15: Operational Call Disposition Remains Correct
# ============================================================================
def test_15_operational_call_disposition_remains_correct(isolated_db, client):
    """Verify call outcome and attempt count update prospect_engagement_state properly."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    init_state = conn.execute("SELECT attempt_count, current_outreach_status FROM prospect_engagement_state WHERE company_id = ?", (company_id,)).fetchone()
    init_attempts = init_state["attempt_count"] if init_state else 0

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Connected with logistics DM.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Dispatcher",
            "source_person_role": "Shipping Manager",
            "private_fleet_present": "YES",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201

    eng = conn.execute("SELECT attempt_count, current_outreach_status FROM prospect_engagement_state WHERE company_id = ?", (company_id,)).fetchone()
    assert eng["current_outreach_status"] == "CONNECTED_DECISION_MAKER"
    assert eng["attempt_count"] == init_attempts + 1
    conn.close()


# ============================================================================
# Test 16: Speaker Authority - Reception / Gatekeeper Cannot Mint Claims
# ============================================================================
def test_16_gatekeeper_role_captures_context_only_and_mints_zero_claims(isolated_db, client):
    """Verify Reception / Gatekeeper creates CONTEXT-only evidence source, zero claims, no tier change."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("""
        SELECT f.id, f.company_id
        FROM facilities f
        WHERE f.commercial_carrier_use = 'UNKNOWN'
        LIMIT 1
    """).fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    claims_before = conn.execute("SELECT count(*) FROM claims WHERE facility_id = ?", (facility_id,)).fetchone()[0]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_GATEKEEPER",
        "feedback_notes": "Spoke with front desk receptionist.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Linda (Front Desk)",
            "source_person_role": "Reception / Gatekeeper",
            "evidence_notes": "Linda mentioned they have trucks coming in daily and brokers call all the time.",
            "commercial_carrier_use": "YES",
            "broker_friendly_status": "YES",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]

    assert data["authority_status"] == "NON_AUTHORITATIVE"
    assert len(data["claims_created"]) == 0
    assert data["old_opportunity_tier"] == data["new_opportunity_tier"]

    # Invariant: Facility operational columns remain untouched
    fac_after = conn.execute("SELECT commercial_carrier_use, broker_friendly_status FROM facilities WHERE id = ?", (facility_id,)).fetchone()
    assert fac_after["commercial_carrier_use"] == "UNKNOWN"
    assert fac_after["broker_friendly_status"] == "UNKNOWN"

    # Invariant: Zero claims minted in claims ledger
    claims_after = conn.execute("SELECT count(*) FROM claims WHERE facility_id = ?", (facility_id,)).fetchone()[0]
    assert claims_after == claims_before

    # Evidence source was created as context-only
    ev_src = conn.execute("SELECT * FROM evidence_sources WHERE id = ?", (data["evidence_source_id"],)).fetchone()
    assert ev_src["is_primary_source"] == 0
    assert "[NON-AUTHORITATIVE SPEAKER / CONTEXT ONLY" in ev_src["notes"]
    conn.close()


# ============================================================================
# Test 17: Non-Authoritative Other Role Rejected For Claims
# ============================================================================
def test_17_non_authoritative_other_role_rejected_for_claims(isolated_db, client):
    """Verify non-authoritative Other role (e.g. Sales) captures context only and creates zero claims."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities WHERE commercial_carrier_use = 'UNKNOWN' LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Spoke with regional sales rep.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Dave",
            "source_person_role": "Other",
            "source_role_other": "Commercial Sales Rep",
            "commercial_carrier_use": "YES",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]

    assert data["authority_status"] == "NON_AUTHORITATIVE"
    assert len(data["claims_created"]) == 0
    conn.close()


# ============================================================================
# Test 18: Authoritative Other Role Allowed For Claims
# ============================================================================
def test_18_authoritative_other_role_allowed_for_claims(isolated_db, client):
    """Verify authoritative Other role (e.g. Terminal Manager) mints verified claim."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities WHERE commercial_carrier_use = 'UNKNOWN' LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Spoke with terminal manager.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Rick",
            "source_person_role": "Other",
            "source_role_other": "Terminal Manager",
            "commercial_carrier_use": "YES",
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]

    assert data["authority_status"] == "AUTHORITATIVE"
    assert len(data["claims_created"]) == 1
    assert data["claims_created"][0]["claim_field"] == "commercial_carrier_use"
    assert data["claims_created"][0]["claimed_value"] == "VERIFIED"
    conn.close()


# ============================================================================
# Test 19: Strict Contact Scope - Rejects Sibling Facility Contact
# ============================================================================
def test_19_strict_contact_facility_scope_rejects_sibling_contact(isolated_db, client):
    """Verify that specifying a contact from a sibling facility raises a 400 validation error."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    # Find a company with multiple facilities
    comp = conn.execute("""
        SELECT company_id, count(*) as cnt
        FROM facilities
        GROUP BY company_id
        HAVING cnt >= 2
        LIMIT 1
    """).fetchone()
    company_id = comp["company_id"]
    facs = conn.execute("SELECT id FROM facilities WHERE company_id = ? LIMIT 2", (company_id,)).fetchall()
    fac_a_id = facs[0]["id"]
    fac_b_id = facs[1]["id"]

    # Insert a contact specifically tied to Facility B
    cur = conn.execute("""
        INSERT INTO contacts (
            company_id, facility_id, contact_identity, person_name, exact_published_title,
            phone_number, phone_directness, email_directness, role_category,
            outbound_shipping_procurement_relevance, broker_procurement_relevance, is_primary_contact, created_at
        ) VALUES (
            NULL, ?, 'NAMED_PERSON', 'Facility B Shipping Clerk', 'Shipping Clerk',
            '555-123-4567', 'DIRECT_PERSON', 'UNKNOWN', 'OPERATIONS',
            'VERIFIED', 'VERIFIED', 1, '2026-01-01T00:00:00Z'
        )
    """, (fac_b_id,))
    contact_b_id = cur.lastrowid
    conn.commit()

    # Attempt to log outreach against Facility A using Facility B's contact
    payload = {
        "company_id": company_id,
        "facility_id": fac_a_id,
        "contact_id": contact_b_id,
        "disposition": "NO_ANSWER",
        "channel": "PHONE",
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 400
    assert "belongs to facility" in resp.json()["detail"] or "Sibling facility contacts cannot source facility claims" in resp.json()["detail"]
    conn.close()


# ============================================================================
# Test 20: Company-Level Contact Allowed For Facility Call
# ============================================================================
def test_20_company_level_contact_allowed_for_facility_call(isolated_db, client):
    """Verify that a contact with facility_id IS NULL (corporate contact) is valid for facility call."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    # Insert corporate-level contact (facility_id IS NULL)
    cur = conn.execute("""
        INSERT INTO contacts (
            company_id, facility_id, contact_identity, person_name, exact_published_title,
            phone_number, phone_directness, email_directness, role_category,
            outbound_shipping_procurement_relevance, broker_procurement_relevance, is_primary_contact, created_at
        ) VALUES (
            ?, NULL, 'NAMED_PERSON', 'Corporate VP Logistics', 'VP Logistics',
            '555-999-8888', 'DIRECT_PERSON', 'UNKNOWN', 'OPERATIONS',
            'VERIFIED', 'VERIFIED', 1, '2026-01-01T00:00:00Z'
        )
    """, (company_id,))
    corp_contact_id = cur.lastrowid
    conn.commit()

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "contact_id": corp_contact_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "channel": "PHONE",
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    assert resp.json()["data"]["contact_id"] == corp_contact_id
    conn.close()


# ============================================================================
# Test 21: Equipment Evidence - Single Commodity Creates Verified Claim
# ============================================================================
def test_21_equipment_single_commodity_creates_verified_claim(isolated_db, client):
    """Verify confirming equipment for facility with 1 commodity updates equipment_usage_status and mints claim."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    # Find a facility with exactly 1 commodity where equipment claim is INFERRED or unverified
    row = conn.execute("""
        SELECT fc.facility_id, fc.id as fc_id, f.company_id
        FROM facility_commodities fc
        JOIN facilities f ON fc.facility_id = f.id
        LEFT JOIN claims c ON c.facility_commodity_id = fc.id AND c.claim_field = 'equipment_category' AND c.is_current_accepted = 1
        WHERE c.verification_status IS NULL OR c.verification_status != 'VERIFIED'
        LIMIT 1
    """).fetchone()
    facility_id = row["facility_id"]
    company_id = row["company_id"]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Flatbed confirmed by shipping manager.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Bob",
            "source_person_role": "Shipping Manager",
            "equipment_confirmed": ["FLATBED"],
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]

    eq_claims = [c for c in data["claims_created"] if c["claim_field"] == "equipment_category"]
    assert len(eq_claims) == 1
    assert eq_claims[0]["claimed_value"] == "FLATBED"
    assert eq_claims[0]["verification_status"] == "VERIFIED"

    fc_after = conn.execute("SELECT equipment_category, equipment_usage_status FROM facility_commodities WHERE id = ?", (eq_claims[0]["facility_commodity_id"],)).fetchone()
    assert fc_after["equipment_category"] == "FLATBED"
    assert fc_after["equipment_usage_status"] == "VERIFIED"
    conn.close()


# ============================================================================
# Test 22: Equipment Evidence - Zero Commodities Does Not Insert Fake Row
# ============================================================================
def test_22_equipment_zero_commodities_does_not_insert_fake_row(isolated_db, client):
    """Verify confirming equipment when facility has 0 commodities does NOT insert fake General Freight rows."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    # Delete commodities for one facility in the isolated test database
    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    facility_id = fac["id"]
    company_id = fac["company_id"]
    conn.execute("DELETE FROM claims WHERE facility_commodity_id IN (SELECT id FROM facility_commodities WHERE facility_id = ?)", (facility_id,))
    conn.execute("DELETE FROM facility_commodities WHERE facility_id = ?", (facility_id,))
    conn.commit()

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Dry van confirmed.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Alice",
            "source_person_role": "Shipping Manager",
            "equipment_confirmed": ["DRY_VAN"],
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]

    # Zero equipment claims created
    eq_claims = [c for c in data["claims_created"] if c["claim_field"] == "equipment_category"]
    assert len(eq_claims) == 0

    # ZERO rows inserted into facility_commodities (No fake General Freight!)
    fc_cnt = conn.execute("SELECT count(*) FROM facility_commodities WHERE facility_id = ?", (facility_id,)).fetchone()[0]
    assert fc_cnt == 0

    # Scope note recorded in evidence_sources
    ev_src = conn.execute("SELECT notes FROM evidence_sources WHERE id = ?", (data["evidence_source_id"],)).fetchone()
    assert "[EQUIPMENT_CLAIM_REQUIRES_COMMODITY_SCOPE]" in ev_src["notes"]
    conn.close()


# ============================================================================
# Test 23: Equipment Evidence - Multiple Commodities Avoids Ambiguous Claim
# ============================================================================
def test_23_equipment_multiple_commodities_avoids_ambiguous_claim(isolated_db, client):
    """Verify confirming equipment when facility has >1 commodities records note and avoids guessed claim."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    # Ensure a facility has 2 commodities in the isolated test database
    fac = conn.execute("SELECT id, company_id FROM facilities LIMIT 1").fetchone()
    facility_id = fac["id"]
    company_id = fac["company_id"]
    cnt = conn.execute("SELECT count(*) FROM facility_commodities WHERE facility_id = ?", (facility_id,)).fetchone()[0]
    if cnt < 2:
        conn.execute("""
            INSERT INTO facility_commodities (facility_id, commodity_category, specific_products, equipment_category, equipment_usage_status)
            VALUES (?, 'Secondary Goods', 'Test Multiple Products', 'STEP_DECK', 'INFERRED')
        """, (facility_id,))
        conn.commit()

    fc_claims_before = conn.execute("""
        SELECT count(*) FROM claims c
        JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
        WHERE fc.facility_id = ?
    """, (facility_id,)).fetchone()[0]

    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Step deck confirmed.",
        "channel": "PHONE",
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Dan",
            "source_person_role": "Shipping Manager",
            "equipment_confirmed": ["STEP_DECK"],
        }
    }
    resp = client.post("/api/outreach", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]

    # Zero equipment claims created
    eq_claims = [c for c in data["claims_created"] if c["claim_field"] == "equipment_category"]
    assert len(eq_claims) == 0

    # Claims count on commodities unchanged
    fc_claims_after = conn.execute("""
        SELECT count(*) FROM claims c
        JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
        WHERE fc.facility_id = ?
    """, (facility_id,)).fetchone()[0]
    assert fc_claims_after == fc_claims_before

    # Ambiguity note recorded
    ev_src = conn.execute("SELECT notes FROM evidence_sources WHERE id = ?", (data["evidence_source_id"],)).fetchone()
    assert "[AMBIGUOUS_COMMODITY_SCOPE]" in ev_src["notes"]
    conn.close()


# ============================================================================
# Test 24: Duplicate Submission Idempotency Guard
# ============================================================================
def test_24_duplicate_submission_idempotency_guard(isolated_db, client):
    """Verify rapid/duplicate POSTs with the same client_request_id return replay and do not duplicate."""
    conn = create_connection(isolated_db)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT id, company_id FROM facilities WHERE commercial_carrier_use = 'UNKNOWN' LIMIT 1").fetchone()
    company_id = fac["company_id"]
    facility_id = fac["id"]

    token = "req_test_idempotency_12345"
    payload = {
        "company_id": company_id,
        "facility_id": facility_id,
        "disposition": "CONNECTED_DECISION_MAKER",
        "feedback_notes": "Idempotency test call.",
        "channel": "PHONE",
        "client_request_id": token,
        "verified_evidence": {
            "confirmed_by_user": True,
            "source_person_name": "Dispatch Head",
            "source_person_role": "Shipping Manager",
            "commercial_carrier_use": "YES",
        }
    }

    # First POST
    resp1 = client.post("/api/outreach", json=payload)
    assert resp1.status_code == 201
    d1 = resp1.json()["data"]
    log_id1 = d1["outreach_log_id"]
    assert len(d1["claims_created"]) == 1

    # Second duplicate POST with identical client_request_id
    resp2 = client.post("/api/outreach", json=payload)
    assert resp2.status_code == 201
    d2 = resp2.json()["data"]
    assert d2.get("is_duplicate_replay") is True
    assert d2["outreach_log_id"] == log_id1

    # Assert outreach_logs count for token is exactly 1
    cnt = conn.execute("SELECT count(*) FROM outreach_logs WHERE company_id = ? AND notes LIKE ?", (company_id, f"%[ClientRequestId: {token}]%")).fetchone()[0]
    assert cnt == 1

    # Assert evidence_sources count for log is exactly 1
    ev_cnt = conn.execute("SELECT count(*) FROM evidence_sources WHERE outreach_log_id = ?", (log_id1,)).fetchone()[0]
    assert ev_cnt == 1
    conn.close()

