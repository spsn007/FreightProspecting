"""
FreightProspecting V1 — Batch 3 Final Closure Remediation Test Suite
Mandatory 20-point test coverage validating all Codex audit blocker resolutions:
1. Tolko scope correction
2. Precision fleet relationship correction
3. O'Neal carrier correction
4. Peerless ownership correction
5. Rex procurement relevance conservative truth
6. Two Rivers exact title
7. Two Rivers phone directness
8. Mixed-facility DIRECT_ONLY semantics (Steel Dynamics)
9. All-restricted facility company
10. Company DNC/restriction
11. Engine == metadata counts across all 5 tiers
12. Engine == each directory tier filter (set equality)
13. No tier-filter overlap (0 pairwise overlap)
14. Search + tier combination
15. Pagination + tier combination
16. 100-company documented research provenance
17. No google.com misclassified as COMPANY_WEBSITE
18. No SAFER-only accepted truth
19. Lifecycle diff = 0 across all 653 facilities
20. Operational tables = 0
"""

import json
import sqlite3
from pathlib import Path
import pytest

from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.opportunity import (
    BROKER_OPPORTUNITY_RULE_VERSION,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    RESTRICTED,
    evaluate_broker_opportunity,
    evaluate_broker_opportunity_raw,
    get_opportunity_tier_company_ids,
)
from src.backend.db.queries import (
    get_company_grouped_prospects,
    get_universe_metadata,
)

ACTIVE_DB = Path("data/backups/prospects_backup_pre_tier_a_phase_a_freeze_20260929.db")
PRE_BATCH3_BASELINE = Path("data/backups/prospects_backup_pre_batch3_wave_A_20260928_212245.db")
FROZEN_ROSTER_B3 = Path("reports/batch_3_frozen_selection.json")


# 1. Tolko scope correction
def test_1_tolko_scope_correction():
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        # Facility 81 commercial carrier use must be UNKNOWN
        fac = conn.execute("SELECT commercial_carrier_use FROM facilities WHERE id = 81").fetchone()
        assert fac["commercial_carrier_use"] == "UNKNOWN"

        # Claim 2743 must be superseded (is_current_accepted = 0)
        c2743 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2743").fetchone()
        assert c2743["is_current_accepted"] == 0

        # Current accepted claim for Facility 81 commercial_carrier_use must be UNKNOWN
        cur_claim = conn.execute("""
            SELECT id, claimed_value, verification_status, is_current_accepted
            FROM claims
            WHERE facility_id = 81 AND claim_field = 'commercial_carrier_use' AND is_current_accepted = 1
        """).fetchone()
        assert cur_claim is not None
        assert cur_claim["claimed_value"] == "UNKNOWN"
        assert cur_claim["verification_status"] == "UNKNOWN"

        # Tolko (Company 71) evaluates to TIER_B_WORTH_CALLING
        res = evaluate_broker_opportunity(71, conn=conn)
        assert res["opportunity_tier"] == TIER_B_WORTH_CALLING
    finally:
        conn.close()


# 2. Precision fleet relationship correction
def test_2_precision_fleet_relationship_correction():
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        fac = conn.execute("SELECT private_fleet_present, fleet_relationship_type FROM facilities WHERE id = 134").fetchone()
        assert fac["private_fleet_present"] == "VERIFIED_PRESENT"
        assert fac["fleet_relationship_type"] == "UNKNOWN"

        # Claim 2747 superseded
        c2747 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2747").fetchone()
        assert c2747["is_current_accepted"] == 0

        cur_claim = conn.execute("""
            SELECT id, claimed_value, verification_status, is_current_accepted
            FROM claims
            WHERE facility_id = 134 AND claim_field = 'fleet_relationship_type' AND is_current_accepted = 1
        """).fetchone()
        assert cur_claim is not None
        assert cur_claim["claimed_value"] == "UNKNOWN"

        # Precision Strip evaluates to TIER_C_SECONDARY
        res = evaluate_broker_opportunity(105, conn=conn)
        assert res["opportunity_tier"] == TIER_C_SECONDARY
    finally:
        conn.close()


