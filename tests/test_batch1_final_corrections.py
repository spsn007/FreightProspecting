"""
FreightProspecting V1 — Broker Research Batch 1 Final Closure Regression Tests
Validates all 13 mandatory invariant tests specified in the Codex batch 1 final closure audit:
1. Edwards outside-carrier VERIFIED does not imply broker acceptance
2. E.C. Babbert fleet UNKNOWN after correction
3. Beasley final fleet/relationship invariant is valid
4. Yoder affiliated carrier handling
5. High Concrete affiliated relationship remains correct
6. SyBridge lifecycle QUALIFIED
7. SyBridge unsupported named logistics contact absent/unverified
8. Leslie personal/shared email attribution
9. AarKel ext 205 + diecast email separation
10. Anchor fleet remains UNKNOWN
11. No SAFER-only accepted claims
12. Contact labels match source scope
13. Lifecycle table unchanged across all 653 facilities
"""

import sqlite3
from pathlib import Path
import pytest

from src.backend.db.connection import get_db_path
from src.backend.db.queries import get_company_grouped_prospects, get_universe_metadata
from src.backend.db.opportunity import (
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    RESTRICTED,
    evaluate_broker_opportunity,
)

ACTIVE_DB = get_db_path()
BACKUP_PRE_CORRECTIONS = Path("data/backups/prospects_backup_pre_batch1_final_corrections_20260928_234545.db")

@pytest.fixture(autouse=True, scope="module")
def pin_historical_db(use_historical_stage3_db):
    global ACTIVE_DB
    ACTIVE_DB = use_historical_stage3_db
    yield
    ACTIVE_DB = get_db_path()


def test_1_edwards_outside_carrier_verified_does_not_imply_broker_acceptance():
    """Edwards Wood Products (Co 14, Fac 13) has verified outside carrier use, broker UNKNOWN, and is Tier A."""
    conn = sqlite3.connect(ACTIVE_DB)
    row = conn.execute("""
        SELECT commercial_carrier_use, broker_friendly_status, private_fleet_present
        FROM facilities WHERE id = 13
    """).fetchone()
    conn.close()

    assert row[0] == "VERIFIED"
    assert row[1] == "UNKNOWN"
    assert row[2] == "VERIFIED_PRESENT"

    res = evaluate_broker_opportunity(14, facility_id=13)
    assert res["opportunity_tier"] == TIER_A_PRIORITY
    assert "Outside carrier use confirmed (VERIFIED)" in res["positive_facts"]
    assert "Broker acceptance explicitly confirmed (VERIFIED)" not in res["positive_facts"]


def test_2_ec_babbert_fleet_unknown_after_correction():
    """E.C. Babbert (Co 34, Fac 33) has private_fleet_present = UNKNOWN, fleet_relationship = UNKNOWN, Tier B."""
    conn = sqlite3.connect(ACTIVE_DB)
    row = conn.execute("""
        SELECT private_fleet_present, fleet_relationship_type, commercial_carrier_use, broker_friendly_status
        FROM facilities WHERE id = 33
    """).fetchone()
    conn.close()

    assert row[0] == "UNKNOWN"
    assert row[1] == "UNKNOWN"
    assert row[2] == "UNKNOWN"
    assert row[3] == "UNKNOWN"

    res = evaluate_broker_opportunity(34, facility_id=33)
    assert res["opportunity_tier"] == TIER_B_WORTH_CALLING


def test_3_beasley_final_fleet_relationship_invariant_valid():
    """Beasley Forest Products (Co 1, Fac 1) has fleet_relationship_type = AFFILIATED_CARRIER_ENTITY, Tier A."""
    conn = sqlite3.connect(ACTIVE_DB)
    row = conn.execute("""
        SELECT private_fleet_present, fleet_relationship_type, commercial_carrier_use, broker_friendly_status
        FROM facilities WHERE id = 1
    """).fetchone()
    c1 = conn.execute("SELECT phone_extension FROM contacts WHERE id = 1").fetchone()[0]
    conn.close()

    assert row[0] == "UNKNOWN"
    assert row[1] == "AFFILIATED_CARRIER_ENTITY"
    assert row[2] == "VERIFIED"
    assert row[3] == "UNKNOWN"
    assert c1 == "4317"

    res = evaluate_broker_opportunity(1, facility_id=1)
    assert res["opportunity_tier"] == TIER_A_PRIORITY


