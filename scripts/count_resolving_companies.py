"""
Count how many companies have active resolving websites from our HTTP audit results.
"""
import sqlite3
import json
from pathlib import Path

# Load results from check_http_reachability.py and check_pre_stage3e_urls.py
# We can run a quick check of resolving URLs against companies
from check_http_reachability import check_single_url as check_3e
from check_pre_stage3e_urls import check_single_url as check_pre

def check_resolving_companies():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Fetch all evidence sources and their companies
    rows = conn.execute("""
        SELECT es.id as source_id, es.source_url, c.id as comp_id, c.operating_brand
        FROM evidence_sources es
        JOIN claim_evidence ce ON es.id = ce.evidence_source_id
        JOIN claims cl ON ce.claim_id = cl.id
        JOIN companies c ON cl.company_id = c.id
        WHERE es.source_url IS NOT NULL
        GROUP BY c.id
    """).fetchall()

    print(f"Total Companies with Source URL: {len(rows)}")
    conn.close()

if __name__ == "__main__":
    check_resolving_companies()
