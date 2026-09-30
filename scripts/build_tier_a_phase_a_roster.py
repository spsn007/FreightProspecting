"""
FreightProspecting V1 — Tier A Acceleration Campaign Phase A Roster Builder
Extracts all current Tier B (102) and Tier C (5) operating companies (107 total),
orders them deterministically by information value priority, and freezes the roster.
Generates:
- reports/tier_a_acceleration_phase_a_roster.json
- reports/tier_a_acceleration_phase_a_roster.csv
"""

import json
import csv
import sqlite3
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend.db.opportunity import (
    get_opportunity_tier_company_ids,
    evaluate_broker_opportunity,
    load_opportunity_universe_context,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
)

DB_PATH = Path("data/prospects.db")
ROSTER_JSON_PATH = Path("reports/tier_a_acceleration_phase_a_roster.json")
ROSTER_CSV_PATH = Path("reports/tier_a_acceleration_phase_a_roster.csv")

def compute_sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest().upper()

def main():
    initial_hash = compute_sha256(DB_PATH)
    print(f"Starting DB Hash: {initial_hash}")
    assert initial_hash == "95D7FE5C53676AD286CF460F0B9A76D676A4678683D04193634804F4D42FB321"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    context = load_opportunity_universe_context(conn)
    tier_map = get_opportunity_tier_company_ids(conn=conn, universe_context=context)

    tier_b_cids = sorted(tier_map[TIER_B_WORTH_CALLING])
    tier_c_cids = sorted(tier_map[TIER_C_SECONDARY])

    print(f"Tier B companies count: {len(tier_b_cids)}")
    print(f"Tier C companies count: {len(tier_c_cids)}")
    assert len(tier_b_cids) == 102
    assert len(tier_c_cids) == 5

    candidate_cids = tier_b_cids + tier_c_cids
    assert len(candidate_cids) == 107

    # Gather data for each candidate company
    candidates_data = []

    for cid in candidate_cids:
        c_row = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()
        brand = c_row["operating_brand"]
        website = c_row["website_url"] or ""

        # Facilities
        fac_rows = conn.execute("""
            SELECT f.*, COALESCE(pl.stage, 'DISCOVERY') as lifecycle_stage
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.company_id = ?
            ORDER BY f.id ASC
        """, (cid,)).fetchall()

        op_fac_ids = [f["id"] for f in fac_rows]

        # Contacts
        contacts = conn.execute("""
            SELECT * FROM contacts
            WHERE company_id = ? OR facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
            ORDER BY id ASC
        """, (cid, cid)).fetchall()

        # Best usable contact route
        usable_route = "None"
        for ct in contacts:
            chan = ct["phone_number"] or ct["email_address"]
            if chan:
                name = ct["person_name"] or ct["exact_published_title"] or ct["department"] or "Logistics"
                directness = ct["phone_directness"] or ct["email_directness"] or "GENERAL"
                usable_route = f"{name}: {chan} [{directness}]"
                if directness == "DIRECT_PERSON":
                    break

        # Commodities & equipment
        comm_rows = conn.execute("""
            SELECT fc.commodity_category, fc.equipment_category, fc.equipment_usage_status
            FROM facility_commodities fc
            WHERE fc.facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
        """, (cid,)).fetchall()

        commodities = sorted(list(set(r["commodity_category"] for r in comm_rows if r["commodity_category"])))
        equipments = sorted(list(set(r["equipment_category"] for r in comm_rows if r["equipment_category"])))

        # Aggregate current company fact statuses
        # Private fleet
        if any(f["private_fleet_present"] == "VERIFIED_PRESENT" for f in fac_rows):
            c_fleet = "VERIFIED_PRESENT"
        elif all(f["private_fleet_present"] == "VERIFIED_NO_FLEET" for f in fac_rows):
            c_fleet = "VERIFIED_NO_FLEET"
        else:
            c_fleet = "UNKNOWN"

        # Fleet relationship
        fleet_rels = [f["fleet_relationship_type"] for f in fac_rows if f["fleet_relationship_type"] and f["fleet_relationship_type"] != "UNKNOWN"]
        c_fleet_rel = fleet_rels[0] if fleet_rels else "UNKNOWN"

        # Commercial carrier
        if any(f["commercial_carrier_use"] == "VERIFIED" for f in fac_rows):
            c_carrier = "VERIFIED"
        elif all(f["commercial_carrier_use"] == "UNLIKELY" for f in fac_rows):
            c_carrier = "UNLIKELY"
        else:
            c_carrier = "UNKNOWN"

        # Broker friendly
        if any(f["broker_friendly_status"] == "VERIFIED_ACCEPTS" for f in fac_rows):
            c_broker = "VERIFIED_ACCEPTS"
        elif any(f["broker_friendly_status"] == "VERIFIED_DIRECT_ONLY" for f in fac_rows):
            c_broker = "VERIFIED_DIRECT_ONLY"
        else:
            c_broker = "UNKNOWN"

        # Candidate focus facilities: prioritize facilities with FTL equipment and non-restricted broker status
        focus_fac_ids = []
        for f in fac_rows:
            if f["broker_friendly_status"] != "VERIFIED_DIRECT_ONLY":
                focus_fac_ids.append(f["id"])
        if not focus_fac_ids:
            focus_fac_ids = op_fac_ids

        # Lifecycle summary
        stages = [f["lifecycle_stage"] for f in fac_rows]
        if "SHORTLISTED" in stages:
            lc_summary = "SHORTLISTED"
        elif "QUALIFIED" in stages:
            lc_summary = "QUALIFIED"
        elif "DISCOVERY" in stages:
            lc_summary = "DISCOVERY"
        else:
            lc_summary = "UNKNOWN"

        tier = TIER_C_SECONDARY if cid in tier_c_cids else TIER_B_WORTH_CALLING

        # Evaluate priority tier
        # PRIORITY 1: Tier C companies where private_fleet_present = VERIFIED_PRESENT AND commercial_carrier_use = UNKNOWN AND broker_friendly_status = UNKNOWN
        # PRIORITY 2: Tier B companies where all normal readiness/FTL/callability requirements are already satisfied AND commercial_carrier_use = UNKNOWN AND broker_friendly_status = UNKNOWN AND official website exists
        # PRIORITY 3: Tier B companies with strong official web presence and only 1 obvious Tier-A trigger gap
        # PRIORITY 4: remaining Tier B/C
        has_website = bool(website and website.strip())
        has_callable = usable_route != "None"
        has_ftl = any(eq in ("FLATBED", "STEP_DECK", "DRY_VAN") for eq in equipments)

        if tier == TIER_C_SECONDARY and c_fleet == "VERIFIED_PRESENT" and c_carrier == "UNKNOWN" and c_broker == "UNKNOWN":
            priority = 1
            priority_reason = "Tier C candidate with verified private fleet; resolving outside carrier use can trigger immediate Tier A promotion."
            primary_gap = "commercial_carrier_use"
            secondary_gap = "broker_friendly_status"
        elif tier == TIER_B_WORTH_CALLING and has_ftl and has_callable and c_carrier == "UNKNOWN" and c_broker == "UNKNOWN" and has_website:
            priority = 2
            priority_reason = "Tier B candidate fully actionable with FTL fit and verified website; commercial carrier use unresolved."
            primary_gap = "commercial_carrier_use"
            secondary_gap = "broker_friendly_status"
        elif tier == TIER_B_WORTH_CALLING and has_website and (c_carrier == "UNKNOWN" or c_broker == "UNKNOWN"):
            priority = 3
            priority_reason = "Tier B candidate with verified official website and single primary carrier/broker evidence gap."
            primary_gap = "commercial_carrier_use" if c_carrier == "UNKNOWN" else "broker_friendly_status"
            secondary_gap = "broker_friendly_status" if primary_gap == "commercial_carrier_use" else "fleet_relationship_type"
        else:
            priority = 4
            priority_reason = "Tier B/C candidate; secondary research queue."
            primary_gap = "commercial_carrier_use"
            secondary_gap = "broker_friendly_status"

        candidates_data.append({
            "company_id": cid,
            "operating_brand": brand,
            "current_tier": tier,
            "priority": priority,
            "priority_reason": priority_reason,
            "primary_gap": primary_gap,
            "secondary_gap": secondary_gap,
            "operating_facility_ids": op_fac_ids,
            "candidate_focus_facility_ids": focus_fac_ids,
            "commodity_categories": commodities,
            "equipment_categories": equipments,
            "commercial_carrier_use_current": c_carrier,
            "broker_friendly_status_current": c_broker,
            "private_fleet_current": c_fleet,
            "fleet_relationship_current": c_fleet_rel,
            "usable_contact_route": usable_route,
            "official_website": website,
            "lifecycle_summary": lc_summary,
        })

    conn.close()

    # Sort deterministically: priority ascending, then company_id ascending
    candidates_data.sort(key=lambda x: (x["priority"], x["company_id"]))

    # Assign campaign_position (1..107) and wave (A..E)
    roster_json = []
    roster_csv_rows = []

    for idx, c in enumerate(candidates_data, start=1):
        if idx <= 25:
            wave = "A"
        elif idx <= 50:
            wave = "B"
        elif idx <= 75:
            wave = "C"
        elif idx <= 100:
            wave = "D"
        else:
            wave = "E"

        item = {
            "campaign": "TIER_A_ACCELERATION",
            "phase": "PHASE_A",
            "campaign_position": idx,
            "wave": wave,
            "company_id": c["company_id"],
            "operating_brand": c["operating_brand"],
            "current_tier": c["current_tier"],
            "lifecycle_summary": c["lifecycle_summary"],
            "operating_facility_ids": c["operating_facility_ids"],
            "candidate_focus_facility_ids": c["candidate_focus_facility_ids"],
            "commodity_categories": c["commodity_categories"],
            "equipment_categories": c["equipment_categories"],
            "commercial_carrier_use_current": c["commercial_carrier_use_current"],
            "broker_friendly_status_current": c["broker_friendly_status_current"],
            "private_fleet_current": c["private_fleet_current"],
            "fleet_relationship_current": c["fleet_relationship_current"],
            "usable_contact_route": c["usable_contact_route"],
            "official_website": c["official_website"],
            "primary_A_trigger_gap": c["primary_gap"],
            "secondary_A_trigger_gap": c["secondary_gap"],
            "research_priority_reason": c["priority_reason"],
        }
        roster_json.append(item)

        roster_csv_rows.append({
            "campaign": item["campaign"],
            "phase": item["phase"],
            "campaign_position": item["campaign_position"],
            "wave": item["wave"],
            "company_id": item["company_id"],
            "operating_brand": item["operating_brand"],
            "current_tier": item["current_tier"],
            "lifecycle_summary": item["lifecycle_summary"],
            "operating_facility_ids": "; ".join(map(str, item["operating_facility_ids"])),
            "candidate_focus_facility_ids": "; ".join(map(str, item["candidate_focus_facility_ids"])),
            "commodity_categories": "; ".join(item["commodity_categories"]),
            "equipment_categories": "; ".join(item["equipment_categories"]),
            "commercial_carrier_use_current": item["commercial_carrier_use_current"],
            "broker_friendly_status_current": item["broker_friendly_status_current"],
            "private_fleet_current": item["private_fleet_current"],
            "fleet_relationship_current": item["fleet_relationship_current"],
            "usable_contact_route": item["usable_contact_route"],
            "official_website": item["official_website"],
            "primary_A_trigger_gap": item["primary_A_trigger_gap"],
            "secondary_A_trigger_gap": item["secondary_A_trigger_gap"],
            "research_priority_reason": item["research_priority_reason"],
        })

    with open(ROSTER_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(roster_json, f, indent=2)

    with open(ROSTER_CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(roster_csv_rows[0].keys()))
        writer.writeheader()
        writer.writerows(roster_csv_rows)

    print(f"Wrote {len(roster_json)} entries to {ROSTER_JSON_PATH}")
    print(f"Wrote {len(roster_csv_rows)} rows to {ROSTER_CSV_PATH}")

    # Summary by wave
    from collections import Counter
    wave_counts = Counter(item["wave"] for item in roster_json)
    print("Wave distribution:")
    for w in sorted(wave_counts.keys()):
        print(f"  Wave {w}: {wave_counts[w]} companies")

    # Final DB Hash check
    final_hash = compute_sha256(DB_PATH)
    print(f"Final DB Hash: {final_hash}")
    assert final_hash == initial_hash, "DB hash changed during roster freeze!"
    print("[PASS] Roster freeze completed with ZERO database mutations.")

if __name__ == "__main__":
    main()
