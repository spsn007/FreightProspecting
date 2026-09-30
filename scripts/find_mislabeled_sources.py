import sqlite3
from urllib.parse import urlparse

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

rows = cur.execute("""
    SELECT id, source_title_publisher, source_type, source_url, is_primary_source
    FROM evidence_sources
    WHERE source_type = 'COMPANY_WEBSITE'
""").fetchall()

# List of domains or publisher names that are not the prospect's first-party website
suspects = []
for r in rows:
    title = (r[1] or "")
    url = (r[3] or "")
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    # Check if the domain is an aggregator, association, directory, or portal
    # e.g., naturallywood.com, ohioprecast.org, forestproductslocator.org, etc.
    is_third_party = False
    category = None

    if any(k in domain for k in ["gatrees.org", ".gov", ".gc.ca", "usda"]):
        is_third_party = True
        category = "GOVERNMENT_REGISTRY"
    elif any(k in domain for k in ["association", "precast.org", "naturallywood.com", "woodworkingnetwork.com"]):
        is_third_party = True
        category = "TRADE_ASSOCIATION"
    elif any(k in domain for k in ["locator.org", "directory", "yellowpages", "manta.com", "thomasnet.com", "dnb.com", "zoominfo.com"]):
        is_third_party = True
        category = "INDUSTRY_DIRECTORY"
    elif any(w in title.lower() for w in ["association", "locator directory", "supplier directory", "trade"]):
        is_third_party = True
        category = "INDUSTRY_DIRECTORY"

    if is_third_party:
        suspects.append((r, domain, category))

print(f"Found {len(suspects)} third-party sources mislabeled as COMPANY_WEBSITE:")
for r, dom, cat in suspects:
    print(f"ID {r[0]} | Proposed Type: {cat} | Domain: {dom} | Title: '{r[1]}' | URL: {r[3]}")

conn.close()
