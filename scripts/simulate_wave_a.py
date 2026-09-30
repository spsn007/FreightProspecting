import sqlite3
import shutil
from pathlib import Path
from src.backend.db.opportunity import evaluate_broker_opportunity
from src.backend.db.queries import get_universe_metadata

# Copy DB to temp file
shutil.copyfile("data/prospects.db", "data/test_temp.db")
conn = sqlite3.connect("data/test_temp.db")
conn.row_factory = sqlite3.Row

# Mutate CID 23
conn.execute("""
    UPDATE facilities 
    SET commercial_carrier_use = 'VERIFIED',
        private_fleet_present = 'VERIFIED_PRESENT',
        fleet_relationship_type = 'IN_HOUSE_OWNED'
    WHERE id = 22
""")

# Mutate CID 3
conn.execute("""
    UPDATE facilities
    SET private_fleet_present = 'VERIFIED_PRESENT',
        fleet_relationship_type = 'IN_HOUSE_OWNED'
    WHERE id = 3
""")

# Mutate CID 60
conn.execute("""
    UPDATE facilities
    SET private_fleet_present = 'VERIFIED_PRESENT',
        fleet_relationship_type = 'AFFILIATED_CARRIER_ENTITY'
    WHERE id = 65
""")

conn.commit()

print("--- Opportunity Tiers after simulated mutations ---")
for cid in [23, 3, 60, 49]:
    res = evaluate_broker_opportunity(cid, conn=conn)
    print(f"CID {cid}: New Tier = {res['opportunity_tier']} ({res['frontend_label']})")
    print(f"  Reason codes: {res['reason_codes']}")
    print(f"  Positive facts: {res['positive_facts']}")
    print(f"  Unknowns: {res['unknowns']}")

meta = get_universe_metadata(conn=conn)
print("\nUniverse metadata opportunity counts:")
print(meta["opportunity_counts"])

conn.close()
Path("data/test_temp.db").unlink(missing_ok=True)
