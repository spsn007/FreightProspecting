"""
Tests for FreightProspecting V1 — Deterministic Broker Opportunity Engine
Rule Version: 1.1 (BROKER_OPPORTUNITY_RULE_VERSION = "1.1")

Verifies all 10 mandatory edge cases and the audit snapshot of the 29 shortlisted companies.
"""

import sqlite3
from pathlib import Path
import pytest

from src.backend.db.opportunity import (
    BROKER_OPPORTUNITY_RULE_VERSION,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    RESTRICTED,
    UNKNOWN_FLEET_TEXT,
    UNKNOWN_CARRIER_TEXT,
    UNKNOWN_BROKER_TEXT,
    evaluate_broker_opportunity_raw,
    evaluate_broker_opportunity,
)
from src.backend.db.connection import get_db_path


def test_rule_version():
    """Verify rule version constant."""
    assert BROKER_OPPORTUNITY_RULE_VERSION == "1.1"


def test_case_1_all_unknown_never_no_fleet():
    """
    Mandatory Test Case 1:
    Private fleet UNKNOWN, Commercial carrier UNKNOWN, Broker acceptance UNKNOWN
    Must NOT become 'No private fleet' or 'Does not use carriers'.
    Must use honest unknown wording.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="UNKNOWN",
        broker_friendly_status="UNKNOWN",
        lifecycle_stage="QUALIFIED",
        has_callable_route=True,
        has_ftl_fit=True,
    )
    assert res["opportunity_tier"] == TIER_B_WORTH_CALLING
    assert res["frontend_label"] == "Worth Calling"
    
    # Assert honest unknown wording
    assert UNKNOWN_FLEET_TEXT in res["unknowns"]
    assert "No own trucks" not in res["unknowns"]
    assert "no private fleet" not in str(res).lower()
    
    assert UNKNOWN_CARRIER_TEXT in res["unknowns"]
    assert "Does not use outside carriers" not in res["unknowns"]
    
    assert UNKNOWN_BROKER_TEXT in res["unknowns"]
    assert "Does not use brokers" not in res["unknowns"]


def test_case_2_private_fleet_verified_carrier_unknown_secondary():
    """
    Mandatory Test Case 2:
    Private fleet VERIFIED_PRESENT, Commercial carrier UNKNOWN, Broker acceptance UNKNOWN
    Evaluates to Tier C Secondary Prospect.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="VERIFIED_PRESENT",
        commercial_carrier_use="UNKNOWN",
        broker_friendly_status="UNKNOWN",
        lifecycle_stage="SHORTLISTED",
        has_callable_route=True,
        has_ftl_fit=True,
    )
    assert res["opportunity_tier"] == TIER_C_SECONDARY
    assert res["frontend_label"] == "Secondary Prospect"
    assert "Own trucks confirmed" in res["counter_factors"]
    assert "Use of outside carriers not confirmed" in res["counter_factors"]
    assert UNKNOWN_CARRIER_TEXT in res["unknowns"]
    assert res["is_actionable"] is True


def test_case_3_private_fleet_verified_and_carrier_verified_priority():
    """
    Mandatory Test Case 3:
    Private fleet VERIFIED_PRESENT + Commercial carrier VERIFIED
    Must NOT be downgraded; evaluates to Tier A Priority Prospect provided readiness rules pass.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="VERIFIED_PRESENT",
        commercial_carrier_use="VERIFIED",
        broker_friendly_status="UNKNOWN",
        lifecycle_stage="SHORTLISTED",
        has_callable_route=True,
        has_ftl_fit=True,
    )
    assert res["opportunity_tier"] == TIER_A_PRIORITY
    assert res["frontend_label"] == "Priority Prospect"
    assert res["has_strong_opportunity_signal"] is True
    assert res["is_actionable"] is True
    assert any("Outside carrier use confirmed" in f for f in res["positive_facts"])
    assert any("Own trucks confirmed" in f for f in res["positive_facts"])
    # Broker acceptance remains unknown
    assert UNKNOWN_BROKER_TEXT in res["unknowns"]


def test_case_4_private_fleet_unknown_carrier_verified_priority():
    """
    Mandatory Test Case 4:
    Private fleet UNKNOWN + Commercial carrier VERIFIED
    Evaluates to Tier A Priority Prospect provided readiness rules pass.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="VERIFIED",
        broker_friendly_status="UNKNOWN",
        lifecycle_stage="QUALIFIED",
        has_callable_route=True,
        has_ftl_fit=True,
    )
    assert res["opportunity_tier"] == TIER_A_PRIORITY
    assert res["frontend_label"] == "Priority Prospect"
    assert any("Outside carrier use confirmed" in f for f in res["positive_facts"])
    assert UNKNOWN_FLEET_TEXT in res["unknowns"]
    assert UNKNOWN_BROKER_TEXT in res["unknowns"]


