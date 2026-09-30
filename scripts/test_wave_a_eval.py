import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
import sqlite3
from src.backend.db.opportunity import (
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    RESTRICTED,
    load_opportunity_universe_context,
)
from src.backend.db.queries import (
    evaluate_qualification_readiness,
    get_universe_metadata,
    get_company_grouped_prospects,
)

DB_PATH = Path("data/prospects.db")

def simulate():
    conn = sqlite3.connect(":memory:")
    src_conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    src_conn.backup(conn)
    src_conn.close()
    conn.row_factory = sqlite3.Row

    with open("reports/tier_a_acceleration_phase_b_roster.json", "r", encoding="utf-8") as f:
        roster = json.load(f)
    wave_a = [r for r in roster if r["wave"] == "A"]

    print(f"Simulating Wave A on {len(wave_a)} companies...")

    cur = conn.cursor()

    # CID 128: Add commercial_carrier_use claim for Bush Concrete Products (FID 157)
    # First create evidence source
    cur.execute("""
        INSERT INTO evidence_sources (
            source_type, source_title_publisher, observed_at, source_url, is_primary_source, notes
        ) VALUES (
            'COMPANY_WEBSITE', 'Bush Concrete Products - Delivery & Trucking', '2026-09-29T07:48:00Z',
            'https://bushconcreteproducts.com/delivery-trucking/', 1,
            'Official delivery capabilities page explicitly documents shipments via common carrier.'
        )
    """)
    src128 = cur.lastrowid

    cur.execute("""
        INSERT INTO claims (
            facility_id, claim_field, claimed_value, verification_status,
            is_current_accepted, claim_notes
        ) VALUES (
            157, 'commercial_carrier_use', 'VERIFIED', 'VERIFIED', 1,
            'Official delivery capabilities page explicitly documents shipments via common carrier.'
        )
    """)
    c128 = cur.lastrowid
    cur.execute("INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship) VALUES (?, ?, 'SUPPORTS')", (c128, src128))
    cur.execute("UPDATE facilities SET commercial_carrier_use = 'VERIFIED' WHERE id = 157")

    # Now evaluate readiness for all 50 companies in Wave A
    qualified_cids = []
    remained_discovery_cids = []

    for r in wave_a:
        fid = r["focus_facility_id"]
        cid = r["company_id"]
        res = evaluate_qualification_readiness(fid, conn=conn)
        if res["is_ready"]:
            qualified_cids.append(cid)
            cur.execute("UPDATE prospect_lifecycle SET stage = 'QUALIFIED' WHERE facility_id = ?", (fid,))
        else:
            remained_discovery_cids.append(cid)

    print(f"Qualified: {len(qualified_cids)}/50")
    print(f"Remained Discovery: {len(remained_discovery_cids)}: {remained_discovery_cids}")

    # Evaluate distributions
    ctx = load_opportunity_universe_context(conn)
    eng_counts = {k: len(v) for k, v in ctx["tier_company_ids"].items()}

    meta = get_universe_metadata(conn)
    meta_counts = {
        TIER_A_PRIORITY: meta["opportunity_counts"][TIER_A_PRIORITY],
        TIER_B_WORTH_CALLING: meta["opportunity_counts"][TIER_B_WORTH_CALLING],
        TIER_C_SECONDARY: meta["opportunity_counts"][TIER_C_SECONDARY],
        TIER_D_RESEARCH_NEEDED: meta["opportunity_counts"][TIER_D_RESEARCH_NEEDED],
        RESTRICTED: meta["opportunity_counts"][RESTRICTED],
    }

    directory = get_company_grouped_prospects(lifecycle_stage="ALL", conn=conn, tier="ALL")
    dir_tiers = {
        TIER_A_PRIORITY: set(),
        TIER_B_WORTH_CALLING: set(),
        TIER_C_SECONDARY: set(),
        TIER_D_RESEARCH_NEEDED: set(),
        RESTRICTED: set(),
    }
    for card in directory:
        dir_tiers[card["opportunity_tier"]].add(card["company_id"])
    dir_counts = {k: len(v) for k, v in dir_tiers.items()}

    print("\n--- SIMULATION RESULTS ---")
    print("Engine:   ", eng_counts)
    print("Metadata: ", meta_counts)
    print("Directory:", dir_counts)
    parity_ok = (eng_counts == meta_counts == dir_counts)
    print("Engine == Meta == Dir:", parity_ok)

    # Check ID sets
    for t in [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]:
        assert set(ctx["tier_company_ids"][t]) == dir_tiers[t], f"Mismatch in tier {t}"
    print("Tier set equality: 100% MATCH across all 5 tiers!")

    print("\nTier A companies in simulation (total", len(ctx["tier_company_ids"][TIER_A_PRIORITY]), "):")
    for cid in ctx["tier_company_ids"][TIER_A_PRIORITY]:
        row = conn.execute("SELECT id, operating_brand FROM companies WHERE id = ?", (cid,)).fetchone()
        print(f"  CID {cid:3d}: {row['operating_brand']}")

if __name__ == "__main__":
    simulate()
