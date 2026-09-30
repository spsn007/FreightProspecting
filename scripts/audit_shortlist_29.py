import sqlite3
from pathlib import Path
from test_opportunity_engine import evaluate_company_tier

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

sl_comps = conn.execute("""
    SELECT DISTINCT c.id, c.operating_brand
    FROM companies c
    JOIN facilities f ON c.id = f.company_id
    JOIN prospect_lifecycle pl ON f.id = pl.facility_id
    WHERE pl.stage = 'SHORTLISTED'
    ORDER BY c.operating_brand
""").fetchall()

print(f"=== ALL {len(sl_comps)} SHORTLISTED COMPANIES UNDER NEW EVALUATION ===")
print(f"{'Company':<35} | {'Old Status':<18} | {'New Tier':<22} | {'Fleet':<16} | {'Carrier':<10}")
print("-" * 110)

tier_c_list = []
tier_a_list = []
tier_b_list = []

for c in sl_comps:
    cid = c["id"]
    brand = c["operating_brand"]
    eval_res = evaluate_company_tier(cid, conn)
    tier = eval_res["tier"]
    
    # Get fleet & carrier from facility
    fac = conn.execute("SELECT private_fleet_present, commercial_carrier_use FROM facilities WHERE company_id = ?", (cid,)).fetchone()
    fleet = fac["private_fleet_present"]
    carrier = fac["commercial_carrier_use"]
    
    print(f"{brand[:35]:<35} | {'Priority (Short)':<18} | {eval_res['frontend_label']:<22} | {fleet:<16} | {carrier:<10}")
    
    if tier == "TIER_A_PRIORITY":
        tier_a_list.append((brand, eval_res))
    elif tier == "TIER_C_SECONDARY":
        tier_c_list.append((brand, eval_res))
    elif tier == "TIER_B_WORTH_CALLING":
        tier_b_list.append((brand, eval_res))

print(f"\nSummary of old 29:")
print(f"  Tier A (Priority Prospect): {len(tier_a_list)}")
print(f"  Tier B (Worth Calling): {len(tier_b_list)}")
print(f"  Tier C (Secondary Prospect): {len(tier_c_list)}")

print("\n--- PRIVATE-FLEET COMPANIES IN OLD 29 ---")
for brand, res in tier_c_list:
    print(f"* {brand}:")
    print(f"    Positive: {res['positive_facts']}")
    print(f"    Counters: {res['counter_factors']}")
    print(f"    Unknowns: {res['unknowns']}")

conn.close()
