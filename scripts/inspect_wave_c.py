import json
import sqlite3

with open("reports/batch_3_frozen_selection.json", "r", encoding="utf-8") as f:
    roster = json.load(f)

wave_c = [r for r in roster if r["wave"] == "C"]
print(f"Loaded Wave C: {len(wave_c)} companies (Positions {wave_c[0]['batch_position']} to {wave_c[-1]['batch_position']})")

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

for item in wave_c:
    cid = item["company_id"]
    fid = item["research_focus_facility_id"]
    pos = item["batch_position"]
    brand = item["operating_brand"]
    tier = item["pre_research_opportunity_tier"]
    
    comp = conn.execute("SELECT website_url FROM companies WHERE id = ?", (cid,)).fetchone()
    fac = conn.execute("SELECT city, state_prov FROM facilities WHERE id = ?", (fid,)).fetchone()
    contacts = conn.execute("SELECT person_name, phone_number, email_address, role_category FROM contacts WHERE company_id = ? OR facility_id = ?", (cid, fid)).fetchall()
    
    ct_info = "; ".join([f"{c['person_name'] or c['role_category']} [phone:{c['phone_number']}, email:{c['email_address']}]" for c in contacts])
    url = comp["website_url"] if comp else "None"
    
    print(f"Pos {pos:02d} | CID {cid:3d} | FID {fid:3d} | {brand} | {fac['city']}, {fac['state_prov']} | Tier: {tier} | Web: {url} | Contacts: {ct_info or 'None'}")

conn.close()
