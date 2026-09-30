import json
from pathlib import Path

CRAWLER_FILE = Path("reports/tier_a_phase_b_wave_A_crawler_raw.json")

def main():
    with open(CRAWLER_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Total crawled companies: {len(data)}")
    
    with_carrier = []
    with_broker = []
    with_fleet = []

    for item in data:
        cid = item["company_id"]
        pos = item["campaign_position"]
        brand = item["operating_brand"]
        ev = item["evidence"]
        
        c_snips = ev.get("carrier_snippets", [])
        b_snips = ev.get("broker_snippets", [])
        f_snips = ev.get("fleet_snippets", [])
        
        if c_snips:
            with_carrier.append((pos, cid, brand, c_snips))
        if b_snips:
            with_broker.append((pos, cid, brand, b_snips))
        if f_snips:
            with_fleet.append((pos, cid, brand, f_snips))

    print(f"\n=== Companies with Carrier Snippets ({len(with_carrier)}) ===")
    for pos, cid, brand, snips in with_carrier:
        print(f"\n[{pos:02d}] CID {cid} ({brand}): {len(snips)} snippets")
        for s in snips[:3]:
            print(f"  URL: {s['url']}")
            print(f"  SNIP: {s['snippet']}")

    print(f"\n=== Companies with Broker Snippets ({len(with_broker)}) ===")
    for pos, cid, brand, snips in with_broker:
        print(f"\n[{pos:02d}] CID {cid} ({brand}): {len(snips)} snippets")
        for s in snips[:3]:
            print(f"  URL: {s['url']}")
            print(f"  SNIP: {s['snippet']}")

    print(f"\n=== Companies with Fleet Snippets ({len(with_fleet)}) ===")
    for pos, cid, brand, snips in with_fleet:
        print(f"\n[{pos:02d}] CID {cid} ({brand}): {len(snips)} snippets")
        for s in snips[:3]:
            print(f"  URL: {s['url']}")
            print(f"  SNIP: {s['snippet']}")

if __name__ == "__main__":
    main()
