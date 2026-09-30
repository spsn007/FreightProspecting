import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import sqlite3

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

keywords = [
    "pallet", "roofing", "pipe", "conduit", "fence", "truss",
    "shed", "machinery", "hvac", "box", "packaging", "drum", "container",
    "paver", "mulch", "pellet", "firewood"
]

for kw in keywords:
    rows = conn.execute("""
        SELECT fc.id, fc.facility_id, c.operating_brand, fc.commodity_category, fc.specific_products
        FROM facility_commodities fc
        JOIN facilities f ON fc.facility_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE lower(fc.commodity_category) LIKE ? OR lower(fc.specific_products) LIKE ?
    """, (f"%{kw}%", f"%{kw}%")).fetchall()
    if rows:
        print(f"=== Keyword: {kw} ({len(rows)} matches) ===")
        for r in rows:
            print(f"  FID {r['facility_id']} ({r['operating_brand']}) | {r['commodity_category']} | {r['specific_products']}")

conn.close()
