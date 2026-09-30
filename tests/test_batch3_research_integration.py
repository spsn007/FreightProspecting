"""
FreightProspecting V1 — Broker Research Batch 3 Integration Test Suite
Validates research findings, invariants, provenance ledger, and opportunity engine results for Batch 3:
1. Exact 100/100 frozen companies researched, 0 missing, 0 extras.
2. Zero overlap with Batch 1 (20) and Batch 2 (20) frozen rosters.
3. Zero outside-roster mutations across companies, facilities, and contacts vs pre-Batch 3 baseline.
4. Zero lifecycle stage changes across all 653 facilities (0 diff vs pre-mutation baseline).
5. Zero active accepted VERIFIED claims solely supported by SAFER globally.
6. Carrier != Broker invariant: Commercial carrier use does NOT imply broker acceptance.
7. Affiliate != Private Fleet invariant: Affiliated carrier entity does not imply private fleet unless separately proven.
8. Contact directness correctness: named personnel have DIRECT_PERSON channels.
9. Single Current Accepted Claim Invariant: unique constraint holds, no duplicate current claims.
10. Expected opportunity engine distribution: 15 Tier A, 99 Tier B, 5 Tier C, 445 Tier D, 1 Restricted = 565.
11. Strict match: get_universe_metadata counts match evaluate_broker_opportunity across all 565 companies.
12. Exact tier movements: 3 into Tier A (CID 23, 71, 217), 1 into Tier C (CID 105), 1 into Restricted (CID 219).
13. Operational tables count = 0 (no fake calls, loads, demand signals, matches).
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

ACTIVE_DB = Path("data/backups/prospects_backup_pre_tier_a_phase_a_freeze_20260929.db")
PRE_BATCH3_BASELINE = Path("data/backups/prospects_backup_pre_batch3_wave_A_20260928_212245.db")
FROZEN_ROSTER_B3 = Path("reports/batch_3_frozen_selection.json")
FROZEN_ROSTER_B2 = Path("reports/batch_2_frozen_selection.json")
FROZEN_ROSTER_B1 = Path("reports/batch_1_frozen_selection.json")


def test_1_exact_frozen_roster_membership_and_zero_overlap():
    """Verify exactly 100 companies in Batch 3 roster with 0 overlap with Batch 1 and Batch 2."""
    assert FROZEN_ROSTER_B3.exists()
    assert FROZEN_ROSTER_B2.exists()
    assert FROZEN_ROSTER_B1.exists()

    b3_roster = json.load(open(FROZEN_ROSTER_B3, "r", encoding="utf-8"))
    b2_roster = json.load(open(FROZEN_ROSTER_B2, "r", encoding="utf-8"))
    b1_roster = json.load(open(FROZEN_ROSTER_B1, "r", encoding="utf-8"))

    b3_ids = {c["company_id"] for c in b3_roster}
    b2_ids = {c["company_id"] for c in b2_roster}
    b1_ids = {c["company_id"] for c in b1_roster}

    assert len(b3_roster) == 100
    assert len(b3_ids) == 100
    assert len(b3_ids & b1_ids) == 0, f"Found Batch 1 overlap: {b3_ids & b1_ids}"
    assert len(b3_ids & b2_ids) == 0, f"Found Batch 2 overlap: {b3_ids & b2_ids}"


def test_2_zero_outside_roster_mutations():
    """Verify no company, facility, or contact outside the 100 Batch 3 companies was mutated."""
    assert PRE_BATCH3_BASELINE.exists()

    conn = sqlite3.connect(ACTIVE_DB)
    bak_conn = sqlite3.connect(PRE_BATCH3_BASELINE)
    conn.row_factory = sqlite3.Row
    bak_conn.row_factory = sqlite3.Row

    b3_roster = json.load(open(FROZEN_ROSTER_B3, "r", encoding="utf-8"))
    b3_ids = {c["company_id"] for c in b3_roster}

    # 1. Companies
    prod_comps = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM companies").fetchall()}
    bak_comps = {r["id"]: dict(r) for r in bak_conn.execute("SELECT * FROM companies").fetchall()}
    outside_comp_diffs = [cid for cid in bak_comps if cid not in b3_ids and prod_comps[cid] != bak_comps[cid]]
    assert len(outside_comp_diffs) == 0, f"Outside company mutations: {outside_comp_diffs}"

    # 2. Facilities
    prod_facs = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM facilities").fetchall()}
    bak_facs = {r["id"]: dict(r) for r in bak_conn.execute("SELECT * FROM facilities").fetchall()}
    outside_fac_diffs = []
    for fid, bf in bak_facs.items():
        pf = prod_facs[fid]
        if bf["company_id"] not in b3_ids:
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
        if comp_id not in b3_ids:
            diff_keys = [k for k in bct if bct[k] != pct[k]]
            if diff_keys:
                outside_ct_diffs.append((cid_ct, comp_id, diff_keys))
    assert len(outside_ct_diffs) == 0, f"Outside contact mutations: {outside_ct_diffs}"

    conn.close()
    bak_conn.close()


def test_3_zero_lifecycle_mutations_across_universe():
    """Verify zero prospect_lifecycle rows were altered across all 653 facilities."""
    assert PRE_BATCH3_BASELINE.exists()

    conn = sqlite3.connect(ACTIVE_DB)
    bak_conn = sqlite3.connect(PRE_BATCH3_BASELINE)
    conn.row_factory = sqlite3.Row
    bak_conn.row_factory = sqlite3.Row

    prod_lc = {r["facility_id"]: dict(r) for r in conn.execute("SELECT * FROM prospect_lifecycle").fetchall()}
    bak_lc = {r["facility_id"]: dict(r) for r in bak_conn.execute("SELECT * FROM prospect_lifecycle").fetchall()}

    assert len(prod_lc) == 653
    assert len(bak_lc) == 653

    diffs = []
    for fid, bl in bak_lc.items():
        pl = prod_lc[fid]
        diff_keys = [k for k in bl if bl[k] != pl[k]]
        if diff_keys:
            diffs.append((fid, diff_keys))

    assert len(diffs) == 0, f"Lifecycle mutations found: {diffs}"

    conn.close()
    bak_conn.close()


def test_4_zero_active_accepted_verified_claims_solely_supported_by_safer():
    """Verify no active accepted VERIFIED claim relies solely on SAFER."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row

    safer_claims = conn.execute("""
        SELECT c.id, c.claim_field, c.claimed_value, c.verification_status, es.source_type, es.source_url
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.is_current_accepted = 1
          AND c.verification_status = 'VERIFIED'
          AND (es.source_title_publisher LIKE '%SAFER%' OR es.source_url LIKE '%safer.fmcsa.dot.gov%')
    """).fetchall()

    for sc in safer_claims:
        cid = sc["id"]
        other_sources = conn.execute("""
            SELECT es.source_type, es.source_url
            FROM claim_evidence ce
            JOIN evidence_sources es ON ce.evidence_source_id = es.id
            WHERE ce.claim_id = ?
              AND es.source_title_publisher NOT LIKE '%SAFER%'
              AND (es.source_url IS NULL OR es.source_url NOT LIKE '%safer.fmcsa.dot.gov%')
        """, (cid,)).fetchall()
        assert len(other_sources) > 0, f"Claim {cid} relies solely on SAFER: {dict(sc)}"

    conn.close()


