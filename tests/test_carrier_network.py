"""
Comprehensive Pytest Test Suite for Carrier & Capacity Network
Tests:
- Schema migration idempotency & triggers
- Carrier identity & USDOT/MC deduplication
- Equipment & capacity postings lifecycle
- Append-only carrier outreach logs (UPDATE/DELETE triggers)
- Preserved quotes history
- Scoped carrier suppressions
- Deterministic matching engine (hard exclusions, explainability, UNKNOWN neutrality, cross-border)
- Team ownership (claim, conflict, transfer, release)
- API and view endpoints
"""

import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.backend.db.connection import get_db_path
from src.backend.db import carrier_schema, carrier_service
from src.backend.matching.engine import (
    haversine_distance_miles,
    is_cross_border_lane,
    check_hard_exclusions,
    evaluate_match_score,
)
from src.backend.main import app


@pytest.fixture(autouse=True)
def setup_carrier_schema():
    """Ensure carrier schema is applied to the isolated test database."""
    db_path = get_db_path()
    carrier_schema.apply_carrier_schema_migration(db_path)


@pytest.fixture(scope="module", autouse=True)
def carrier_module_db_cleanup():
    yield
    # Clean up test data after all carrier tests finish so session database remains clean
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM capacity_postings")
        conn.execute("DELETE FROM carrier_quotes")
        conn.execute("DELETE FROM carrier_suppressions")
        conn.execute("DELETE FROM carrier_assignments")
        conn.execute("DELETE FROM carrier_assignment_history")
        conn.execute("DELETE FROM carrier_engagement_state")
        conn.execute("DELETE FROM load_opportunities WHERE id > 0")
        conn.execute("DROP TRIGGER IF EXISTS trg_carrier_outreach_logs_no_delete")
        conn.execute("DELETE FROM carrier_outreach_logs")
        conn.executescript(carrier_schema.CARRIER_TRIGGERS)
        conn.execute("DELETE FROM carriers WHERE legal_name LIKE '%Apex%' OR legal_name LIKE '%Outreach%' OR legal_name LIKE '%Quoting%' OR legal_name LIKE '%Blacklisted%' OR legal_name LIKE '%Claimable%' OR legal_name LIKE '%API Test%'")
        conn.commit()


# ============================================================================
# 1. SCHEMA & MIGRATION IDEMPOTENCY
# ============================================================================

def test_carrier_schema_migration_is_idempotent():
    """Running migration multiple times must not error and preserves schema."""
    db_path = get_db_path()
    res1 = carrier_schema.apply_carrier_schema_migration(db_path)
    res2 = carrier_schema.apply_carrier_schema_migration(db_path)
    assert res1["status"] == "SUCCESS"
    assert res2["status"] == "SUCCESS"

    with sqlite3.connect(db_path) as conn:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "carriers" in tables
        assert "carrier_lane_activity" in tables
        assert "capacity_postings" in tables
        assert "carrier_outreach_logs" in tables
        assert "carrier_quotes" in tables
        assert "carrier_suppressions" in tables
        assert "carrier_assignments" in tables
        assert "carrier_assignment_history" in tables

        triggers = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()]
        assert "trg_carrier_outreach_logs_no_update" in triggers
        assert "trg_carrier_outreach_logs_no_delete" in triggers
        assert "trg_carrier_outreach_logs_no_replace" in triggers


# ============================================================================
# 2. CARRIER IDENTITY & DEDUPLICATION
# ============================================================================

def test_carrier_creation_and_deduplication():
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        c1 = carrier_service.create_or_update_carrier(conn, {
            "legal_name": "Apex Freight Logistics LLC",
            "country": "US",
            "physical_state_prov": "IL",
            "physical_city": "Chicago",
            "usdot_number": "9988112",
            "mc_number": "MC776655",
        }, user_id=1)
        assert c1["id"] is not None
        assert c1["legal_name"] == "Apex Freight Logistics LLC"
        c1_id = c1["id"]

        # Attempting to create carrier with same USDOT must update/dedup the existing carrier
        c2 = carrier_service.create_or_update_carrier(conn, {
            "legal_name": "Apex Freight Logistics LLC Updated",
            "country": "US",
            "physical_state_prov": "IL",
            "physical_city": "Chicago",
            "usdot_number": "9988112",
        }, user_id=1)
        assert c2["id"] == c1_id

        # Total carriers with this USDOT must remain exactly 1
        count = conn.execute("SELECT count(*) FROM carriers WHERE usdot_number = '9988112'").fetchone()[0]
        assert count == 1