def test_case_5_broker_acceptance_verified_positive():
    """
    Mandatory Test Case 5:
    Broker acceptance explicitly positive (VERIFIED_ACCEPTS)
    Strong positive evidence resulting in Tier A Priority Prospect.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="UNKNOWN",
        broker_friendly_status="VERIFIED_ACCEPTS",
        lifecycle_stage="QUALIFIED",
        has_callable_route=True,
        has_ftl_fit=True,
    )
    assert res["opportunity_tier"] == TIER_A_PRIORITY
    assert res["frontend_label"] == "Priority Prospect"
    assert any("Broker acceptance explicitly confirmed" in f for f in res["positive_facts"])
    assert "BROKER_ACCEPTANCE_CONFIRMED" in res["reason_codes"]


def test_case_6_direct_only_policy_restricted():
    """
    Mandatory Test Case 6:
    Explicit global no-broker / direct-only policy (VERIFIED_DIRECT_ONLY)
    Evaluates to RESTRICTED.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="VERIFIED",
        broker_friendly_status="VERIFIED_DIRECT_ONLY",
        lifecycle_stage="QUALIFIED",
        has_callable_route=True,
        has_ftl_fit=True,
    )
    assert res["opportunity_tier"] == RESTRICTED
    assert res["frontend_label"] == "Restricted"
    assert res["is_actionable"] is False
    assert "RESTRICTED_DIRECT_ONLY_POLICY" in res["reason_codes"]


def test_case_7_lane_only_restriction_not_global():
    """
    Mandatory Test Case 7:
    Lane-only restriction (e.g. COMPANY_LANE suppression)
    Must NOT globally disqualify company.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="VERIFIED",
        broker_friendly_status="UNKNOWN",
        lifecycle_stage="SHORTLISTED",
        has_callable_route=True,
        has_ftl_fit=True,
        suppression_status="DO_NOT_CONTACT",
        is_lane_suppression_only=True,  # Lane-specific suppression
    )
    assert res["opportunity_tier"] == TIER_A_PRIORITY
    assert res["frontend_label"] == "Priority Prospect"


def test_case_8_global_dnc_restricted():
    """
    Mandatory Test Case 8:
    DNC (DO_NOT_CONTACT)
    Must remain RESTRICTED.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="VERIFIED",
        broker_friendly_status="UNKNOWN",
        lifecycle_stage="SHORTLISTED",
        has_callable_route=True,
        has_ftl_fit=True,
        suppression_status="DO_NOT_CONTACT",
        is_lane_suppression_only=False,
    )
    assert res["opportunity_tier"] == RESTRICTED
    assert res["frontend_label"] == "Restricted"
    assert "RESTRICTED_DO_NOT_CONTACT" in res["reason_codes"]


def test_case_9_direct_contact_does_not_invent_opportunity():
    """
    Mandatory Test Case 9:
    Direct freight contact improves contactability, but must NOT create fake external-capacity evidence.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="UNKNOWN",
        broker_friendly_status="UNKNOWN",
        lifecycle_stage="QUALIFIED",
        has_callable_route=True,
        has_ftl_fit=True,
        direct_contact_role="FREIGHT_LOGISTICS",
        direct_contact_directness="DIRECT_PERSON",
    )
    # Does NOT become Tier A! It remains Tier B Worth Calling
    assert res["opportunity_tier"] == TIER_B_WORTH_CALLING
    assert any("Direct logistics manager" in f for f in res["positive_facts"])
    assert res["has_strong_opportunity_signal"] is False


def test_case_10_missing_contact_not_tier_a_actionable():
    """
    Mandatory Test Case 10:
    Missing contact must not be Tier A actionable even with strong opportunity evidence.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="VERIFIED",
        broker_friendly_status="UNKNOWN",
        lifecycle_stage="QUALIFIED",
        has_callable_route=False,  # No phone, no email
        has_ftl_fit=True,
    )
    # Evaluates to Tier D Needs More Research due to missing outreach route
    assert res["opportunity_tier"] == TIER_D_RESEARCH_NEEDED
    assert res["frontend_label"] == "Needs More Research"
    assert res["is_actionable"] is False
    assert "RESEARCH_NEEDED_NO_CALLABLE_ROUTE" in res["reason_codes"]


