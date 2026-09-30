"""
FreightProspecting V1 — Broker Research Batch 2 Frozen Selection Generator
Generates:
  - reports/batch_2_frozen_selection.json
  - reports/batch_2_frozen_selection.csv
Directly from SQLite database (prospects.db) ensuring zero database mutation.
"""

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/prospects.db")
B1_PATH = Path("reports/batch_1_frozen_selection.json")
OUTPUT_JSON = Path("reports/batch_2_frozen_selection.json")
OUTPUT_CSV = Path("reports/batch_2_frozen_selection.csv")

EXPECTED_BASELINE_HASH = "6E1658D57CA698E672D7006C57F795E901FD2DD6069BBFC8579F311445ACEE47"

# 20 Selected Companies for Batch 2 with their research focus facility ID and curated rationale
SELECTED_ROSTER_DEFS = [
    {
        "priority": 1,
        "company_id": 104,
        "facility_id": 133,
        "reason": "Major Michigan flat-rolled steel coil service center with a verified dedicated outbound traffic desk (traffic@targetsteel.net). Prime candidate to confirm outside carrier dispatching and third-party broker onboarding.",
    },
    {
        "priority": 2,
        "company_id": 32,
        "facility_id": 31,
        "reason": "Tier 1 structural and architectural precast/prestressed concrete producer in Ontario shipping heavy bridge girders, hollowcore slabs, and wall panels across Ontario and US cross-border lanes.",
    },
    {
        "priority": 3,
        "company_id": 48,
        "facility_id": 51,
        "reason": "One of North America's largest lumber producers with huge FTL volume from its Baxley, GA mill; research can identify regional flatbed dispatching rules and outside carrier tenders.",
    },
    {
        "priority": 4,
        "company_id": 43,
        "facility_id": 42,
        "reason": "Major multi-plant injection molder supplying automotive, appliance, and consumer markets with steady outbound 53' Dry Van truckload shipments and dedicated sales desk.",
    },
    {
        "priority": 5,
        "company_id": 36,
        "facility_id": 35,
        "reason": "Premier Windsor, ON mold maker producing mid-to-large injection molds (up to 40+ tons) shipping cross-border flatbed and step deck loads directly to US tier-1 automotive molders. High-upside Tier D target.",
    },
    {
        "priority": 6,
        "company_id": 24,
        "facility_id": 23,
        "reason": "High-volume Detroit metro steel processor and fabricator requiring continuous heavy flatbed equipment for plate, structural shapes, and processed steel.",
    },
    {
        "priority": 7,
        "company_id": 134,
        "facility_id": 163,
        "reason": "Major Michigan reinforced concrete pipe and box culvert manufacturer with published executive contact (trw@ncp-inc.com); research can confirm outside hauling and broker partnerships.",
    },
    {
        "priority": 8,
        "company_id": 11,
        "facility_id": 10,
        "reason": "High-value Pacific Northwest specialty timber sawmill exporting heavy rough-sawn Douglas Fir and Hemlock beams to US and Canadian building markets.",
    },
    {
        "priority": 9,
        "company_id": 92,
        "facility_id": 114,
        "reason": "Major Burns Harbor / Portage, IN steel distribution center shipping heavy hot-rolled and pickled & oiled carbon sheet across the Midwest industrial corridor.",
    },
    {
        "priority": 10,
        "company_id": 108,
        "facility_id": 137,
        "reason": "Western Canadian manufacturer of heavy underground civil and electrical utility vaults requiring dedicated flatbed and boom-truck transport.",
    },
    {
        "priority": 11,
        "company_id": 12,
        "facility_id": 11,
        "reason": "Western Red Cedar sawmill complex in Surrey, BC with substantial cross-border truckload movements into US Western and Midwest distribution centers.",
    },
    {
        "priority": 12,
        "company_id": 41,
        "facility_id": 40,
        "reason": "High-volume custom injection molding manufacturer in suburban Detroit producing medical, automotive, and defense plastic components on 53' Dry Vans.",
    },
    {
        "priority": 13,
        "company_id": 115,
        "facility_id": 144,
        "reason": "Established Southern Ontario precast concrete infrastructure manufacturer producing drainage and building modules with regular multi-load deliveries.",
    },
    {
        "priority": 14,
        "company_id": 52,
        "facility_id": 55,
        "reason": "Long-standing Georgia southern yellow pine sawmill with steady outbound flatbed demand across the Southeast corridor.",
    },
    {
        "priority": 15,
        "company_id": 143,
        "facility_id": 172,
        "reason": "Manufacturer of heavy-duty molded polyurethane and plastic automotive dunnage shipping dry van loads to assembly plants across the automotive corridor.",
    },
    {
        "priority": 16,
        "company_id": 89,
        "facility_id": 107,
        "reason": "Western Michigan flat-rolled coil distributor with active slit coil shipments; research can resolve regional carrier usage and broker acceptance.",
    },
    {
        "priority": 17,
        "company_id": 146,
        "facility_id": 175,
        "reason": "Tooling, mold, and complex machinery manufacturing facility in Oakland County, MI shipping heavy dies and components on flatbeds.",
    },
    {
        "priority": 18,
        "company_id": 379,
        "facility_id": 466,
        "reason": "Multi-facility Ohio steel service center with multi-product carbon steel line. Blocked in Tier D only by missing carrier/fleet facts; high upside to advance to Tier B or Tier A with verified logistics evidence.",
    },
    {
        "priority": 19,
        "company_id": 331,
        "facility_id": 418,
        "reason": "Large Pacific Northwest forest products manufacturer operating modern sawmills and plywood facilities in Oregon; prime Tier D candidate with strong FTL upside once carrier procurement is verified.",
    },
    {
        "priority": 20,
        "company_id": 130,
        "facility_id": 159,
        "reason": "Massive Southwestern Ontario precast and hollowcore manufacturing complex; blocked in Tier D due to initial discovery stage, but possesses tremendous freight volume upside upon verifying transportation operations.",
    },
]


