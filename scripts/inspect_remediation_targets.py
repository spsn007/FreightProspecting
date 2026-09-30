import sqlite3
import json

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

print("=== CID 105 (Precision Strip) ===")
facs = conn.execute("SELECT * FROM facilities WHERE company_id = 105").fetchall()
for f in facs:
    print("FACILITY:", dict(f))
cts = conn.execute("SELECT * FROM contacts WHERE facility_id IN (SELECT id FROM facilities WHERE company_id = 105)").fetchall()
for c in cts:
    print("CONTACT:", dict(c))
srcs = conn.execute("SELECT * FROM evidence_sources WHERE source_url LIKE '%precision-strip%'").fetchall()
for s in srcs:
    print("SOURCE:", dict(s))
claims_p = conn.execute("SELECT * FROM claims WHERE facility_id IN (134) OR contact_id IN (SELECT id FROM contacts WHERE facility_id = 134)").fetchall()
for cl in claims_p:
    print("CLAIM:", dict(cl))

print("\n=== CID 91 (Worthington Steel) ===")
facs_w = conn.execute("SELECT id, company_id, facility_name, city, state_prov, commercial_carrier_use, broker_friendly_status FROM facilities WHERE company_id = 91").fetchall()
for f in facs_w:
    print("FACILITY:", dict(f))
claims_w = conn.execute("SELECT * FROM claims WHERE company_id = 91 OR facility_id IN (SELECT id FROM facilities WHERE company_id = 91)").fetchall()
for cl in claims_w:
    print("CLAIM:", dict(cl))
srcs_w = conn.execute("SELECT * FROM evidence_sources WHERE source_url LIKE '%worthington%'").fetchall()
for s in srcs_w:
    print("SOURCE:", dict(s))

print("\n=== CID 218 (Metals USA) ===")
facs_m = conn.execute("SELECT id, company_id, facility_name, city, state_prov, commercial_carrier_use, broker_friendly_status FROM facilities WHERE company_id = 218").fetchall()
for f in facs_m:
    print("FACILITY:", dict(f))
claims_m = conn.execute("SELECT * FROM claims WHERE company_id = 218 OR facility_id IN (SELECT id FROM facilities WHERE company_id = 218)").fetchall()
for cl in claims_m:
    print("CLAIM:", dict(cl))
srcs_m = conn.execute("SELECT * FROM evidence_sources WHERE source_url LIKE '%metalsusa%'").fetchall()
for s in srcs_m:
    print("SOURCE:", dict(s))
