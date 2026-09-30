import sqlite3

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

# Search for any source where title or URL indicates directory / association / government / registry
keywords = [
    "directory", "registry", "commission", "department", "association",
    "council", "bureau", "government", "portal", "index", "guide",
    "chamber", "federation", "network", "yellowpages", "manta", "thomasnet",
    "zoominfo", "dnb", "industrynet", "database"
]

rows = cur.execute("""
    SELECT id, source_title_publisher, source_type, source_url, is_primary_source
    FROM evidence_sources
""").fetchall()

suspicious = []
for r in rows:
    title = (r[1] or "").lower()
    url = (r[3] or "").lower()
    stype = r[2]
    is_prim = r[4]
    matched = [k for k in keywords if k in title or k in url]
    if matched:
        suspicious.append((r, matched))

print(f"Total matching sources: {len(suspicious)}")
for r, m in suspicious:
    print(f"ID {r[0]} | Type: {r[2]} | is_primary: {r[4]} | Title: '{r[1]}' | URL: {r[3]} | Matched: {m}")

conn.close()