# ============================================================================
# 3. APPEND-ONLY CARRIER OUTREACH (TRIGGER ENFORCEMENT)
# ============================================================================

def test_append_only_carrier_outreach_logs():
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        c = carrier_service.create_or_update_carrier(conn, {
            "legal_name": "Outreach Protected Freight",
            "country": "US",
            "physical_state_prov": "OH",
            "physical_city": "Columbus",
        }, user_id=1)
        cid = c["id"]

        log = carrier_service.log_carrier_outreach_call(
            conn=conn,
            carrier_id=cid,
            user_id=1,
            disposition="INTERESTED",
            notes="Discussed flatbed availability for next week."
        )
        log_id = log["id"]

        # Direct UPDATE must fail due to trigger
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(
                "UPDATE carrier_outreach_logs SET notes = 'Tampered' WHERE id = ?",
                (log_id,)
            )

        # Direct DELETE must fail due to trigger
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(
                "DELETE FROM carrier_outreach_logs WHERE id = ?",
                (log_id,)
            )


# ============================================================================
# 4. CARRIER QUOTES PRESERVATION
# ============================================================================

def test_carrier_quotes_preservation():
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        c = carrier_service.create_or_update_carrier(conn, {
            "legal_name": "Quoting Carrier LLC",
            "country": "US",
            "physical_state_prov": "IN",
            "physical_city": "Indianapolis",
        }, user_id=1)
        cid = c["id"]

        # Ensure a load opportunity exists for quote testing
        cur = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        fac_row = conn.execute("SELECT id FROM facilities LIMIT 1").fetchone()
        fac_id = fac_row[0] if fac_row else 1
        cur.execute("""
            INSERT INTO load_opportunities (
                facility_id, load_status, equipment_required,
                origin_city, origin_state_prov, origin_country,
                dest_city, dest_state_prov, dest_country,
                shipper_target_rate, carrier_target_cost, gross_margin, margin_pct, observed_at, created_at
            ) VALUES (?, 'IDENTIFIED', 'FLATBED', 'Chicago', 'IL', 'US', 'Atlanta', 'GA', 'US', 2500, 2100, 400.0, 16.0, ?, ?)
        """, (fac_id, now, now))
        load_id = cur.lastrowid
        conn.commit()

        # Round 1 quote
        q1 = carrier_service.add_carrier_quote(
            conn=conn,
            carrier_id=cid,
            load_id=load_id,
            author_user_id=1,
            quoted_amount=2200.0,
            notes="Initial quote submitted"
        )
        assert q1["id"] is not None

        # Round 2 quote (negotiation)
        q2 = carrier_service.add_carrier_quote(
            conn=conn,
            carrier_id=cid,
            load_id=load_id,
            author_user_id=1,
            quoted_amount=2050.0,
            notes="Counter offer accepted for consideration"
        )
        assert q2["id"] is not None

        # Verify both records exist and earlier quote is NOT overwritten
        quotes = carrier_service.get_carrier_quotes(conn=conn, load_id=load_id, carrier_id=cid)
        assert len(quotes) == 2
        # Ordered by id DESC
        assert quotes[0]["quoted_amount"] == 2050.0
        assert quotes[1]["quoted_amount"] == 2200.0

        # Clean up temporary test records so session DB remains clean
        cur.execute("DELETE FROM carrier_quotes WHERE load_opportunity_id = ?", (load_id,))
        cur.execute("DELETE FROM load_opportunities WHERE id = ?", (load_id,))
        conn.commit()


# ============================================================================
# 5. CARRIER SUPPRESSIONS
# ============================================================================

