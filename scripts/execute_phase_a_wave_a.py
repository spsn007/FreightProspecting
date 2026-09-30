"""
FreightProspecting V1 — Phase A Wave A Execution
Performs:
1. Verifies baseline hash
2. Takes pre-mutation backup: data/backups/prospects_backup_pre_tier_a_phase_a_wave_A_<timestamp>.db
3. Atomically applies accepted changes (CID 105 -> Tier A, CID 24 -> Tier C)
4. Verifies PRAGMA integrity, FKs, lifecycle diff = 0, operational tables = 0
5. Verifies engine == metadata == directory parity across all 565 companies
6. Updates promotion ledger (reports/tier_a_promotion_ledger.json & .csv)
7. Generates checkpoint: reports/tier_a_phase_a_wave_A_checkpoint.json
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

EXPECTED_PRE_HASH = "95D7FE5C53676AD286CF460F0B9A76D676A4678683D04193634804F4D42FB321"

def main():
    now_utc = datetime.now(timezone.utc)
    ts_str = now_utc.strftime("%Y%m%d_%H%M%S")
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Verify pre-mutation hash
    current_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    assert current_hash == EXPECTED_PRE_HASH, f"Hash mismatch: {current_hash} != {EXPECTED_PRE_HASH}"
    print(f"[WAVE A] Baseline DB SHA-256 verified: {current_hash}")

    # 2. Create pre-mutation backup
    backup_path = BACKUP_DIR / f"prospects_backup_pre_tier_a_phase_a_wave_A_{ts_str}.db"
    shutil.copy2(DB_PATH, backup_path)
    print(f"[WAVE A] Pre-mutation backup created: {backup_path}")

    # Load change plan
    with open("reports/tier_a_phase_a_wave_A_change_plan.json", "r", encoding="utf-8") as f:
        change_plan = json.load(f)

    # 3. Apply atomic mutation
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    try:
        # A. Apply CID 105 (Precision Strip, Facility 134)
        src_id_105 = record_evidence_source(
            conn=conn,
            source_type="COMPANY_WEBSITE",
            source_title_publisher="Precision Strip - Transportation Services",
            observed_at=now_iso,
            source_url="https://www.precision-strip.com/capabilities/transportation-services/",
            is_primary_source=True,
            notes="Official capabilities page documents approved common carrier shipping arranged by Traffic Coordinator and 3PL logistic services."
        )

        # Claim: commercial_carrier_use = VERIFIED
        c_carrier_105 = record_claim(
            conn=conn,
            claim_field="commercial_carrier_use",
            claimed_value="VERIFIED",
            verification_status="VERIFIED",
            is_current_accepted=True,
            claim_notes="Shipment of material by approved common carrier arranged by Traffic Coordinator.",
            facility_id=134
        )
        link_claim_evidence(conn=conn, claim_id=c_carrier_105, evidence_source_id=src_id_105, relationship="SUPPORTS")
        cur.execute("UPDATE facilities SET commercial_carrier_use = 'VERIFIED' WHERE id = 134;")

        # Claim: broker_friendly_status = VERIFIED_ACCEPTS
        c_broker_105 = record_claim(
            conn=conn,
            claim_field="broker_friendly_status",
            claimed_value="VERIFIED_ACCEPTS",
            verification_status="VERIFIED",
            is_current_accepted=True,
            claim_notes="Provision and utilization of 3PL logistics services and approved common carriers.",
            facility_id=134
        )
        link_claim_evidence(conn=conn, claim_id=c_broker_105, evidence_source_id=src_id_105, relationship="SUPPORTS")
        cur.execute("UPDATE facilities SET broker_friendly_status = 'VERIFIED_ACCEPTS' WHERE id = 134;")

        # Add Logistics Contact: Jamey Eilerman
        cur.execute("""
            INSERT INTO contacts (
                facility_id, contact_identity, person_name, department, exact_published_title,
                phone_number, phone_extension, phone_directness, email_address, email_directness,
                role_category, outbound_shipping_procurement_relevance, broker_procurement_relevance,
                is_primary_contact
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            134, "NAMED_PERSON", "Jamey Eilerman", "Transportation & Logistics", "Main Contact - Transportation Services",
            "419-628-2343", None, "GENERAL_SWITCHBOARD", "jamey_eilerman@precision-strip.com", "DIRECT_PERSON",
            "FREIGHT_LOGISTICS", "VERIFIED", "VERIFIED", 1
        ))
        contact_id_105 = cur.lastrowid

        c_ct_phone = record_claim(
            conn=conn,
            claim_field="phone_number",
            claimed_value="419-628-2343",
            verification_status="VERIFIED",
            is_current_accepted=True,
            claim_notes="Minster headquarters general phone for Transportation Services.",
            contact_id=contact_id_105
        )
        link_claim_evidence(conn=conn, claim_id=c_ct_phone, evidence_source_id=src_id_105, relationship="SUPPORTS")

        c_ct_email = record_claim(
            conn=conn,
            claim_field="email_address",
            claimed_value="jamey_eilerman@precision-strip.com",
            verification_status="VERIFIED",
            is_current_accepted=True,
            claim_notes="Direct personal corporate email for Transportation Services Main Contact.",
            contact_id=contact_id_105
        )
        link_claim_evidence(conn=conn, claim_id=c_ct_email, evidence_source_id=src_id_105, relationship="SUPPORTS")

        # B. Apply CID 24 (AmeriSteel, Facility 23)
        src_id_24 = record_evidence_source(
            conn=conn,
            source_type="COMPANY_WEBSITE",
            source_title_publisher="About AmeriSteel | Family-Owned Steel Service Center",
            observed_at=now_iso,
            source_url="https://www.ameristeel.com/about",
            is_primary_source=True,
            notes="Official corporate site confirms in-house owned 2022 Kenworth delivery truck with 40,000lb capacity."
        )

        c_fleet_24 = record_claim(
            conn=conn,
            claim_field="private_fleet_present",
            claimed_value="VERIFIED_PRESENT",
            verification_status="VERIFIED",
            is_current_accepted=True,
            claim_notes="Company operates owned 2022 Kenworth delivery truck with 40,000lb capacity.",
            facility_id=23
        )
        link_claim_evidence(conn=conn, claim_id=c_fleet_24, evidence_source_id=src_id_24, relationship="SUPPORTS")
        cur.execute("UPDATE facilities SET private_fleet_present = 'VERIFIED_PRESENT' WHERE id = 23;")

        c_rel_24 = record_claim(
            conn=conn,
            claim_field="fleet_relationship_type",
            claimed_value="IN_HOUSE_OWNED",
            verification_status="VERIFIED",
            is_current_accepted=True,
            claim_notes="Dedicated Kenworth delivery asset owned by company.",
            facility_id=23
        )
        link_claim_evidence(conn=conn, claim_id=c_rel_24, evidence_source_id=src_id_24, relationship="SUPPORTS")
        cur.execute("UPDATE facilities SET fleet_relationship_type = 'IN_HOUSE_OWNED' WHERE id = 23;")

        conn.commit()
        print("[WAVE A] All mutations committed successfully.")

    except Exception as e:
        conn.rollback()
        conn.close()
        shutil.copyfile(backup_path, DB_PATH)
        print(f"[FATAL] Mutation failed, restored backup! Error: {e}")
        sys.exit(1)

    # 4. Post-Wave Verification
    cur.execute("PRAGMA integrity_check;")
    integrity = cur.fetchall()
    assert integrity == [("ok",)], f"Integrity check failed: {integrity}"

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
    print(f"[WAVE A] Post-Wave A Opportunity Counts: {opp_counts}")

    assert opp_counts[TIER_A_PRIORITY] == 14, f"Expected 14 Tier A, got {opp_counts[TIER_A_PRIORITY]}"
    assert opp_counts[TIER_B_WORTH_CALLING] == 101, f"Expected 101 Tier B, got {opp_counts[TIER_B_WORTH_CALLING]}"
    assert opp_counts[TIER_C_SECONDARY] == 5, f"Expected 5 Tier C, got {opp_counts[TIER_C_SECONDARY]}"
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

    print("[WAVE A] Exact Parity Verified: Engine == Metadata == Directory across all 5 tiers.")

    post_wave_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    print(f"[WAVE A] Post-Wave A DB SHA-256: {post_wave_hash}")

    # 5. Update Promotion Ledger
    ledger_path_json = Path("reports/tier_a_promotion_ledger.json")
    ledger_path_csv = Path("reports/tier_a_promotion_ledger.csv")

    promotion_records = []
    if ledger_path_json.exists():
        with open(ledger_path_json, "r", encoding="utf-8") as f:
            promotion_records = json.load(f)

    new_promo = {
        "promotion_number": len(promotion_records) + 1,
        "promoted_at_utc": now_iso,
        "wave": "A",
        "company_id": 105,
        "operating_brand": "Precision Strip",
        "focus_facility_id": 134,
        "previous_tier": "TIER_C_SECONDARY",
        "new_tier": "TIER_A_PRIORITY",
        "primary_trigger": "commercial_carrier_use = VERIFIED",
        "secondary_trigger": "broker_friendly_status = VERIFIED_ACCEPTS",
        "primary_source_url": "https://www.precision-strip.com/capabilities/transportation-services/",
        "direct_contact_added": "Jamey Eilerman (Main Contact - Transportation Services, jamey_eilerman@precision-strip.com)",
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

    print(f"[WAVE A] Updated promotion ledger: {ledger_path_json} and {ledger_path_csv}")

    # 6. Checkpoint Artifact
    checkpoint_data = {
        "campaign": "TIER_A_ACCELERATION",
        "phase": "PHASE_A",
        "wave": "A",
        "status": "COMPLETED_SAFE",
        "timestamp_utc": now_iso,
        "hash_before": current_hash,
        "hash_after": post_wave_hash,
        "backup_path": str(backup_path),
        "companies_researched_count": 25,
        "accepted_changes_count": 5,
        "tier_movements": [
            {
                "company_id": 105,
                "operating_brand": "Precision Strip",
                "old_tier": "TIER_C_SECONDARY",
                "new_tier": "TIER_A_PRIORITY",
                "reason": "commercial_carrier_use = VERIFIED and broker_friendly_status = VERIFIED_ACCEPTS"
            },
            {
                "company_id": 24,
                "operating_brand": "AmeriSteel",
                "old_tier": "TIER_B_WORTH_CALLING",
                "new_tier": "TIER_C_SECONDARY",
                "reason": "private_fleet_present = VERIFIED_PRESENT, commercial_carrier_use = UNKNOWN"
            }
        ],
        "engine_counts": opp_counts,
        "metadata_counts": opp_counts,
        "pragma_integrity": "ok",
        "pragma_fk_check": 0,
        "lifecycle_diff": 0,
        "operational_table_counts": 0,
        "stop_condition_check": {
            "tier_a_count": opp_counts[TIER_A_PRIORITY],
            "target": 100,
            "stop_condition_1_met": False,
            "next_action": "PROCEED_TO_WAVE_B"
        }
    }

    chk_path = Path("reports/tier_a_phase_a_wave_A_checkpoint.json")
    with open(chk_path, "w", encoding="utf-8") as f:
        json.dump(checkpoint_data, f, indent=2)
    print(f"[WAVE A] Created checkpoint artifact: {chk_path}")

    conn.close()

if __name__ == "__main__":
    main()
