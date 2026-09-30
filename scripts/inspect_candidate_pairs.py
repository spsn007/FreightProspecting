import sqlite3

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

pairs = [
    (13, 67, "Jordan"),
    (48, 204, "Interfor/Eacom"),
    (83, 206, "Groupe Lebel/Bois Daaquam"),
    (98, 106, "Russel Metals/Acier Leroux"),
    (79, 203, "Resolute/Domtar"),
    (61, 193, "Boise Cascade/Coastal Forest"),
]

for c1, c2, label in pairs:
    print(f"\n=== PAIR: {label} (Comp {c1} vs Comp {c2}) ===")
    c.execute("SELECT id, operating_brand, legal_name, corporate_address, website_url FROM companies WHERE id IN (?, ?)", (c1, c2))
    for comp in c.fetchall():
        print(f"Company {comp['id']}: '{comp['operating_brand']}' | Legal: '{comp['legal_name']}' | Addr: '{comp['corporate_address']}' | Web: {comp['website_url']}")
        c.execute("SELECT id, facility_name, city, state_prov, physical_address FROM facilities WHERE company_id = ?", (comp["id"],))
        for fac in c.fetchall():
            print(f"   Facility {fac['id']}: '{fac['facility_name']}' in {fac['city']}, {fac['state_prov']} ({fac['physical_address']})")

conn.close()
