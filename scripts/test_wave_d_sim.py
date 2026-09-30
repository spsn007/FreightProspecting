import sqlite3
import shutil
from pathlib import Path
from src.backend.db.opportunity import evaluate_broker_opportunity
from src.backend.db.queries import get_universe_metadata

shutil.copyfile("data/prospects.db", "data/test_temp_d.db")
conn = sqlite3.connect("data/test_temp_d.db")
conn.row_factory = sqlite3.Row

# Test Steel Dynamics (CID 219)
conn.execute("""
    UPDATE facilities 
    SET broker_friendly_status = 'VERIFIED_DIRECT_ONLY',
        commercial_carrier_use = 'VERIFIED'
    WHERE id = 266
""")

# Test Peerless Steel (CID 395)
conn.execute("""
    UPDATE facilities 
    SET private_fleet_present = 'VERIFIED_PRESENT',
        fleet_relationship_type = 'IN_HOUSE_OWNED',
        commercial_carrier_use = 'VERIFIED'
    WHERE id = 482
""")

conn.commit()

sd_opp = evaluate_broker_opportunity(219, conn=conn)
print("Steel Dynamics Tier:", sd_opp["opportunity_tier"], sd_opp["frontend_label"])
print("  Reason codes:", sd_opp["reason_codes"])

ps_opp = evaluate_broker_opportunity(395, conn=conn)
print("Peerless Steel Tier:", ps_opp["opportunity_tier"], ps_opp["frontend_label"])
print("  Reason codes:", ps_opp["reason_codes"])
print("  Positive facts:", ps_opp["positive_facts"])

meta = get_universe_metadata(conn=conn)
print("\nOpportunity counts after Wave D simulation:")
print(meta["opportunity_counts"])

conn.close()
Path("data/test_temp_d.db").unlink(missing_ok=True)