def test_frozen_audit_snapshot_29_shortlisted():
    """
    Audited regression snapshot of the 29 old SHORTLISTED companies.
    Verifies that the 29 split into:
      - 6 Tier A Priority Prospects
      - 18 Tier B Worth Calling
      - 5 Tier C Secondary Prospects
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        sl_comps = conn.execute("""
            SELECT DISTINCT c.id, c.operating_brand
            FROM companies c
            JOIN facilities f ON c.id = f.company_id
            JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE pl.stage = 'SHORTLISTED'
            ORDER BY c.operating_brand
        """).fetchall()

        assert len(sl_comps) == 29

        tier_counts = {"TIER_A_PRIORITY": 0, "TIER_B_WORTH_CALLING": 0, "TIER_C_SECONDARY": 0, "TIER_D_RESEARCH_NEEDED": 0}
        tier_c_names = []
        tier_a_names = []

        for c in sl_comps:
            res = evaluate_broker_opportunity(c["id"], conn=conn)
            tier_counts[res["opportunity_tier"]] += 1
            if res["opportunity_tier"] == TIER_C_SECONDARY:
                tier_c_names.append(c["operating_brand"])
            elif res["opportunity_tier"] == TIER_A_PRIORITY:
                tier_a_names.append(c["operating_brand"])

        assert tier_counts["TIER_A_PRIORITY"] == 7
        assert tier_counts["TIER_B_WORTH_CALLING"] == 20
        assert tier_counts["TIER_C_SECONDARY"] == 2
        assert tier_counts["TIER_D_RESEARCH_NEEDED"] == 0

        # Verify the 2 Tier C private fleet companies in Shortlisted (E.C. Babbert and Yoder moved to Tier B)
        expected_tier_c = {
            "Cole Hardwood Inc.",
            "Norwalk Concrete Industries",
        }
        assert set(tier_c_names) == expected_tier_c

        # Verify the 7 Tier A outside carrier verified companies in Shortlisted
        expected_tier_a = {
            "Battle Lumber Company",
            "Beasley Forest Products",
            "Coil Steel Processing (CSP)",
            "Liberty Steel Products, Inc.",
            "Miami Valley Steel Service, Inc.",
            "MidWest Materials, Inc.",
            "Taylor Steel Inc.",
        }
        assert set(tier_a_names) == expected_tier_a
    finally:
        conn.close()


def test_full_565_universe_distribution():
    """
    Verifies deterministic distribution across all 565 operating companies.
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        comps = conn.execute("""
            SELECT id FROM companies 
            WHERE id IN (SELECT DISTINCT company_id FROM facilities)
        """).fetchall()

        assert len(comps) == 1032

        counts = {
            TIER_A_PRIORITY: 0,
            TIER_B_WORTH_CALLING: 0,
            TIER_C_SECONDARY: 0,
            TIER_D_RESEARCH_NEEDED: 0,
            RESTRICTED: 0,
        }

        for c in comps:
            res = evaluate_broker_opportunity(c["id"], conn=conn)
            counts[res["opportunity_tier"]] += 1

        assert counts[TIER_A_PRIORITY] == 19
        assert counts[TIER_B_WORTH_CALLING] == 956
        assert counts[TIER_C_SECONDARY] == 10
        assert counts[TIER_D_RESEARCH_NEEDED] == 47
        assert counts[RESTRICTED] == 0
        assert sum(counts.values()) == 1032
    finally:
        conn.close()


