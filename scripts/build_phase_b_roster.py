import csv
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, ".")

from src.backend.db.opportunity import TIER_D_RESEARCH_NEEDED, get_opportunity_tier_company_ids
from src.backend.db.queries import evaluate_qualification_readiness

DB_PATH = Path("data/prospects.db")
ROSTER_JSON = Path("reports/tier_a_acceleration_phase_b_roster.json")
ROSTER_CSV = Path("reports/tier_a_acceleration_phase_b_roster.csv")

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    tier_map = get_opportunity_tier_company_ids(conn=conn)
    tier_d_cids = sorted(list(tier_map[TIER_D_RESEARCH_NEEDED]))
    assert len(tier_d_cids) == 445, f"Expected 445 Tier D companies, found {len(tier_d_cids)}"

    ranked_items = []

    for cid in tier_d_cids:
        comp = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()
        facs = conn.execute("""
            SELECT f.*, pl.stage as lifecycle_stage
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.company_id = ?
            ORDER BY f.id ASC
        """, (cid,)).fetchall()

        # Check existing A-trigger facts across all facilities of this company
        existing_triggers = []
        for f in facs:
            if f["commercial_carrier_use"] == "VERIFIED":
                existing_triggers.append(f"commercial_carrier_use=VERIFIED (FID {f['id']})")
            if f["broker_friendly_status"] == "VERIFIED_ACCEPTS":
                existing_triggers.append(f"broker_friendly_status=VERIFIED_ACCEPTS (FID {f['id']})")

        # Select focus facility: prefer one with existing trigger, or one that is ready, else first
        focus_fac = None
        for f in facs:
            if f["commercial_carrier_use"] == "VERIFIED" or f["broker_friendly_status"] == "VERIFIED_ACCEPTS":
                focus_fac = f
                break
        if not focus_fac:
            for f in facs:
                if evaluate_qualification_readiness(f["id"], conn=conn)["is_ready"]:
                    focus_fac = f
                    break
        if not focus_fac:
            focus_fac = facs[0]

        fid = focus_fac["id"]
        readiness = evaluate_qualification_readiness(fid, conn=conn)
        missing_items = [chk for chk, val in readiness["checks"].items() if not val["passed"]]

        # Assign priority class
        if existing_triggers:
            priority_class = 0
            reason = "Existing verified carrier/broker capacity claim in place; qualification gate advancement will immediately unlock Tier A."
        elif readiness["is_ready"]:
            priority_class = 1
            reason = "Qualification gate already 100% satisfied; needs facility-specific carrier/broker evidence to trigger Tier A."
        elif len(missing_items) == 1:
            priority_class = 2
            reason = f"Missing exactly 1 qualification item ({missing_items[0]}); targeted evidence resolution enables qualification."
        elif comp["website_url"] and len(missing_items) <= 3:
            priority_class = 3
            reason = "Website and usable route present; multi-fact qualification and carrier evidence required."
        else:
            priority_class = 4
            reason = "Remaining Tier D candidate; requires complete baseline investigation."

        brand = comp["operating_brand"] or comp["legal_name"]
        ranked_items.append({
            "company_id": cid,
            "operating_brand": brand,
            "legal_name": comp["legal_name"],
            "website_url": comp["website_url"],
            "candidate_focus_facility_ids": [f["id"] for f in facs],
            "focus_facility_id": fid,
            "facility_city": focus_fac["city"],
            "facility_state": focus_fac["state_prov"],
            "current_tier": "TIER_D_RESEARCH_NEEDED",
            "current_lifecycle": focus_fac["lifecycle_stage"] or "DISCOVERY",
            "priority_class": priority_class,
            "missing_qualification_items": missing_items,
            "existing_A_trigger_facts": existing_triggers if existing_triggers else ["NONE"],
            "research_reason": reason,
        })

    # Sort deterministically: priority_class ASC, company_id ASC
    ranked_items.sort(key=lambda x: (x["priority_class"], x["company_id"]))

    # Assign campaign positions (1 to 445) and waves
    def get_wave(pos):
        if pos <= 50:
            return "A"
        elif pos <= 100:
            return "B"
        elif pos <= 150:
            return "C"
        elif pos <= 200:
            return "D"
        elif pos <= 250:
            return "E"
        elif pos <= 300:
            return "F"
        elif pos <= 350:
            return "G"
        elif pos <= 400:
            return "H"
        else:
            return "I"

    for idx, item in enumerate(ranked_items, start=1):
        item["campaign_position"] = idx
        item["wave"] = get_wave(idx)

    # Save JSON
    with open(ROSTER_JSON, "w", encoding="utf-8") as f:
        json.dump(ranked_items, f, indent=2)
    print(f"Saved Phase B roster JSON: {ROSTER_JSON} ({len(ranked_items)} companies)")

    # Save CSV
    csv_fields = [
        "campaign_position", "wave", "priority_class", "company_id", "operating_brand",
        "focus_facility_id", "facility_city", "facility_state", "current_tier",
        "current_lifecycle", "existing_A_trigger_facts", "missing_qualification_items",
        "research_reason", "website_url"
    ]
    with open(ROSTER_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for r in ranked_items:
            row = dict(r)
            row["existing_A_trigger_facts"] = "; ".join(r["existing_A_trigger_facts"])
            row["missing_qualification_items"] = "; ".join(r["missing_qualification_items"])
            writer.writerow(row)
    print(f"Saved Phase B roster CSV: {ROSTER_CSV}")

    # Summary of priority classes
    p_counts = {}
    for r in ranked_items:
        p_counts[r["priority_class"]] = p_counts.get(r["priority_class"], 0) + 1
    print(f"Priority class distribution: {p_counts}")

    # Summary of wave sizes
    w_counts = {}
    for r in ranked_items:
        w_counts[r["wave"]] = w_counts.get(r["wave"], 0) + 1
    print(f"Wave distribution: {w_counts}")

    conn.close()

if __name__ == "__main__":
    main()
