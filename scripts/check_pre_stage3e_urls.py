"""
Test reachability of pre-Stage 3E URLs (id < 428).
"""
import concurrent.futures
import sqlite3
import urllib.parse
import urllib.request

def check_single_url(row):
    source_id, url = row
    parsed = urllib.parse.urlparse(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    status = None
    error = None
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            status = resp.getcode()
    except urllib.error.HTTPError as e:
        status = e.code
    except urllib.error.URLError as e:
        error = str(e.reason)
    except Exception as e:
        error = str(e)

    return {"id": source_id, "url": url, "status": status, "error": error}

def main():
    conn = sqlite3.connect("data/prospects.db")
    rows = conn.execute("SELECT id, source_url FROM evidence_sources WHERE id < 428 AND source_url IS NOT NULL").fetchall()
    conn.close()

    print(f"Testing {len(rows)} pre-Stage 3E URLs with ThreadPoolExecutor...")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(check_single_url, r): r for r in rows}
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    working = [r for r in results if r["status"] in (200, 301, 302, 307, 308, 403, 401)]
    dead = [r for r in results if r["error"] or (r["status"] and r["status"] >= 404)]

    print(f"Total Pre-Stage 3E URLs : {len(results)}")
    print(f"Working / Resolving URLs: {len(working)}")
    print(f"Dead / Unreachable URLs : {len(dead)}")

if __name__ == "__main__":
    main()
