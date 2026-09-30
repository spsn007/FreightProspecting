import sqlite3
from urllib.parse import urlparse

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

rows = cur.execute("""
    SELECT id, source_title_publisher, source_type, source_url, is_primary_source
    FROM evidence_sources
""").fetchall()

print(f"Total evidence sources: {len(rows)}")

# Group by domain
domains = {}
third_party_candidates = []

for r in rows:
    url = r[3] or ""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    domains[domain] = domains.get(domain, 0) + 1

    # Check for known directories, portals, government sites
    if any(ind in domain for ind in [
        ".gov", ".gc.ca", "directory", "registry", "yellowpages", "manta",
        "thomasnet", "zoominfo", "dnb.com", "chamberofcommerce", "industrynet",
        "hardwoodinfo", "forestinfo", "woodworkingnetwork", "alberta.ca",
        "ontario.ca", "quebec.ca", "canada.ca", "usda.gov"
    ]):
        third_party_candidates.append((domain, r))

print("\n--- Third Party / Government Candidates in evidence_sources ---")
for dom, r in third_party_candidates:
    print(f"ID {r[0]} | {dom} | Type: {r[2]} | Title: {r[1]} | is_primary: {r[4]} | URL: {r[3]}")

# Also check sources with domain frequency > 1
print("\n--- Domains with multiple sources ---")
for dom, cnt in sorted(domains.items(), key=lambda x: x[1], reverse=True):
    if cnt > 1 and dom:
        print(f"  {dom}: {cnt}")

conn.close()
