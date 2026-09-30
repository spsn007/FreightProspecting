import json
import sqlite3
from collections import Counter
from pathlib import Path

ROSTER_PATH = Path("reports/tier_a_acceleration_phase_b_roster.json")
DB_PATH = Path("data/prospects.db")

def main():
    with open(ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)

    wave_b = [r for r in roster if r["wave"] == "B"]
    print(f"Wave B count: {len(wave_b)}")
    print("Priority classes in Wave B:")
    print(Counter(r["priority_class"] for r in wave_b))

    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    for r in wave_b[:15]:
        pos = r["campaign_position"]
        cid = r["company_id"]
        fid = r["focus_facility_id"]
        brand = r["operating_brand"]
        city = r["facility_city"]
        state = r["facility_state"]
        url = r["website_url"]
        p_class = r["priority_class"]
        
        fac = conn.execute("SELECT commercial_carrier_use, broker_friendly_status, private_fleet_present FROM facilities WHERE id = ?", (fid,)).fetchone()
        carrier = fac["commercial_carrier_use"] if fac else "UNKNOWN"
        broker = fac["broker_friendly_status"] if fac else "UNKNOWN"
        fleet = fac["private_fleet_present"] if fac else "UNKNOWN"
        
        print(f"[{pos:02d}] CID {cid:3d} (P{p_class}) | FID {fid:3d} | {brand[:25]:25s} | {city}, {state} | Carrier={carrier} Broker={broker} Fleet={fleet} | {url}")

if __name__ == "__main__":
    main()
