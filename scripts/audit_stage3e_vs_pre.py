import sqlite3
import re
from urllib.parse import urlparse

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("""
    SELECT c.id, c.operating_brand, c.legal_name, c.website_url, c.corporate_address,
           f.id as facility_id, f.facility_name, f.city, f.state_prov, f.physical_address
    FROM companies c
    JOIN facilities f ON f.company_id = c.id
    ORDER BY c.id
""")
rows = c.fetchall()
conn.close()

pre_stage3e = [r for r in rows if r["id"] < 287]
stage3e = [r for r in rows if r["id"] >= 287]

print(f"Pre-Stage 3E records: {len(pre_stage3e)}")
print(f"Stage 3E records: {len(stage3e)}")

def extract_domain(url):
    if not url:
        return ""
    if not url.startswith("http"):
        url = "http://" + url
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""

def clean_name(n):
    n = n.lower()
    n = re.sub(r"[^\w\s]", "", n)
    words = [w for w in n.split() if w not in ["inc", "llc", "corp", "corporation", "ltd", "limited", "co", "company", "group", "holdings", "products", "lumber", "steel", "concrete"]]
    return " ".join(words).strip()

pre_domains = {extract_domain(r["website_url"]): r for r in pre_stage3e if extract_domain(r["website_url"])}
pre_clean_names = {clean_name(r["operating_brand"]): r for r in pre_stage3e if clean_name(r["operating_brand"])}
pre_addresses = {r["physical_address"].lower().strip(): r for r in pre_stage3e if r["physical_address"]}

print("\n--- CHECKING STAGE 3E AGAINST PRE-STAGE 3E ---")
domain_matches = []
name_matches = []
address_matches = []

for r in stage3e:
    dom = extract_domain(r["website_url"])
    if dom and dom in pre_domains:
        domain_matches.append((r, pre_domains[dom]))
    
    cn = clean_name(r["operating_brand"])
    if cn and cn in pre_clean_names:
        name_matches.append((r, pre_clean_names[cn]))
        
    addr = r["physical_address"].lower().strip()
    if addr and addr in pre_addresses:
        address_matches.append((r, pre_addresses[addr]))

print(f"Domain matches between Stage 3E and Pre-Stage 3E: {len(domain_matches)}")
for s, p in domain_matches:
    print(f"  Stage 3E: Comp {s['id']} ('{s['operating_brand']}') vs Pre: Comp {p['id']} ('{p['operating_brand']}') | Domain: {extract_domain(s['website_url'])}")

print(f"\nAddress matches between Stage 3E and Pre-Stage 3E: {len(address_matches)}")
for s, p in address_matches:
    print(f"  Stage 3E: Fac {s['facility_id']} ('{s['facility_name']}') vs Pre: Fac {p['facility_id']} ('{p['facility_name']}') | Addr: {s['physical_address']}")

print(f"\nClean name matches between Stage 3E and Pre-Stage 3E: {len(name_matches)}")
for s, p in name_matches:
    print(f"  Stage 3E: Comp {s['id']} ('{s['operating_brand']}', {s['city']}, {s['state_prov']}) vs Pre: Comp {p['id']} ('{p['operating_brand']}', {p['city']}, {p['state_prov']}) | Clean Name: '{clean_name(s['operating_brand'])}'")
