import json

with open("D:/FreightProspecting-Audit/professional_audit_findings.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print("Baseline:", data.get("baseline"))
print("Severity counts:", data.get("severity_counts"))
print("Total findings:", len(data.get("findings", [])))
print("-" * 80)
for idx, item in enumerate(data.get("findings", []), 1):
    fid = item.get("id")
    sev = item.get("severity")
    dom = item.get("domain")
    title = item.get("title")
    print(f"{idx:2d}. [{fid}] [{sev}] [{dom}] {title}")