def main():
    # 1. Verify DB SHA-256 before doing anything
    db_bytes = DB_PATH.read_bytes()
    current_hash = hashlib.sha256(db_bytes).hexdigest().upper()
    assert current_hash == EXPECTED_BASELINE_HASH, f"DB SHA-256 mismatch: {current_hash} != {EXPECTED_BASELINE_HASH}"
    print(f"Verified production DB SHA-256: {current_hash}")

    # 2. Check Batch 1 roster
    with open(B1_PATH, "r", encoding="utf-8") as f:
        b1_data = json.load(f)
    b1_ids = {r["company_id"] for r in b1_data}
    assert len(b1_ids) == 20, f"Expected 20 Batch 1 companies, found {len(b1_ids)}"
    print(f"Loaded Batch 1 frozen roster: {len(b1_ids)} companies")

    # Connect to DB (read-only mode)
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    from src.backend.db.opportunity import (
        evaluate_broker_opportunity,
        TIER_B_WORTH_CALLING,
        TIER_D_RESEARCH_NEEDED,
    )

    batch_records = []
    selected_comp_ids = set()

    for item in SELECTED_ROSTER_DEFS:
        cid = item["company_id"]
        fid = item["facility_id"]
        priority = item["priority"]
        reason = item["reason"]

        # Ensure no duplicate selection
        assert cid not in selected_comp_ids, f"Duplicate company ID {cid} in selection"
        selected_comp_ids.add(cid)

        # Assert no overlap with Batch 1
        assert cid not in b1_ids, f"Company ID {cid} overlaps with Batch 1!"

        # Query company
        comp = conn.execute("SELECT id, operating_brand, legal_name, website_url FROM companies WHERE id = ?", (cid,)).fetchone()
        assert comp is not None, f"Company {cid} not found in database!"

        # Evaluate opportunity tier
        opp = evaluate_broker_opportunity(cid, conn=conn)
        tier = opp["opportunity_tier"]
        assert tier in (TIER_B_WORTH_CALLING, TIER_D_RESEARCH_NEEDED), f"Company {cid} has unexpected tier: {tier}"

        # Query facility
        fac = conn.execute("""
            SELECT f.id, f.facility_name, f.city, f.state_prov, f.country,
                   pl.stage as lifecycle_stage,
                   f.private_fleet_present, f.fleet_relationship_type,
                   f.commercial_carrier_use, f.broker_friendly_status
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.id = ? AND f.company_id = ?
        """, (fid, cid)).fetchone()
        assert fac is not None, f"Facility {fid} for company {cid} not found in database!"

        # Geography check: Lower 48 US or 10 Canadian provinces (no AK, HI, MX)
        state = (fac["state_prov"] or "").upper()
        country = (fac["country"] or "USA").upper()
        assert state not in ("AK", "HI", "ALASKA", "HAWAII"), f"Facility {fid} is in excluded territory: {state}"
        assert country not in ("MX", "MEX", "MEXICO"), f"Facility {fid} is in Mexico: {country}"

        # Commodity & equipment
        comms = conn.execute("""
            SELECT commodity_category, specific_products, equipment_category, equipment_usage_status
            FROM facility_commodities WHERE facility_id = ?
        """, (fid,)).fetchall()
        assert len(comms) > 0, f"Facility {fid} has no commodity records!"

        comm_cat = comms[0]["commodity_category"] or comms[0]["specific_products"] or "Industrial Freight"
        eq_cat = comms[0]["equipment_category"] or "FLATBED"
        eq_ver = comms[0]["equipment_usage_status"] or "INFERRED"

        # Contacts
        contacts = conn.execute("""
            SELECT id, person_name, department, exact_published_title,
                   phone_number, phone_directness, email_address, email_directness
            FROM contacts WHERE facility_id = ? OR company_id = ?
        """, (fid, cid)).fetchall()

        # Find best usable phone and email
        best_phone = "NONE"
        best_email = "NONE"
        for ct in contacts:
            if best_phone == "NONE" and ct["phone_number"]:
                best_phone = f"{ct['phone_number']} [{ct['phone_directness'] or 'UNKNOWN'}]"
            if best_email == "NONE" and ct["email_address"]:
                best_email = f"{ct['email_address']} [{ct['email_directness'] or 'UNKNOWN'}]"

        # Identify primary unknowns to research
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

        record = {
            "batch": 2,
            "company_id": cid,
            "operating_brand": comp["operating_brand"],
            "research_focus_facility_id": fid,
            "facility_name": fac["facility_name"],
            "city": fac["city"],
            "state_prov": fac["state_prov"],
            "country": fac["country"] or "USA",
            "lifecycle": fac["lifecycle_stage"] or "UNKNOWN",
            "pre_research_opportunity_tier": tier,
            "commodity/category": comm_cat,
            "equipment_category": eq_cat,
            "equipment_verification": eq_ver,
            "private_fleet_present": fleet,
            "fleet_relationship_type": fleet_type,
            "commercial_carrier_use": carrier,
            "broker_friendly_status": broker,
            "usable_phone": best_phone,
            "usable_email": best_email,
            "selection_priority": priority,
            "selection_reason": reason,
            "primary_unknowns_to_research": unknowns,
        }
        batch_records.append(record)

    conn.close()

    # Validation checks
    assert len(batch_records) == 20, f"Expected exactly 20 records, got {len(batch_records)}"
    assert len({r["company_id"] for r in batch_records}) == 20, "Company IDs must be unique"
    assert len({r["research_focus_facility_id"] for r in batch_records}) == 20, "Facility IDs must be unique"

    # Tier counts
    tier_counts = {}
    for r in batch_records:
        tier_counts[r["pre_research_opportunity_tier"]] = tier_counts.get(r["pre_research_opportunity_tier"], 0) + 1

    print("Selected Tier Breakdown:", tier_counts)
    assert tier_counts.get("TIER_B_WORTH_CALLING", 0) == 16, f"Expected 16 Tier B, got {tier_counts.get('TIER_B_WORTH_CALLING')}"
    assert tier_counts.get("TIER_D_RESEARCH_NEEDED", 0) == 4, f"Expected 4 Tier D, got {tier_counts.get('TIER_D_RESEARCH_NEEDED')}"
    assert tier_counts.get("TIER_A_PRIORITY", 0) == 0, "No Tier A should be selected"
    assert tier_counts.get("TIER_C_SECONDARY", 0) == 0, "No Tier C should be selected"

    # Write JSON artifact
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(batch_records, f, indent=2)
    print(f"Generated {OUTPUT_JSON} successfully ({len(batch_records)} records).")

    # Write CSV artifact
    fieldnames = [
        "batch",
        "selection_priority",
        "company_id",
        "operating_brand",
        "research_focus_facility_id",
        "facility_name",
        "city",
        "state_prov",
        "country",
        "lifecycle",
        "pre_research_opportunity_tier",
        "commodity/category",
        "equipment_category",
        "equipment_verification",
        "private_fleet_present",
        "fleet_relationship_type",
        "commercial_carrier_use",
        "broker_friendly_status",
        "usable_phone",
        "usable_email",
        "primary_unknowns_to_research",
        "selection_reason",
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
    main()