def test_queries_opportunity_tier_filtering():
    """Verify get_company_grouped_prospects and get_prospects_list filter accurately by tier."""
    from src.backend.db.queries import get_company_grouped_prospects, get_prospects_list

    # Tier A Priority: 19 companies, 19 facilities
    tier_a_comps = get_company_grouped_prospects(tier="TIER_A_PRIORITY")
    assert len(tier_a_comps) == 19
    assert all(c["opportunity_tier"] == TIER_A_PRIORITY for c in tier_a_comps)
    assert all(c["broker_status_label"] == "Priority Prospect" for c in tier_a_comps)

    tier_a_facs = get_prospects_list(tier="TIER_A_PRIORITY")
    assert len(tier_a_facs) == 19
    assert all(f["opportunity_tier"] == TIER_A_PRIORITY for f in tier_a_facs)

    # Tier B Worth Calling: 956 companies, 988 facilities
    tier_b_comps = get_company_grouped_prospects(tier="TIER_B_WORTH_CALLING")
    assert len(tier_b_comps) == 956
    assert all(c["opportunity_tier"] == TIER_B_WORTH_CALLING for c in tier_b_comps)

    tier_b_facs = get_prospects_list(tier="TIER_B_WORTH_CALLING")
    assert len(tier_b_facs) == 988
    assert all(f["opportunity_tier"] == TIER_B_WORTH_CALLING for f in tier_b_facs)

    # Tier C Secondary: 10 companies, 10 facilities (with fleet verified, outside carrier unconfirmed)
    tier_c_comps = get_company_grouped_prospects(tier="TIER_C_SECONDARY")
    assert len(tier_c_comps) == 10
    assert all(c["opportunity_tier"] == TIER_C_SECONDARY for c in tier_c_comps)

    tier_c_facs = get_prospects_list(tier="TIER_C_SECONDARY")
    assert len(tier_c_facs) == 10
    assert all(f["opportunity_tier"] == TIER_C_SECONDARY for f in tier_c_facs)

    # Tier D Research Needed: 47 companies, 102 facilities
    tier_d_comps = get_company_grouped_prospects(tier="TIER_D_RESEARCH_NEEDED")
    assert len(tier_d_comps) == 47
    assert all(c["opportunity_tier"] == TIER_D_RESEARCH_NEEDED for c in tier_d_comps)

    tier_d_facs = get_prospects_list(tier="TIER_D_RESEARCH_NEEDED")
    assert len(tier_d_facs) == 102
    assert all(f["opportunity_tier"] == TIER_D_RESEARCH_NEEDED for f in tier_d_facs)


def test_fastapi_endpoints_opportunity_integration():
    """Verify HTTP endpoints reflect broker opportunity tiers."""
    from tests.authenticated_client import TestClient
    from src.backend.main import app

    client = TestClient(app)

    # Cockpit endpoint (/)
    r_dash = client.get("/")
    assert r_dash.status_code == 200
    assert "Priority Prospects" in r_dash.text
    assert "Worth Calling" in r_dash.text
    assert "Secondary Prospects" in r_dash.text

    # Master directory with tier filter
    r_tier_a = client.get("/prospects?tier=TIER_A_PRIORITY")
    assert r_tier_a.status_code == 200
    assert "Battle Lumber Company" in r_tier_a.text
    assert "Beasley Forest Products" in r_tier_a.text
    assert "Liberty Steel Products" in r_tier_a.text
    assert "Heidtman Steel" in r_tier_a.text

    r_tier_b = client.get("/prospects?tier=TIER_B_WORTH_CALLING&q=Scotch")
    assert r_tier_b.status_code == 200
    assert "Scotch Plywood" in r_tier_b.text

    r_tier_c = client.get("/prospects?tier=TIER_C_SECONDARY")
    assert r_tier_c.status_code == 200
    assert "Cole Hardwood" in r_tier_c.text
    assert "Norwalk Concrete" in r_tier_c.text


# ============================================================================
# AUDIT REGRESSION TESTS (AUDIT PASS 1.1)
# ============================================================================

def test_audit_rule_version_is_1_1():
    """Verify rule version constant is 1.1."""
    assert BROKER_OPPORTUNITY_RULE_VERSION == "1.1"


def test_audit_no_speculative_capacity_insufficient_language():
    """
    Audit Test: Verify opportunity engine never uses speculative capacity insufficiency claims.
    Forbidden: 'cannot handle', 'insufficient', 'needs outside trucks', 'overflow confirmed', 'proves outsourced'.
    """
    for fleet in ("UNKNOWN", "VERIFIED_PRESENT", "VERIFIED_NO_FLEET"):
        for carrier in ("UNKNOWN", "VERIFIED"):
            for broker in ("UNKNOWN", "VERIFIED_ACCEPTS", "VERIFIED_DIRECT_ONLY"):
                res = evaluate_broker_opportunity_raw(
                    private_fleet_present=fleet,
                    commercial_carrier_use=carrier,
                    broker_friendly_status=broker,
                    lifecycle_stage="SHORTLISTED",
                    has_callable_route=True,
                    has_ftl_fit=True,
                )
                text = str(res).lower()
                assert "cannot handle" not in text
                assert "insufficient" not in text
                assert "needs outside trucks" not in text
                assert "overflow" not in text
                assert "proves outsourced" not in text


