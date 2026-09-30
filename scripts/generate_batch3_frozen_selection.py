"""
FreightProspecting V1 — Broker Research Batch 3 Frozen Selection Generator
Generates:
  - reports/batch_3_frozen_selection.json
  - reports/batch_3_frozen_selection.csv
Directly from SQLite database (prospects.db) ensuring zero database mutation.
"""

import csv
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend.db.opportunity import (
    evaluate_broker_opportunity,
    TIER_B_WORTH_CALLING,
    TIER_D_RESEARCH_NEEDED,
    TIER_A_PRIORITY,
    TIER_C_SECONDARY,
    RESTRICTED,
)

DB_PATH = Path("data/prospects.db")
B1_PATH = Path("reports/batch_1_frozen_selection.json")
B2_PATH = Path("reports/batch_2_frozen_selection.json")
OUTPUT_JSON = Path("reports/batch_3_frozen_selection.json")
OUTPUT_CSV = Path("reports/batch_3_frozen_selection.csv")

EXPECTED_BASELINE_HASH = "05BAE4B965716E16B902B4C37E293B7C03278B62490C03E8344F33F4FEC87D65"

# List of 23 curated, high-value Tier D industrial shippers with heavy FTL demand
TIER_D_CURATED_PICKS = [
    {
        "company_id": 541,
        "reason": "Major national manufacturer of industrial wooden pallets, bulk shipping packaging, and export crates with steady outbound 53' Dry Van volume across industrial centers.",
    },
    {
        "company_id": 546,
        "reason": "Massive Kentucky fencing, steel pipe, and industrial gate manufacturer distributing heavy flatbed loads nationwide across multiple manufacturing hubs.",
    },
    {
        "company_id": 545,
        "reason": "High-volume municipal and agricultural PVC & HDPE water/irrigation pipe producer shipping continuous 48'/53' flatbed loads across the Great Plains and Midwest.",
    },
    {
        "company_id": 151,
        "reason": "Precision injection molder and tooling manufacturer producing complex automotive and medical plastics components on Dry Vans and specialized flatbed tooling shipments.",
    },
    {
        "company_id": 547,
        "reason": "Leading Canadian roll-formed metal roofing, commercial siding, and steel panel manufacturer shipping flatbed loads across Ontario, Quebec, and US borders.",
    },
    {
        "company_id": 554,
        "reason": "World-class manufacturer of heavy commercial HVAC, roof-top air handling units, and industrial blowers requiring dedicated flatbed and step deck capacity.",
    },
    {
        "company_id": 560,
        "reason": "Multi-facility Western NY and PA industrial packaging and heavy corrugated box producer moving regular outbound truckload dry van freight.",
    },
    {
        "company_id": 540,
        "reason": "Large Pacific Northwest wooden pallet and agricultural crate manufacturer shipping continuous flatbed and dry van lumber and dunnage loads.",
    },
    {
        "company_id": 543,
        "reason": "Premier Ohio manufacturer of pre-engineered roof trusses, floor trusses, and wall panels moving wide-load and standard flatbed freight to commercial construction sites.",
    },
    {
        "company_id": 550,
        "reason": "Large Iowa agricultural planter and grain cart manufacturer requiring regular flatbed and step deck equipment across the Corn Belt and industrial manufacturing corridors.",
    },
    {
        "company_id": 447,
        "reason": "Specialty steel mechanical tubing and pipe distributor in Ontario shipping heavy bundles on flatbeds to fabrication and automotive customers across Canada and US.",
    },
    {
        "company_id": 549,
        "reason": "Prominent Midwest agricultural equipment and header transport manufacturer shipping heavy industrial farm machinery on flatbeds and step decks.",
    },
    {
        "company_id": 558,
        "reason": "Major North American designer and manufacturer of solar racking and structural mounting systems with high-volume outbound flatbed construction freight.",
    },
    {
        "company_id": 39,
        "reason": "Tier-1 Windsor automotive tooling and large-scale injection mold producer shipping heavy dies and molds (up to 50 tons) cross-border to US assembly plants.",
    },
    {
        "company_id": 445,
        "reason": "Integrated Ontario steel service center and reinforcing steel fabricator supplying structural steel and rebar on flatbeds throughout Ontario and Northern US.",
    },
    {
        "company_id": 474,
        "reason": "Southern Ontario distributor of stainless steel, aluminum, and nickel alloy coils, sheet, and bar shipping flatbed freight across cross-border manufacturing lanes.",
    },
    {
        "company_id": 552,
        "reason": "Major national dealer and rebuilder of heavy sheet metal equipment, hydraulic presses, and stamping presses moving heavy machinery on step decks.",
    },
    {
        "company_id": 553,
        "reason": "Global manufacturer of evaporative cooling towers, closed-circuit coolers, and industrial condensers requiring heavy flatbed and oversized step deck logistics.",
    },
    {
        "company_id": 387,
        "reason": "Large regional structural steel service center stocking heavy wide flange beams, channels, and structural angles moving continuous flatbed outbound loads.",
    },
    {
        "company_id": 432,
        "reason": "Multi-metal distributor of non-ferrous, aluminum, and carbon plate/sheet serving aerospace, defense, and industrial fabrication with regular FTL flatbed shipments.",
    },
    {
        "company_id": 525,
        "reason": "Established Nebraska precast concrete producer manufacturing utility vaults, bridge components, and retaining wall systems shipping on heavy flatbeds.",
    },
    {
        "company_id": 138,
        "reason": "Major British Columbia heavy civil precast concrete and bridge girder manufacturer moving massive precast elements across Western Canada and US border.",
    },
    {
        "company_id": 395,
        "reason": "Southeast Michigan specialty tool steel and alloy plate service center serving mold makers, tool & die shops, and automotive machine shops on local and regional flatbeds.",
    },
]


