import urllib.request
import ssl
import sqlite3
from concurrent.futures import ThreadPoolExecutor

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

conn = sqlite3.connect('data/prospects.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute('''
    SELECT c.id, c.operating_brand, c.website_url, f.id as fid, f.city, f.state_prov
    FROM facilities f 
    JOIN companies c ON f.company_id = c.id 
    JOIN prospect_lifecycle pl ON f.id = pl.facility_id 
    WHERE pl.stage = 'SHORTLISTED' 
    ORDER BY c.id
''')
rows = c.fetchall()

def check_url(r):
    cid = r['id']
    brand = r['operating_brand']
    url = r['website_url']
    status = "NO_URL"
    if url:
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, context=ctx, timeout=3) as resp:
                status = f"HTTP {resp.getcode()}"
        except Exception as e:
            status = f"ERR: {type(e).__name__} ({str(e)[:35]})"
    return (cid, brand, url, status)

print(f"Testing {len(rows)} shortlisted companies with ThreadPool...", flush=True)

with ThreadPoolExecutor(max_workers=10) as executor:
    results = list(executor.map(check_url, rows))

results.sort(key=lambda x: x[0])

with open('url_results.txt', 'w', encoding='utf-8') as out:
    for res in results:
        line = f"CID {res[0]}: {res[1]} | {res[2]} | {res[3]}"
        print(line, flush=True)
        out.write(line + "\n")
