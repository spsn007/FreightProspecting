import sqlite3

conn = sqlite3.connect('data/prospects.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute('''
    SELECT 
        c.id as cid, 
        c.operating_brand, 
        c.website_url,
        f.id as fid, 
        f.facility_name,
        f.city, 
        f.state_prov, 
        f.commercial_carrier_use, 
        f.private_fleet_present,
        (SELECT count(*) FROM contacts ct WHERE ct.facility_id = f.id AND ct.phone_number IS NOT NULL) as phone_cnt,
        (SELECT count(f2.id) FROM facilities f2 WHERE f2.company_id = c.id) as db_fac_cnt
    FROM facilities f 
    JOIN companies c ON f.company_id = c.id 
    JOIN prospect_lifecycle pl ON f.id = pl.facility_id 
    WHERE pl.stage = 'QUALIFIED' 
      AND phone_cnt > 0
      AND db_fac_cnt <= 2
    ORDER BY c.id
''')

rows = c.fetchall()
print(f"Qualified candidates with phone and <=2 facilities: {len(rows)}")
for r in rows:
    c2 = conn.cursor()
    c2.execute("SELECT person_name, exact_published_title, phone_number, phone_directness, email_address FROM contacts WHERE facility_id = ? OR (company_id = ? AND facility_id IS NULL)", (r['fid'], r['cid']))
    cts = [dict(ct) for ct in c2.fetchall()]
    ct_strs = [f"{ct['person_name']} ({ct['exact_published_title']}) {ct['phone_number']} [{ct['phone_directness']}]" for ct in cts]
    
    c2.execute("SELECT specific_products, equipment_category, equipment_usage_status FROM facility_commodities WHERE facility_id = ?", (r['fid'],))
    comms = [f"{cm['equipment_category']}: {cm['specific_products']}" for cm in c2.fetchall()]

    print(f"CID {r['cid']} | FID {r['fid']}: {r['operating_brand']} ({r['city']}, {r['state_prov']})")
    print(f"   Web: {r['website_url']}")
    print(f"   Carrier: {r['commercial_carrier_use']} | Fleet: {r['private_fleet_present']}")
    print(f"   Products: {', '.join(comms)}")
    print(f"   Contacts: {'; '.join(ct_strs)}")
    print()
