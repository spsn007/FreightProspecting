import sqlite3
import json
import re
from urllib.parse import urlparse
from pathlib import Path

def normalize_text(text):
    if not text:
        return ""
    text = text.lower()
    return re.sub(r"[^a-z0-9]", "", text)

def extract_domain(url):
    if not url:
        return ""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""

def normalize_phone(phone):
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    return digits

def normalize_address(addr):
    if not addr:
        return ""
    # Standardize street abbreviations
    a = addr.lower().strip()
    a = re.sub(r"\b(street|st|avenue|ave|road|rd|drive|dr|boulevard|blvd|lane|ln|court|ct|highway|hwy|parkway|pkwy|route|rt)\b", "", a)
    a = re.sub(r"[^a-z0-9]", "", a)
    return a

def build_existing_identity_index(db_path='data/prospects.db'):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    companies = conn.execute("SELECT * FROM companies").fetchall()
    facilities = conn.execute("SELECT * FROM facilities").fetchall()
    contacts = conn.execute("SELECT * FROM contacts").fetchall()
    relationships = conn.execute("SELECT * FROM company_relationships").fetchall()

    comp_map = {}
    for c in companies:
        cid = c["id"]
        brand_norm = normalize_text(c["operating_brand"])
        legal_norm = normalize_text(c["legal_name"])
        domain = extract_domain(c["website_url"])
        comp_map[cid] = {
            "company_id": cid,
            "operating_brand": c["operating_brand"],
            "legal_name": c["legal_name"],
            "operating_brand_norm": brand_norm,
            "legal_name_norm": legal_norm,
            "website_url": c["website_url"],
            "domain": domain,
            "domains": [domain] if domain else [],
            "facility_addresses_norm": [],
            "facility_names_norm": [],
            "cities_states": [],
            "phones_norm": [],
            "parent_companies": [],
            "child_companies": [],
        }

    for r in relationships:
        parent_id = r["parent_company_id"]
        child_id = r["child_company_id"]
        if child_id in comp_map:
            comp_map[child_id]["parent_companies"].append({
                "parent_id": parent_id,
                "relationship_type": r["relationship_type"],
            })
        if parent_id in comp_map:
            comp_map[parent_id]["child_companies"].append({
                "child_id": child_id,
                "relationship_type": r["relationship_type"],
            })

    for f in facilities:
        cid = f["company_id"]
        if cid in comp_map:
            addr_norm = normalize_address(f["physical_address"])
            if addr_norm:
                comp_map[cid]["facility_addresses_norm"].append(addr_norm)
            fac_name_norm = normalize_text(f["facility_name"])
            if fac_name_norm:
                comp_map[cid]["facility_names_norm"].append(fac_name_norm)
            city_state = f"{normalize_text(f['city'])}|{normalize_text(f['state_prov'])}"
            if city_state:
                comp_map[cid]["cities_states"].append(city_state)

    for c in contacts:
        cid = c["company_id"]
        phone_norm = normalize_phone(c["phone_number"])
        if cid and cid in comp_map and phone_norm:
            comp_map[cid]["phones_norm"].append(phone_norm)
        # also associate facility-level contact with the company
        if c["facility_id"]:
            # find facility's company_id
            fac = next((f for f in facilities if f["id"] == c["facility_id"]), None)
            if fac and fac["company_id"] in comp_map and phone_norm:
                comp_map[fac["company_id"]]["phones_norm"].append(phone_norm)

    # Deduplicate lists
    for cid, data in comp_map.items():
        data["facility_addresses_norm"] = list(set(data["facility_addresses_norm"]))
        data["facility_names_norm"] = list(set(data["facility_names_norm"]))
        data["cities_states"] = list(set(data["cities_states"]))
        data["phones_norm"] = list(set(data["phones_norm"]))

    index = {
        "metadata": {
            "source_db": db_path,
            "total_companies": len(comp_map),
            "total_facilities": len(facilities),
            "total_contacts": len(contacts),
            "total_relationships": len(relationships),
        },
        "companies": comp_map,
        # Global lookup sets
        "lookup": {
            "domains": {},
            "brands_norm": {},
            "legals_norm": {},
            "addresses_norm": {},
            "phones_norm": {},
        }
    }

    for cid, data in comp_map.items():
        for d in data["domains"]:
            if d:
                index["lookup"]["domains"].setdefault(d, []).append(cid)
        if data["operating_brand_norm"]:
            index["lookup"]["brands_norm"].setdefault(data["operating_brand_norm"], []).append(cid)
        if data["legal_name_norm"]:
            index["lookup"]["legals_norm"].setdefault(data["legal_name_norm"], []).append(cid)
        for a in data["facility_addresses_norm"]:
            if a:
                index["lookup"]["addresses_norm"].setdefault(a, []).append(cid)
        for p in data["phones_norm"]:
            if p:
                index["lookup"]["phones_norm"].setdefault(p, []).append(cid)

    return index

if __name__ == "__main__":
    idx = build_existing_identity_index()
    out_path = Path("reports/expansion_1000_identity_dedup.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)
    print(f"Task 2 complete: Existing identity index saved to {out_path}")
    print(f"Indexed {idx['metadata']['total_companies']} companies, {len(idx['lookup']['domains'])} domains, {len(idx['lookup']['brands_norm'])} brands, {len(idx['lookup']['phones_norm'])} phones.")