def test_4_yoder_affiliated_carrier_handling():
    """Yoder Lumber (Co 321, Fac 408) has fleet_relationship_type = AFFILIATED_CARRIER_ENTITY, private fleet UNKNOWN, Tier B."""
    conn = sqlite3.connect(ACTIVE_DB)
    row = conn.execute("""
        SELECT private_fleet_present, fleet_relationship_type, commercial_carrier_use
        FROM facilities WHERE id = 408
    """).fetchone()
    c418_email = conn.execute("SELECT email_address FROM contacts WHERE id = 418").fetchone()[0]
    c627_email = conn.execute("SELECT email_address FROM contacts WHERE id = 627").fetchone()[0]
    conn.close()

    assert row[0] == "UNKNOWN"
    assert row[1] == "AFFILIATED_CARRIER_ENTITY"
    assert row[2] == "UNKNOWN"
    assert c418_email is None
    assert c627_email is None

    res = evaluate_broker_opportunity(321, facility_id=408)
    assert res["opportunity_tier"] == TIER_B_WORTH_CALLING


def test_5_high_concrete_affiliated_relationship_remains_correct():
    """High Concrete Group (Co 30, Fac 29) retains private_fleet_present = UNKNOWN, fleet_relationship = AFFILIATED_CARRIER_ENTITY, Tier B."""
    conn = sqlite3.connect(ACTIVE_DB)
    row = conn.execute("""
        SELECT private_fleet_present, fleet_relationship_type, commercial_carrier_use
        FROM facilities WHERE id = 29
    """).fetchone()
    conn.close()

    assert row[0] == "UNKNOWN"
    assert row[1] == "AFFILIATED_CARRIER_ENTITY"
    assert row[2] == "UNKNOWN"

    res = evaluate_broker_opportunity(30, facility_id=29)
    assert res["opportunity_tier"] == TIER_B_WORTH_CALLING


def test_6_sybridge_lifecycle_qualified():
    """SyBridge Technologies (Co 44, Fac 43) lifecycle remains QUALIFIED."""
    conn = sqlite3.connect(ACTIVE_DB)
    stage = conn.execute("SELECT stage FROM prospect_lifecycle WHERE facility_id = 43").fetchone()[0]
    conn.close()

    assert stage == "QUALIFIED"


def test_7_sybridge_unsupported_contact_absent_and_global_route():
    """SyBridge Technologies (Contact 53) has Ryan Hurley removed, phone updated to +1 (833) 824-1116."""
    conn = sqlite3.connect(ACTIVE_DB)
    c53 = conn.execute("""
        SELECT person_name, exact_published_title, phone_number, phone_directness, contact_identity, role_category
        FROM contacts WHERE id = 53
    """).fetchone()
    conn.close()

    assert c53[0] is None
    assert c53[1] is None
    assert c53[2] == "+1 (833) 824-1116"
    assert c53[3] == "TOLL_FREE"
    assert c53[4] == "GENERAL_FACILITY"
    assert c53[5] == "GENERAL_FACILITY"


def test_8_leslie_personal_shared_email_attribution():
    """Leslie Forest Products: James Sangara (Contact 11) has personal email, Contact 12 retains shipping email."""
    conn = sqlite3.connect(ACTIVE_DB)
    c11 = conn.execute("SELECT person_name, email_address FROM contacts WHERE id = 11").fetchone()
    c12 = conn.execute("SELECT exact_published_title, email_address FROM contacts WHERE id = 12").fetchone()
    conn.close()

    assert c11[0] == "James Sangara"
    assert c11[1] == "james@leslieforest.com"
    assert c12[0] == "Shipping Department"
    assert c12[1] == "shipping@leslieforest.com"


