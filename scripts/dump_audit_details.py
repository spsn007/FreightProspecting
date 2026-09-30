import json

with open("D:/FreightProspecting-Audit/professional_audit_findings.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("Keys of first finding:", list(data.get("findings", [])[0].keys()))
for k, v in data.get("findings", [])[0].items():
    print(f"  {k}: {repr(v)[:150]}")
