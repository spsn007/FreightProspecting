import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
from src.backend.db.queries import evaluate_qualification_readiness

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

# 1. Bush Concrete Products (CID 128, FID 157)
print("=== Bush Concrete Products (CID 128) ===")
fac128 = conn.execute("SELECT * FROM facilities WHERE company_id = 128").fetchall()
print(f"Facilities count: {len(fac128)}")
for f in fac128:
    print(f"  FID {f['id']}: {f['facility_name']} | {f['city']}, {f['state_prov']} | Carrier={f['commercial_carrier_use']}")
    q = evaluate_qualification_readiness(f['id'], conn=conn)
    print(f"  Qualification: is_ready={q['is_ready']}")

# 2. Challenger Pallet (CID 540, FID 627)
print("\n=== Challenger Pallet (CID 540) ===")
comm540 = conn.execute("SELECT * FROM facility_commodities WHERE facility_id = 627").fetchall()
print("Commodities:", [dict(c) for c in comm540])
cts540 = conn.execute("SELECT * FROM contacts WHERE facility_id = 627").fetchall()
print("Contacts:", [dict(c) for c in cts540])
clms540 = conn.execute("SELECT * FROM claims WHERE facility_id = 627").fetchall()
print("Claims:", [(c['id'], c['claim_field'], c['claimed_value'], c['verification_status']) for c in clms540])

# 3. Cascade Engineering (CID 40, FID 39)
print("\n=== Cascade Engineering (CID 40) ===")
comm40 = conn.execute("SELECT * FROM facility_commodities WHERE facility_id = 39").fetchall()
print("Commodities:", [dict(c) for c in comm40])
clms40 = conn.execute("SELECT * FROM claims WHERE facility_id = 39").fetchall()
print("Claims:", [(c['id'], c['claim_field'], c['claimed_value'], c['verification_status']) for c in clms40])
