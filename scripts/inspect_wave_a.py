import json
import sqlite3
from pathlib import Path

with open("reports/batch_3_frozen_selection.json", "r", encoding="utf-8") as f:
    roster = json.load(f)

wave_a = [r for r in roster if r["wave"] == "A"]
print(f"Loaded Wave A: {len(wave_a)} companies")

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

for item in wave_a:
    cid = item["company_id"]
    fid = item["research_focus_facility_id"]
    pos = item["batch_position"]
    brand = item["operating_brand"]
    tier = item["pre_research_opportunity_tier"]
    
    comp = conn.execute("SELECT website_url, legal_name FROM companies WHERE id = ?", (cid,)).fetchone()
    fac = conn.execute("SELECT facility_name, city, state_prov, private_fleet_present, commercial_carrier_use, broker_friendly_status FROM facilities WHERE id = ?", (fid,)).fetchone()
    contacts = conn.execute("SELECT person_name, exact_published_title, phone_number, email_address, role_category FROM contacts WHERE company_id = ? OR facility_id = ?", (cid, fid)).fetchall()
    
    ct_info = "; ".join([f"{c['person_name'] or c['role_category']} ({c['exact_published_title'] or 'No title'}) [phone:{c['phone_number']}, email:{c['email_address']}]" for c in contacts])
    
    print(f"Pos {pos:02d} | Comp {cid:3d} | Fac {fid:3d} | {brand} | {fac['city']}, {fac['state_prov']} | Tier: {tier} | Web: {comp['website_url']} | Contacts: {ct_info or 'None'}")

conn.close()
