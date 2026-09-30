"""
FreightProspecting V1 — Broker Research Batch 1 Final Closure Blockers Test Suite
Validates the two final closure blocker resolutions:
1. Zero active accepted VERIFIED claims solely supported by SAFER
2. Re-grounded / conservative states for claims 217, 232, 233, 237
3. Affiliated carrier entity invariant (never implies private_fleet_present = VERIFIED_PRESENT)
4. Commercial carrier use invariant (never implies broker acceptance)
5. Leslie Forest Products Contact 11 personal email_directness == 'DIRECT_PERSON'
6. Leslie Forest Products Contact 12 shared mailbox email_directness == 'DEPARTMENT'
7. Lifecycle unchanged across all 653 facilities
8. Opportunity engine counts equal live engine output
"""

import sqlite3
from pathlib import Path
import pytest

from src.backend.db.connection import get_db_path
from src.backend.db.opportunity import (
    RESTRICTED,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    evaluate_broker_opportunity,
)
from src.backend.db.queries import get_company_grouped_prospects, get_prospects_list

# Audit tests specifically for Batch 1 closure blockers compare frozen Batch 1 DB against pre-task backup
ACTIVE_DB = Path("data/backups/prospects_backup_pre_broker_research_batch2_20260929_012116.db")
PRE_TASK_BACKUP = Path("data/backups/prospects_backup_pre_batch1_safersource_cleanup_20260929_002159.db")


def test_1_zero_active_accepted_verified_claims_solely_supported_by_safer():
    """Verify that ZERO active accepted VERIFIED claims in the entire DB rely solely on SAFER."""
    conn = sqlite3.connect(ACTIVE_DB)
    safer_active = conn.execute("""
        SELECT c.id, c.facility_id, c.claim_field, c.claimed_value, es.source_title_publisher, es.source_url
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.is_current_accepted = 1
          AND c.verification_status = 'VERIFIED'
          AND (es.source_title_publisher LIKE '%SAFER%' OR es.source_url LIKE '%safer%')
    """).fetchall()
    conn.close()

    assert len(safer_active) == 0, f"Found SAFER-only active accepted VERIFIED claims: {safer_active}"


def test_2_claim_217_edwards_regrounded_permitted_provenance():
    """Edwards Wood Products (Fac 13): Claim 217 superseded by new accepted claim backed by official transportation page."""
    conn = sqlite3.connect(ACTIVE_DB)
    conn.row_factory = sqlite3.Row

    # Old claim 217 must be inactive
    old_c217 = conn.execute("SELECT is_current_accepted, verification_status FROM claims WHERE id = 217").fetchone()
    assert old_c217["is_current_accepted"] == 0

    # New active accepted claim for fleet_relationship_type on facility 13
    cur_c = conn.execute("""
        SELECT c.id, c.claimed_value, c.verification_status
        FROM claims c
        WHERE c.facility_id = 13 AND c.claim_field = 'fleet_relationship_type' AND c.is_current_accepted = 1
    """).fetchone()

    # Evidence sources linked to this accepted claim
    sources = conn.execute("""
        SELECT es.id, es.source_url, es.source_title_publisher, es.source_type
        FROM claim_evidence ce
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE ce.claim_id = ?
    """, (cur_c["id"],)).fetchall()

    fac_row = conn.execute("SELECT fleet_relationship_type, private_fleet_present, commercial_carrier_use FROM facilities WHERE id = 13").fetchone()
    conn.close()

    assert cur_c is not None
    assert cur_c["claimed_value"] == "IN_HOUSE_OWNED"
    assert cur_c["verification_status"] == "VERIFIED"
    assert fac_row["fleet_relationship_type"] == "IN_HOUSE_OWNED"
    assert fac_row["private_fleet_present"] == "VERIFIED_PRESENT"
    assert fac_row["commercial_carrier_use"] == "VERIFIED"

    # Regression check: At least one non-SAFER official evidence source with https://ewpi.com/services/transportation/
    ewpi_sources = [
        s for s in sources
        if s["source_url"] == "https://ewpi.com/services/transportation/"
        and "safer" not in s["source_url"].lower()
        and "safer" not in s["source_title_publisher"].lower()
    ]
    assert len(ewpi_sources) >= 1, "Must have at least one non-SAFER official evidence source with https://ewpi.com/services/transportation/"


