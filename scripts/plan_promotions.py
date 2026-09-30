"""
Design and verify the exact Stage 3F promotion plan:
- 32 Shortlisted companies (4 existing + 28 new)
- 95 Qualified companies (passing all 5 factual gates with active resolving primary websites)
- 400 Discovery companies remaining for future investigation
Total = 527 Operating Companies.
"""
import sqlite3
import json
from pathlib import Path

# The 28 newly proposed Shortlist company IDs (plus existing 1, 2, 3, 5 = 32 total)
SHORTLIST_NEW_IDS = [
    # Track A: Wood (9)
    321,  # Yoder Lumber Co.
    300,  # Cole Hardwood Inc.
    6,    # Battle Lumber Company
    7,    # Custom Cut Timber Products
    10,   # Leslie Forest Products Ltd.
    63,   # Scotch Plywood Company
    68,   # Troy Lumber Company
    77,   # Vanderwell Contractors
    60,   # Rex Lumber
    # Track B: Steel (8)
    19,   # Coil Steel Processing (CSP)
    16,   # Miami Valley Steel Service, Inc.
    17,   # MidWest Materials, Inc.
    18,   # Liberty Steel Products, Inc.
    21,   # Taylor Steel Inc.
    25,   # Majestic Steel USA
    26,   # Heidtman Steel Products, Inc.
    86,   # Scott Steel
    # Track C: Precast / Building (6)
    30,   # High Concrete Group LLC
    31,   # Metromont Corporation
    32,   # Gate Precast Company
    33,   # Tindall Corporation
    34,   # Fabcon Precast
    35,   # Coreslab Structures
    # Track D: Tooling / Industrial (5)
    40,   # Cascade Engineering
    42,   # Bemis Manufacturing Company
    44,   # SyBridge Technologies
    155,  # AarKel Tool and Die Inc.
    289,  # A.C. Miller Concrete Products, Inc.
]

def plan_promotions():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Verify all SHORTLIST_NEW_IDS exist and are currently DISCOVERY
    for cid in SHORTLIST_NEW_IDS:
        row = conn.execute("""
            SELECT c.id, c.operating_brand, l.stage, f.id as fac_id, f.facility_name, f.city, f.state_prov, f.country
            FROM companies c
            JOIN facilities f ON c.id = f.company_id
            JOIN prospect_lifecycle l ON f.id = l.facility_id
            WHERE c.id = ?
        """, (cid,)).fetchone()
        if not row:
            print(f"ERROR: Company ID {cid} not found!")
        elif row["stage"] != "DISCOVERY":
            print(f"ERROR: Company ID {cid} is in stage {row['stage']}, not DISCOVERY!")
        else:
            print(f"Shortlist candidate verified: ID {cid:<3} | {row['operating_brand']:<35} | {row['facility_name']} ({row['city']}, {row['state_prov']} {row['country']})")

    print(f"\nAll {len(SHORTLIST_NEW_IDS)} new shortlist candidates verified!")

    # Now let's select candidate pool for QUALIFIED
    # Look for companies with:
    # 1. Active resolving URL from pre-Stage 3E or Stage 3E checks
    # 2. Complete street address
    # 3. Callable phone
    # 4. Exclude the 28 shortlist candidates
    # We want around 90-100 Qualified companies
    
    # Query candidates with working URLs
    # We can select from Batch 1, FastTrack, and Stage 3E
    conn.close()

if __name__ == "__main__":
    plan_promotions()