# 3. O'Neal carrier correction
def test_3_oneal_carrier_correction():
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        fac = conn.execute("SELECT commercial_carrier_use FROM facilities WHERE id = 262").fetchone()
        assert fac["commercial_carrier_use"] == "UNKNOWN"

        # Claim 2748 superseded
        c2748 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2748").fetchone()
        assert c2748["is_current_accepted"] == 0

        cur_claim = conn.execute("""
            SELECT id, claimed_value, verification_status, is_current_accepted
            FROM claims
            WHERE facility_id = 262 AND claim_field = 'commercial_carrier_use' AND is_current_accepted = 1
        """).fetchone()
        assert cur_claim is not None
        assert cur_claim["claimed_value"] == "UNKNOWN"

        # O'Neal Steel evaluates to TIER_B_WORTH_CALLING
        res = evaluate_broker_opportunity(217, conn=conn)
        assert res["opportunity_tier"] == TIER_B_WORTH_CALLING
    finally:
        conn.close()


# 4. Peerless ownership correction
def test_4_peerless_ownership_correction():
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        fac = conn.execute("SELECT private_fleet_present, fleet_relationship_type, commercial_carrier_use FROM facilities WHERE id = 482").fetchone()
        assert fac["private_fleet_present"] == "VERIFIED_PRESENT"
        assert fac["commercial_carrier_use"] == "VERIFIED"
        assert fac["fleet_relationship_type"] == "UNKNOWN"

        # Claim 2752 superseded
        c2752 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2752").fetchone()
        assert c2752["is_current_accepted"] == 0

        cur_claim = conn.execute("""
            SELECT id, claimed_value, verification_status, is_current_accepted
            FROM claims
            WHERE facility_id = 482 AND claim_field = 'fleet_relationship_type' AND is_current_accepted = 1
        """).fetchone()
        assert cur_claim is not None
        assert cur_claim["claimed_value"] == "UNKNOWN"

        # Peerless Steel evaluates to TIER_D_RESEARCH_NEEDED (Troy is in DISCOVERY)
        res = evaluate_broker_opportunity(395, conn=conn)
        assert res["opportunity_tier"] == TIER_D_RESEARCH_NEEDED
    finally:
        conn.close()


# 5. Rex procurement relevance conservative truth
def test_5_rex_procurement_relevance_conservative_truth():
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        ct = conn.execute("SELECT * FROM contacts WHERE id = 666").fetchone()
        assert ct["person_name"] == "Chris Brown"
        assert ct["exact_published_title"] == "General Manager"
        assert ct["role_category"] == "OPERATIONS"
        assert ct["phone_number"] == "334.405.2036"
        assert ct["phone_directness"] == "DIRECT_PERSON"
        assert ct["outbound_shipping_procurement_relevance"] == "UNKNOWN"
    finally:
        conn.close()


# 6. Two Rivers exact title
def test_6_two_rivers_exact_title():
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        ct = conn.execute("SELECT * FROM contacts WHERE id = 669").fetchone()
        assert ct["person_name"] == "Jody King"
        assert ct["exact_published_title"] == "Demopolis General Manager"
    finally:
        conn.close()


# 7. Two Rivers phone directness
def test_7_two_rivers_phone_directness():
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        ct = conn.execute("SELECT * FROM contacts WHERE id = 669").fetchone()
        assert ct["phone_number"] == "334-654-8077"
        assert ct["phone_directness"] == "GENERAL_SWITCHBOARD"
        assert ct["outbound_shipping_procurement_relevance"] == "UNKNOWN"
    finally:
        conn.close()


