import json
import sqlite3
from pathlib import Path

DB_PATH = Path("data/prospects.db")
ROSTER_PATH = Path("reports/tier_a_acceleration_phase_a_roster.json")

def main():
    with open(ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)

    wave_e = [r for r in roster if r["wave"] == "E"]
    print(f"Total Wave E targets: {len(wave_e)}")

    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    for item in wave_e:
        pos = item["campaign_position"]
        cid = item["company_id"]
        fid = item["candidate_focus_facility_ids"][0]
        tier = item["current_tier"]
        brand = item["operating_brand"]
        web_url = item.get("official_website")

        fac = conn.execute("""
            SELECT f.id, f.facility_name, f.city, f.state_prov,
                   f.private_fleet_present, f.fleet_relationship_type, f.commercial_carrier_use,
                   f.broker_friendly_status, pl.stage
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.id = ?
        """, (fid,)).fetchone()

        contacts = conn.execute("""
            SELECT id, person_name, exact_published_title, phone_number, phone_directness, email_address, role_category
            FROM contacts WHERE company_id = ? OR facility_id = ?
        """, (cid, fid)).fetchall()

        print(f"[{pos:02d}] CID {cid:3d} | FID {fid:3d} | Tier: {tier:23s} | Brand: {brand}")
        print(f"     Loc: {fac['city']}, {fac['state_prov']}")
        print(f"     Fleet: {fac['private_fleet_present']} | Carrier: {fac['commercial_carrier_use']} | Broker: {fac['broker_friendly_status']}")
        print(f"     Web: {web_url}")
        print(f"     Contacts ({len(contacts)}): {[str(c['person_name']) + ' (' + str(c['role_category']) + '): ' + (c['phone_number'] or c['email_address'] or '') for c in contacts]}")
        print("-" * 80)

    conn.close()

if __name__ == "__main__":
    main()