def generate_batch3_roster():
    # 1. Verify DB SHA-256 before doing anything
    db_bytes = DB_PATH.read_bytes()
    current_hash = hashlib.sha256(db_bytes).hexdigest().upper()
    assert current_hash == EXPECTED_BASELINE_HASH, f"DB SHA-256 mismatch: {current_hash} != {EXPECTED_BASELINE_HASH}"
    print(f"Verified production DB SHA-256: {current_hash}")

    # 2. Check Batch 1 and Batch 2 rosters
    with open(B1_PATH, "r", encoding="utf-8") as f:
        b1_data = json.load(f)
    b1_ids = {r["company_id"] for r in b1_data}
    assert len(b1_ids) == 20, f"Expected 20 Batch 1 companies, found {len(b1_ids)}"

    with open(B2_PATH, "r", encoding="utf-8") as f:
        b2_data = json.load(f)
    b2_ids = {r["company_id"] for r in b2_data}
    assert len(b2_ids) == 20, f"Expected 20 Batch 2 companies, found {len(b2_ids)}"

    print(f"Loaded Batch 1 ({len(b1_ids)}) and Batch 2 ({len(b2_ids)}) frozen rosters.")

    # Connect to DB (read-only mode)
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # Find all available operating companies
    comp_ids = [r[0] for r in conn.execute("SELECT DISTINCT company_id FROM facilities ORDER BY company_id").fetchall()]

    tier_b_candidates = []
    tier_d_curated_map = {p["company_id"]: p["reason"] for p in TIER_D_CURATED_PICKS}

    for cid in comp_ids:
        if cid in b1_ids or cid in b2_ids:
            continue
        opp = evaluate_broker_opportunity(cid, conn=conn)
        tier = opp["opportunity_tier"]
        if tier == TIER_B_WORTH_CALLING:
            tier_b_candidates.append(cid)

    print(f"Found {len(tier_b_candidates)} eligible Tier B companies.")
    assert len(tier_b_candidates) == 77, f"Expected 77 Tier B companies, found {len(tier_b_candidates)}"
    assert len(TIER_D_CURATED_PICKS) == 23, f"Expected 23 curated Tier D picks, found {len(TIER_D_CURATED_PICKS)}"

    # Build the combined 100 roster:
    # 77 Tier B + 23 Tier D = 100
    roster_defs = []

    # Add 77 Tier B companies
    for idx, cid in enumerate(tier_b_candidates, 1):
        comp = conn.execute("SELECT operating_brand FROM companies WHERE id = ?", (cid,)).fetchone()
        brand = comp["operating_brand"]
        # Retrieve primary commodity and location for tailored reason
        fac = conn.execute("SELECT id, city, state_prov FROM facilities WHERE company_id = ? ORDER BY id LIMIT 1", (cid,)).fetchone()
        comm = conn.execute("SELECT commodity_category, equipment_category FROM facility_commodities WHERE facility_id = ? LIMIT 1", (fac["id"],)).fetchone()
        comm_cat = comm["commodity_category"] if comm else "Industrial Freight"
        eq = comm["equipment_category"] if comm else "FLATBED"
        reason = f"Active {brand} facility in {fac['city']}, {fac['state_prov']} producing {comm_cat} with strong {eq} truckload suitability. Prime candidate to investigate commercial carrier dispatching, private fleet relationship, and broker acceptance."
        roster_defs.append({
            "company_id": cid,
            "facility_id": fac["id"],
            "pre_tier": TIER_B_WORTH_CALLING,
            "reason": reason,
        })

    # Add 23 Tier D companies
    for pick in TIER_D_CURATED_PICKS:
        cid = pick["company_id"]
        assert cid not in b1_ids and cid not in b2_ids, f"Tier D pick {cid} overlaps with Batch 1 or 2!"
        opp = evaluate_broker_opportunity(cid, conn=conn)
        assert opp["opportunity_tier"] == TIER_D_RESEARCH_NEEDED, f"Company {cid} tier is not Tier D: {opp['opportunity_tier']}"
        fac = conn.execute("SELECT id FROM facilities WHERE company_id = ? ORDER BY id LIMIT 1", (cid,)).fetchone()
        roster_defs.append({
            "company_id": cid,
            "facility_id": fac["id"],
            "pre_tier": TIER_D_RESEARCH_NEEDED,
            "reason": pick["reason"],
        })

    assert len(roster_defs) == 100, f"Expected 100 companies, got {len(roster_defs)}"

    batch_records = []
    selected_comp_ids = set()

    for idx, item in enumerate(roster_defs, 1):
        cid = item["company_id"]
        fid = item["facility_id"]
        tier = item["pre_tier"]
        reason = item["reason"]

        assert cid not in selected_comp_ids, f"Duplicate company ID {cid} in selection"
        selected_comp_ids.add(cid)

        # Assign wave: 1-25: A, 26-50: B, 51-75: C, 76-100: D
        if idx <= 25:
            wave = "A"
        elif idx <= 50:
            wave = "B"
        elif idx <= 75:
            wave = "C"
        else:
            wave = "D"

        comp = conn.execute("SELECT id, operating_brand, legal_name, website_url FROM companies WHERE id = ?", (cid,)).fetchone()
        assert comp is not None, f"Company {cid} not found!"

        fac = conn.execute("""
            SELECT f.id, f.facility_name, f.city, f.state_prov, f.country,
                   pl.stage as lifecycle_stage,
                   f.private_fleet_present, f.fleet_relationship_type,
                   f.commercial_carrier_use, f.broker_friendly_status
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.id = ? AND f.company_id = ?
        """, (fid, cid)).fetchone()
        assert fac is not None, f"Facility {fid} for company {cid} not found!"

        # Geography check
        state = (fac["state_prov"] or "").upper()
        country = (fac["country"] or "USA").upper()
        assert state not in ("AK", "HI", "ALASKA", "HAWAII"), f"Facility {fid} is in excluded territory: {state}"
        assert country not in ("MX", "MEX", "MEXICO"), f"Facility {fid} is in Mexico: {country}"

        comms = conn.execute("""
            SELECT commodity_category, specific_products, equipment_category, equipment_usage_status
            FROM facility_commodities WHERE facility_id = ?
        """, (fid,)).fetchall()
        assert len(comms) > 0, f"Facility {fid} has no commodity records!"

        comm_cat = comms[0]["commodity_category"] or comms[0]["specific_products"] or "Industrial Freight"
        eq_cat = comms[0]["equipment_category"] or "FLATBED"
        eq_ver = comms[0]["equipment_usage_status"] or "INFERRED"

        contacts = conn.execute("""
            SELECT id, person_name, department, exact_published_title,
                   phone_number, phone_directness, email_address, email_directness
            FROM contacts WHERE facility_id = ? OR company_id = ?
        """, (fid, cid)).fetchall()

        best_phone = "NONE"
        best_email = "NONE"
        for ct in contacts:
            if best_phone == "NONE" and ct["phone_number"]:
                best_phone = f"{ct['phone_number']} [{ct['phone_directness'] or 'UNKNOWN'}]"
            if best_email == "NONE" and ct["email_address"]:
                best_email = f"{ct['email_address']} [{ct['email_directness'] or 'UNKNOWN'}]"

        unknowns = []
        fleet = fac["private_fleet_present"] or "UNKNOWN"
        fleet_type = fac["fleet_relationship_type"] or "UNKNOWN"
        carrier = fac["commercial_carrier_use"] or "UNKNOWN"
        broker = fac["broker_friendly_status"] or "UNKNOWN"

        if carrier == "UNKNOWN":
            unknowns.append("commercial_carrier_use")
        if broker == "UNKNOWN":
            unknowns.append("broker_friendly_status")
        if fleet == "UNKNOWN":
            unknowns.append("private_fleet_present")
        if fleet_type == "UNKNOWN":
            unknowns.append("fleet_relationship_type")
        if best_phone == "NONE" and best_email == "NONE":
            unknowns.append("logistics_contact")

        record = {
            "batch": 3,
            "batch_position": idx,
            "wave": wave,
            "company_id": cid,
            "operating_brand": comp["operating_brand"],
            "research_focus_facility_id": fid,
            "facility_name": fac["facility_name"],
            "city": fac["city"],
            "state_prov": fac["state_prov"],
            "country": fac["country"] or "USA",
            "lifecycle": fac["lifecycle_stage"] or "UNKNOWN",
            "pre_research_opportunity_tier": tier,
            "commodity_category": comm_cat,
            "equipment_category": eq_cat,
            "equipment_verification": eq_ver,
            "private_fleet_present": fleet,
            "fleet_relationship_type": fleet_type,
            "commercial_carrier_use": carrier,
            "broker_friendly_status": broker,
            "usable_phone": best_phone,
            "usable_email": best_email,
            "selection_priority": idx,
            "selection_reason": reason,
            "primary_unknowns_to_research": unknowns,
        }
        batch_records.append(record)

    conn.close()

    # Validation checks
    assert len(batch_records) == 100, f"Expected exactly 100 records, got {len(batch_records)}"
    assert len({r["company_id"] for r in batch_records}) == 100, "Company IDs must be unique"
    assert len({r["research_focus_facility_id"] for r in batch_records}) == 100, "Facility IDs must be unique"

    # Tier counts
    tier_counts = {}
    for r in batch_records:
        t = r["pre_research_opportunity_tier"]
        tier_counts[t] = tier_counts.get(t, 0) + 1

    print("Selected Tier Breakdown:", tier_counts)
    assert tier_counts.get(TIER_B_WORTH_CALLING, 0) == 77, f"Expected 77 Tier B, got {tier_counts.get(TIER_B_WORTH_CALLING)}"
    assert tier_counts.get(TIER_D_RESEARCH_NEEDED, 0) == 23, f"Expected 23 Tier D, got {tier_counts.get(TIER_D_RESEARCH_NEEDED)}"
    assert tier_counts.get(TIER_A_PRIORITY, 0) == 0, "No Tier A should be selected"
    assert tier_counts.get(TIER_C_SECONDARY, 0) == 0, "No Tier C should be selected"
    assert tier_counts.get(RESTRICTED, 0) == 0, "No Restricted should be selected"

    # Write JSON artifact
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(batch_records, f, indent=2)
    print(f"Generated {OUTPUT_JSON} successfully ({len(batch_records)} records).")

    # Write CSV artifact
    fieldnames = [
        "batch",
        "batch_position",
        "wave",
        "company_id",
        "operating_brand",
        "research_focus_facility_id",
        "facility_name",
        "city",
        "state_prov",
        "country",
        "lifecycle",
        "pre_research_opportunity_tier",
        "commodity_category",
        "equipment_category",
        "equipment_verification",
        "private_fleet_present",
        "fleet_relationship_type",
        "commercial_carrier_use",
        "broker_friendly_status",
        "usable_phone",
        "usable_email",
        "selection_priority",
        "selection_reason",
        "primary_unknowns_to_research",
    ]
    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in batch_records:
            row = dict(r)
            row["primary_unknowns_to_research"] = "; ".join(row["primary_unknowns_to_research"])
            writer.writerow(row)
    print(f"Generated {OUTPUT_CSV} successfully ({len(batch_records)} rows).")

    # Verify DB SHA-256 after generation
    post_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    assert post_hash == EXPECTED_BASELINE_HASH, f"Database mutated! {post_hash} != {EXPECTED_BASELINE_HASH}"
    print(f"Post-generation DB SHA-256 verified unchanged: {post_hash}")


if __name__ == "__main__":
    generate_batch3_roster()