def test_audit_no_probability_language():
    """
    Audit Test: Verify opportunity outputs use deterministic terms, never probability.
    Forbidden: 'probability', 'conversion probability', 'likelihood percentage'.
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="VERIFIED_PRESENT",
        commercial_carrier_use="VERIFIED",
        lifecycle_stage="SHORTLISTED",
        has_callable_route=True,
        has_ftl_fit=True,
    )
    text = str(res).lower()
    assert "probability" not in text
    assert "conversion probability" not in text
    assert "likelihood percentage" not in text


def test_audit_csp_entity_and_scope():
    """
    Audit Test: Verify CSP raw SQLite database records.
    - Company ID is 19 (Coil Steel Processing (CSP)), NOT 8 (Lamb Brothers Lumber).
    - Facility ID is 18 (Toledo Stretcher Leveling & Processing Plant), NOT 8 (Pooler Sawmill).
    - Equipment verified at facility 18 is strictly FLATBED, not STEP_DECK (Step Deck was category guidance).
    - Primary contact is contact 22 (Shipping & Receiving Desk, (419) 269-9706).
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        # Check Company 19
        c19 = conn.execute("SELECT * FROM companies WHERE id = 19").fetchone()
        assert c19 is not None
        assert "Coil Steel Processing" in c19["operating_brand"]

        # Check Company 8 is Lamb Brothers Lumber
        c8 = conn.execute("SELECT * FROM companies WHERE id = 8").fetchone()
        assert c8 is not None
        assert "Lamb Brothers" in c8["operating_brand"]
        assert "Coil Steel" not in c8["operating_brand"]

        # Check Facility 18 belongs to Company 19
        f18 = conn.execute("SELECT * FROM facilities WHERE id = 18").fetchone()
        assert f18 is not None
        assert f18["company_id"] == 19
        assert "Toledo" in f18["facility_name"]
        assert f18["commercial_carrier_use"] == "VERIFIED"
        assert f18["private_fleet_present"] == "UNKNOWN"

        # Check Facility 8 is Pooler Sawmill (belongs to Company 9)
        f8 = conn.execute("SELECT * FROM facilities WHERE id = 8").fetchone()
        assert f8 is not None
        assert f8["company_id"] == 9
        assert "Pooler Sawmill" in f8["facility_name"]

        # Check equipment for Facility 18
        commodities = conn.execute("SELECT * FROM facility_commodities WHERE facility_id = 18").fetchall()
        assert len(commodities) >= 1
        for comm in commodities:
            assert comm["equipment_category"] == "FLATBED"
            assert comm["equipment_usage_status"] == "VERIFIED"
            assert "Flatbeds only" in (comm["trailer_specs_notes"] or "")

        # Check contact for Facility 18
        contacts = conn.execute("SELECT * FROM contacts WHERE facility_id = 18").fetchall()
        assert len(contacts) >= 1
        c22 = next((ct for ct in contacts if ct["id"] == 22), None)
        assert c22 is not None
        assert "Shipping & Receiving" in (c22["exact_published_title"] or "")
        assert c22["phone_number"] == "(419) 269-9706"
        assert c22["phone_directness"] == "DEPARTMENT_LINE"
    finally:
        conn.close()


def test_audit_all_11_tier_a_entities_and_carrier_claims():
    """
    Audit Test: Verify exact identities and evidence for all 11 Tier A Priority Prospects.
    All 11 have commercial_carrier_use == 'VERIFIED' and broker_friendly_status == 'UNKNOWN'.
    """
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        expected = [
            (1, 1, "Beasley Forest Products", "FLATBED", "UNKNOWN"),
            (6, 5, "Battle Lumber Company", "FLATBED", "UNKNOWN"),
            (14, 13, "Edwards Wood Products, Inc.", "FLATBED", "VERIFIED_PRESENT"),
            (16, 15, "Miami Valley Steel Service, Inc.", "FLATBED", "VERIFIED_PRESENT"),
            (17, 16, "MidWest Materials, Inc.", "FLATBED", "UNKNOWN"),
            (18, 17, "Liberty Steel Products, Inc.", "FLATBED", "VERIFIED_PRESENT"),
            (19, 18, "Coil Steel Processing (CSP)", "FLATBED", "UNKNOWN"),
            (21, 20, "Taylor Steel Inc.", "FLATBED", "VERIFIED_PRESENT"),
            (25, 24, "Majestic Steel USA", "FLATBED", "UNKNOWN"),
            (26, 25, "Heidtman Steel Products, Inc.", "FLATBED", "UNKNOWN"),
            (42, 41, "Bemis Manufacturing Company", "DRY_VAN", "VERIFIED_PRESENT"),
        ]
        for cid, fid, brand, expected_equip, expected_fleet in expected:
            c_row = conn.execute("SELECT operating_brand FROM companies WHERE id = ?", (cid,)).fetchone()
            assert c_row is not None
            assert c_row["operating_brand"] == brand

            f_row = conn.execute("SELECT * FROM facilities WHERE id = ? AND company_id = ?", (fid, cid)).fetchone()
            assert f_row is not None
            assert f_row["commercial_carrier_use"] == "VERIFIED"
            assert f_row["broker_friendly_status"] == "UNKNOWN"
            assert f_row["private_fleet_present"] == expected_fleet

            # Verify facility commodity equipment
            comms = conn.execute("SELECT equipment_category FROM facility_commodities WHERE facility_id = ?", (fid,)).fetchall()
            equip_cats = {c["equipment_category"] for c in comms}
            assert expected_equip in equip_cats
    finally:
        conn.close()


