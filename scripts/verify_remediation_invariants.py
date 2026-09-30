import sqlite3
import json
import hashlib
import sys
from pathlib import Path
sys.path.insert(0, ".")

from src.backend.db.opportunity import (
    RESTRICTED,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    evaluate_broker_opportunity,
)
from src.backend.db.queries import get_company_grouped_prospects, get_universe_metadata

DB_PATH = Path("data/prospects.db")
BASELINE_PRE_PHASE_A = Path("data/backups/prospects_backup_pre_tier_a_phase_a_freeze_20260929.db")
PRE_REMEDIATION_BACKUP = Path("data/backups/prospects_backup_pre_tier_a_phase_a_wave_E_20260929_062651.db")

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. PRAGMAs
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    print(f"PRAGMA integrity_check: {integrity}")
    print(f"PRAGMA foreign_key_check violations: {len(fk_violations)}")
    assert integrity == "ok"
    assert len(fk_violations) == 0

    # 2. Lifecycle diff vs baseline
    bak = sqlite3.connect(BASELINE_PRE_PHASE_A)
    p_life = dict(conn.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
    b_life = dict(bak.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
    diffs = [fid for fid, s in b_life.items() if p_life.get(fid) != s]
    print(f"Lifecycle diffs across all {len(p_life)} facilities: {len(diffs)}")
    assert len(diffs) == 0
    bak.close()

    # 3. Operational tables
    op_tables = ["freight_demand_signals", "load_opportunities", "carrier_lane_activity", "capacity_postings"]
    op_counts = {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in op_tables}
    print(f"Operational table counts: {op_counts}")
    assert all(c == 0 for c in op_counts.values())

    # 4. SAFER-only claims
    safer_claims = conn.execute("""
        SELECT c.id FROM claims c
        JOIN claim_evidence ce ON ce.claim_id = c.id
        JOIN evidence_sources es ON es.id = ce.evidence_source_id
        WHERE c.is_current_accepted = 1
          AND c.verification_status = 'VERIFIED'
          AND es.source_type = 'GOVERNMENT_REGISTRY'
          AND es.source_url LIKE '%safety.fmcsa.dot.gov%'
          AND c.claim_field IN ('commercial_carrier_use', 'broker_friendly_status', 'private_fleet_present')
    """).fetchall()
    print(f"SAFER-only verified operational claims: {len(safer_claims)}")
    assert len(safer_claims) == 0

    # 5. Orphans
    orphan_claims = conn.execute("""
        SELECT count(*) FROM claims c
        WHERE c.company_id IS NOT NULL AND c.company_id NOT IN (SELECT id FROM companies)
           OR c.facility_id IS NOT NULL AND c.facility_id NOT IN (SELECT id FROM facilities)
           OR c.contact_id IS NOT NULL AND c.contact_id NOT IN (SELECT id FROM contacts)
    """).fetchone()[0]
    print(f"Orphan claims: {orphan_claims}")
    assert orphan_claims == 0

    orphan_ce = conn.execute("""
        SELECT count(*) FROM claim_evidence ce
        WHERE ce.claim_id NOT IN (SELECT id FROM claims)
           OR ce.evidence_source_id NOT IN (SELECT id FROM evidence_sources)
    """).fetchone()[0]
    print(f"Orphan claim_evidence: {orphan_ce}")
    assert orphan_ce == 0

    # 6. Duplicate current accepted groups
    dup_comp = conn.execute("""
        SELECT company_id, claim_field, count(*) FROM claims
        WHERE is_current_accepted = 1 AND company_id IS NOT NULL
        GROUP BY company_id, claim_field HAVING count(*) > 1
    """).fetchall()
    dup_fac = conn.execute("""
        SELECT facility_id, claim_field, count(*) FROM claims
        WHERE is_current_accepted = 1 AND facility_id IS NOT NULL
        GROUP BY facility_id, claim_field HAVING count(*) > 1
    """).fetchall()
    dup_ct = conn.execute("""
        SELECT contact_id, claim_field, count(*) FROM claims
        WHERE is_current_accepted = 1 AND contact_id IS NOT NULL
        GROUP BY contact_id, claim_field HAVING count(*) > 1
    """).fetchall()
    print(f"Duplicate current accepted: comp={len(dup_comp)}, fac={len(dup_fac)}, ct={len(dup_ct)}")
    assert len(dup_comp) == 0 and len(dup_fac) == 0 and len(dup_ct) == 0

    # 7. Engine distribution
    all_comps = [r[0] for r in conn.execute("SELECT id FROM companies WHERE id IN (SELECT DISTINCT company_id FROM facilities)").fetchall()]
    engine_tiers = {}
    engine_tier_ids = {TIER_A_PRIORITY: set(), TIER_B_WORTH_CALLING: set(), TIER_C_SECONDARY: set(), TIER_D_RESEARCH_NEEDED: set(), RESTRICTED: set()}
    for cid in all_comps:
        res = evaluate_broker_opportunity(cid, conn=conn)
        t = res["opportunity_tier"]
        engine_tiers[t] = engine_tiers.get(t, 0) + 1
        engine_tier_ids[t].add(cid)
    print(f"\nENGINE DISTRIBUTION ({len(all_comps)} companies): {engine_tiers}")

    # 8. Metadata distribution
    meta = get_universe_metadata(conn)
    meta_tiers = meta["opportunity_counts"]
    print(f"METADATA DISTRIBUTION: {meta_tiers}")

    # 9. Directory distribution
    dir_tier_ids = {}
    for t in [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]:
        items = get_company_grouped_prospects(tier=t, db_path=DB_PATH)
        dir_tier_ids[t] = {item["company_id"] for item in items}
    dir_counts = {t: len(ids) for t, ids in dir_tier_ids.items()}
    print(f"DIRECTORY DISTRIBUTION: {dir_counts}")

    # 10. Parity checks
    for t in [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]:
        assert engine_tiers.get(t, 0) == meta_tiers.get(t, 0), f"Engine vs Meta mismatch for {t}"
        assert engine_tiers.get(t, 0) == dir_counts.get(t, 0), f"Engine vs Dir mismatch for {t}"
        assert engine_tier_ids[t] == dir_tier_ids[t], f"Engine vs Dir ID set mismatch for {t}"
    print("\nPARITY CHECK: ENGINE == METADATA == DIRECTORY EXACT SET EQUALITY CONFIRMED across all 5 tiers!")

    # 11. Specific company checks
    p_opp = evaluate_broker_opportunity(105, conn=conn)
    w_opp = evaluate_broker_opportunity(91, conn=conn)
    m_opp = evaluate_broker_opportunity(218, conn=conn)
    a_opp = evaluate_broker_opportunity(24, conn=conn)
    f_opp = evaluate_broker_opportunity(102, conn=conn)
    t_opp = evaluate_broker_opportunity(104, conn=conn)

    print(f"\nSpecific Checks:")
    print(f"Precision Strip (CID 105): tier={p_opp['opportunity_tier']}, facts={p_opp['positive_facts']}")
    print(f"Worthington Steel (CID 91): tier={w_opp['opportunity_tier']}, facts={w_opp['positive_facts']}")
    print(f"Metals USA (CID 218): tier={m_opp['opportunity_tier']}, facts={m_opp['positive_facts']}")
    print(f"AmeriSteel (CID 24): tier={a_opp['opportunity_tier']}")
    print(f"FerrouSouth (CID 102): tier={f_opp['opportunity_tier']}")
    print(f"Target Steel (CID 104): tier={t_opp['opportunity_tier']}")

    assert p_opp["opportunity_tier"] == TIER_A_PRIORITY
    assert w_opp["opportunity_tier"] == TIER_B_WORTH_CALLING
    assert m_opp["opportunity_tier"] == TIER_B_WORTH_CALLING
    assert a_opp["opportunity_tier"] == TIER_C_SECONDARY
    assert f_opp["opportunity_tier"] == TIER_C_SECONDARY
    assert t_opp["opportunity_tier"] == TIER_C_SECONDARY

    # Check contact 671
    ct671 = conn.execute("SELECT * FROM contacts WHERE id = 671").fetchone()
    print(f"Contact 671: title={ct671['exact_published_title']}, broker_proc={ct671['broker_procurement_relevance']}")
    assert ct671["exact_published_title"] == "Main Contact"
    assert ct671["broker_procurement_relevance"] == "UNKNOWN"

    conn.close()

if __name__ == "__main__":
    main()
