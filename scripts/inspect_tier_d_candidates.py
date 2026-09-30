import json
import sqlite3
from pathlib import Path
from src.backend.db.opportunity import evaluate_broker_opportunity, TIER_D_RESEARCH_NEEDED

DB_PATH = Path("data/prospects.db")
with open("reports/batch_1_frozen_selection.json", "r") as f:
    b1_ids = {r["company_id"] for r in json.load(f)}
with open("reports/batch_2_frozen_selection.json", "r") as f:
    b2_ids = {r["company_id"] for r in json.load(f)}

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

comp_ids = [r[0] for r in conn.execute("SELECT DISTINCT company_id FROM facilities").fetchall()]
tier_d = []

for cid in comp_ids:
    if cid in b1_ids or cid in b2_ids:
        continue
    opp = evaluate_broker_opportunity(cid, conn=conn)
    if opp["opportunity_tier"] == TIER_D_RESEARCH_NEEDED:
        comp = conn.execute("SELECT id, operating_brand, legal_name, website_url FROM companies WHERE id = ?", (cid,)).fetchone()
        facs = conn.execute("SELECT id, facility_name, city, state_prov, country FROM facilities WHERE company_id = ?", (cid,)).fetchall()
        comms = conn.execute("""
            SELECT fc.commodity_category, fc.equipment_category, fc.equipment_usage_status 
            FROM facility_commodities fc
            JOIN facilities f ON fc.facility_id = f.id
            WHERE f.company_id = ?
        """, (cid,)).fetchall()
        contacts = conn.execute("""
            SELECT count(*) FROM contacts 
            WHERE company_id = ? OR facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
        """, (cid, cid)).fetchone()[0]

        # Check geo exclusions
        geo_ok = True
        for f in facs:
            st = (f["state_prov"] or "").upper()
            co = (f["country"] or "USA").upper()
            if st in ("AK", "ALASKA", "HI", "HAWAII") or co in ("MX", "MEX", "MEXICO"):
                geo_ok = False
                break
        if not geo_ok:
            continue

        tier_d.append({
            "company_id": cid,
            "brand": comp["operating_brand"],
            "website": comp["website_url"],
            "first_fac_id": facs[0]["id"],
            "fac_name": facs[0]["facility_name"],
            "city": facs[0]["city"],
            "state": facs[0]["state_prov"],
            "country": facs[0]["country"],
            "contact_count": contacts,
            "cats": list({c["commodity_category"] for c in comms if c["commodity_category"]}),
            "eqs": list({c["equipment_category"] for c in comms if c["equipment_category"]}),
        })

print(f"Total eligible Tier D: {len(tier_d)}")

# Print top 40 candidates that have websites and contacts or solid manufacturing commodities
sorted_d = sorted(tier_d, key=lambda x: (x["contact_count"] > 0, bool(x["website"]), len(x["fac_name"])), reverse=True)
for i, c in enumerate(sorted_d[:40], 1):
    print(f"{i}. ID {c['company_id']} | {c['brand']} | {c['city']}, {c['state']} | {c['cats']} | {c['eqs']} | contacts={c['contact_count']} | web={c['website']}")
