import sqlite3

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row
p_cids = [6, 42, 19, 26, 18, 25, 16, 17, 21]
for cid in p_cids:
    brand = conn.execute("SELECT operating_brand FROM companies WHERE id = ?", (cid,)).fetchone()[0]
    fac = conn.execute("SELECT private_fleet_present, commercial_carrier_use FROM facilities WHERE company_id = ?", (cid,)).fetchone()
    contacts = conn.execute("""
        SELECT person_name, department, exact_published_title, role_category, phone_directness, phone_number, email_address 
        FROM contacts 
        WHERE company_id = ? OR facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
    """, (cid, cid)).fetchall()
    print(f"CoID {cid}: {brand}")
    print(f"  Fleet: {fac['private_fleet_present']}, Carrier: {fac['commercial_carrier_use']}")
    for ct in contacts:
        name = ct['person_name'] or ct['department'] or ct['exact_published_title']
        print(f"  Contact: {name}, Role: {ct['role_category']}, Dir: {ct['phone_directness']}, Phone: {ct['phone_number']}")
conn.close()
