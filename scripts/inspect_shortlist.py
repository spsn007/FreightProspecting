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
        f.physical_address,
        f.commercial_carrier_use,
        f.private_fleet_present,
        f.broker_friendly_status
    FROM facilities f 
    JOIN companies c ON f.company_id = c.id 
    JOIN prospect_lifecycle pl ON f.id = pl.facility_id 
    WHERE pl.stage = 'SHORTLISTED' 
    ORDER BY c.id
''')

rows = c.fetchall()
with open('shortlist_32.txt', 'w', encoding='utf-8') as out:
    out.write(f"Total Shortlisted: {len(rows)}\n\n")
    for i, r in enumerate(rows, 1):
        c2 = conn.cursor()
        c2.execute("SELECT * FROM contacts WHERE facility_id = ? OR (company_id = ? AND facility_id IS NULL)", (r['fid'], r['cid']))
        contacts = [dict(ct) for ct in c2.fetchall()]
        ct_info = []
        for ct in contacts:
            ct_info.append(f"{ct.get('person_name') or 'NoName'} ({ct.get('exact_published_title') or 'NoTitle'}) phone={ct.get('phone_number')} ({ct.get('phone_directness')}) email={ct.get('email_address')}")
        
        c2.execute("SELECT specific_products, equipment_category, equipment_usage_status FROM facility_commodities WHERE facility_id = ?", (r['fid'],))
        comms = [dict(cm) for cm in c2.fetchall()]
        cm_str = ", ".join([f"{cm['equipment_category']}({cm['equipment_usage_status']}): {cm['specific_products']}" for cm in comms])

        out.write(f"{i}. [CID {r['cid']} | FID {r['fid']}] {r['operating_brand']}\n")
        out.write(f"   Facility: {r['facility_name']} - {r['physical_address']}, {r['city']}, {r['state_prov']}\n")
        out.write(f"   Web: {r['website_url']}\n")
        out.write(f"   Carrier={r['commercial_carrier_use']}, Fleet={r['private_fleet_present']}, BrokerFriendly={r['broker_friendly_status']}\n")
        out.write(f"   Equip/Products: {cm_str}\n")
        out.write(f"   Contacts ({len(contacts)}): {'; '.join(ct_info)}\n\n")

print("Saved shortlist_32.txt")