# 8. Mixed-facility DIRECT_ONLY semantics (Steel Dynamics)
def test_8_mixed_facility_direct_only_semantics():
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        # Butler facility (266) is DIRECT_ONLY -> RESTRICTED
        butler_opp = evaluate_broker_opportunity(219, facility_id=266, conn=conn)
        assert butler_opp["opportunity_tier"] == RESTRICTED

        # Columbia City facility (267) is UNKNOWN -> TIER_B_WORTH_CALLING
        columbia_opp = evaluate_broker_opportunity(219, facility_id=267, conn=conn)
        assert columbia_opp["opportunity_tier"] == TIER_B_WORTH_CALLING

        # Steel Dynamics company (219) evaluates across actionable non-restricted facility -> TIER_B_WORTH_CALLING
        comp_opp = evaluate_broker_opportunity(219, conn=conn)
        assert comp_opp["opportunity_tier"] == TIER_B_WORTH_CALLING
    finally:
        conn.close()


# 9. All-restricted facility company
def test_9_all_restricted_facility_company():
    # Functional test using raw evaluation
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="VERIFIED",
        broker_friendly_status="VERIFIED_DIRECT_ONLY",
        lifecycle_stage="QUALIFIED",
        has_callable_route=True,
        has_ftl_fit=True,
    )
    assert res["opportunity_tier"] == RESTRICTED
    assert "RESTRICTED_DIRECT_ONLY_POLICY" in res["reason_codes"]


# 10. Company DNC / restriction
def test_10_company_dnc_restriction():
    res = evaluate_broker_opportunity_raw(
        private_fleet_present="UNKNOWN",
        commercial_carrier_use="VERIFIED",
        broker_friendly_status="VERIFIED_ACCEPTS",
        lifecycle_stage="QUALIFIED",
        has_callable_route=True,
        has_ftl_fit=True,
        suppression_status="DO_NOT_CONTACT",
        is_lane_suppression_only=False,
    )
    assert res["opportunity_tier"] == RESTRICTED
    assert "RESTRICTED_DO_NOT_CONTACT" in res["reason_codes"]


# 11. Engine == metadata counts across all 5 tiers
def test_11_engine_metadata_equality():
    conn = create_connection(ACTIVE_DB)
    tier_map = get_opportunity_tier_company_ids(conn=conn)
    meta = get_universe_metadata(conn=conn)
    meta_opp = meta["opportunity_counts"]

    for t in [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]:
        assert len(tier_map[t]) == meta_opp[t], f"Mismatch for {t}: engine={len(tier_map[t])} vs meta={meta_opp[t]}"
    conn.close()


# 12. Engine == each directory tier filter (set equality)
def test_12_engine_directory_set_equality():
    conn = create_connection(ACTIVE_DB)
    tier_map = get_opportunity_tier_company_ids(conn=conn)

    for tier_key in [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]:
        res = get_company_grouped_prospects(page=1, page_size=600, tier=tier_key, conn=conn)
        dir_cids = {item["company_id"] for item in res["items"]}
        engine_cids = set(tier_map[tier_key])
        assert dir_cids == engine_cids, f"Directory set mismatch for {tier_key}: dir={len(dir_cids)} vs engine={len(engine_cids)}"
    conn.close()


# 13. No tier-filter overlap (pairwise disjoint)
def test_13_no_tier_filter_overlap():
    conn = create_connection(ACTIVE_DB)
    tier_map = get_opportunity_tier_company_ids(conn=conn)
    tiers = [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]

    for i in range(len(tiers)):
        for j in range(i + 1, len(tiers)):
            t1, t2 = tiers[i], tiers[j]
            overlap = set(tier_map[t1]) & set(tier_map[t2])
            assert len(overlap) == 0, f"Overlap between {t1} and {t2}: {overlap}"
    conn.close()


# 14. Search + tier combination
def test_14_search_plus_tier():
    conn = create_connection(ACTIVE_DB)
    res = get_company_grouped_prospects(search="Steel", tier="TIER_A_PRIORITY", page=1, page_size=50, conn=conn)
    for item in res["items"]:
        assert item["opportunity_tier"] == TIER_A_PRIORITY
        brand = item["operating_brand"].lower()
        searchable = item.get("searchable_text", "").lower()
        assert "steel" in brand or "steel" in searchable
    conn.close()