def test_carrier_suppression_blocks_matching():
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        c = carrier_service.create_or_update_carrier(conn, {
            "legal_name": "Blacklisted Express Inc",
            "country": "US",
            "physical_state_prov": "GA",
            "physical_city": "Atlanta",
        }, user_id=1)
        cid = c["id"]

        # Add capacity
        cap = carrier_service.add_capacity_posting(conn, cid, {
            "equipment_type": "FLATBED",
            "available_city": "Chicago",
            "available_state_prov": "IL",
            "available_country": "US",
            "destination_city": "Atlanta",
            "destination_state_prov": "GA",
            "destination_country": "US",
            "available_date_start": "2026-10-15",
            "available_date_end": "2026-10-25",
        }, user_id=1)

        load = {
            "id": 99,
            "equipment_required": "FLATBED",
            "origin_city": "Chicago",
            "origin_state_prov": "IL",
            "origin_country": "US",
            "dest_city": "Atlanta",
            "dest_state_prov": "GA",
            "dest_country": "US",
            "pickup_date_earliest": "2026-10-16",
        }

        carrier_obj = dict(c)

        # Without suppression, should pass hard exclusions
        passed, reason = check_hard_exclusions(load, carrier_obj, cap, [])
        assert passed is True
        assert reason is None

        # Add carrier suppression
        carrier_service.add_carrier_suppression(
            conn=conn,
            scope_type="CARRIER",
            carrier_id=cid,
            reason_notes="Consistent late arrivals and insurance lapse",
            suppression_status="DO_NOT_USE"
        )

        suppressions = carrier_service.get_carrier_suppressions(conn, carrier_id=cid)
        passed_supp, reason_supp = check_hard_exclusions(load, carrier_obj, cap, suppressions)
        assert passed_supp is False
        assert "suppressed" in reason_supp.lower()


# ============================================================================
# 6. DETERMINISTIC MATCHING ENGINE & HARD EXCLUSIONS
# ============================================================================

def test_matching_engine_hard_exclusions():
    load = {
        "id": 101,
        "equipment_required": "FLATBED",
        "origin_city": "Detroit",
        "origin_state_prov": "MI",
        "origin_country": "US",
        "dest_city": "Toronto",
        "dest_state_prov": "ON",
        "dest_country": "CA",
        "pickup_date_earliest": "2026-10-20",
        "pickup_date_latest": "2026-10-22",
        "carrier_target_cost": 2100.0,
    }

    carrier_base = {
        "id": 501,
        "legal_name": "Test Freight Inc",
        "operating_status": "VERIFIED_AUTHORIZED",
        "cross_border_capability": "US_CANADA_CAPABLE",
    }

    # Case 1: Equipment mismatch (DRY_VAN vs FLATBED)
    cap_bad_eq = {
        "id": 1,
        "carrier_id": 501,
        "equipment_type": "DRY_VAN",
        "available_city": "Detroit",
        "available_state_prov": "MI",
        "available_date_start": "2026-10-20",
        "available_date_end": "2026-10-25",
        "capacity_status": "TRUCK_CONFIRMED_AVAILABLE_NOW",
    }
    p1, r1 = check_hard_exclusions(load, carrier_base, cap_bad_eq, [])
    assert p1 is False
    assert "Equipment mismatch" in r1

    # Case 2: Cross-border mismatch (Load is US->CA, carrier is US_ONLY)
    carrier_domestic = dict(carrier_base, cross_border_capability="US_ONLY")
    cap_good = dict(cap_bad_eq, equipment_type="FLATBED")
    p2, r2 = check_hard_exclusions(load, carrier_domestic, cap_good, [])
    assert p2 is False
    assert "cross-border" in r2.lower()

    # Case 3: Out of service authority
    carrier_oos = dict(carrier_base, operating_status="VERIFIED_OUT_OF_SERVICE")
    p3, r3 = check_hard_exclusions(load, carrier_oos, cap_good, [])
    assert p3 is False
    assert "authority" in r3.lower()

    # Case 4: Expired capacity
    cap_expired = dict(cap_good, capacity_status="EXPIRED")
    p4, r4 = check_hard_exclusions(load, carrier_base, cap_expired, [])
    assert p4 is False

    # Case 5: Valid match with UNKNOWN fields remaining neutral (0 pts)
    # Target cost unknown, destination unknown on capacity
    cap_neutral = {
        "id": 2,
        "carrier_id": 501,
        "equipment_type": "FLATBED",
        "available_city": "Detroit",
        "available_state_prov": "MI",
        "destination_city": None,
        "destination_state_prov": None,
        "available_date_start": "2026-10-20",
        "available_date_end": "2026-10-25",
        "capacity_status": "TRUCK_CONFIRMED_AVAILABLE_NOW",
        "desired_rate": None,  # Carrier cost UNKNOWN
    }
    p5, r5 = check_hard_exclusions(load, carrier_base, cap_neutral, [])
    assert p5 is True

    score_result = evaluate_match_score(load, carrier_base, cap_neutral, [], [])
    assert score_result["score_percent"] > 0
    # Explanations must be non-empty and explainable
    assert len(score_result["explanations"]) > 0
    # Must have neutral explanations acknowledging unknown fields without negative penalties
    neutral_items = [e for e in score_result["explanations"] if e["type"] == "neutral"]
    assert len(neutral_items) > 0