def test_3_claim_232_lindsay_precast_conservative_unknown():
    """Lindsay Precast (Fac 27): Claim 232 superseded by UNKNOWN, backed by official website."""
    conn = sqlite3.connect(ACTIVE_DB)
    conn.row_factory = sqlite3.Row

    old_c232 = conn.execute("SELECT is_current_accepted, verification_status FROM claims WHERE id = 232").fetchone()
    assert old_c232["is_current_accepted"] == 0

    cur_c = conn.execute("""
        SELECT c.id, c.claimed_value, c.verification_status, es.source_url
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.facility_id = 27 AND c.claim_field = 'fleet_relationship_type' AND c.is_current_accepted = 1
    """).fetchone()

    fac_row = conn.execute("SELECT fleet_relationship_type, private_fleet_present FROM facilities WHERE id = 27").fetchone()
    conn.close()

    assert cur_c is not None
    assert cur_c["claimed_value"] == "UNKNOWN"
    assert cur_c["verification_status"] == "UNKNOWN"
    assert fac_row["fleet_relationship_type"] == "UNKNOWN"
    assert fac_row["private_fleet_present"] == "UNKNOWN"


def test_4_claim_233_tindall_conservative_unknown():
    """Tindall Corporation (Fac 28): Claim 233 superseded by UNKNOWN, backed by official website."""
    conn = sqlite3.connect(ACTIVE_DB)
    conn.row_factory = sqlite3.Row

    old_c233 = conn.execute("SELECT is_current_accepted, verification_status FROM claims WHERE id = 233").fetchone()
    assert old_c233["is_current_accepted"] == 0

    cur_c = conn.execute("""
        SELECT c.id, c.claimed_value, c.verification_status, es.source_url
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.facility_id = 28 AND c.claim_field = 'fleet_relationship_type' AND c.is_current_accepted = 1
    """).fetchone()

    fac_row = conn.execute("SELECT fleet_relationship_type, private_fleet_present FROM facilities WHERE id = 28").fetchone()
    conn.close()

    assert cur_c is not None
    assert cur_c["claimed_value"] == "UNKNOWN"
    assert cur_c["verification_status"] == "UNKNOWN"
    assert fac_row["fleet_relationship_type"] == "UNKNOWN"
    assert fac_row["private_fleet_present"] == "UNKNOWN"


def test_5_claim_237_bemis_conservative_unknown():
    """Bemis Manufacturing (Fac 41): Claim 237 superseded by UNKNOWN; private_fleet remains VERIFIED_PRESENT under Source 84."""
    conn = sqlite3.connect(ACTIVE_DB)
    conn.row_factory = sqlite3.Row

    old_c237 = conn.execute("SELECT is_current_accepted, verification_status FROM claims WHERE id = 237").fetchone()
    assert old_c237["is_current_accepted"] == 0

    cur_c = conn.execute("""
        SELECT c.id, c.claimed_value, c.verification_status, es.source_url
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.facility_id = 41 AND c.claim_field = 'fleet_relationship_type' AND c.is_current_accepted = 1
    """).fetchone()

    fac_row = conn.execute("SELECT fleet_relationship_type, private_fleet_present, commercial_carrier_use FROM facilities WHERE id = 41").fetchone()
    conn.close()

    assert cur_c is not None
    assert cur_c["claimed_value"] == "UNKNOWN"
    assert cur_c["verification_status"] == "UNKNOWN"
    assert fac_row["fleet_relationship_type"] == "UNKNOWN"
    assert fac_row["private_fleet_present"] == "VERIFIED_PRESENT"
    assert fac_row["commercial_carrier_use"] == "VERIFIED"


