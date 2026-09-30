import sqlite3

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

rows = cur.execute("""
    SELECT id, source_title_publisher, source_type, source_url, is_primary_source
    FROM evidence_sources
    WHERE source_url LIKE '%gatrees.org%'
""").fetchall()

print(f"Sources with gatrees.org: {len(rows)}")
for r in rows:
    print(r)

conn.close()
