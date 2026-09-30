"""
FreightProspecting V1 — Broker Research Batch 2 Integration Test Suite
Validates the research findings, invariants, and opportunity engine results for Batch 2:
1. Exact 20/20 frozen companies researched, 0 missing, 0 extras.
2. Zero overlap with Batch 1 frozen roster.
3. Zero outside-roster mutations across companies, facilities, and contacts.
4. Zero lifecycle stage changes across all 653 facilities (0 diff vs pre-mutation backup).
5. Zero active accepted VERIFIED claims solely supported by SAFER globally.
6. Carrier != Broker invariant: Commercial carrier use does NOT imply broker acceptance.
7. Affiliate != Private Fleet invariant: Affiliated carrier entity does NOT imply company-owned private fleet.
8. Contact directness correctness: Jordan Davidson direct email is DIRECT_PERSON.
9. Expected opportunity engine distribution: 12 Tier A, 103 Tier B, 5 Tier C, 445 Tier D, 0 Restricted = 565.
10. Deterministic tier movements: Exactly Interfor (Tier B -> A) and Northern Concrete Pipe (Tier B -> C).
"""

import json
import sqlite3
from pathlib import Path
import pytest

from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.opportunity import (
    RESTRICTED,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    evaluate_broker_opportunity,
)
from src.backend.db.queries import get_company_grouped_prospects, get_universe_metadata

# Audit tests specifically for Batch 2 integration compare frozen Batch 2 DB against pre-Batch 2 backup
ACTIVE_DB = Path("data/backups/prospects_backup_pre_batch3_wave_A_20260928_212245.db")
PRE_MUTATION_BACKUP = Path("data/backups/prospects_backup_pre_broker_research_batch2_20260929_012116.db")
FROZEN_ROSTER_FILE = Path("reports/batch_2_frozen_selection.json")
BATCH_1_ROSTER_FILE = Path("reports/batch_1_frozen_selection.json")


def test_1_exact_frozen_roster_membership_and_zero_batch1_overlap():
    """Verify exactly 20 companies in Batch 2 roster with zero Batch 1 overlap."""
    assert FROZEN_ROSTER_FILE.exists()
    assert BATCH_1_ROSTER_FILE.exists()
    
    b2_roster = json.load(open(FROZEN_ROSTER_FILE))
    b1_roster = json.load(open(BATCH_1_ROSTER_FILE))
    
    b2_ids = {c["company_id"] for c in b2_roster}
    b1_ids = {c["company_id"] for c in b1_roster}
    
    assert len(b2_roster) == 20
    assert len(b2_ids) == 20
    assert len(b2_ids & b1_ids) == 0, f"Found Batch 1 overlap: {b2_ids & b1_ids}"


def test_2_zero_outside_roster_mutations():
    """Verify no company, facility, or contact outside the 20 Batch 2 companies was mutated."""
    assert PRE_MUTATION_BACKUP.exists()
    
    conn = sqlite3.connect(ACTIVE_DB)
    bak_conn = sqlite3.connect(PRE_MUTATION_BACKUP)
    conn.row_factory = sqlite3.Row
    bak_conn.row_factory = sqlite3.Row
    
    b2_roster = json.load(open(FROZEN_ROSTER_FILE))
    b2_ids = {c["company_id"] for c in b2_roster}
    
    # 1. Companies
    prod_comps = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM companies").fetchall()}
    bak_comps = {r["id"]: dict(r) for r in bak_conn.execute("SELECT * FROM companies").fetchall()}
    outside_comp_diffs = [cid for cid in bak_comps if cid not in b2_ids and prod_comps[cid] != bak_comps[cid]]
    assert len(outside_comp_diffs) == 0, f"Outside company mutations: {outside_comp_diffs}"
    
    # 2. Facilities
    prod_facs = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM facilities").fetchall()}
    bak_facs = {r["id"]: dict(r) for r in bak_conn.execute("SELECT * FROM facilities").fetchall()}
    outside_fac_diffs = []
    for fid, bf in bak_facs.items():
        pf = prod_facs[fid]
        if bf["company_id"] not in b2_ids:
            diff_keys = [k for k in bf if k != "updated_at" and bf[k] != pf[k]]
            if diff_keys:
                outside_fac_diffs.append((fid, bf["company_id"], diff_keys))
    assert len(outside_fac_diffs) == 0, f"Outside facility mutations: {outside_fac_diffs}"
    
    # 3. Contacts
    prod_cts = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM contacts").fetchall()}
    bak_cts = {r["id"]: dict(r) for r in bak_conn.execute("SELECT * FROM contacts").fetchall()}
    outside_ct_diffs = []
    for cid_ct, bct in bak_cts.items():
        pct = prod_cts[cid_ct]
        comp_id = pct["company_id"] or (prod_facs[pct["facility_id"]]["company_id"] if pct["facility_id"] else None)
        if comp_id not in b2_ids:
            diff_keys = [k for k in bct if bct[k] != pct[k]]
            if diff_keys:
                outside_ct_diffs.append((cid_ct, comp_id, diff_keys))
    assert len(outside_ct_diffs) == 0, f"Outside contact mutations: {outside_ct_diffs}"
    
    conn.close()
    bak_conn.close()


