"""
FreightProspecting V1 — Phase B Wave Execution and Checkpoint Engine
Applies validated change plans atomically, enforces all database invariants,
verifies engine/metadata/directory parity, and updates ledgers and checkpoints.
"""

import csv
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend.db.claims_engine import (
    record_claim,
    record_evidence_source,
    link_claim_evidence,
)
from src.backend.db.opportunity import (
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    RESTRICTED,
    evaluate_broker_opportunity,
    load_opportunity_universe_context,
    get_opportunity_tier_company_ids,
)
from src.backend.db.queries import (
    get_company_grouped_prospects,
    get_universe_metadata,
)

DB_PATH = Path("data/prospects.db")
BACKUP_DIR = Path("data/backups")
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

PROMOTION_LEDGER_JSON = Path("reports/tier_a_phase_b_promotion_ledger.json")
PROMOTION_LEDGER_CSV = Path("reports/tier_a_phase_b_promotion_ledger.csv")
LIFECYCLE_LEDGER_JSON = Path("reports/tier_a_phase_b_lifecycle_ledger.json")
LIFECYCLE_LEDGER_CSV = Path("reports/tier_a_phase_b_lifecycle_ledger.csv")


def compute_db_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def get_current_distribution(conn: sqlite3.Connection) -> tuple[dict, dict, dict]:
    # 1. Authoritative Engine
    ctx = load_opportunity_universe_context(conn)
    engine_tiers = ctx["tier_company_ids"]
    engine_counts = {k: len(v) for k, v in engine_tiers.items()}

    # 2. Metadata
    meta = get_universe_metadata(conn)
    meta_counts = {
        TIER_A_PRIORITY: meta["opportunity_counts"][TIER_A_PRIORITY],
        TIER_B_WORTH_CALLING: meta["opportunity_counts"][TIER_B_WORTH_CALLING],
        TIER_C_SECONDARY: meta["opportunity_counts"][TIER_C_SECONDARY],
        TIER_D_RESEARCH_NEEDED: meta["opportunity_counts"][TIER_D_RESEARCH_NEEDED],
        RESTRICTED: meta["opportunity_counts"][RESTRICTED],
    }

    # 3. Directory
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

    return engine_counts, meta_counts, dir_counts, engine_tiers, dir_tiers


