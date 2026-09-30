"""
FreightProspecting V1 — Phase A Wave E Execution
Performs:
1. Verifies pre-mutation baseline hash (CD970B4B0D6D1462FA1611099D00CE421582ED39BBDA54A407975A01EAE447BB)
2. Takes pre-mutation backup: data/backups/prospects_backup_pre_tier_a_phase_a_wave_E_<timestamp>.db
3. Atomically applies accepted changes:
   - CID 218 (Metals USA, Fac 264): commercial_carrier_use = VERIFIED -> TIER A
4. Runs PRAGMA wal_checkpoint(TRUNCATE)
5. Verifies PRAGMA integrity, FKs, lifecycle diff = 0, operational tables = 0
6. Verifies engine == metadata == directory parity across all 565 companies
7. Updates promotion ledger (reports/tier_a_promotion_ledger.json & .csv)
8. Generates checkpoint: reports/tier_a_phase_a_wave_E_checkpoint.json
"""

import csv
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend.db.claims_engine import (
    record_evidence_source,
    record_claim,
    link_claim_evidence,
)
from src.backend.db.opportunity import (
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    RESTRICTED,
    get_opportunity_tier_company_ids,
)
from src.backend.db.queries import (
    get_company_grouped_prospects,
    get_universe_metadata,
)

