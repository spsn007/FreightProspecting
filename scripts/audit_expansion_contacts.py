import sqlite3
import sys
sys.path.insert(0, '.')
from src.backend.db.connection import create_connection

conn = create_connection('data/prospects.db')
conn.row_factory = sqlite3.Row

rows = conn.execute('''
    SELECT c.id as contact_id, comp.id as comp_id, comp.operating_brand, comp.website_url,
           f.physical_address, f.city, f.state_prov, f.country,
           c.phone_number, c.department, c.contact_identity, c.role_category, c.phone_directness,
           fc.equipment_category, fc.equipment_usage_status, fc.specific_products,
           es.source_url, es.source_title_publisher
    FROM companies comp
    JOIN facilities f ON f.company_id = comp.id
    JOIN contacts c ON c.facility_id = f.id
    JOIN facility_commodities fc ON fc.facility_id = f.id
    JOIN claims cl ON cl.contact_id = c.id
    JOIN claim_evidence ce ON ce.claim_id = cl.id
    JOIN evidence_sources es ON ce.evidence_source_id = es.id
    WHERE comp.id > 567
    ORDER BY comp.id ASC
''').fetchall()

print(f"Total new companies retrieved: {len(rows)}")

# Let's inspect distribution of departments
depts = {}
for r in rows:
    depts[r['department']] = depts.get(r['department'], 0) + 1
print(f"Department distribution: {depts}")

# Let's inspect distribution of phone_directness
directness = {}
for r in rows:
    directness[r['phone_directness']] = directness.get(r['phone_directness'], 0) + 1
print(f"Phone directness distribution: {directness}")

# Let's print 15 diverse samples across the dataset
step = len(rows) // 15
for i in range(0, len(rows), step):
    r = rows[i]
    print(f"[{i}] ID {r['comp_id']}: {r['operating_brand']} ({r['city']}, {r['state_prov']} {r['country']}) | Phone: {r['phone_number']} | Dept: {r['department']} | Equip: {r['equipment_category']} ({r['equipment_usage_status']}) | Prod: {r['specific_products'][:40]} | URL: {r['website_url']}")

conn.close()
