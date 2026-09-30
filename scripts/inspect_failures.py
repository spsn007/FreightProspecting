import sqlite3, csv

conn = sqlite3.connect('file:data/prospects.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

with open('D:/FreightProspecting-Audit/closure_qualification_failures.csv') as f:
    rows = list(csv.DictReader(f))

print(f"Total failures in CSV: {len(rows)}")
for r in rows:
    fid = int(r['facility_id'])
    brand = r['operating_brand']
    gate = r['failed_or_unknown_gate']
    if 'equipment' in gate:
        cur.execute('''
            SELECT c.id as claim_id, c.claimed_value, c.verification_status, ce.id as ce_id,
                   ce.evidence_source_id, ce.relationship, s.source_type, s.source_title_publisher, s.is_primary_source,
                   fc.equipment_category, fc.equipment_usage_status, fc.commodity_category, fc.specific_products
            FROM claims c 
            JOIN claim_evidence ce ON c.id = ce.claim_id 
            JOIN evidence_sources s ON ce.evidence_source_id = s.id 
            JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
            WHERE c.claim_field = 'equipment_category' 
              AND fc.facility_id = ?
        ''', (fid,))
        res = cur.fetchall()
        for x in res:
            print(f"Fac {fid} ({brand}): Claim {x['claim_id']} val={x['claimed_value']} stat={x['verification_status']} CE={x['ce_id']} rel={x['relationship']} src={x['evidence_source_id']} ({x['source_title_publisher']}, primary={x['is_primary_source']}) FC equip={x['equipment_category']} ({x['commodity_category']}: {x['specific_products'][:30]}...)")
conn.close()
