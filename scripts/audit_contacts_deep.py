import sqlite3

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("""
    SELECT ct.*, f.facility_name, comp.operating_brand, comp.website_url
    FROM contacts ct
    JOIN facilities f ON ct.facility_id = f.id
    JOIN companies comp ON f.company_id = comp.id
    WHERE ct.id >= 383
    ORDER BY ct.id
""")
rows = [dict(r) for r in c.fetchall()]
conn.close()

print(f"Total Stage 3E contacts: {len(rows)}")

freight_keywords = ["ship", "traffic", "logist", "freight", "transport", "dispatch"]

special_contacts = []
for r in rows:
    em = (r["email_address"] or "").lower()
    pn = (r["person_name"] or "")
    has_freight_email = any(k in em for k in freight_keywords)
    is_real_name = False
    if pn:
        generic_terms = ["manager", "coordinator", "lead", "operations", "dept", "supervisor", "director", "desk", "office"]
        if not any(g in pn.lower() for g in generic_terms):
            is_real_name = True
    if has_freight_email or is_real_name:
        special_contacts.append(r)

print(f"Contacts with freight email or possible real person name: {len(special_contacts)}")
for r in special_contacts:
    print(f"ID {r['id']}: {r['operating_brand']} | Email: {r['email_address']} | Person: {r['person_name']} | Dept: {r['department']}")
