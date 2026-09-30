"""
Check HTTP resolution and company domain match for Stage 3E evidence sources.
"""
import asyncio
import http.client
import json
import re
import sqlite3
import urllib.parse
import urllib.request
from typing import Dict, List, Tuple

async def check_url(source_id: int, brand: str, url: str) -> Dict:
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower().replace("www.", "")
    
    # Check domain brand match heuristic
    # Simplify brand name: e.g. "Yoder Lumber Co." -> "yoder"
    brand_tokens = re.sub(r"[^a-z0-9 ]", "", brand.lower()).split()
    meaningful_tokens = [t for t in brand_tokens if t not in ("inc", "llc", "corp", "corporation", "ltd", "co", "company", "products", "industries", "group", "the", "and", "of")]
    
    domain_match = any(t in netloc for t in meaningful_tokens) if meaningful_tokens else True

    # Test HTTP reachability with 3-second timeout
    status_code = None
    resolved_url = None
    is_redirect = False
    error_msg = None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        # Use short timeout so we don't hang
        with urllib.request.urlopen(req, timeout=3.5) as response:
            status_code = response.getcode()
            resolved_url = response.geturl()
            if resolved_url and urllib.parse.urlparse(resolved_url).netloc.lower() != parsed.netloc.lower():
                is_redirect = True
    except urllib.error.HTTPError as e:
        status_code = e.code
        # HTTP 403 / 401 often means bot protection (Cloudflare, etc.) but domain is alive
    except urllib.error.URLError as e:
        error_msg = str(e.reason)
    except Exception as e:
        error_msg = str(e)

    return {
        "id": source_id,
        "brand": brand,
        "url": url,
        "netloc": netloc,
        "domain_match": domain_match,
        "status_code": status_code,
        "resolved_url": resolved_url,
        "is_redirect": is_redirect,
        "error": error_msg
    }

def run_url_audit():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Join evidence_sources with claims and companies
    query = """
    SELECT es.id, es.source_url, es.source_type, c.operating_brand
    FROM evidence_sources es
    JOIN claim_evidence ce ON es.id = ce.evidence_source_id
    JOIN claims cl ON ce.claim_id = cl.id
    LEFT JOIN companies c ON cl.company_id = c.id
    WHERE es.id >= 428 AND es.source_url IS NOT NULL
    GROUP BY es.id
    ORDER BY es.id
    """
    rows = conn.execute(query).fetchall()
    print(f"Total Stage 3E Evidence Sources to Audit: {len(rows)}")

    # Check basic URL formats first
    malformed = []
    for r in rows:
        url = r["source_url"]
        if not (url.startswith("http://") or url.startswith("https://")):
            malformed.append((r["id"], url))
    print(f"Malformed URLs: {len(malformed)}")

    # Check domain brand match
    mismatched = []
    for r in rows:
        brand = r["operating_brand"] or ""
        url = r["source_url"]
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower().replace("www.", "")
        brand_tokens = re.sub(r"[^a-z0-9 ]", "", brand.lower()).split()
        meaningful_tokens = [t for t in brand_tokens if t not in ("inc", "llc", "corp", "corporation", "ltd", "co", "company", "products", "industries", "group", "the", "and", "of", "international", "holding", "holdings")]
        match = any(t in netloc for t in meaningful_tokens) if meaningful_tokens else True
        if not match:
            mismatched.append((r["id"], brand, url, netloc))

    print(f"Domain mismatch candidates: {len(mismatched)}")
    for m in mismatched[:10]:
        print(f"  ID {m[0]}: Brand='{m[1]}' vs Domain='{m[3]}' (URL: {m[2]})")

    conn.close()

if __name__ == "__main__":
    run_url_audit()
