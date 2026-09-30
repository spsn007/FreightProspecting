import sqlite3

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("""
    SELECT f.city, f.state_prov, count(DISTINCT f.company_id) as comp_cnt
    FROM facilities f
    JOIN companies c ON f.company_id = c.id
    GROUP BY f.city, f.state_prov
    HAVING comp_cnt > 1
    ORDER BY comp_cnt DESC
""")
clusters = [dict(r) for r in c.fetchall()]

print(f"Total city/state pairs with >1 company: {len(clusters)}")

potential_duplicates = []
for cl in clusters:
    city, sp = cl["city"], cl["state_prov"]
    c.execute("""
        SELECT c.id as comp_id, c.operating_brand, c.website_url, f.id as fac_id, f.facility_name, f.physical_address
        FROM facilities f
        JOIN companies c ON f.company_id = c.id
        WHERE f.city = ? AND f.state_prov = ?
    """, (city, sp))
    comps = [dict(r) for r in c.fetchall()]
    # Check if any two companies in the same city are related or similar
    for i in range(len(comps)):
        for j in range(i+1, len(comps)):
            c1, c2 = comps[i], comps[j]
            # check address match or website match or name match
            if c1["comp_id"] != c2["comp_id"]:
                potential_duplicates.append((city, sp, c1, c2))

print(f"Total pairs in same city/state: {len(potential_duplicates)}")
for city, sp, c1, c2 in potential_duplicates:
    # Print if addresses are similar or names are similar
    n1, n2 = c1["operating_brand"].lower(), c2["operating_brand"].lower()
    a1, a2 = (c1["physical_address"] or "").lower(), (c2["physical_address"] or "").lower()
    if any(w in n2 for w in n1.split() if len(w) > 4) or (a1 and a2 and a1 == a2):
        print(f"[{city}, {sp}]: Comp {c1['comp_id']} ('{c1['operating_brand']}') vs Comp {c2['comp_id']} ('{c2['operating_brand']}')")
        print(f"   Addr 1: {c1['physical_address']} | Addr 2: {c2['physical_address']}")

conn.close()
