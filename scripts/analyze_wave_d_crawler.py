import json
from pathlib import Path

with open("reports/batch_3_wave_D_crawler_raw.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for item in data:
    cid = item["company_id"]
    brand = item["operating_brand"]
    pos = item["batch_position"]
    carrier_snips = item["evidence_snippets"]["commercial_carrier"]
    broker_snips = item["evidence_snippets"]["broker"]
    fleet_snips = item["evidence_snippets"]["private_fleet"]
    contact_snips = item["evidence_snippets"]["shipping_logistics"]
    emails = item["all_emails"]
    phones = item["all_phones"]
    
    print(f"=== Pos {pos:02d} | Comp {cid} | {brand} ===")
    print(f"  Pages: {len(item['pages_checked'])} | Emails: {len(emails)} | Phones: {len(phones)}")
    if carrier_snips:
        print(f"  [Carrier]: {len(carrier_snips)} snippets")
        for s in carrier_snips[:2]:
            safe_snip = s['snippet'][:120].encode('ascii', 'replace').decode('ascii')
            print(f"    - ({s['url']}) {safe_snip}...")
    if broker_snips:
        print(f"  [Broker]: {len(broker_snips)} snippets")
        for s in broker_snips[:2]:
            safe_snip = s['snippet'][:120].encode('ascii', 'replace').decode('ascii')
            print(f"    - ({s['url']}) {safe_snip}...")
    if fleet_snips:
        print(f"  [Fleet]: {len(fleet_snips)} snippets")
        for s in fleet_snips[:2]:
            safe_snip = s['snippet'][:120].encode('ascii', 'replace').decode('ascii')
            print(f"    - ({s['url']}) {safe_snip}...")
    if contact_snips:
        print(f"  [Contacts]: {len(contact_snips)} snippets")
        for s in contact_snips[:2]:
            safe_snip = s['snippet'][:120].encode('ascii', 'replace').decode('ascii')
            print(f"    - ({s['url']}) {safe_snip}...")
    
    key_emails = [e for e in emails if any(k in e.lower() for k in ["ship", "traffic", "logist", "dispatch", "sales", "order"])]
    if key_emails:
        print(f"  Key emails: {key_emails}")