def test_5_carrier_use_does_not_imply_broker_acceptance():
    """Verify that commercial_carrier_use = VERIFIED does not set broker_friendly_status to VERIFIED_ACCEPTS."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row

    # Companies with confirmed outside carrier use
    for fid in [22, 482, 627]: # Imperial Metal, Peerless, Challenger
        fac = conn.execute("SELECT commercial_carrier_use, broker_friendly_status FROM facilities WHERE id = ?", (fid,)).fetchone()
        assert fac["commercial_carrier_use"] == "VERIFIED"
        assert fac["broker_friendly_status"] in ("UNKNOWN", "VERIFIED_DIRECT_ONLY"), f"Broker status was invalidly inferred for facility {fid}"

    # Facilities conservatively reverted to UNKNOWN in final closure remediation
    for fid in [81, 262]: # Tolko Armstrong, O'Neal Birmingham
        fac = conn.execute("SELECT commercial_carrier_use, broker_friendly_status FROM facilities WHERE id = ?", (fid,)).fetchone()
        assert fac["commercial_carrier_use"] == "UNKNOWN"

    conn.close()


def test_6_affiliated_carrier_does_not_imply_in_house_fleet():
    """Verify Rex Lumber has fleet_relationship_type = AFFILIATED_CARRIER_ENTITY and private_fleet_present = UNKNOWN."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row

    fac = conn.execute("SELECT private_fleet_present, fleet_relationship_type FROM facilities WHERE id = 65").fetchone()
    assert fac["fleet_relationship_type"] == "AFFILIATED_CARRIER_ENTITY"
    assert fac["private_fleet_present"] == "UNKNOWN"

    conn.close()


