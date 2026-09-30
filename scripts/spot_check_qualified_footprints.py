import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
from src.backend.db.queries import evaluate_broker_access_friction

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

# Get 20 qualified companies
rows = conn.execute("""
    SELECT c.id, c.operating_brand, c.company_footprint_status, c.verified_operating_location_count,
           COUNT(f.id) as db_fac_count
    FROM companies c
    JOIN facilities f ON f.company_id = c.id
    JOIN prospect_lifecycle pl ON pl.facility_id = f.id
    WHERE pl.stage = 'QUALIFIED'
    GROUP BY c.id
    ORDER BY c.id
    LIMIT 20
""").fetchall()

print(f"Spot-checking {len(rows)} Qualified companies:")
print(f"{'Brand':<35} | {'DB Fac':<6} | {'Footprint Status':<20} | {'Locs':<5} | {'Friction':<8}")
print("-" * 85)

for r in rows:
    comp = dict(conn.execute("SELECT * FROM companies WHERE id = ?", (r["id"],)).fetchone())
    facs = [dict(x) for x in conn.execute("SELECT * FROM facilities WHERE company_id = ?", (r["id"],)).fetchall()]
    friction = evaluate_broker_access_friction(comp, facs)
    
    brand = r["operating_brand"][:34]
    db_fac = r["db_fac_count"]
    fp_stat = r["company_footprint_status"] or "UNKNOWN"
    locs = str(r["verified_operating_location_count"] or "-")
    fric_lvl = friction["level"]
    
    # Assert invariant: if footprint is UNKNOWN and db_fac == 1, friction should NOT say 'Single independent shipping facility'
    if fp_stat == "UNKNOWN" and db_fac == 1:
        assert not any("Single independent shipping facility" in reason for reason in friction["reasons"]), (
            f"Violation for {brand}: assumed single site without verification! Reasons: {friction['reasons']}"
        )
    
    print(f"{brand:<35} | {db_fac:<6} | {fp_stat:<20} | {locs:<5} | {fric_lvl:<8}")

print("\nAll 20 spot-checks passed! No false single-site assumptions detected.")
conn.close()
