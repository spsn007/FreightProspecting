import sys
sys.path.insert(0, ".")
import sqlite3
from pathlib import Path
from src.backend.db.queries import evaluate_qualification_readiness

DB_PATH = Path("data/prospects.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get all Shortlisted facilities
shortlisted_facs = cur.execute("""
    SELECT f.id as facility_id, f.facility_name, f.company_id, c.operating_brand
    FROM facilities f
    JOIN companies c ON f.company_id = c.id
    JOIN prospect_lifecycle pl ON f.id = pl.facility_id
    WHERE pl.stage = 'SHORTLISTED'
    ORDER BY f.id
""").fetchall()

# Get all Qualified facilities
qualified_facs = cur.execute("""
    SELECT f.id as facility_id, f.facility_name, f.company_id, c.operating_brand
    FROM facilities f
    JOIN companies c ON f.company_id = c.id
    JOIN prospect_lifecycle pl ON f.id = pl.facility_id
    WHERE pl.stage = 'QUALIFIED'
    ORDER BY f.id
""").fetchall()

# conn will be closed at end of script

print("=" * 80)
print(f"1D. QUALIFICATION READINESS IMPACT ANALYSIS")
print("=" * 80)

# Evaluate Shortlisted
shortlist_pass = []
shortlist_fail = []

for fac in shortlisted_facs:
    res = evaluate_qualification_readiness(fac["facility_id"], conn=conn)
    if res["is_ready"]:
        shortlist_pass.append((fac, res))
    else:
        shortlist_fail.append((fac, res))

print(f"\nSHORTLISTED FACILITIES: Total = {len(shortlisted_facs)}")
print(f"  PASS: {len(shortlist_pass)}")
print(f"  FAIL/UNKNOWN: {len(shortlist_fail)}")

if shortlist_fail:
    print("\n  Shortlist Failures:")
    for fac, res in shortlist_fail:
        failed_gates = [g for g, v in res.get("gates", {}).items() if not v.get("passed")]
        print(f"    - Facility {fac['facility_id']} ({fac['operating_brand']} - {fac['facility_name']}):")
        for g in failed_gates:
            print(f"        Failed Gate: {g} -> {res['gates'][g].get('reason')}")

# Evaluate Qualified
qual_pass = []
qual_fail = []

for fac in qualified_facs:
    res = evaluate_qualification_readiness(fac["facility_id"], conn=conn)
    if res["is_ready"]:
        qual_pass.append((fac, res))
    else:
        qual_fail.append((fac, res))

print(f"\nQUALIFIED FACILITIES: Total = {len(qualified_facs)}")
print(f"  PASS: {len(qual_pass)}")
print(f"  FAIL/UNKNOWN: {len(qual_fail)}")

if qual_fail:
    print(f"\n  Qualified Failures (first 20 of {len(qual_fail)}):")
    for fac, res in qual_fail[:20]:
        failed_gates = [g for g, v in res.get("gates", {}).items() if not v.get("passed")]
        print(f"    - Facility {fac['facility_id']} (Comp {fac['company_id']} {fac['operating_brand']} - {fac['facility_name']}):")
        for g in failed_gates:
            print(f"        Failed Gate: {g} -> {res['gates'][g].get('reason')}")

# Also evaluate unique companies
print("\n" + "-" * 40)
print("COMPANY-LEVEL READINESS BREAKDOWN:")
# Group by company
def eval_company_level(fac_list):
    comp_map = {}
    for fac in fac_list:
        cid = fac["company_id"]
        if cid not in comp_map:
            comp_map[cid] = {"brand": fac["operating_brand"], "facs": []}
        res = evaluate_qualification_readiness(fac["facility_id"], conn=conn)
        comp_map[cid]["facs"].append((fac["facility_id"], res["is_ready"], res))
    
    comp_pass = 0
    comp_fail = 0
    for cid, info in comp_map.items():
        # A company passes if at least one facility is ready (or all facilities?)
        # Let's check both
        any_ready = any(f[1] for f in info["facs"])
        all_ready = all(f[1] for f in info["facs"])
        if any_ready:
            comp_pass += 1
        else:
            comp_fail += 1
    return len(comp_map), comp_pass, comp_fail

s_tot, s_cpass, s_cfail = eval_company_level(shortlisted_facs)
print(f"Shortlisted Companies (total {s_tot}): PASS={s_cpass}, FAIL={s_cfail}")

q_tot, q_cpass, q_cfail = eval_company_level(qualified_facs)
print(f"Qualified Companies (total {q_tot}): PASS={q_cpass}, FAIL={q_cfail}")
