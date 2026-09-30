import sqlite3
from urllib.parse import urlparse

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

rows = cur.execute("SELECT id, source_title_publisher, source_type, source_url FROM evidence_sources").fetchall()

all_domains = set()
for r in rows:
    url = r[3] or ""
    if url:
        p = urlparse(url)
        d = p.netloc.lower()
        if d.startswith("www."):
            d = d[4:]
        all_domains.add(d)

print(f"Total unique domains: {len(all_domains)}")
for d in sorted(all_domains):
    print(" ", d)

conn.close()
