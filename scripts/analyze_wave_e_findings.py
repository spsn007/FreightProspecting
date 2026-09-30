import json
import sys
from pathlib import Path

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raw_path = Path("reports/tier_a_phase_a_wave_E_crawler_raw.json")
    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Total Wave E companies analyzed: {len(data)}")
    for item in data:
        cid = item["company_id"]
        pos = item["campaign_position"]
        brand = item["operating_brand"]
        web = item["website_url"]
        prov_cnt = len(item["provenance_records"])
        succ_cnt = item["successful_pages_count"]

        ev = item["evidence"]
        carrier_snips = ev["carrier_snippets"]
        broker_snips = ev["broker_snippets"]
        fleet_snips = ev["fleet_snippets"]
        contact_snips = ev["contact_snippets"]
        emails = ev["emails"]
        phones = ev["phones"]

        print(f"\n================================================================================")
        print(f"[{pos:02d}] CID {cid:3d} | {brand} | Pages checked: {prov_cnt} (200 OK: {succ_cnt})")
        print(f"URL: {web}")
        if carrier_snips:
            print(f"--- CARRIER SNIPPETS ({len(carrier_snips)}) ---")
            for cs in carrier_snips[:3]:
                print(f"  [{cs['url']}] {cs['snippet']}")
        if broker_snips:
            print(f"--- BROKER SNIPPETS ({len(broker_snips)}) ---")
            for bs in broker_snips[:3]:
                print(f"  [{bs['url']}] {bs['snippet']}")
        if fleet_snips:
            print(f"--- FLEET SNIPPETS ({len(fleet_snips)}) ---")
            for fs in fleet_snips[:3]:
                print(f"  [{fs['url']}] {fs['snippet']}")
        if contact_snips:
            print(f"--- CONTACT SNIPPETS ({len(contact_snips)}) ---")
            for cs in contact_snips[:3]:
                print(f"  [{cs['url']}] {cs['snippet']}")
        if emails:
            print(f"--- EMAILS ({len(emails)}) ---: {emails[:5]}")
        if phones:
            print(f"--- PHONES ({len(phones)}) ---: {phones[:5]}")

if __name__ == "__main__":
    main()
