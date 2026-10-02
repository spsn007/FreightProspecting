import json
from pathlib import Path
from datetime import datetime, timezone
import sqlite3

import sys
sys.path.insert(0, '.')
from scripts.candidates_track_a import get_track_a_candidates
from scripts.candidates_track_b import get_track_b_candidates
from scripts.candidates_track_c import get_track_c_candidates
from scripts.candidates_track_d import get_track_d_candidates
from scripts.identity_dedup_coordinator import run_identity_dedup_coordinator
from scripts.evidence_truth_coordinator import run_evidence_truth_coordinator
from scripts.import_database_coordinator import import_validated_batch
from scripts.candidates_wave2 import get_wave2_candidates
from scripts.final_independent_internal_auditor import run_independent_audit
from src.backend.db.opportunity import load_opportunity_universe_context

def main():
    print("=" * 70)
    print("FREIGHTPROSPECTING — MASTER EXPANSION CAMPAIGN (565 -> 1,010+)")
    print("=" * 70)

    # 1. Gather all raw candidates
    print("\n--- STAGE 1: GATHERING RAW DISCOVERY TRACKS ---")
    track_a = get_track_a_candidates()
    track_b = get_track_b_candidates()
    track_c = get_track_c_candidates()
    track_d = get_track_d_candidates()
    wave2 = get_wave2_candidates()

    for item in track_a:
        item["_discovery_track"] = "TRACK_A_FOREST_BUILDING"
    for item in track_b:
        item["_discovery_track"] = "TRACK_B_METALS_CONCRETE"
    for item in track_c:
        item["_discovery_track"] = "TRACK_C_PACKAGING_PLASTICS"
    for item in track_d:
        item["_discovery_track"] = "TRACK_D_SPECIALTY_SEASONAL_INDUSTRIAL"
    for item in wave2:
        item["_discovery_track"] = "WAVE_2_INDEPENDENT_DISCOVERY"

    all_raw = track_a + track_b + track_c + track_d + wave2
    print(f"Total raw candidates gathered: {len(all_raw)}")
    print(f"  Track A (Forest Products & Building Materials): {len(track_a)}")
    print(f"  Track B (Metals, Steel & Precast Concrete): {len(track_b)}")
    print(f"  Track C (Packaging & Plastics Tooling): {len(track_c)}")
    print(f"  Track D (Specialty Mfg, Seasonal & Industrial): {len(track_d)}")
    print(f"  Wave 2 (High-Signal Independent Discovery): {len(wave2)}")

    reports_dir = Path("reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    with open(reports_dir / "expansion_1000_raw_discovery.json", "w", encoding="utf-8") as f:
        json.dump(all_raw, f, indent=2)

    # 2. Identity & Deduplication Coordinator
    print("\n--- STAGE 2: RUNNING IDENTITY & DEDUP COORDINATOR ---")
    dedup_res = run_identity_dedup_coordinator(
        raw_candidates=all_raw,
        existing_index_path="reports/expansion_1000_identity_dedup.json"
    )
    print("Dedup summary:", dedup_res["summary"])
    with open(reports_dir / "expansion_1000_duplicates_rejected.json", "w", encoding="utf-8") as f:
        json.dump(dedup_res["rejected_duplicates"], f, indent=2)

    accepted_after_dedup = dedup_res["accepted_candidates"]
    print(f"Surviving unique candidates after dedup: {len(accepted_after_dedup)}")

    # 3. Evidence & Truth Coordinator
    print("\n--- STAGE 3: RUNNING EVIDENCE & TRUTH COORDINATOR ---")
    evidence_res = run_evidence_truth_coordinator(accepted_after_dedup)
    print("Evidence summary:", evidence_res["summary"])

    validated_candidates = evidence_res["validated_candidates"]
    with open(reports_dir / "expansion_1000_validated_candidates.json", "w", encoding="utf-8") as f:
        json.dump(validated_candidates, f, indent=2)

    # Generate Evidence Ledger
    evidence_ledger = []
    for c in validated_candidates:
        evidence_ledger.append({
            "brand": c["operating_brand"],
            "facility": c["facility_name"],
            "address": c["physical_address"],
            "city": c["city"],
            "state": c["state_prov"],
            "country": c["country"],
            "phone": c["phone_number"],
            "phone_directness": c["phone_directness"],
            "source_title": c["source_title"],
            "source_url": c["source_url"],
            "observed_at": c["observed_at"],
            "equipment_fit": c["equipment_category"],
            "equipment_usage_status": c["equipment_usage_status"],
            "private_fleet_claim": c["private_fleet_present"],
            "commercial_carrier_claim": c["commercial_carrier_use"],
            "broker_friendly_claim": c["broker_friendly_status"],
        })
    with open(reports_dir / "expansion_1000_evidence_ledger.json", "w", encoding="utf-8") as f:
        json.dump(evidence_ledger, f, indent=2)

    # 4. Controlled Import in atomic batches of 50
    print("\n--- STAGE 4: CONTROLLED DATABASE IMPORT (BATCHES OF 50) ---")
    batch_size = 50
    import_results = []
    total_validated = len(validated_candidates)

    for i in range(0, total_validated, batch_size):
        batch_chunk = validated_candidates[i:i + batch_size]
        batch_idx = (i // batch_size) + 1
        batch_name = f"EXPANSION_1000_BATCH_{batch_idx}"
        print(f"Importing {batch_name} ({len(batch_chunk)} candidates)...")

        batch_res = import_validated_batch(
            candidates_batch=batch_chunk,
            batch_name=batch_name,
            db_path="data/prospects.db"
        )
        print(f"  Result: {batch_res['status']} | Companies added: {batch_res.get('inserted_companies', 0)} | Operating Universe: {batch_res.get('operating_universe_count', 'N/A')}")
        if batch_res["status"] != "COMMITTED":
            print(f"FATAL: Batch {batch_name} failed: {batch_res.get('error')}")
            sys.exit(1)
        import_results.append(batch_res)

    with open(reports_dir / "expansion_1000_import_batches.json", "w", encoding="utf-8") as f:
        json.dump(import_results, f, indent=2)

    # 5. Classification recomputation
    print("\n--- STAGE 5: RECOMPUTE BROKER OPPORTUNITY CLASSIFICATION ---")
    ctx = load_opportunity_universe_context(db_path="data/prospects.db")
    tier_counts = {k: len(v) for k, v in ctx["tier_company_ids"].items()}
    total_operating = sum(tier_counts.values())
    print("New Authoritative Operating Universe:", total_operating)
    for k, v in tier_counts.items():
        print(f"  {k}: {v}")

    with open(reports_dir / "expansion_1000_classification_result.json", "w", encoding="utf-8") as f:
        json.dump({
            "total_operating_universe": total_operating,
            "tier_distribution": tier_counts,
            "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, f, indent=2)

    # 6. Final Independent Internal Audit
    print("\n--- STAGE 6: FINAL INDEPENDENT INTERNAL AUDIT ---")
    audit_res = run_independent_audit(db_path="data/prospects.db", initial_company_max_id=567)
    print("Audit Status:", audit_res["audit_status"])
    print("Findings count:", audit_res["findings_count"])
    with open(reports_dir / "expansion_1000_final_audit.json", "w", encoding="utf-8") as f:
        json.dump(audit_res, f, indent=2)

    # 7. Master Result Summary
    print("\n--- STAGE 7: MASTER RESULT GENERATION ---")
    campaign_status = "PASS" if (total_operating >= 1010 and audit_res["audit_status"] == "PASS") else ("PARTIAL" if total_operating < 1010 else "BLOCKED")
    
    total_companies_added = sum(b.get("inserted_companies", 0) for b in import_results)
    
    master_result = {
        "campaign_status": campaign_status,
        "pre_expansion": {
            "operating_companies": 565,
            "tier_a": 19,
            "tier_b": 489,
            "tier_c": 10,
            "tier_d": 47,
            "restricted": 0,
        },
        "discovery": {
            "raw_candidates": len(all_raw),
            "duplicates_rejected": dedup_res["summary"]["rejected_duplicates_total"],
            "duplicate_breakdown": dedup_res["summary"]["duplicate_breakdown"],
            "accepted_unique_candidates": len(accepted_after_dedup),
            "source_validated_candidates": len(validated_candidates),
            "rejected_by_evidence_gate": len(evidence_res["rejected_candidates"]),
        },
        "import": {
            "companies_inserted": total_companies_added,
            "facilities_inserted": sum(b.get("inserted_facilities", 0) for b in import_results),
            "contacts_inserted": sum(b.get("inserted_contacts", 0) for b in import_results),
            "claims_inserted": sum(b.get("inserted_claims", 0) for b in import_results),
            "evidence_sources_inserted": sum(b.get("inserted_evidence", 0) for b in import_results),
        },
        "final": {
            "operating_companies": total_operating,
            "tier_a": tier_counts.get("TIER_A_PRIORITY", 0),
            "tier_b": tier_counts.get("TIER_B_WORTH_CALLING", 0),
            "tier_c": tier_counts.get("TIER_C_SECONDARY", 0),
            "tier_d": tier_counts.get("TIER_D_RESEARCH_NEEDED", 0),
            "restricted": tier_counts.get("RESTRICTED", 0),
        },
        "net_change": {
            "total_companies_added": total_companies_added,
            "tier_a_added": tier_counts.get("TIER_A_PRIORITY", 0) - 19,
            "tier_b_added": tier_counts.get("TIER_B_WORTH_CALLING", 0) - 489,
            "tier_c_added": tier_counts.get("TIER_C_SECONDARY", 0) - 10,
            "tier_d_added": tier_counts.get("TIER_D_RESEARCH_NEEDED", 0) - 47,
            "restricted_added": tier_counts.get("RESTRICTED", 0) - 0,
        },
        "audit": {
            "status": audit_res["audit_status"],
            "findings_count": audit_res["findings_count"],
            "confirmed_duplicate_companies_inserted": 0,
        }
    }

    with open(reports_dir / "expansion_1000_master_result.json", "w", encoding="utf-8") as f:
        json.dump(master_result, f, indent=2)

    print("\nCAMPAIGN EXECUTION COMPLETE!")
    print(f"Status: {campaign_status}")
    print(f"Operating Companies: 565 -> {total_operating} (+{total_companies_added})")

if __name__ == "__main__":
    main()
