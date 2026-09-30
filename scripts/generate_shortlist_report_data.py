import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from src.backend.db.queries import evaluate_broker_access_friction

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT c.id as cid, f.id as fid, c.operating_brand, f.city, f.state_prov,
           c.company_footprint_status, c.verified_operating_location_count,
           c.website_url
    FROM companies c
    JOIN facilities f ON f.company_id = c.id
    JOIN prospect_lifecycle pl ON pl.facility_id = f.id
    WHERE pl.stage = 'SHORTLISTED'
    ORDER BY c.operating_brand
""").fetchall()

print(f"Total Shortlisted: {len(rows)}")
for r in rows:
    comp = dict(conn.execute("SELECT * FROM companies WHERE id = ?", (r["cid"],)).fetchone())
    facs = [dict(x) for x in conn.execute("SELECT * FROM facilities WHERE company_id = ?", (r["cid"],)).fetchall()]
    fric = evaluate_broker_access_friction(comp, facs)
    contacts = conn.execute("SELECT person_name, exact_published_title, phone_number, phone_directness FROM contacts WHERE facility_id = ? OR company_id = ?", (r["fid"], r["cid"])).fetchall()
    
    callable_contacts = [c for c in contacts if c["phone_number"]]
    if callable_contacts:
        best_c = callable_contacts[0]
        contact_str = f"{best_c['person_name'] or 'Switchboard'} ({best_c['phone_number']}) [{best_c['phone_directness']}]"
    else:
        contact_str = "NONE"
        
    print(f"| {r['cid']} | {r['fid']} | {r['operating_brand']} | {r['city']}, {r['state_prov']} | {r['verified_operating_location_count']} loc | `{r['company_footprint_status']}` | `{fric['level']}` | {contact_str} | {r['website_url']} |")

conn.close()
