"""
Generate Broker Opportunity Research Queue Artifact.
Audits all 565 operating companies, categorizes into Tiers A-D + Restricted,
identifies strong opportunity signals in Discovery (like Cascade Engineering),
and outputs reports/broker_opportunity_research_queue.json.
"""

import json
import sqlite3
from pathlib import Path
from src.backend.db.connection import get_db_path
from src.backend.db.opportunity import evaluate_broker_opportunity
from src.backend.db.queries import get_company_grouped_prospects, get_universe_metadata


def main():
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)

    db_path = get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Fetch all 565 operating companies grouped
    res = get_company_grouped_prospects(db_path=db_path, conn=conn)
    all_groups = res if isinstance(res, list) else res.get("items", [])

    tier_a = [g for g in all_groups if g["opportunity_tier"] == "TIER_A_PRIORITY"]
    tier_b = [g for g in all_groups if g["opportunity_tier"] == "TIER_B_WORTH_CALLING"]
    tier_c = [g for g in all_groups if g["opportunity_tier"] == "TIER_C_SECONDARY"]
    tier_d = [g for g in all_groups if g["opportunity_tier"] == "TIER_D_RESEARCH_NEEDED"]
    restricted = [g for g in all_groups if g["opportunity_tier"] == "RESTRICTED"]

    # Identify strong opportunity signals in Discovery pool (Tier D)
    tier_d_strong_signals = [g for g in tier_d if g.get("has_strong_opportunity_signal")]

    # Categorize Tier D by primary research blocker
    missing_phone = [g for g in tier_d if not g.get("best_phone")]
    missing_equip = [g for g in tier_d if not g.get("equipment_categories")]
    remediation_blocked = [g for g in tier_d if g.get("operating_brand") == "Cascade Engineering"]

    queue_data = {
        "metadata": {
            "total_operating_companies": len(all_groups),
            "tier_counts": {
                "TIER_A_PRIORITY": len(tier_a),
                "TIER_B_WORTH_CALLING": len(tier_b),
                "TIER_C_SECONDARY": len(tier_c),
                "TIER_D_RESEARCH_NEEDED": len(tier_d),
                "RESTRICTED": len(restricted),
            },
            "tier_d_strong_opportunity_signals_count": len(tier_d_strong_signals),
        },
        "tier_a_priority_prospects": [
            {
                "company_id": g["company_id"],
                "operating_brand": g["operating_brand"],
                "lifecycle_stage": g["lifecycle_stage"],
                "best_location": g["best_location"],
                "best_phone": g["best_phone"],
                "best_phone_label": g["best_phone_label"],
                "equipment_categories": g["equipment_categories"],
                "private_fleet_present": g["private_fleet_present"],
                "commercial_carrier_use": g["commercial_carrier_use"],
                "broker_friendly_status": g["broker_friendly_status"],
                "broker_why_bullets": g["broker_why_bullets"],
            }
            for g in tier_a
        ],
        "tier_c_secondary_prospects": [
            {
                "company_id": g["company_id"],
                "operating_brand": g["operating_brand"],
                "lifecycle_stage": g["lifecycle_stage"],
                "best_location": g["best_location"],
                "best_phone": g["best_phone"],
                "best_phone_label": g["best_phone_label"],
                "equipment_categories": g["equipment_categories"],
                "private_fleet_present": g["private_fleet_present"],
                "commercial_carrier_use": g["commercial_carrier_use"],
                "counter_factor": "Private fleet verified, outside carrier usage not confirmed yet",
                "broker_why_bullets": g["broker_why_bullets"],
            }
            for g in tier_c
        ],
        "tier_d_strong_opportunity_signals": [
            {
                "company_id": g["company_id"],
                "operating_brand": g["operating_brand"],
                "lifecycle_stage": g["lifecycle_stage"],
                "commercial_carrier_use": g["commercial_carrier_use"],
                "best_location": g["best_location"],
                "best_phone": g["best_phone"],
                "reason": "Commercial carrier use verified, but blocked in Discovery pool pending Stage 1 remediation/qualification review",
            }
            for g in tier_d_strong_signals
        ],
        "tier_d_research_queue_summary": {
            "total_discovery": len(tier_d),
            "missing_callable_phone": len(missing_phone),
            "missing_equipment_fit": len(missing_equip),
            "strong_opportunity_candidates": [g["operating_brand"] for g in tier_d_strong_signals],
        }
    }

    out_file = reports_dir / "broker_opportunity_research_queue.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(queue_data, f, indent=2)

    print(f"Research queue generated: {out_file} ({out_file.stat().st_size} bytes)")
    print(f"Tier A (Priority): {len(tier_a)}")
    print(f"Tier B (Worth Calling): {len(tier_b)}")
    print(f"Tier C (Secondary): {len(tier_c)}")
    print(f"Tier D (Research Needed): {len(tier_d)}")
    print(f"Tier D Strong Signals: {len(tier_d_strong_signals)} ({[g['operating_brand'] for g in tier_d_strong_signals]})")


if __name__ == "__main__":
    main()
