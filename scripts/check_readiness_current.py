import sys
sys.path.insert(0, ".")
import sqlite3
from src.backend.db.queries import evaluate_qualification_readiness

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

# Check currently evaluated readiness
lifecycle_rows = conn.execute("""
    SELECT pl.facility_id, pl.stage, f.facility_name, c.operating_brand
    FROM prospect_lifecycle pl
    JOIN facilities f ON pl.facility_id = f.id
    JOIN companies c ON f.company_id = c.id
""").fetchall()

print(f"Total lifecycle rows: {len(lifecycle_rows)}")
stages = {}
for r in lifecycle_rows:
    stages[r["stage"]] = stages.get(r["stage"], 0) + 1
print("Current lifecycle counts in DB:", stages)

# Evaluate each facility
ready_by_stage = {"SHORTLISTED": 0, "QUALIFIED": 0, "DISCOVERY": 0}
not_ready_by_stage = {"SHORTLISTED": [], "QUALIFIED": [], "DISCOVERY": []}

for r in lifecycle_rows:
    fid = r["facility_id"]
    stg = r["stage"]
    res = evaluate_qualification_readiness(fid, conn=conn)
    if res["is_ready"]:
        ready_by_stage[stg] = ready_by_stage.get(stg, 0) + 1
    else:
        not_ready_by_stage[stg].append((fid, r["operating_brand"], r["facility_name"], [k for k, v in res["checks"].items() if not v["passed"]]))

print("\n--- Current Evaluator Results ---")
print("Ready by stage:", ready_by_stage)
print("Not ready counts by stage:", {k: len(v) for k, v in not_ready_by_stage.items()})

if not_ready_by_stage["SHORTLISTED"]:
    print("\nShortlisted not ready under current evaluator:")
    for nr in not_ready_by_stage["SHORTLISTED"]:
        print(" ", nr)

if not_ready_by_stage["QUALIFIED"]:
    print(f"\nQualified not ready under current evaluator (first 10 of {len(not_ready_by_stage['QUALIFIED'])}):")
    for nr in not_ready_by_stage["QUALIFIED"][:10]:
        print(" ", nr)

conn.close()
