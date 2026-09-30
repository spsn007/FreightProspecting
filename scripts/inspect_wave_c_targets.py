import json
import sqlite3
from collections import Counter
from pathlib import Path

ROSTER_PATH = Path("reports/tier_a_acceleration_phase_b_roster.json")
DB_PATH = Path("data/prospects.db")

def main():
    with open(ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)

    wave_c = [r for r in roster if r["wave"] == "C"]
    print(f"Wave C count: {len(wave_c)}")
    print("Priority classes in Wave C:")
    print(Counter(r["priority_class"] for r in wave_c))

    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    for r in wave_c[:15]:
        pos = r["campaign_position"]
        cid = r["company_id"]
        fid = r["focus_facility_id"]
        brand = r["operating_brand"]
        city = r["facility_city"]
        state = r["facility_state"]
        url = r["website_url"]
        p_class = r["priority_class"]
        print(f"[{pos:03d}] CID {cid:3d} (P{p_class}) | FID {fid:3d} | {brand[:25]:25s} | {city}, {state} | {url}")

if __name__ == "__main__":
    main()
