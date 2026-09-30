import sqlite3
import json
import re
from pathlib import Path

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

companies = cur.execute("SELECT id, operating_brand, legal_name, website_url FROM companies").fetchall()
facilities = cur.execute("SELECT id, company_id, facility_name, physical_address, city, state_prov, postal_code FROM facilities").fetchall()
contacts = cur.execute("SELECT id, company_id, facility_id, person_name, phone_number, email_address FROM contacts").fetchall()

conn.close()

def clean_name(n):
    if not n:
        return ""
    s = n.lower()
    s = re.sub(r"[^a-z0-9]", "", s)
    return s

def extract_domain(u):
    if not u:
        return ""
    m = re.search(r"https?://(?:www\.)?([^/]+)", u.lower())
    return m.group(1) if m else u.lower()

existing_data = {
    "company_count": len(companies),
    "facility_count": len(facilities),
    "contact_count": len(contacts),
    "companies": [{"id": c[0], "brand": c[1], "legal": c[2], "url": c[3], "domain": extract_domain(c[3]), "clean_brand": clean_name(c[1])} for c in companies],
    "facilities": [{"id": f[0], "company_id": f[1], "name": f[2], "city": f[4], "state": f[5], "zip": f[6]} for f in facilities],
    "phones": [c[4] for c in contacts if c[4]],
    "domains": [extract_domain(c[3]) for c in companies if c[3]],
    "brands": [c[1] for c in companies]
}

Path("data/existing_entities_lookup.json").write_text(json.dumps(existing_data, indent=2))
print(f"Exported {len(companies)} companies, {len(facilities)} facilities, {len(existing_data['phones'])} contacts to data/existing_entities_lookup.json")