# ============================================================================
# 7. TEAM OWNERSHIP & EXCLUSIVE CLAIMING
# ============================================================================

def test_team_ownership_and_exclusive_claim():
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        c = carrier_service.create_or_update_carrier(conn, {
            "legal_name": "Claimable Transport LLC",
            "country": "US",
            "physical_state_prov": "WI",
            "physical_city": "Milwaukee",
        }, user_id=1)
        cid = c["id"]

        # Selena (ID: 1) claims carrier
        c1 = carrier_service.claim_carrier(conn, cid, user_id=1)
        assert c1["owner_id"] == 1

        # Kevin (ID: 2) attempts to claim -> should raise HTTPException 409
        with pytest.raises(HTTPException) as exc_info:
            carrier_service.claim_carrier(conn, cid, user_id=2)
        assert exc_info.value.status_code == 409

        # Admin (ID: 3) transfers carrier to Kevin (ID: 2)
        c_trans = carrier_service.transfer_carrier(
            conn,
            carrier_id=cid,
            actor_id=3,
            target_id=2,
            note="Territory rebalance"
        )
        assert c_trans["owner_id"] == 2

        # Kevin releases carrier
        carrier_service.release_carrier(conn, cid, actor_id=2, note="Releasing back")
        owner_after = carrier_service.get_carrier_owner(conn, cid)
        assert owner_after is None

        # Check assignment history
        history = carrier_service.get_carrier_assignment_history(conn, cid)
        assert len(history) >= 3
        actions = [h["action"] for h in history]
        assert "CLAIM" in actions
        assert "TRANSFER" in actions
        assert "RELEASE" in actions


# ============================================================================
# 8. API CLIENT & HTTP ENDPOINTS
# ============================================================================

def test_carrier_api_endpoints():
    client = TestClient(app)

    # Login as Selena Harrison
    login_res = client.post("/login", data={"username": "Selena Harrison", "password": "12345"}, follow_redirects=False)
    assert login_res.status_code == 303

    # List carriers API
    r_list = client.get("/api/carriers")
    assert r_list.status_code == 200
    data = r_list.json()
    assert "items" in data

    # Summary API
    r_sum = client.get("/api/carriers/summary")
    assert r_sum.status_code == 200
    assert "total_carriers" in r_sum.json()

    # Create Carrier API
    new_carrier_payload = {
        "legal_name": "API Test Trucking Corp",
        "country": "US",
        "physical_state_prov": "TX",
        "physical_city": "Dallas",
        "usdot_number": "12300099",
        "mc_number": "MC999000",
        "primary_equipment_types": ["DRY_VAN"]
    }
    r_create = client.post("/api/carriers", json=new_carrier_payload)
    assert r_create.status_code == 201
    created = r_create.json()
    cid = created["id"]

    # Claim carrier API
    r_claim = client.post(f"/api/carriers/{cid}/assign", json={"action": "claim"})
    assert r_claim.status_code == 200

    # Add capacity API
    cap_payload = {
        "equipment_type": "DRY_VAN",
        "available_city": "Dallas",
        "available_state_prov": "TX",
        "destination_city": "Atlanta",
        "destination_state_prov": "GA",
        "available_date_start": "2026-10-18",
        "available_date_end": "2026-10-25",
        "desired_rate": 1800.0,
        "notes": "Clean van ready"
    }
    r_cap = client.post(f"/api/carriers/{cid}/capacity", json=cap_payload)
    assert r_cap.status_code == 201

    # Log outreach API
    outreach_payload = {
        "carrier_id": cid,
        "disposition": "CONNECTED_DISPATCH",
        "notes": "Discussed Dallas lanes with dispatch."
    }
    r_outreach = client.post(f"/api/carriers/{cid}/outreach", json=outreach_payload)
    assert r_outreach.status_code == 201

    # View carriers HTML
    r_html = client.get("/carriers")
    assert r_html.status_code == 200
    assert "Carrier Directory" in r_html.text

    # View capacity HTML
    r_cap_html = client.get("/capacity")
    assert r_cap_html.status_code == 200
    assert "Available Trucks" in r_cap_html.text

    # View loads HTML
    r_loads_html = client.get("/loads")
    assert r_loads_html.status_code == 200
    assert "Discrete Loads" in r_loads_html.text
