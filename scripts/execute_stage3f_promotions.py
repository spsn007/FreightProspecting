"""
Execute Stage 3F Atomic Promotions:
Promotes 28 new companies to SHORTLISTED and 96 companies to QUALIFIED.
Maintains atomic transaction safety, provenance notes, and database integrity.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

def execute_promotions():
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest_path = Path("data/stage3f_manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        conn.execute("BEGIN TRANSACTION;")

        # 1. Promote new shortlist companies
        shortlist_new_ids = manifest["shortlist_new_ids"]
        print(f"Promoting {len(shortlist_new_ids)} companies to SHORTLISTED...")
        for cid in shortlist_new_ids:
            cur = conn.execute("""
                UPDATE prospect_lifecycle
                SET stage = 'SHORTLISTED',
                    shortlisted_at = ?,
                    qualified_at = COALESCE(qualified_at, ?),
                    qualification_notes = 'Promoted to Shortlist in Stage 3F: Active broker prospecting priority verified with callable phone, heavy FTL fit, and manageable friction.',
                    updated_at = ?
                WHERE facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
            """, (now_iso, now_iso, now_iso, cid))
            assert cur.rowcount > 0, f"No facility found for shortlist company {cid}"

        # 2. Promote qualified companies
        qualified_ids = manifest["qualified_ids"]
        print(f"Promoting {len(qualified_ids)} companies to QUALIFIED...")
        for cid in qualified_ids:
            cur = conn.execute("""
                UPDATE prospect_lifecycle
                SET stage = 'QUALIFIED',
                    qualified_at = ?,
                    qualification_notes = 'Promoted to Qualified in Stage 3F: Factual readiness checks passed (verified operating facility, approved FTL equipment, eligible geography, callable route, primary evidence).',
                    updated_at = ?
                WHERE facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
            """, (now_iso, now_iso, cid))
            assert cur.rowcount > 0, f"No facility found for qualified company {cid}"

        # 3. Verify counts
        s_facs = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
        q_facs = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'QUALIFIED'").fetchone()[0]
        d_facs = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
        t_facs = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]

        print("\n=== POST-PROMOTION FACILITY COUNTS ===")
        print(f"Shortlisted Facilities: {s_facs}")
        print(f"Qualified Facilities  : {q_facs}")
        print(f"Discovery Facilities  : {d_facs}")
        print(f"Total Facilities      : {t_facs}")

        assert s_facs == 32, f"Expected 32 shortlisted facilities, got {s_facs}"
        assert q_facs == 130, f"Expected 130 qualified facilities, got {q_facs}"
        assert d_facs == 453, f"Expected 453 discovery facilities, got {d_facs}"
        assert s_facs + q_facs + d_facs == 615, f"Total facilities mismatch"

        # Company stage counts based on highest active facility stage
        comp_stages = conn.execute("""
            SELECT 
                c.id,
                CASE 
                    WHEN SUM(CASE WHEN l.stage = 'SHORTLISTED' THEN 1 ELSE 0 END) > 0 THEN 'SHORTLISTED'
                    WHEN SUM(CASE WHEN l.stage = 'QUALIFIED' THEN 1 ELSE 0 END) > 0 THEN 'QUALIFIED'
                    ELSE 'DISCOVERY'
                END as primary_stage
            FROM companies c
            JOIN facilities f ON c.id = f.company_id
            JOIN prospect_lifecycle l ON f.id = l.facility_id
            GROUP BY c.id
        """).fetchall()

        s_comps = sum(1 for r in comp_stages if r["primary_stage"] == "SHORTLISTED")
        q_comps = sum(1 for r in comp_stages if r["primary_stage"] == "QUALIFIED")
        d_comps = sum(1 for r in comp_stages if r["primary_stage"] == "DISCOVERY")

        print("\n=== POST-PROMOTION OPERATING COMPANY COUNTS ===")
        print(f"Shortlisted Companies : {s_comps}")
        print(f"Qualified Companies   : {q_comps}")
        print(f"Discovery Companies   : {d_comps}")
        print(f"Total Operating       : {s_comps + q_comps + d_comps}")

        assert s_comps == 32, f"Expected 32 shortlisted companies, got {s_comps}"
        assert q_comps == 96, f"Expected 96 qualified companies, got {q_comps}"
        assert d_comps == 399, f"Expected 399 discovery companies, got {d_comps}"
        assert s_comps + q_comps + d_comps == 527, f"Total operating companies mismatch"

        # 4. Integrity checks
        fk_errors = conn.execute("PRAGMA foreign_key_check;").fetchall()
        assert len(fk_errors) == 0, f"Foreign key errors: {fk_errors}"

        integ = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        assert integ == "ok", f"Integrity check failed: {integ}"

        conn.commit()
        print("\nAll Stage 3F promotions committed atomically!")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: Transaction rolled back: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    execute_promotions()
