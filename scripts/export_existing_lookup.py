import json
import re
import sqlite3
from pathlib import Path

def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"\b(inc|corp|corporation|llc|ltd|co|company|group|holdings|enterprises)\b", "", text)
    return re.sub(r"[^a-z0-9]", "", text)

def export_lookup():
    conn = sqlite3.connect('data/prospects.db')
    conn.row_factory = sqlite3.Row

    companies = conn.execute("SELECT id, operating_brand, legal_name, website_url FROM companies").fetchall()
    facilities = conn.execute("SELECT id, company_id, facility_name, physical_address, city, state_prov, country FROM facilities").fetchall()
    contacts = conn.execute("SELECT id, facility_id, phone_number, email_address FROM contacts").fetchall()

    brands = {}
    normalized_brands = set()
    for c in companies:
        b = (c["operating_brand"] or "").strip().lower()
        if b:
            brands[b] = c["id"]
        nb = normalize_text(c["operating_brand"])
        if nb:
            normalized_brands.add(nb)
        nl = normalize_text(c["legal_name"])
        if nl:
            normalized_brands.add(nl)

    addresses = set()
    for f in facilities:
        addr = (f["physical_address"] or "").strip().lower()
        state = (f["state_prov"] or "").strip().lower()
        if addr and state:
            addresses.add(f"{addr}|{state}")

    phones = set()
    for con in contacts:
        p = con["phone_number"]
        if p:
            clean_p = re.sub(r"[^0-9]", "", p)
            if len(clean_p) >= 10:
                phones.add(clean_p[-10:])

    websites = set()
    for c in companies:
        u = c["website_url"]
        if u:
            dom = re.sub(r"^https?://(www\.)?", "", u.lower()).split("/")[0]
            if dom:
                websites.add(dom)

    lookup = {
        "count_companies": len(companies),
        "count_facilities": len(facilities),
        "normalized_brands": list(normalized_brands),
        "addresses": list(addresses),
        "phones": list(phones),
        "domains": list(websites)
    }

    out_path = Path("data/existing_lookup.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(lookup, f, indent=2)

    print(f"Exported lookup to {out_path}:")
    print(f"  Existing normalized brands: {len(normalized_brands)}")
    print(f"  Existing addresses: {len(addresses)}")
    print(f"  Existing phone numbers: {len(phones)}")
    print(f"  Existing domains: {len(websites)}")

if __name__ == "__main__":
    export_lookup()
