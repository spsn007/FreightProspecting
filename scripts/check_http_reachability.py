"""
Asynchronous HTTP reachability audit for Stage 3E URLs.
Tests: resolving (200/300/403 bot check), redirects, dead/connection refused.
"""
import asyncio
import http.client
import json
import sqlite3
import urllib.parse
import urllib.request
import concurrent.futures

def check_single_url(row):
    source_id, url = row
    parsed = urllib.parse.urlparse(url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    status = None
    redirected_to = None
    is_redirect = False
    error = None

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            status = resp.getcode()
            final_url = resp.geturl()
            if urllib.parse.urlparse(final_url).netloc.lower() != parsed.netloc.lower():
                is_redirect = True
                redirected_to = final_url
    except urllib.error.HTTPError as e:
        status = e.code
    except urllib.error.URLError as e:
        error = str(e.reason)
    except Exception as e:
        error = str(e)

    return {
        "id": source_id,
        "url": url,
        "status": status,
        "is_redirect": is_redirect,
        "redirected_to": redirected_to,
        "error": error
    }

def main():
    conn = sqlite3.connect("data/prospects.db")
    rows = conn.execute("SELECT id, source_url FROM evidence_sources WHERE id >= 428 AND source_url IS NOT NULL").fetchall()
    conn.close()

    print(f"Testing {len(rows)} URLs with ThreadPoolExecutor...")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(check_single_url, r): r for r in rows}
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    working = [r for r in results if r["status"] in (200, 301, 302, 307, 308, 403, 401)]
    redirected = [r for r in results if r["is_redirect"]]
    dead = [r for r in results if r["error"] or (r["status"] and r["status"] >= 404)]

    print("\n=== HTTP AUDIT SUMMARY FOR STAGE 3E EVIDENCE SOURCES ===")
    print(f"Total URLs Checked       : {len(results)}")
    print(f"Resolving / Working URLs : {len(working)} (Note: 403/401 includes bot-protected active sites)")
    print(f"Redirected URLs          : {len(redirected)}")
    print(f"Dead / Unreachable URLs  : {len(dead)}")

    if redirected:
        print("\nSample Redirects:")
        for r in redirected[:5]:
            print(f"  ID {r['id']}: {r['url']} -> {r['redirected_to']}")

    if dead:
        print("\nSample Dead / Unreachable:")
        for r in dead[:10]:
            print(f"  ID {r['id']}: {r['url']} - Error: {r['error']} / Status: {r['status']}")

if __name__ == "__main__":
    main()
