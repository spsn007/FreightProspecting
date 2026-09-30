import sys
sys.path.insert(0, '.')
import sqlite3
from src.backend.db.queries import create_connection, evaluate_broker_access_friction, get_db_path

conn = create_connection(get_db_path())
conn.row_factory = sqlite3.Row

rows = conn.execute('''
    SELECT c.*, f.id as fid 
    FROM facilities f 
    JOIN companies c ON f.company_id = c.id 
    JOIN prospect_lifecycle pl ON pl.facility_id = f.id 
    WHERE pl.stage = 'SHORTLISTED' 
    ORDER BY c.id
''').fetchall()

print(f"Total Shortlisted: {len(rows)}")
for r in rows:
    c_dict = dict(r)
    f_rows = conn.execute("SELECT * FROM facilities WHERE company_id = ?", (r["id"],)).fetchall()
    facs = [dict(f) for f in f_rows]
    for f in facs:
        f_cts = conn.execute("SELECT * FROM contacts WHERE facility_id = ?", (f["id"],)).fetchall()
        f["contacts"] = [dict(ct) for ct in f_cts]
    friction = evaluate_broker_access_friction(c_dict, facs)
    print(f"CID {r['id']}: {r['operating_brand']} -> Friction: {friction['level']} | Footprint: {r['company_footprint_status']} ({r['verified_operating_location_count']} loc) | Reasons: {friction['reasons']}")

conn.close()
