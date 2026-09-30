import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DB_PATH = Path("data/prospects.db")

def main():
    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # Find which companies are currently in Tier D
    from src.backend.db.opportunity import get_opportunity_tier_company_ids, TIER_D_RESEARCH_NEEDED
    tier_map = get_opportunity_tier_company_ids(conn=conn)
    tier_d_cids = tier_map[TIER_D_RESEARCH_NEEDED]
    print(f"Total Tier D companies: {len(tier_d_cids)}")

    # Analyze reasons for Tier D
    # 1. Actionable contact route?
    # 2. Lifecycle stage?
    # 3. Commodity / equipment?
    has_contact = 0
    in_discovery = 0
    in_qualified = 0

    candidates_with_contacts = []

    for cid in tier_d_cids:
        comp = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()
        facs = conn.execute("""
            SELECT f.*, pl.stage FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.company_id = ?
        """, (cid,)).fetchall()

        contacts = conn.execute("""
            SELECT * FROM contacts WHERE company_id = ? OR facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
        """, (cid, cid)).fetchall()

        stages = {f["stage"] for f in facs}
        if "QUALIFIED" in stages or "SHORTLISTED" in stages:
            in_qualified += 1
        else:
            in_discovery += 1

        callable_contacts = [c for c in contacts if c["phone_number"] or c["email_address"]]
        if callable_contacts:
            has_contact += 1
            candidates_with_contacts.append({
                "company_id": cid,
                "operating_brand": comp["operating_brand"] or comp["legal_name"],
                "stages": list(stages),
                "facilities_count": len(facs),
                "website_url": comp["website_url"],
                "callable_routes_count": len(callable_contacts),
                "sample_route": (callable_contacts[0]["phone_number"] or callable_contacts[0]["email_address"]),
                "contact_role": callable_contacts[0]["role_category"],
            })

    print(f"Tier D breakdown:")
    print(f"  In DISCOVERY stage: {in_discovery}")
    print(f"  In QUALIFIED/SHORTLISTED stage: {in_qualified}")
    print(f"  Has callable contact route: {has_contact}")
    print(f"  Missing callable route: {len(tier_d_cids) - has_contact}")
    print(f"High-potential candidates with existing callable routes: {len(candidates_with_contacts)}")

    conn.close()

if __name__ == "__main__":
    main()
