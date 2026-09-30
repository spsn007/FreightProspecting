import sqlite3

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

# Check claims for facilities 1, 2, 3, 4
for fid in [1, 2, 3, 4]:
    print(f"\n--- Claims for Facility {fid} ---")
    rows = cur.execute("""
        SELECT c.id, c.claim_field, c.claimed_value, c.verification_status, c.is_current_accepted
        FROM claims c
        WHERE c.facility_id = ?
    """, (fid,)).fetchall()
    for r in rows:
        print("  ", r)

# Check contacts for facilities 1, 2, 3, 4 and their claims
for fid in [1, 2, 3, 4]:
    print(f"\n--- Contacts for Facility {fid} ---")
    contacts = cur.execute("""
        SELECT ct.id, ct.person_name, ct.exact_published_title, ct.phone_number, ct.phone_directness
        FROM contacts ct
        WHERE ct.facility_id = ?
    """, (fid,)).fetchall()
    for ct in contacts:
        print("   Contact:", ct)
        c_claims = cur.execute("""
            SELECT c.id, c.claim_field, c.claimed_value, c.verification_status
            FROM claims c WHERE c.contact_id = ?
        """, (ct[0],)).fetchall()
        for cc in c_claims:
            print("     Claim:", cc)

# Check CSP (Facility 18) contacts
print("\n--- CSP (Facility 18) Contacts ---")
csp_contacts = cur.execute("""
    SELECT ct.id, ct.person_name, ct.exact_published_title, ct.phone_number, ct.phone_directness, ct.department, ct.email_address, ct.role_category
    FROM contacts ct
    WHERE ct.facility_id = 18
""").fetchall()
for c in csp_contacts:
    print("  CSP Contact:", c)

conn.close()
