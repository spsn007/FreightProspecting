import sqlite3

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

rows = cur.execute("""
    SELECT id, source_title_publisher, source_type, source_url, is_primary_source
    FROM evidence_sources
    WHERE source_type = 'COMPANY_WEBSITE'
""").fetchall()

misclassified = []
for r in rows:
    url = (r[3] or "").lower()
    title = (r[1] or "").lower()
    if any(k in url or k in title for k in [
        ".gov", "registry", "directory", "association", "thomasnet", "manta", "zoominfo",
        "dnb.com", "yellowpages", "chamberofcommerce", "industrynet", "dnr.state", "agr.state",
        "michigan.gov", "georgia.gov", "alberta.ca", "ontario.ca", "quebec.ca", "bc.ca",
        "forestinfo", "hardwoodinfo", "woodworkingnetwork", "profile", "listing", "database"
    ]):
        misclassified.append(r)

print(f"Total COMPANY_WEBSITE sources: {len(rows)}")
print(f"Potentially misclassified COMPANY_WEBSITE sources: {len(misclassified)}")
for m in misclassified:
    print(" ", m)

# Also check CHECK constraint on source_type
print("\n--- evidence_sources CREATE SQL ---")
create_sql = cur.execute("SELECT sql FROM sqlite_master WHERE name='evidence_sources'").fetchone()[0]
print(create_sql)

conn.close()
