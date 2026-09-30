"""
Synchronizes Stage 3H JSON data files with the corrected database records.
- data/stage3h_all_candidates.json
- data/existing_entities_lookup.json
"""

import json
from pathlib import Path

def sync_all_candidates():
    p = Path("data/stage3h_all_candidates.json")
    if not p.exists():
        print(f"{p} not found, skipping.")
        return

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        # 1. Reset footprint to UNKNOWN for all 38
        item["footprint_status"] = "UNKNOWN"

        # 2. Lignetics
        if "Lignetics" in item["operating_brand"]:
            item["facility_type"] = "HEADQUARTERS"
            item["facility_name"] = "Lignetics Corporate Headquarters"
            item["specific_products"] = "Company-level commercial product line: bagged wood heating pellets, barbecue wood pellets, and compressed firelogs (corporate administrative location; production at regional mills)"

        # 3. Kempler
        if "Kempler" in item["operating_brand"]:
            item["facility_name"] = "Kempler Machinery Corporate Office & Operations"
            item["physical_address"] = "2720 Dundee Rd, Suite 300"
            item["city"] = "Northbrook"
            item["state_prov"] = "IL"
            item["postal_code"] = "60062"

        # 4. SCHÜTZ
        if "SCH" in item["operating_brand"] and "Container" in item["operating_brand"]:
            item["operating_brand"] = "SCHÜTZ Container Systems"
            item["legal_name"] = "SCHÜTZ Container Systems, Inc."
            item["facility_name"] = "SCHÜTZ North Branch IBC Plant"
            item["source_title"] = "SCHÜTZ Container Systems Official Website"

    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Synchronized {p.name}")

def sync_existing_lookup():
    p = Path("data/existing_entities_lookup.json")
    if not p.exists():
        print(f"{p} not found, skipping.")
        return

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    for co in data.get("companies", []):
        if co["id"] == 565:
            co["brand"] = "SCHÜTZ Container Systems"
            co["legal"] = "SCHÜTZ Container Systems, Inc."
            co["clean_brand"] = "schutzcontainersystems"
        elif co["id"] == 552:
            co["legal"] = "Kempler Industries, Inc."

    for fac in data.get("facilities", []):
        if fac["id"] == 652:
            fac["name"] = "SCHÜTZ North Branch IBC Plant"
        elif fac["id"] == 623:
            fac["name"] = "Lignetics Corporate Headquarters"
        elif fac["id"] == 639:
            fac["name"] = "Kempler Machinery Corporate Office & Operations"
            fac["city"] = "Northbrook"
            fac["state"] = "IL"
            fac["zip"] = "60062"

    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Synchronized {p.name}")

if __name__ == "__main__":
    sync_all_candidates()
    sync_existing_lookup()
