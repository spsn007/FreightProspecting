import sqlite3
import re
from urllib.parse import urlparse
from difflib import SequenceMatcher

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("""
    SELECT c.id, c.operating_brand, c.legal_name, c.website_url, c.corporate_address,
           f.id as facility_id, f.facility_name, f.city, f.state_prov, f.physical_address
    FROM companies c
    JOIN facilities f ON f.company_id = c.id
    WHERE c.id >= 287
    ORDER BY c.id
""")
rows = c.fetchall()
conn.close()

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

# Check domain collisions within Stage 3E
domains = {}
for r in rows:
    dom = extract_domain(r["website_url"])
    if dom:
        domains.setdefault(dom, []).append(r)

dom_dups = {k: v for k, v in domains.items() if len(v) > 1}
print(f"Domain collisions within Stage 3E: {len(dom_dups)}")
for dom, entries in dom_dups.items():
    print(f"  Domain: {dom}")
    for e in entries:
        print(f"    Comp {e['id']}: '{e['operating_brand']}' ({e['city']}, {e['state_prov']})")

# Check clean name collisions within Stage 3E
names = {}
for r in rows:
    cn = clean_name(r["operating_brand"])
    if cn:
        names.setdefault(cn, []).append(r)

name_dups = {k: v for k, v in names.items() if len(v) > 1}
print(f"\nClean name collisions within Stage 3E: {len(name_dups)}")
for cn, entries in name_dups.items():
    print(f"  Clean Name: '{cn}'")
    for e in entries:
        print(f"    Comp {e['id']}: '{e['operating_brand']}' ({e['city']}, {e['state_prov']})")

# Check address collisions within Stage 3E
addrs = {}
for r in rows:
    addr = r["physical_address"].lower().strip()
    if addr:
        addrs.setdefault(addr, []).append(r)

addr_dups = {k: v for k, v in addrs.items() if len(v) > 1}
print(f"\nAddress collisions within Stage 3E: {len(addr_dups)}")
for addr, entries in addr_dups.items():
    print(f"  Address: {addr}")
    for e in entries:
        print(f"    Comp {e['id']}: '{e['operating_brand']}' ({e['city']}, {e['state_prov']})")

# Fuzzy similarity >= 0.82 within Stage 3E
print(f"\nFuzzy similarity >= 0.82 within Stage 3E:")
for i in range(len(rows)):
    for j in range(i+1, len(rows)):
        c1 = clean_name(rows[i]["operating_brand"])
        c2 = clean_name(rows[j]["operating_brand"])
        if len(c1) < 4 or len(c2) < 4:
            continue
        sim = SequenceMatcher(None, c1, c2).ratio()
        if sim >= 0.82:
            print(f"  Sim {sim:.2f}: Comp {rows[i]['id']} ('{rows[i]['operating_brand']}', {rows[i]['city']}) vs Comp {rows[j]['id']} ('{rows[j]['operating_brand']}', {rows[j]['city']})")
