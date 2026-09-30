import sqlite3
import re
from urllib.parse import urlparse
from difflib import SequenceMatcher

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("""
    SELECT c.id, c.operating_brand, c.legal_name, c.website_url, c.corporate_address,
           f.id as facility_id, f.facility_name, f.physical_address, f.city, f.state_prov, f.postal_code,
           ct.phone_number, ct.email_address
    FROM companies c
    LEFT JOIN facilities f ON f.company_id = c.id
    LEFT JOIN contacts ct ON ct.facility_id = f.id OR ct.company_id = c.id
    ORDER BY c.id
""")
rows = c.fetchall()
conn.close()

# Group by company
companies = {}
for r in rows:
    cid = r["id"]
    if cid not in companies:
        companies[cid] = {
            "id": cid,
            "operating_brand": r["operating_brand"] or "",
            "legal_name": r["legal_name"] or "",
            "website_url": r["website_url"] or "",
            "corporate_address": r["corporate_address"] or "",
            "facilities": {},
            "phones": set(),
            "emails": set(),
        }
    fid = r["facility_id"]
    if fid and fid not in companies[cid]["facilities"]:
        companies[cid]["facilities"][fid] = {
            "id": fid,
            "facility_name": r["facility_name"] or "",
            "physical_address": r["physical_address"] or "",
            "city": r["city"] or "",
            "state_prov": r["state_prov"] or "",
            "postal_code": r["postal_code"] or "",
        }
    if r["phone_number"]:
        clean_p = re.sub(r"\D", "", r["phone_number"])
        if len(clean_p) >= 10:
            companies[cid]["phones"].add(clean_p[-10:])
    if r["email_address"]:
        companies[cid]["emails"].add(r["email_address"].lower().strip())

# Normalization helper
SUFFIXES = [
    r"\binc\b\.?", r"\bincorporated\b", r"\bllc\b\.?", r"\bl\.l\.c\b\.?", r"\bcorp\b\.?", r"\bcorporation\b",
    r"\bltd\b\.?", r"\blimited\b", r"\bco\b\.?", r"\bcompany\b", r"\bgroup\b", r"\bholdings\b",
    r"\benterprises\b", r"\bindustries\b", r"\bproducts\b", r"\bsolutions\b", r"\bservices\b",
    r"\bmanufacturing\b", r"\bmfg\b\.?", r"\bintl\b\.?", r"\binternational\b", r"\btechnologies\b",
    r"\btech\b\.?", r"\bcanada\b", r"\busa\b", r"\bus\b"
]

def normalize_name(name):
    n = name.lower()
    n = re.sub(r"[^\w\s]", " ", n)
    for s in SUFFIXES:
        n = re.sub(s, " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n

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

# 1. Check exact normalized name collisions
norm_map = {}
for cid, data in companies.items():
    norm = normalize_name(data["operating_brand"])
    if norm:
        norm_map.setdefault(norm, []).append(cid)

print("=== 1. EXACT NORMALIZED NAME COLLISIONS ===")
norm_collisions = {k: v for k, v in norm_map.items() if len(v) > 1}
for norm, cids in norm_collisions.items():
    print(f"Normalized Name '{norm}':")
    for cid in cids:
        fac_locs = [f"{f['city']}, {f['state_prov']}" for f in companies[cid]['facilities'].values()]
        print(f"  Company {cid}: '{companies[cid]['operating_brand']}' | Website: {companies[cid]['website_url']} | Facs: {fac_locs}")

# 2. Check domain collisions
domain_map = {}
for cid, data in companies.items():
    dom = extract_domain(data["website_url"])
    if dom and dom not in ["linkedin.com", "facebook.com", "manta.com", "yellowpages.com"]:
        domain_map.setdefault(dom, []).append(cid)

print("\n=== 2. DOMAIN COLLISIONS ===")
domain_collisions = {k: v for k, v in domain_map.items() if len(v) > 1}
for dom, cids in domain_collisions.items():
    print(f"Domain '{dom}':")
    for cid in cids:
        fac_locs = [f"{f['city']}, {f['state_prov']}" for f in companies[cid]['facilities'].values()]
        print(f"  Company {cid}: '{companies[cid]['operating_brand']}' | Facs: {fac_locs}")

# 3. Check Phone Collisions
phone_map = {}
for cid, data in companies.items():
    for p in data["phones"]:
        if len(p) >= 10:  # standard US/CA phone
            phone_map.setdefault(p, []).append(cid)

print("\n=== 3. PHONE NUMBER COLLISIONS ===")
phone_collisions = {k: v for k, v in phone_map.items() if len(v) > 1}
for p, cids in phone_collisions.items():
    print(f"Phone '{p}':")
    for cid in cids:
        fac_locs = [f"{f['city']}, {f['state_prov']}" for f in companies[cid]['facilities'].values()]
        print(f"  Company {cid}: '{companies[cid]['operating_brand']}' | Facs: {fac_locs}")

# 4. Check Facility Physical Address collisions across different companies
addr_map = {}
for cid, data in companies.items():
    for fid, f in data["facilities"].items():
        addr = f["physical_address"].lower().strip()
        city = f["city"].lower().strip()
        state = f["state_prov"].lower().strip()
        if addr and len(addr) > 5:
            key = f"{addr}|{city}|{state}"
            addr_map.setdefault(key, []).append((cid, fid))

print("\n=== 4. FACILITY ADDRESS COLLISIONS ACROSS COMPANIES ===")
addr_collisions = {k: v for k, v in addr_map.items() if len(set(cid for cid, _ in v)) > 1}
for key, pairs in addr_collisions.items():
    print(f"Address '{key}':")
    for cid, fid in pairs:
        print(f"  Company {cid} ('{companies[cid]['operating_brand']}'), Facility {fid}")

# 5. Fuzzy Name Similarity (SequenceMatcher >= 0.88 on normalized names)
print("\n=== 5. HIGH FUZZY NAME SIMILARITY (>= 0.88) ===")
cids = sorted(companies.keys())
fuzzy_pairs = []
for i in range(len(cids)):
    cid1 = cids[i]
    n1 = normalize_name(companies[cid1]["operating_brand"])
    if len(n1) < 4:
        continue
    for j in range(i + 1, len(cids)):
        cid2 = cids[j]
        n2 = normalize_name(companies[cid2]["operating_brand"])
        if len(n2) < 4:
            continue
        # If identical, already caught
        if n1 == n2:
            continue
        sim = SequenceMatcher(None, n1, n2).ratio()
        if sim >= 0.88:
            fuzzy_pairs.append((sim, cid1, cid2, n1, n2))

fuzzy_pairs.sort(reverse=True, key=lambda x: x[0])
for sim, cid1, cid2, n1, n2 in fuzzy_pairs[:30]:
    c1 = companies[cid1]
    c2 = companies[cid2]
    print(f"Sim {sim:.2f}: Company {cid1} ('{c1['operating_brand']}', {c1['website_url']}) vs Company {cid2} ('{c2['operating_brand']}', {c2['website_url']})")
