import sqlite3
from pathlib import Path

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

for cid in [42, 26, 25, 40]:
    comp = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()
    facs = conn.execute("SELECT * FROM facilities WHERE company_id = ?", (cid,)).fetchall()
    contacts = conn.execute("""
        SELECT * FROM contacts 
        WHERE company_id = ? OR facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
    """, (cid, cid)).fetchall()
    comms = conn.execute("""
        SELECT * FROM facility_commodities 
        WHERE facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
    """, (cid,)).fetchall()
    lc = conn.execute("""
        SELECT * FROM prospect_lifecycle 
        WHERE facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
    """, (cid,)).fetchall()
    print(f"=== Company {cid}: {comp['operating_brand']} ===")
    print(f"Lifecycle: {[l['stage'] for l in lc]}")
    print(f"Facilities: {len(facs)}")
    for f in facs:
        print(f"  Fac {f['id']}: {f['facility_name']}, {f['city']}, {f['state_prov']}, Fleet: {f['private_fleet_present']}, Carrier: {f['commercial_carrier_use']}")
    print(f"Commodities: {[c['equipment_category'] for c in comms]}")
    print(f"Contacts: {len(contacts)}")
    for ct in contacts:
        name = ct['person_name'] or ct['department'] or ct['contact_identity']
        print(f"  Contact {ct['id']}: {name}, Role: {ct['role_category']}, Phone: {ct['phone_number']}, Dir: {ct['phone_directness']}, Email: {ct['email_address']}")
    print()

conn.close()