DB_PATH = Path("data/prospects.db")
BACKUP_DIR = Path("data/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

EXPECTED_PRE_HASH = "CD970B4B0D6D1462FA1611099D00CE421582ED39BBDA54A407975A01EAE447BB"

def main():
    now_utc = datetime.now(timezone.utc)
    ts_str = now_utc.strftime("%Y%m%d_%H%M%S")
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Verify pre-mutation hash
    current_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    assert current_hash == EXPECTED_PRE_HASH, f"Hash mismatch: {current_hash} != {EXPECTED_PRE_HASH}"
    print(f"[WAVE E] Pre-mutation DB SHA-256 verified: {current_hash}")

    # 2. Create pre-mutation backup
    backup_path = BACKUP_DIR / f"prospects_backup_pre_tier_a_phase_a_wave_E_{ts_str}.db"
    shutil.copy2(DB_PATH, backup_path)
    print(f"[WAVE E] Pre-mutation backup created: {backup_path}")

    # 3. Apply atomic mutation
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    try:
        # A. Apply CID 218 (Metals USA, Facility 264)
        src_id_218 = record_evidence_source(
            conn=conn,
            source_type="COMPANY_WEBSITE",
            source_title_publisher="Metal Shipping Services | Metals USA",
            observed_at=now_iso,
            source_url="https://www.metalsusa.com/metal-shipping-services/",
            is_primary_source=True,
            notes="Official website explicitly documents partnership with freight carriers and common carriers for customer shipments."
        )

        c_carrier_218 = record_claim(
            conn=conn,
            claim_field="commercial_carrier_use",
            claimed_value="VERIFIED",
            verification_status="VERIFIED",
            is_current_accepted=True,
            claim_notes="Common carriers and freight carriers transport steel products for customer orders.",
            facility_id=264
        )
        link_claim_evidence(conn=conn, claim_id=c_carrier_218, evidence_source_id=src_id_218, relationship="SUPPORTS")
        cur.execute("UPDATE facilities SET commercial_carrier_use = 'VERIFIED' WHERE id = 264;")

        conn.commit()
        print("[WAVE E] All mutations committed successfully.")

    except Exception as e:
        conn.rollback()
        conn.close()
        shutil.copyfile(backup_path, DB_PATH)
        print(f"[FATAL] Mutation failed, restored backup! Error: {e}")
        sys.exit(1)

    # 4. Checkpoint WAL
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

    # 5. Post-Wave Verification
    cur.execute("PRAGMA integrity_check;")
    integrity = [r[0] for r in cur.fetchall()]
    assert integrity == ["ok"], f"Integrity check failed: {integrity}"

    cur.execute("PRAGMA foreign_key_check;")
    fk_check = cur.fetchall()
    assert fk_check == [], f"Foreign key check failed: {fk_check}"

    # Operational tables == 0
    for tbl in ["outreach_logs", "load_opportunities", "freight_demand_signals", "capacity_postings", "load_capacity_matches"]:
        cnt = cur.execute(f"SELECT COUNT(*) FROM {tbl};").fetchone()[0]
        assert cnt == 0, f"Table {tbl} has non-zero count: {cnt}"

    # Lifecycle diff == 0 across all 653 facilities
    bak_conn = sqlite3.connect(backup_path)
    bak_cur = bak_conn.cursor()
    curr_stages = cur.execute("SELECT facility_id, stage FROM prospect_lifecycle ORDER BY facility_id;").fetchall()
    bak_stages = bak_cur.execute("SELECT facility_id, stage FROM prospect_lifecycle ORDER BY facility_id;").fetchall()
    assert curr_stages == bak_stages, "Lifecycle stages mutated!"
    bak_conn.close()

    # Authoritative engine evaluation
    meta = get_universe_metadata(conn=conn)
    opp_counts = meta["opportunity_counts"]
    print(f"[WAVE E] Post-Wave E Opportunity Counts: {opp_counts}")

    assert opp_counts[TIER_A_PRIORITY] == 16, f"Expected 16 Tier A, got {opp_counts[TIER_A_PRIORITY]}"
    assert opp_counts[TIER_B_WORTH_CALLING] == 97, f"Expected 97 Tier B, got {opp_counts[TIER_B_WORTH_CALLING]}"
    assert opp_counts[TIER_C_SECONDARY] == 7, f"Expected 7 Tier C, got {opp_counts[TIER_C_SECONDARY]}"
    assert opp_counts[TIER_D_RESEARCH_NEEDED] == 445, f"Expected 445 Tier D, got {opp_counts[TIER_D_RESEARCH_NEEDED]}"
    assert opp_counts[RESTRICTED] == 0, f"Expected 0 Restricted, got {opp_counts[RESTRICTED]}"
    assert opp_counts["ALL"] == 565, f"Expected 565 Total, got {opp_counts['ALL']}"

    # Parity check: Engine == Metadata == Directory
    tier_map = get_opportunity_tier_company_ids(conn=conn)
    for t in [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]:
        assert len(tier_map[t]) == opp_counts[t], f"Engine != Metadata for {t}"
        dir_res = get_company_grouped_prospects(page=1, page_size=600, tier=t, conn=conn)
        dir_cids = {item["company_id"] for item in dir_res["items"]}
        engine_cids = set(tier_map[t])
        assert dir_cids == engine_cids, f"Engine != Directory set for {t}"

    print("[WAVE E] Exact Parity Verified: Engine == Metadata == Directory across all 5 tiers.")

    post_wave_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    print(f"[WAVE E] Post-Wave E DB SHA-256: {post_wave_hash}")

    # 6. Update Promotion Ledger
    ledger_path_json = Path("reports/tier_a_promotion_ledger.json")
    ledger_path_csv = Path("reports/tier_a_promotion_ledger.csv")

    promotion_records = []
    if ledger_path_json.exists():
        with open(ledger_path_json, "r", encoding="utf-8") as f:
            promotion_records = json.load(f)

    new_promo = {
        "promotion_number": len(promotion_records) + 1,
        "promoted_at_utc": now_iso,
        "wave": "E",
        "company_id": 218,
        "operating_brand": "Metals USA",
        "focus_facility_id": 264,
        "previous_tier": "TIER_B_WORTH_CALLING",
        "new_tier": "TIER_A_PRIORITY",
        "primary_trigger": "commercial_carrier_use = VERIFIED",
        "secondary_trigger": "NONE",
        "primary_source_url": "https://www.metalsusa.com/metal-shipping-services/",
        "direct_contact_added": "Existing freight & logistics route preserved",
        "db_sha256_after_wave": post_wave_hash,
    }
    promotion_records.append(new_promo)

    with open(ledger_path_json, "w", encoding="utf-8") as f:
        json.dump(promotion_records, f, indent=2)

    fieldnames = list(promotion_records[0].keys())
    with open(ledger_path_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(promotion_records)

    print(f"[WAVE E] Updated promotion ledger: {ledger_path_json} and {ledger_path_csv}")

    # 7. Checkpoint Artifact
    checkpoint_data = {
        "campaign": "TIER_A_ACCELERATION",
        "phase": "PHASE_A",
        "wave": "E",
        "status": "COMPLETED_SAFE",
        "timestamp_utc": now_iso,
        "hash_before": current_hash,
        "hash_after": post_wave_hash,
        "backup_path": str(backup_path),
        "companies_researched_count": 7,
        "accepted_changes_count": 1,
        "tier_movements": [
            {
                "company_id": 218,
                "operating_brand": "Metals USA",
                "old_tier": "TIER_B_WORTH_CALLING",
                "new_tier": "TIER_A_PRIORITY",
                "reason": "commercial_carrier_use = VERIFIED"
            }
        ],
        "engine_counts": opp_counts,
        "metadata_counts": opp_counts,
        "pragma_integrity": "ok",
        "pragma_fk_check": 0,
        "lifecycle_diff": 0,
        "operational_table_counts": 0,
        "phase_a_status": "EXHAUSTED_ALL_107_COMPANIES",
        "stop_condition_check": {
            "tier_a_count": opp_counts[TIER_A_PRIORITY],
            "target": 100,
            "stop_condition_1_met": False,
            "stop_condition_2_met": True,
            "next_action": "CONCLUDE_PHASE_A_AND_BUILD_PHASE_B_CANDIDATE_ANALYSIS"
        }
    }

    chk_path = Path("reports/tier_a_phase_a_wave_E_checkpoint.json")
    with open(chk_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint_data, f, indent=2)
    print(f"[WAVE E] Created checkpoint artifact: {chk_path}")

    conn.close()

if __name__ == "__main__":
    main()
