import sqlite3
from pathlib import Path

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

# Query the facilities with verified fleet or carrier use
query = """
SELECT c.id, c.operating_brand, pl.stage,
       f.id as facility_id, f.facility_name, f.private_fleet_present, f.fleet_relationship_type, f.commercial_carrier_use, f.broker_friendly_status,
       f.city, f.state_prov
FROM companies c
JOIN facilities f ON c.id = f.company_id
LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
WHERE f.private_fleet_present = 'VERIFIED_PRESENT' OR f.commercial_carrier_use = 'VERIFIED'
ORDER BY f.commercial_carrier_use DESC, f.private_fleet_present DESC, c.operating_brand
"""
rows = conn.execute(query).fetchall()

print(f"=== {len(rows)} FACILITIES WITH VERIFIED FLEET OR CARRIER USE ===")
for r in rows:
    print(f"CoID: {r['id']}, FacID: {r['facility_id']}, Brand: {r['operating_brand']}, Stage: {r['stage']}, Fleet: {r['private_fleet_present']}, Rel: {r['fleet_relationship_type']}, Carrier: {r['commercial_carrier_use']}, City: {r['city']}, {r['state_prov']}")

# Now query all 29 shortlisted facilities/companies
print("\n=== ALL 29 SHORTLISTED FACILITIES / COMPANIES ===")
sl_query = """
SELECT c.id, c.operating_brand, pl.stage,
       f.id as facility_id, f.facility_name, f.private_fleet_present, f.commercial_carrier_use, f.broker_friendly_status,
       f.city, f.state_prov
FROM companies c
JOIN facilities f ON c.id = f.company_id
JOIN prospect_lifecycle pl ON f.id = pl.facility_id
WHERE pl.stage = 'SHORTLISTED'
ORDER BY c.operating_brand
"""
sl_rows = conn.execute(sl_query).fetchall()
print(f"Total Shortlisted Facilities: {len(sl_rows)}")
for r in sl_rows:
    print(f"CoID: {r['id']}, FacID: {r['facility_id']}, Brand: {r['operating_brand']}, Fleet: {r['private_fleet_present']}, Carrier: {r['commercial_carrier_use']}, Loc: {r['city']}, {r['state_prov']}")

conn.close()