# 15. Pagination + tier combination
def test_15_pagination_plus_tier():
    conn = create_connection(ACTIVE_DB)
    p1 = get_company_grouped_prospects(tier="TIER_B_WORTH_CALLING", page=1, page_size=25, conn=conn)
    p2 = get_company_grouped_prospects(tier="TIER_B_WORTH_CALLING", page=2, page_size=25, conn=conn)

    assert p1["total_count"] == 102
    assert p2["total_count"] == 102
    assert len(p1["items"]) == 25
    assert len(p2["items"]) == 25

    p1_ids = {item["company_id"] for item in p1["items"]}
    p2_ids = {item["company_id"] for item in p2["items"]}
    assert len(p1_ids & p2_ids) == 0, "Pages 1 and 2 must have disjoint company IDs"

    for item in p1["items"] + p2["items"]:
        assert item["opportunity_tier"] == TIER_B_WORTH_CALLING
    conn.close()


# 16. 100-company documented research provenance
def test_16_100_company_documented_research_provenance():
    assert FROZEN_ROSTER_B3.exists()
    b3_roster = json.load(open(FROZEN_ROSTER_B3, "r", encoding="utf-8"))
    assert len(b3_roster) == 100

    reports_dir = Path("reports")
    all_staging_cids = set()
    for w in ["A", "B", "C", "D"]:
        data = json.loads((reports_dir / f"batch_3_wave_{w}_research_staging.json").read_text(encoding="utf-8"))
        for item in data:
            all_staging_cids.add(item["company_id"])

    assert len(all_staging_cids) == 100
    roster_cids = {c["company_id"] for c in b3_roster}
    assert all_staging_cids == roster_cids


# 17. No google.com misclassified as COMPANY_WEBSITE
def test_17_no_google_misclassified_as_company_website():
    reports_dir = Path("reports")
    misclassified = 0
    for w in ["A", "B", "C", "D"]:
        data = json.loads((reports_dir / f"batch_3_wave_{w}_research_staging.json").read_text(encoding="utf-8"))
        for item in data:
            for s in item.get("research_findings", {}).get("sources", []):
                if "google.com" in s.get("source_url", "") and s.get("source_type") == "COMPANY_WEBSITE":
                    misclassified += 1

    assert misclassified == 0


# 18. No SAFER-only accepted truth
def test_18_no_safer_only_accepted_truth():
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    safer_only = conn.execute("""
        SELECT c.id
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.is_current_accepted = 1
          AND c.verification_status = 'VERIFIED'
        GROUP BY c.id
        HAVING count(DISTINCT es.source_type) = 1
           AND MAX(es.source_type) = 'FMCSA_SAFER'
    """).fetchall()
    assert len(safer_only) == 0
    conn.close()


# 19. Lifecycle diff = 0 across all 653 facilities
def test_19_lifecycle_diff_zero():
    conn = create_connection(ACTIVE_DB)
    bak_conn = create_connection(PRE_BATCH3_BASELINE)
    conn.row_factory = sqlite3.Row
    bak_conn.row_factory = sqlite3.Row

    prod_lc = {r["facility_id"]: dict(r) for r in conn.execute("SELECT * FROM prospect_lifecycle").fetchall()}
    bak_lc = {r["facility_id"]: dict(r) for r in bak_conn.execute("SELECT * FROM prospect_lifecycle").fetchall()}

    assert len(prod_lc) == 653
    assert len(bak_lc) == 653

    for fid, bl in bak_lc.items():
        pl = prod_lc[fid]
        diffs = [k for k in bl if bl[k] != pl[k]]
        assert len(diffs) == 0, f"Lifecycle changed for facility {fid}: {diffs}"

    conn.close()
    bak_conn.close()


# 20. Operational tables = 0
def test_20_operational_tables_zero():
    conn = create_connection(ACTIVE_DB)
    for tbl in ["outreach_logs", "load_opportunities", "freight_demand_signals", "capacity_postings", "load_capacity_matches"]:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl};").fetchone()[0]
        assert cnt == 0, f"Operational table {tbl} has count {cnt} > 0"
    conn.close()