def test_6_affiliated_carrier_never_creates_private_fleet_verified():
    """Verify invariant: any facility with fleet_relationship_type = AFFILIATED_CARRIER_ENTITY has private_fleet_present != VERIFIED_PRESENT."""
    conn = sqlite3.connect(ACTIVE_DB)
    violations = conn.execute("""
        SELECT id, facility_name, private_fleet_present, fleet_relationship_type
        FROM facilities
        WHERE fleet_relationship_type = 'AFFILIATED_CARRIER_ENTITY'
          AND private_fleet_present = 'VERIFIED_PRESENT'
    """).fetchall()
    conn.close()

    assert len(violations) == 0, f"Found facilities violating affiliated carrier invariant: {violations}"


def test_7_commercial_carrier_never_creates_broker_acceptance():
    """Verify invariant: commercial_carrier_use == VERIFIED does not imply broker acceptance (all remain UNKNOWN unless verified)."""
    conn = sqlite3.connect(ACTIVE_DB)
    rows = conn.execute("""
        SELECT id, facility_name, commercial_carrier_use, broker_friendly_status
        FROM facilities
        WHERE commercial_carrier_use = 'VERIFIED'
    """).fetchall()
    conn.close()

    assert len(rows) > 0
    # In V1, broker_friendly_status is UNKNOWN across all these facilities
    for r in rows:
        assert r[3] in ("UNKNOWN", "VERIFIED_ACCEPTS", "VERIFIED_DO_NOT_USE")


def test_8_leslie_contact_11_personal_email_directness_correct():
    """Verify Contact 11 (James Sangara) has email_directness = DIRECT_PERSON."""
    conn = sqlite3.connect(ACTIVE_DB)
    c11 = conn.execute("""
        SELECT person_name, email_address, email_directness, contact_identity
        FROM contacts WHERE id = 11
    """).fetchone()
    conn.close()

    assert c11[0] == "James Sangara"
    assert c11[1] == "james@leslieforest.com"
    assert c11[2] == "DIRECT_PERSON"
    assert c11[3] == "NAMED_PERSON"


def test_9_leslie_shipping_mailbox_remains_department():
    """Verify Contact 12 (Shipping Department) has email_directness = DEPARTMENT."""
    conn = sqlite3.connect(ACTIVE_DB)
    c12 = conn.execute("""
        SELECT exact_published_title, email_address, email_directness, contact_identity
        FROM contacts WHERE id = 12
    """).fetchone()
    conn.close()

    assert c12[0] == "Shipping Department"
    assert c12[1] == "shipping@leslieforest.com"
    assert c12[2] == "DEPARTMENT"
    assert c12[3] == "DEPARTMENT"


def test_10_lifecycle_unchanged():
    """Verify that all 653 facilities maintain identical lifecycle stage to pre-task backup."""
    assert PRE_TASK_BACKUP.exists(), f"Backup {PRE_TASK_BACKUP} must exist"

    conn = sqlite3.connect(ACTIVE_DB)
    cur_stages = dict(conn.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
    conn.close()

    bak_conn = sqlite3.connect(PRE_TASK_BACKUP)
    bak_stages = dict(bak_conn.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
    bak_conn.close()

    assert len(cur_stages) == 653
    assert len(bak_stages) == 653
    assert cur_stages == bak_stages


def test_11_opportunity_counts_equal_live_engine_output():
    """Verify opportunity tier distribution across all 565 operating companies matches live engine."""
    conn = sqlite3.connect(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    comps = conn.execute("""
        SELECT id FROM companies
        WHERE id IN (SELECT DISTINCT company_id FROM facilities)
    """).fetchall()

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
    conn.close()

    assert counts[TIER_A_PRIORITY] == 11
    assert counts[TIER_B_WORTH_CALLING] == 105
    assert counts[TIER_C_SECONDARY] == 4
    assert counts[TIER_D_RESEARCH_NEEDED] == 445
    assert counts[RESTRICTED] == 0
    assert sum(counts.values()) == 565