def test_9_aarkel_ext_205_and_diecast_email_separation():
    """AarKel Tool and Die (Contact 194): phone_extension = 205, diecastsales email removed."""
    conn = sqlite3.connect(ACTIVE_DB)
    c194 = conn.execute("SELECT phone_number, phone_extension, email_address FROM contacts WHERE id = 194").fetchone()
    conn.close()

    assert c194[0] == "519-627-7960"
    assert c194[1] == "205"
    assert c194[2] is None


def test_10_anchor_fleet_remains_unknown_and_ext_250():
    """Anchor Concrete (Co 114, Fac 143): fleet remains UNKNOWN, Contact 153 has ext 250."""
    conn = sqlite3.connect(ACTIVE_DB)
    fac = conn.execute("SELECT private_fleet_present, fleet_relationship_type FROM facilities WHERE id = 143").fetchone()
    c153 = conn.execute("SELECT phone_number, phone_extension FROM contacts WHERE id = 153").fetchone()
    conn.close()

    assert fac[0] == "UNKNOWN"
    assert fac[1] == "UNKNOWN"
    assert c153[0] == "(613) 546-6683"
    assert c153[1] == "250"


def test_11_no_safer_only_accepted_claims():
    """Verify that zero accepted claims from Batch 1 rely solely on FMCSA SAFER as evidence source."""
    conn = sqlite3.connect(ACTIVE_DB)
    safer_accepted = conn.execute("""
        SELECT c.id, c.claim_field, c.claimed_value, es.source_url
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.id >= 2699 AND c.is_current_accepted = 1
          AND (es.source_url LIKE '%safer.fmcsa.dot.gov%' OR es.source_title_publisher LIKE '%SAFER%')
          AND c.verification_status = 'VERIFIED'
          AND c.claim_field IN ('private_fleet_present', 'fleet_relationship_type', 'commercial_carrier_use')
    """).fetchall()
    conn.close()

    assert len(safer_accepted) == 0, f"Found SAFER-based accepted claims: {safer_accepted}"


def test_12_contact_labels_match_source_scope():
    """Verify contact labels accurately reflect published scope (Integrity, Cole, Edwards, Mack)."""
    conn = sqlite3.connect(ACTIVE_DB)
    # Integrity Tool & Mold (Contact 47)
    c47 = conn.execute("SELECT department, exact_published_title, role_category FROM contacts WHERE id = 47").fetchone()
    assert c47[0] == "Canadian headquarters general line"
    assert c47[2] == "GENERAL_FACILITY"

    # Cole Hardwood (Contact 396)
    c396 = conn.execute("SELECT exact_published_title, email_address FROM contacts WHERE id = 396").fetchone()
    assert c396[0] == "General main line"
    assert c396[1] is None

    # Edwards Wood Products (Contact 16)
    c16 = conn.execute("SELECT department FROM contacts WHERE id = 16").fetchone()
    assert c16[0] == "General HQ / transportation referral"

    # Mack Industries (Contact 30)
    c30 = conn.execute("SELECT phone_number, department, phone_directness FROM contacts WHERE id = 30").fetchone()
    assert c30[0] == "(330) 483-3111"
    assert c30[1] == "Valley City Precast Plant Line"
    assert c30[2] == "DEPARTMENT_LINE"
    conn.close()


def test_13_lifecycle_table_unchanged():
    """Verify that all 653 facilities maintain identical lifecycle stage to pre-corrections backup."""
    assert BACKUP_PRE_CORRECTIONS.exists(), "Pre-corrections backup must exist"

    conn = sqlite3.connect(ACTIVE_DB)
    cur_stages = dict(conn.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
    conn.close()

    bak_conn = sqlite3.connect(BACKUP_PRE_CORRECTIONS)
    bak_stages = dict(bak_conn.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
    bak_conn.close()

    assert len(cur_stages) == 653
    assert len(bak_stages) == 653
    assert cur_stages == bak_stages