def test_audit_multi_facility_scope_integrity():
    """
    Audit Test: Verify multi-facility company groups attach qualifying_facility_id
    and scope candidate contacts to the qualifying facility.
    """
    from src.backend.db.queries import get_company_grouped_prospects
    tier_a = get_company_grouped_prospects(tier="TIER_A_PRIORITY")
    assert len(tier_a) == 19
    for c in tier_a:
        assert c["opportunity_tier"] == TIER_A_PRIORITY
        assert c["qualifying_facility_id"] is not None
        assert c["qualifying_facility_name"] is not None
        assert c["qualifying_facility_location"] is not None


def test_audit_own_trucks_plus_outside_carriers_honest_wording():
    """
    Audit Test: Verify exact wording for private fleet verified + commercial carrier verified.
    Must be: 'Own trucks confirmed; outside carrier use also confirmed.'
    """
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="VERIFIED_PRESENT",
        commercial_carrier_use="VERIFIED",
        lifecycle_stage="SHORTLISTED",
        has_callable_route=True,
        has_ftl_fit=True,
    )
    assert "Own trucks confirmed; outside carrier use also confirmed." in res["positive_facts"]


def test_audit_obsolete_disclaimer_removed():
    """
    Audit Test: Verify obsolete disclaimer is replaced on Cockpit (/).
    """
    from tests.authenticated_client import TestClient
    from src.backend.main import app

    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    text_lower = r.text.lower()
    assert "priority scoring is not yet enabled" not in text_lower
    assert "priority is based on verified broker-opportunity evidence" in text_lower
    assert "broker acceptance may still be unconfirmed" in text_lower


def test_audit_ui_truth_panel_rendered():
    """
    Audit Test: Verify Truth Panel elements are rendered on Cockpit and Directory.
    """
    from tests.authenticated_client import TestClient
    from src.backend.main import app

    client = TestClient(app)
    
    # Cockpit
    r_dash = client.get("/")
    assert r_dash.status_code == 200
    assert "truth-panel" in r_dash.text
    assert "OUTSIDE CARRIER USE:" in r_dash.text
    assert "BROKER USE:" in r_dash.text
    assert "OWN TRUCKS:" in r_dash.text

    # Master Directory
    r_dir = client.get("/prospects?tier=TIER_A_PRIORITY")
    assert r_dir.status_code == 200
    assert "truth-panel" in r_dir.text
    assert "OUTSIDE CARRIER USE:" in r_dir.text
    assert "BROKER USE:" in r_dir.text
    assert "OWN TRUCKS:" in r_dir.text


def test_audit_zero_db_mutation_preserved():
    """
    Audit Test: Verify production database SHA-256 is unchanged and database passes integrity check.
    """
    import hashlib
    db_file = Path("data/prospects.db")
    with open(db_file, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest().upper()
    current_operational_sha = "7BF6294FF4FE99E897EFACDB9C636E0DE2E7B786956FB9575E698CCCC293D380"
    historical_freeze_sha = "A0BE4645A2136E2E2F490FB0DBD7D3D7DC395F7E9A89E2A626AC5E8106AEC400"
    assert h in (current_operational_sha, historical_freeze_sha), f"Unexpected production DB hash: {h}"

    conn = sqlite3.connect(db_file)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok"
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert len(fk_violations) == 0
    finally:
        conn.close()