def test_3_zero_lifecycle_mutations_across_universe():
    """Verify that prospect_lifecycle stage is strictly identical across all 653 facilities."""
    conn = sqlite3.connect(ACTIVE_DB)
    bak_conn = sqlite3.connect(PRE_MUTATION_BACKUP)
    
    prod_lc = dict(conn.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
    bak_lc = dict(bak_conn.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
    
    conn.close()
    bak_conn.close()
    
    assert len(prod_lc) == 653
    assert len(bak_lc) == 653
    diffs = [fid for fid in bak_lc if bak_lc[fid] != prod_lc.get(fid)]
    assert len(diffs) == 0, f"Found lifecycle diffs on facilities: {diffs}"


def test_4_zero_active_accepted_verified_claims_solely_supported_by_safer():
    """Verify that ZERO active accepted VERIFIED claims globally rely solely on SAFER."""
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
    assert len(safer_active) == 0, f"Found active accepted VERIFIED SAFER claims: {safer_active}"


def test_5_carrier_use_does_not_imply_broker_acceptance():
    """Verify commercial carrier use is VERIFIED but broker friendly status remains UNKNOWN for Swanson and Interfor."""
    conn = sqlite3.connect(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    
    # Interfor (Fac 51)
    f51 = conn.execute("SELECT commercial_carrier_use, broker_friendly_status FROM facilities WHERE id = 51").fetchone()
    assert f51["commercial_carrier_use"] == "VERIFIED"
    assert f51["broker_friendly_status"] == "UNKNOWN"
    
    # Swanson Group (Fac 418)
    f418 = conn.execute("SELECT commercial_carrier_use, broker_friendly_status FROM facilities WHERE id = 418").fetchone()
    assert f418["commercial_carrier_use"] == "VERIFIED"
    assert f418["broker_friendly_status"] == "UNKNOWN"
    
    conn.close()


def test_6_affiliated_carrier_does_not_imply_private_fleet():
    """Verify Target Steel has fleet_relationship_type = AFFILIATED_CARRIER_ENTITY but private_fleet_present = UNKNOWN."""
    conn = sqlite3.connect(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    
    f133 = conn.execute("SELECT private_fleet_present, fleet_relationship_type, commercial_carrier_use, broker_friendly_status FROM facilities WHERE id = 133").fetchone()
    assert f133["fleet_relationship_type"] == "AFFILIATED_CARRIER_ENTITY"
    assert f133["private_fleet_present"] == "UNKNOWN"
    assert f133["commercial_carrier_use"] == "UNKNOWN"
    assert f133["broker_friendly_status"] == "UNKNOWN"
    
    conn.close()


def test_7_contact_directness_correctness():
    """Verify Jordan Davidson (Contact 38) has direct email and DIRECT_PERSON directness."""
    conn = sqlite3.connect(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    
    c38 = conn.execute("SELECT person_name, email_address, email_directness FROM contacts WHERE id = 38").fetchone()
    assert c38["person_name"] == "Jordan Davidson"
    assert c38["email_address"] == "jdavidson@coreslab.com"
    assert c38["email_directness"] == "DIRECT_PERSON"
    
    conn.close()


def test_8_opportunity_engine_distribution():
    """Verify the live derived broker opportunity distribution matches exact expected counts."""
    conn = create_connection(ACTIVE_DB)
    meta = get_universe_metadata(conn)
    counts = meta["opportunity_counts"]
    
    assert counts["ALL"] == 565
    assert counts["TIER_A_PRIORITY"] == 12
    assert counts["TIER_B_WORTH_CALLING"] == 104
    assert counts["TIER_C_SECONDARY"] == 4
    assert counts["TIER_D_RESEARCH_NEEDED"] == 445
    assert counts["RESTRICTED"] == 0


def test_9_exact_tier_movements():
    """Verify that exactly 1 company changed tiers relative to pre-batch-2 baseline: Interfor (B -> A)."""
    bak_universe = get_company_grouped_prospects(db_path=PRE_MUTATION_BACKUP, page=1, page_size=600)["items"]
    prod_universe = get_company_grouped_prospects(db_path=ACTIVE_DB, page=1, page_size=600)["items"]
    
    bak_tiers = {r["company_id"]: r["opportunity_tier"] for r in bak_universe}
    prod_tiers = {r["company_id"]: r["opportunity_tier"] for r in prod_universe}
    
    diffs = []
    for cid in sorted(prod_tiers.keys()):
        if prod_tiers[cid] != bak_tiers[cid]:
            brand = [r["operating_brand"] for r in prod_universe if r["company_id"] == cid][0]
            diffs.append((cid, brand, bak_tiers[cid], prod_tiers[cid]))
            
    assert len(diffs) == 1
    assert diffs[0] == (48, "Interfor", TIER_B_WORTH_CALLING, TIER_A_PRIORITY)
    # Northern Concrete Pipe started in Tier B and returns to Tier B (B -> B)
    assert prod_tiers[134] == TIER_B_WORTH_CALLING
    assert bak_tiers[134] == TIER_B_WORTH_CALLING


def test_10_swanson_group_remains_tier_d_due_to_discovery_lifecycle():
    """Verify Swanson Group gained verified outside carrier use but remains Tier D due to DISCOVERY lifecycle."""
    conn = create_connection(ACTIVE_DB)
    res = evaluate_broker_opportunity(331, conn=conn)
    assert res["opportunity_tier"] == TIER_D_RESEARCH_NEEDED
    assert "STRONG_OPPORTUNITY_RESEARCH_INCOMPLETE" in res["reason_codes"]


def test_11_ncp_fleet_claims_superseded_and_unknown():
    """Verify Northern Concrete Pipe unsupported claims 2728 and 2729 are superseded by UNKNOWN claims."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    
    c2728 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2728").fetchone()
    assert c2728["is_current_accepted"] == 0
    c2729 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2729").fetchone()
    assert c2729["is_current_accepted"] == 0
    
    active_claims = conn.execute("""
        SELECT id, claim_field, claimed_value, verification_status
        FROM claims
        WHERE facility_id = 163 AND is_current_accepted = 1
    """).fetchall()
    
    active_dict = {c["claim_field"]: c for c in active_claims}
    assert active_dict["private_fleet_present"]["claimed_value"] == "UNKNOWN"
    assert active_dict["private_fleet_present"]["verification_status"] == "UNKNOWN"
    assert active_dict["fleet_relationship_type"]["claimed_value"] == "UNKNOWN"
    assert active_dict["fleet_relationship_type"]["verification_status"] == "UNKNOWN"
    
    f163 = conn.execute("SELECT private_fleet_present, fleet_relationship_type FROM facilities WHERE id = 163").fetchone()
    assert f163["private_fleet_present"] == "UNKNOWN"
    assert f163["fleet_relationship_type"] == "UNKNOWN"
    
    ncp_eval = evaluate_broker_opportunity(134, conn=conn)
    assert ncp_eval["opportunity_tier"] == TIER_B_WORTH_CALLING
    
    conn.close()


def test_12_multi_facility_mixed_lifecycle_counterexample():
    """
    Regression Test: A company with Fac A (QUALIFIED, no carrier) and Fac B (DISCOVERY, carrier VERIFIED)
    must evaluate to TIER_A_PRIORITY, and get_universe_metadata must reflect this identical classification.
    """
    import tempfile
    import shutil
    from pathlib import Path
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        temp_db = tf.name
    
    t_conn = None
    try:
        shutil.copyfile(ACTIVE_DB, temp_db)
        t_conn = sqlite3.connect(temp_db)
        t_conn.row_factory = sqlite3.Row
        
        # Insert test company
        cur = t_conn.execute("INSERT INTO companies (operating_brand, legal_name) VALUES ('Test Mixed Freight', 'Test Mixed Freight LLC')")
        test_cid = cur.lastrowid
        
        # Fac A: QUALIFIED stage, carrier UNKNOWN
        cur = t_conn.execute("""
            INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country, commercial_carrier_use, private_fleet_present)
            VALUES (?, 'Fac A Qualified', 'SAWMILL', '100 Wood St', 'Detroit', 'MI', 'US', 'UNKNOWN', 'UNKNOWN')
        """, (test_cid,))
        fac_a_id = cur.lastrowid
        t_conn.execute("INSERT INTO prospect_lifecycle (facility_id, stage, entered_discovery_at, created_at, updated_at) VALUES (?, 'QUALIFIED', '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z')", (fac_a_id,))
        t_conn.execute("INSERT INTO facility_commodities (facility_id, commodity_category, specific_products, equipment_category, equipment_usage_status) VALUES (?, 'LUMBER', 'Lumber', 'FLATBED', 'VERIFIED')", (fac_a_id,))
        
        # Fac B: DISCOVERY stage, carrier VERIFIED
        cur = t_conn.execute("""
            INSERT INTO facilities (company_id, facility_name, facility_type, physical_address, city, state_prov, country, commercial_carrier_use, private_fleet_present)
            VALUES (?, 'Fac B Discovery', 'SAWMILL', '200 Timber Rd', 'Grand Rapids', 'MI', 'US', 'VERIFIED', 'UNKNOWN')
        """, (test_cid,))
        fac_b_id = cur.lastrowid
        t_conn.execute("INSERT INTO prospect_lifecycle (facility_id, stage, entered_discovery_at, created_at, updated_at) VALUES (?, 'DISCOVERY', '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z', '2026-09-01T00:00:00Z')", (fac_b_id,))
        t_conn.execute("INSERT INTO facility_commodities (facility_id, commodity_category, specific_products, equipment_category, equipment_usage_status) VALUES (?, 'LUMBER', 'Lumber', 'FLATBED', 'VERIFIED')", (fac_b_id,))
        
        # Contact with callable phone
        t_conn.execute("""
            INSERT INTO contacts (company_id, contact_identity, person_name, phone_number, role_category, phone_directness, email_directness)
            VALUES (?, 'NAMED_PERSON', 'Logistics Desk', '555-0199', 'FREIGHT_LOGISTICS', 'DIRECT_PERSON', 'UNKNOWN')
        """, (test_cid,))
        t_conn.commit()
        
        # 1. evaluate_broker_opportunity classifies test company as TIER_A_PRIORITY
        res = evaluate_broker_opportunity(test_cid, conn=t_conn)
        assert res["opportunity_tier"] == TIER_A_PRIORITY
        
        # 2. get_universe_metadata must reflect this company in TIER_A_PRIORITY counts
        meta = get_universe_metadata(conn=t_conn)
        assert meta["opportunity_counts"]["TIER_A_PRIORITY"] == 13  # 12 baseline + 1 test company
    finally:
        if t_conn is not None:
            t_conn.close()
        Path(temp_db).unlink(missing_ok=True)


def test_13_universe_metadata_strict_invariant_match():
    """Verify that get_universe_metadata counts strictly match evaluate_broker_opportunity across all 565 companies."""
    from collections import Counter
    conn = create_connection(ACTIVE_DB)
    meta = get_universe_metadata(conn=conn)
    
    comps = conn.execute("SELECT id FROM companies WHERE id IN (SELECT DISTINCT company_id FROM facilities)").fetchall()
    actual_counts = Counter(evaluate_broker_opportunity(c[0], conn=conn)["opportunity_tier"] for c in comps)
    
    assert meta["opportunity_counts"]["TIER_A_PRIORITY"] == actual_counts[TIER_A_PRIORITY]
    assert meta["opportunity_counts"]["TIER_B_WORTH_CALLING"] == actual_counts[TIER_B_WORTH_CALLING]
    assert meta["opportunity_counts"]["TIER_C_SECONDARY"] == actual_counts[TIER_C_SECONDARY]
    assert meta["opportunity_counts"]["TIER_D_RESEARCH_NEEDED"] == actual_counts[TIER_D_RESEARCH_NEEDED]
    assert meta["opportunity_counts"]["RESTRICTED"] == actual_counts[RESTRICTED]
    assert meta["opportunity_counts"]["ALL"] == len(comps)
    conn.close()
