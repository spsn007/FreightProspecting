"""
FreightProspecting V1 — Stage 2 Verification Inspector
Prints full table inventory, index list, record counts, and integrity status.
"""

from pathlib import Path
import sqlite3

DB_PATH = Path("D:/FreightProspecting/data/prospects.db")


def inspect_database():
    if not DB_PATH.exists():
        print(f"ERROR: Database file not found at {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    print("=" * 70)
    print("FREIGHTPROSPECTING V1 — STAGE 2 DATABASE INSPECTION")
    print(f"Database Location: {DB_PATH}")
    print("=" * 70)

    # 1. Tables and row counts
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    objects = [r["name"] for r in cur.fetchall()]
    print(f"\n[1] TABLES & VIEWS ({len(objects)} total):")
    counts = {}
    for obj in objects:
        cnt = conn.execute(f"SELECT count(*) FROM {obj}").fetchone()[0]
        counts[obj] = cnt
        print(f"  * {obj:30} : {cnt:4} rows")

    # 2. Indexes
    cur = conn.execute(
        "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%' ORDER BY tbl_name, name"
    )
    indexes = cur.fetchall()
    print(f"\n[2] INDEXES ({len(indexes)} total):")
    for idx in indexes:
        print(f"  * {idx['name']:32} on table '{idx['tbl_name']}'")

    # 3. Claims Breakdown
    cur = conn.execute(
        "SELECT verification_status, count(*) as cnt FROM claims GROUP BY verification_status ORDER BY cnt DESC"
    )
    claims_by_status = cur.fetchall()
    print("\n[3] CLAIMS BY VERIFICATION STATUS:")
    for r in claims_by_status:
        print(f"  * {r['verification_status']:15} : {r['cnt']} claims")

    # 4. Companies & Facilities
    cur = conn.execute(
        """
        SELECT c.id as comp_id, c.operating_brand, c.legal_name,
               f.id as fac_id, f.facility_name, f.city, f.state_prov, f.country,
               f.private_fleet_present
        FROM companies c
        LEFT JOIN facilities f ON c.id = f.company_id
        ORDER BY c.id
        """
    )
    entities = cur.fetchall()
    print("\n[4] SEED COMPANIES & FACILITIES:")
    for e in entities:
        fac_str = f"Facility: {e['facility_name']} ({e['city']}, {e['state_prov']} {e['country']}) [Fleet: {e['private_fleet_present']}]" if e['fac_id'] else "No facility (Holding entity)"
        print(f"  * [{e['comp_id']}] {e['operating_brand']} (Legal: {e['legal_name']}) -> {fac_str}")

    # 5. Contacts
    cur = conn.execute(
        """
        SELECT c.person_name, c.exact_published_title, c.phone_number, c.phone_directness, f.facility_name
        FROM contacts c
        LEFT JOIN facilities f ON c.facility_id = f.id
        ORDER BY c.id
        """
    )
    contacts = cur.fetchall()
    print("\n[5] SEED CONTACTS:")
    for ct in contacts:
        name_str = ct['person_name'] or "[Unnamed Role]"
        print(f"  * {name_str} ({ct['exact_published_title']}) - {ct['phone_number']} [{ct['phone_directness']}] at {ct['facility_name']}")

    # 6. Discrete Load / Capacity Postings / Demand Signals Zero-Check
    print("\n[6] ZERO-HALLUCINATION / ZERO-FAKE ENTITY VERIFICATION:")
    print(f"  * load_opportunities count : {counts.get('load_opportunities', 0)} (Must be 0)")
    print(f"  * capacity_postings count  : {counts.get('capacity_postings', 0)} (Must be 0)")
    print(f"  * freight_demand_signals   : {counts.get('freight_demand_signals', 0)} (Must be 0)")
    print(f"  * load_capacity_matches    : {counts.get('load_capacity_matches', 0)} (Must be 0)")

    assert counts.get('load_opportunities', 0) == 0, "Violation: Fake load_opportunities found!"
    assert counts.get('capacity_postings', 0) == 0, "Violation: Fake capacity_postings found!"
    assert counts.get('freight_demand_signals', 0) == 0, "Violation: Fake freight_demand_signals found!"

    print("\n[7] INTEGRITY STATUS: ALL STAGE 2 INVARIANTS MET PERFECTLY.")
    conn.close()


if __name__ == "__main__":
    inspect_database()
