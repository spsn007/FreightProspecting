import json
import re
from pathlib import Path

CRAWLER_FILE = Path("reports/tier_a_phase_b_wave_A_crawler_raw.json")

def main():
    with open(CRAWLER_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    keywords = ["carrier", "truckload", "freight", "fleet", "broker", "logistics", "shipping", "delivery", "flatbed"]

    print("=== Scanning full crawler text for logistics keywords ===")
    for item in data:
        cid = item["company_id"]
        pos = item["campaign_position"]
        brand = item["operating_brand"]
        
        # Check all provenance pages
        for p in item.get("provenance_records", []):
            url = p.get("final_url", "")
            title = p.get("page_title", "")
            # We don't have text saved in prov, but we have evidence snippets
        
        ev = item["evidence"]
        c_snips = ev.get("carrier_snippets", [])
        f_snips = ev.get("fleet_snippets", [])
        b_snips = ev.get("broker_snippets", [])
        
        if c_snips or f_snips or b_snips:
            print(f"[{pos:02d}] CID {cid:3d} ({brand}): Carriers={len(c_snips)} Fleet={len(f_snips)} Broker={len(b_snips)}")

if __name__ == "__main__":
    main()