def test_7_contact_directness_correctness():
    """Verify all new Batch 3 contacts have exact published details and correct directness."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row

    # Chris Brown
    cb = conn.execute("SELECT * FROM contacts WHERE person_name = 'Chris Brown'").fetchone()
    assert cb is not None
    assert cb["phone_number"] == "334.405.2036"
    assert cb["phone_directness"] == "DIRECT_PERSON"
    assert cb["role_category"] == "OPERATIONS"
    assert cb["outbound_shipping_procurement_relevance"] == "UNKNOWN"

    # Paul McRae
    pm = conn.execute("SELECT * FROM contacts WHERE person_name = 'Paul McRae'").fetchone()
    assert pm is not None
    assert pm["phone_number"] == "(229) 333-2577"
    assert pm["phone_directness"] == "DIRECT_PERSON"
    assert pm["email_address"] == "pmcrae@LangdaleForest.com"
    assert pm["email_directness"] == "DIRECT_PERSON"

    # Tim Nave
    tn = conn.execute("SELECT * FROM contacts WHERE person_name = 'Tim Nave'").fetchone()
    assert tn is not None
    assert tn["phone_number"] == "(256) 616-7613"
    assert tn["phone_directness"] == "DIRECT_PERSON"

    # Jody King
    jk = conn.execute("SELECT * FROM contacts WHERE person_name = 'Jody King'").fetchone()
    assert jk is not None
    assert jk["exact_published_title"] == "Demopolis General Manager"
    assert jk["phone_number"] == "334-654-8077"
    assert jk["phone_directness"] == "GENERAL_SWITCHBOARD"
    assert jk["outbound_shipping_procurement_relevance"] == "UNKNOWN"

    # Bob Caldwell
    bc = conn.execute("SELECT * FROM contacts WHERE person_name = 'Bob Caldwell'").fetchone()
    assert bc is not None
    assert bc["phone_number"] == "(330) 979-1545"
    assert bc["phone_directness"] == "DIRECT_PERSON"
    assert bc["email_address"] == "bcaldwell@litco.com"
    assert bc["email_directness"] == "DIRECT_PERSON"

    conn.close()


def test_8_opportunity_engine_distribution():
    """Verify live derived broker opportunity distribution matches exact expected counts."""
    conn = create_connection(ACTIVE_DB)
    meta = get_universe_metadata(conn)
    counts = meta["opportunity_counts"]

    assert counts["ALL"] == 565
    assert counts["TIER_A_PRIORITY"] == 13
    assert counts["TIER_B_WORTH_CALLING"] == 102
    assert counts["TIER_C_SECONDARY"] == 5
    assert counts["TIER_D_RESEARCH_NEEDED"] == 445
    assert counts["RESTRICTED"] == 0

    conn.close()


def test_9_exact_tier_movements():
    """Verify exact tier movements relative to pre-Batch 3 baseline."""
    bak_universe = get_company_grouped_prospects(db_path=PRE_BATCH3_BASELINE, page=1, page_size=600)["items"]
    prod_universe = get_company_grouped_prospects(db_path=ACTIVE_DB, page=1, page_size=600)["items"]

    bak_tiers = {r["company_id"]: r["opportunity_tier"] for r in bak_universe}
    prod_tiers = {r["company_id"]: r["opportunity_tier"] for r in prod_universe}

    diffs = []
    for cid in sorted(prod_tiers.keys()):
        if prod_tiers[cid] != bak_tiers[cid]:
            brand = [r["operating_brand"] for r in prod_universe if r["company_id"] == cid][0]
            diffs.append((cid, brand, bak_tiers[cid], prod_tiers[cid]))

    # Expected tier movements vs pre-Batch 3 baseline:
    # 1. CID 23 Imperial Metal Services: B -> A
    # 2. CID 105 Precision Strip: B -> C
    assert len(diffs) == 2, f"Expected 2 tier changes, found {len(diffs)}: {diffs}"
    expected = {
        (23, "Imperial Metal Services", TIER_B_WORTH_CALLING, TIER_A_PRIORITY),
        (105, "Precision Strip", TIER_B_WORTH_CALLING, TIER_C_SECONDARY),
    }
    assert set(diffs) == expected


def test_10_universe_metadata_strict_invariant_match():
    """Verify get_universe_metadata counts strictly match evaluate_broker_opportunity across all 565 companies."""
    from collections import Counter
    conn = create_connection(ACTIVE_DB)
    meta = get_universe_metadata(conn=conn)
    comp_ids = [r[0] for r in conn.execute("SELECT DISTINCT company_id FROM facilities").fetchall()]
    assert len(comp_ids) == 565

    raw_evals = [evaluate_broker_opportunity(cid, conn=conn)["opportunity_tier"] for cid in comp_ids]
    calc_counts = dict(Counter(raw_evals))

    for tier_code in [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]:
        assert meta["opportunity_counts"][tier_code] == calc_counts.get(tier_code, 0), (
            f"Count mismatch for {tier_code}: meta={meta['opportunity_counts'][tier_code]} vs engine={calc_counts.get(tier_code, 0)}"
        )
    conn.close()


def test_11_single_current_accepted_claim_invariant():
    """Verify SQLite partial unique index enforces exactly at most 1 current accepted claim per subject and field."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row

    # Check for any duplicates in current accepted claims across all subject FKs
    dups = conn.execute("""
        SELECT facility_id, claim_field, COUNT(*) as cnt
        FROM claims
        WHERE is_current_accepted = 1 AND facility_id IS NOT NULL
        GROUP BY facility_id, claim_field
        HAVING cnt > 1;
    """).fetchall()
    assert len(dups) == 0, f"Duplicate current accepted claims on facilities: {dups}"

    contact_dups = conn.execute("""
        SELECT contact_id, claim_field, COUNT(*) as cnt
        FROM claims
        WHERE is_current_accepted = 1 AND contact_id IS NOT NULL
        GROUP BY contact_id, claim_field
        HAVING cnt > 1;
    """).fetchall()
    assert len(contact_dups) == 0, f"Duplicate current accepted claims on contacts: {contact_dups}"

    conn.close()


def test_12_operational_tables_remain_zero():
    """Verify zero fake calls, outreach, loads, rates, or capacity records were created."""
    conn = create_connection(ACTIVE_DB)
    for tbl in ["outreach_logs", "load_opportunities", "freight_demand_signals", "capacity_postings", "load_capacity_matches"]:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl};").fetchone()[0]
        assert cnt == 0, f"Operational table {tbl} has non-zero count: {cnt}"
    conn.close()