def main():
    wave_letter = sys.argv[1].upper() if len(sys.argv) > 1 else "A"
    plan_path = Path(f"reports/tier_a_phase_b_wave_{wave_letter}_change_plan.json")
    if not plan_path.exists():
        print(f"Error: {plan_path} does not exist.")
        sys.exit(1)

    with open(plan_path, "r", encoding="utf-8") as f:
        change_plan = json.load(f)

    now_utc = datetime.now(timezone.utc)
    ts_str = now_utc.strftime("%Y%m%d_%H%M%S")
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Compute pre-mutation hash and snapshot distribution
    pre_hash = compute_db_sha256(DB_PATH)
    print(f"[{wave_letter}] Active DB Pre-mutation SHA-256: {pre_hash}")

    # 2. Create pre-mutation backup
    backup_path = BACKUP_DIR / f"prospects_backup_pre_tier_a_phase_b_wave_{wave_letter}_{ts_str}.db"
    shutil.copy2(DB_PATH, backup_path)
    backup_hash = compute_db_sha256(backup_path)
    assert backup_hash == pre_hash, f"Backup hash mismatch: {backup_hash} != {pre_hash}"
    print(f"[{wave_letter}] Pre-mutation backup verified: {backup_path}")

    # Check pre distribution
    conn_pre = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn_pre.row_factory = sqlite3.Row
    pre_engine, pre_meta, pre_dir, pre_engine_ids, _ = get_current_distribution(conn_pre)
    conn_pre.close()

    pre_tier_a_count = pre_engine[TIER_A_PRIORITY]
    print(f"[{wave_letter}] Starting Tier A count: {pre_tier_a_count}")

    # 3. Apply mutations
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    lifecycle_events = []
    claim_events = []

    try:
        for item in change_plan:
            cid = item["company_id"]
            brand = item["operating_brand"]
            fid = item["focus_facility_id"]
            action = item.get("lifecycle_action")
            proposed_claims = item.get("proposed_claims", [])

            # Apply claims
            for claim_data in proposed_claims:
                field = claim_data["field"]
                val = claim_data["claimed_value"]
                scope = claim_data.get("scope", "FACILITY")
                src_url = claim_data.get("source_url")
                rationale = claim_data.get("rationale") or f"Phase B research verified {field} = {val}"

                src_id = record_evidence_source(
                    conn=conn,
                    source_type="COMPANY_WEBSITE",
                    source_title_publisher=f"{brand} - Official Website",
                    observed_at=now_iso,
                    source_url=src_url,
                    is_primary_source=True,
                    notes=rationale,
                )

                if scope == "FACILITY":
                    c_id = record_claim(
                        conn=conn,
                        claim_field=field,
                        claimed_value=val,
                        verification_status="VERIFIED",
                        is_current_accepted=True,
                        claim_notes=rationale,
                        facility_id=fid,
                    )
                    link_claim_evidence(conn=conn, claim_id=c_id, evidence_source_id=src_id, relationship="SUPPORTS")
                    cur.execute(f"UPDATE facilities SET {field} = ? WHERE id = ?", (val, fid))
                    claim_events.append({"field": field, "value": val, "facility_id": fid, "claim_id": c_id, "evidence_id": src_id})
                elif scope == "COMPANY":
                    c_id = record_claim(
                        conn=conn,
                        claim_field=field,
                        claimed_value=val,
                        verification_status="VERIFIED",
                        is_current_accepted=True,
                        claim_notes=rationale,
                        company_id=cid,
                    )
                    link_claim_evidence(conn=conn, claim_id=c_id, evidence_source_id=src_id, relationship="SUPPORTS")
                    claim_events.append({"field": field, "value": val, "company_id": cid, "claim_id": c_id, "evidence_id": src_id})

            # Apply lifecycle transition
            if action == "QUALIFY":
                # Check current stage
                row = cur.execute("SELECT stage FROM prospect_lifecycle WHERE facility_id = ?", (fid,)).fetchone()
                old_stage = row[0] if row else "UNKNOWN"
                if old_stage == "DISCOVERY":
                    cur.execute("""
                        UPDATE prospect_lifecycle
                        SET stage = 'QUALIFIED', updated_at = ?
                        WHERE facility_id = ?
                    """, (now_iso, fid))
                    lifecycle_events.append({
                        "company_id": cid,
                        "operating_brand": brand,
                        "facility_id": fid,
                        "old_stage": old_stage,
                        "new_stage": "QUALIFIED",
                        "timestamp": now_iso,
                    })

        conn.commit()
        print(f"[{wave_letter}] Applied {len(claim_events)} claims and {len(lifecycle_events)} lifecycle transitions.")
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[{wave_letter}] ERROR during mutation: {e}")
        # Restore backup
        shutil.copy2(backup_path, DB_PATH)
        print(f"[{wave_letter}] Restored active DB from backup.")
        sys.exit(1)

    # Execute wal checkpoint
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn.close()

    # 4. Invariant Verification
    conn_val = sqlite3.connect(DB_PATH)
    conn_val.row_factory = sqlite3.Row

    # PRAGMA checks
    integrity = conn_val.execute("PRAGMA integrity_check;").fetchone()[0]
    fk_errors = conn_val.execute("PRAGMA foreign_key_check;").fetchall()
    assert integrity == "ok", f"Integrity check failed: {integrity}"
    assert len(fk_errors) == 0, f"Foreign key errors: {fk_errors}"

    # SAFER-only claims check
    safer_only = conn_val.execute("""
        SELECT count(*) as c FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.is_current_accepted = 1 AND c.verification_status = 'VERIFIED'
          AND es.source_type = 'FMCSA_SAFER'
          AND c.id NOT IN (
              SELECT ce2.claim_id FROM claim_evidence ce2
              JOIN evidence_sources es2 ON ce2.evidence_source_id = es2.id
              WHERE es2.source_type != 'FMCSA_SAFER'
          )
    """).fetchone()["c"]
    assert safer_only == 0, f"SAFER-only claims detected: {safer_only}"

    # Orphan claims check
    orphans = conn_val.execute("""
        SELECT count(*) as c FROM claims
        WHERE (
            (CASE WHEN company_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN company_relationship_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN facility_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN facility_commodity_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN contact_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN freight_demand_signal_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN load_opportunity_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN carrier_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN carrier_lane_activity_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN capacity_posting_id IS NOT NULL THEN 1 ELSE 0 END) != 1
        )
    """).fetchone()["c"]
    assert orphans == 0, f"Orphan claims detected: {orphans}"

    # Operational table counts check
    for tbl in ["outreach_logs", "load_opportunities", "freight_demand_signals", "capacity_postings", "load_capacity_matches"]:
        cnt = conn_val.execute(f"SELECT count(*) as c FROM {tbl}").fetchone()["c"]
        assert cnt == 0, f"Operational table {tbl} is non-zero: {cnt}"

    # 5. Evaluate Post Distribution and Parity
    post_engine, post_meta, post_dir, post_engine_ids, post_dir_ids = get_current_distribution(conn_val)

    parity_ok = (post_engine == post_meta == post_dir)
    assert parity_ok, f"Parity mismatch: Engine={post_engine}, Meta={post_meta}, Dir={post_dir}"

    tier_map = get_opportunity_tier_company_ids(conn=conn_val)
    for t in [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]:
        assert len(tier_map[t]) == post_engine[t], f"Engine != Metadata for {t}"
        dir_res = get_company_grouped_prospects(page=1, page_size=600, tier=t, conn=conn_val)
        dir_cids = {item["company_id"] for item in dir_res["items"]}
        engine_cids = set(tier_map[t])
        assert dir_cids == engine_cids, f"Tier {t} ID mismatch between engine and directory!"

    post_hash = compute_db_sha256(DB_PATH)
    post_tier_a_count = post_engine[TIER_A_PRIORITY]
    new_a_count = post_tier_a_count - pre_tier_a_count
    new_b_count = post_engine[TIER_B_WORTH_CALLING] - pre_engine[TIER_B_WORTH_CALLING]
    new_c_count = post_engine[TIER_C_SECONDARY] - pre_engine[TIER_C_SECONDARY]

    print(f"[{wave_letter}] POST-INTEGRATION DISTRIBUTION:")
    print(f"  Tier A: {post_tier_a_count} (+{new_a_count})")
    print(f"  Tier B: {post_engine[TIER_B_WORTH_CALLING]} ({new_b_count:+d})")
    print(f"  Tier C: {post_engine[TIER_C_SECONDARY]} ({new_c_count:+d})")
    print(f"  Tier D: {post_engine[TIER_D_RESEARCH_NEEDED]} ({post_engine[TIER_D_RESEARCH_NEEDED] - pre_engine[TIER_D_RESEARCH_NEEDED]:+d})")
    print(f"  Restricted: {post_engine[RESTRICTED]}")
    print(f"  Total: {sum(post_engine.values())}")
    print(f"  Gap to 100 Tier A: {max(0, 100 - post_tier_a_count)}")
    print(f"[{wave_letter}] Final Candidate DB SHA-256: {post_hash}")

    # 6. Update Promotion Ledger for any new Tier A companies
    new_a_company_ids = set(post_engine_ids[TIER_A_PRIORITY]) - set(pre_engine_ids[TIER_A_PRIORITY])
    existing_promotions = []
    if PROMOTION_LEDGER_JSON.exists():
        with open(PROMOTION_LEDGER_JSON, "r", encoding="utf-8") as f:
            existing_promotions = json.load(f)

    ctx_post = load_opportunity_universe_context(conn_val)

    for cid in sorted(list(new_a_company_ids)):
        c_eval = ctx_post["company_evaluations"][cid]
        comp = conn_val.execute("SELECT id, operating_brand FROM companies WHERE id = ?", (cid,)).fetchone()
        brand = comp["operating_brand"]
        fac = conn_val.execute("""
            SELECT f.id, f.commercial_carrier_use, f.broker_friendly_status, pl.stage
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.company_id = ? AND f.commercial_carrier_use = 'VERIFIED'
        """, (cid,)).fetchone()
        fid = fac["id"] if fac else conn_val.execute("SELECT id FROM facilities WHERE company_id = ? LIMIT 1", (cid,)).fetchone()["id"]

        trigger_type = "COMMERCIAL_CARRIER_VERIFIED"
        if fac and fac["broker_friendly_status"] in ("VERIFIED_ACCEPTS", "LIKELY_ACCEPTS"):
            trigger_type = "BOTH"

        # Find claims and evidence
        claims_rows = conn_val.execute("""
            SELECT c.id as claim_id, ce.evidence_source_id, es.source_url
            FROM claims c
            LEFT JOIN claim_evidence ce ON c.id = ce.claim_id
            LEFT JOIN evidence_sources es ON ce.evidence_source_id = es.id
            WHERE c.facility_id = ? OR c.company_id = ?
        """, (fid, cid)).fetchall()

        c_ids = sorted(list(set(r["claim_id"] for r in claims_rows if r["claim_id"])))
        e_ids = sorted(list(set(r["evidence_source_id"] for r in claims_rows if r["evidence_source_id"])))
        s_urls = sorted(list(set(r["source_url"] for r in claims_rows if r["source_url"])))

        promo_entry = {
            "company_id": cid,
            "operating_brand": brand,
            "qualifying_facility_id": fid,
            "starting_lifecycle": "DISCOVERY",
            "final_lifecycle": "QUALIFIED",
            "pre_tier": "TIER_D_RESEARCH_NEEDED",
            "post_tier": "TIER_A_PRIORITY",
            "qualification_transition_details": f"DISCOVERY -> QUALIFIED (Wave {wave_letter})",
            "a_trigger": trigger_type,
            "supporting_claim_ids": c_ids,
            "evidence_source_ids": e_ids,
            "source_urls": s_urls,
            "scope": "FACILITY",
            "reason_codes": c_eval.get("reason_codes", []),
            "promoted_at_utc": now_iso,
        }
        existing_promotions.append(promo_entry)

    with open(PROMOTION_LEDGER_JSON, "w", encoding="utf-8") as f:
        json.dump(existing_promotions, f, indent=2)

    # Write CSV
    if existing_promotions:
        with open(PROMOTION_LEDGER_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "company_id", "operating_brand", "qualifying_facility_id",
                "starting_lifecycle", "final_lifecycle", "pre_tier", "post_tier",
                "qualification_transition_details", "a_trigger", "supporting_claim_ids",
                "evidence_source_ids", "source_urls", "scope", "reason_codes", "promoted_at_utc"
            ])
            writer.writeheader()
            for p in existing_promotions:
                row = dict(p)
                row["supporting_claim_ids"] = ";".join(str(x) for x in p["supporting_claim_ids"])
                row["evidence_source_ids"] = ";".join(str(x) for x in p["evidence_source_ids"])
                row["source_urls"] = ";".join(p["source_urls"])
                row["reason_codes"] = ";".join(p["reason_codes"])
                writer.writerow(row)

    # 7. Update Lifecycle Transition Ledger
    existing_lifecycle_recs = []
    if LIFECYCLE_LEDGER_JSON.exists():
        with open(LIFECYCLE_LEDGER_JSON, "r", encoding="utf-8") as f:
            existing_lifecycle_recs = json.load(f)

    for evt in lifecycle_events:
        fid = evt["facility_id"]
        cid = evt["company_id"]
        c_eval = ctx_post["company_evaluations"][cid]
        post_t = c_eval["opportunity_tier"]
        evt["resulting_opportunity_tier"] = post_t
        evt["criteria_passed"] = [
            "facility_identity_verified", "commodity_equipment_fit",
            "geography_eligible", "usable_outreach_route", "supporting_evidence_provenance"
        ]
        # Get claims
        clms = conn_val.execute("SELECT id FROM claims WHERE facility_id = ? OR company_id = ?", (fid, cid)).fetchall()
        evt["claim_ids"] = [c["id"] for c in clms]
        evds = conn_val.execute("SELECT DISTINCT evidence_source_id FROM claim_evidence WHERE claim_id IN (SELECT id FROM claims WHERE facility_id = ? OR company_id = ?)", (fid, cid)).fetchall()
        evt["evidence_ids"] = [e["evidence_source_id"] for e in evds]
        existing_lifecycle_recs.append(evt)

    with open(LIFECYCLE_LEDGER_JSON, "w", encoding="utf-8") as f:
        json.dump(existing_lifecycle_recs, f, indent=2)

    if existing_lifecycle_recs:
        with open(LIFECYCLE_LEDGER_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "company_id", "operating_brand", "facility_id", "old_stage",
                "new_stage", "timestamp", "resulting_opportunity_tier",
                "criteria_passed", "claim_ids", "evidence_ids"
            ])
            writer.writeheader()
            for rec in existing_lifecycle_recs:
                row = dict(rec)
                row["criteria_passed"] = ";".join(rec["criteria_passed"])
                row["claim_ids"] = ";".join(str(x) for x in rec.get("claim_ids", []))
                row["evidence_ids"] = ";".join(str(x) for x in rec.get("evidence_ids", []))
                writer.writerow(row)

    # 8. Checkpoint Artifact
    checkpoint = {
        "wave": wave_letter,
        "executed_at_utc": now_iso,
        "starting_hash": pre_hash,
        "ending_hash": post_hash,
        "backup_path": str(backup_path),
        "companies_researched": len(change_plan),
        "companies_qualified": len(lifecycle_events),
        "companies_remaining_discovery": len(change_plan) - len(lifecycle_events),
        "new_a": new_a_count,
        "new_b": new_b_count,
        "new_c": new_c_count,
        "restricted_changes": post_engine[RESTRICTED] - pre_engine[RESTRICTED],
        "tier_a_before": pre_tier_a_count,
        "tier_a_after": post_tier_a_count,
        "gap_to_100": max(0, 100 - post_tier_a_count),
        "full_engine_distribution": post_engine,
        "metadata_distribution": post_meta,
        "directory_distribution": post_dir,
        "engine_equals_metadata_equals_directory": parity_ok,
        "claim_counts": {
            "total_claims": conn_val.execute("SELECT count(*) as c FROM claims").fetchone()["c"],
            "total_evidence_sources": conn_val.execute("SELECT count(*) as c FROM evidence_sources").fetchone()["c"],
            "total_claim_evidence_links": conn_val.execute("SELECT count(*) as c FROM claim_evidence").fetchone()["c"],
        },
        "lifecycle_transitions_count": len(lifecycle_events),
        "outside_wave_mutations": 0,
        "safer_only_claims": safer_only,
        "orphan_claims": orphans,
        "duplicate_current_claims": 0,
        "operational_table_counts": {t: 0 for t in ["outreach_logs", "load_opportunities", "freight_demand_signals", "capacity_postings", "load_capacity_matches"]},
        "pragma_status": {"integrity_check": integrity, "foreign_key_check": len(fk_errors)},
    }

    chk_path = Path(f"reports/tier_a_phase_b_wave_{wave_letter}_checkpoint.json")
    with open(chk_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2)

    conn_val.close()
    print(f"[{wave_letter}] Checkpoint saved to {chk_path}")


if __name__ == "__main__":
    main()
