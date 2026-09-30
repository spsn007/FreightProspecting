import json
from pathlib import Path

with open("reports/tier_a_phase_b_wave_A_crawler_raw.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for item in data:
    cid = item["company_id"]
    pos = item["campaign_position"]
    brand = item["operating_brand"]
    ev = item["evidence"]
    c_snips = ev.get("carrier_snippets", [])
    f_snips = ev.get("fleet_snippets", [])
    b_snips = ev.get("broker_snippets", [])
    if c_snips or f_snips or b_snips:
        print(f"[{pos:02d}] CID {cid} ({brand}):")
        for s in c_snips:
            print(f"   CARRIER ({s['url']}):\n      {s['snippet']}")
        for s in f_snips:
            print(f"   FLEET ({s['url']}):\n      {s['snippet']}")
        for s in b_snips:
            print(f"   BROKER ({s['url']}):\n      {s['snippet']}")
