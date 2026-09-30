"""
FreightProspecting V1 — Audit Remediation D.1 Database Migration
Executes final closure database migrations:
1. Reconcile lifecycle stages: demote 9 non-passing facilities to DISCOVERY:
   - Facilities 4 and 6 (from SHORTLISTED to DISCOVERY)
   - Facilities 7, 35, 36, 38, 39, 48, 150 (from QUALIFIED to DISCOVERY)
   Resulting counts:
   - Shortlisted facilities: 29 (100% READY, 0 FAIL)
   - Qualified facilities: 124 (100% READY, 0 FAIL)
   - Discovery facilities: 462
   - Total facilities: 615
   - Total companies: 529 (527 operating + 2 holding)
2. Install trg_outreach_logs_no_replace trigger on outreach_logs to close the REPLACE bypass.
"""

import hashlib
import os
import sqlite3
import sys
from pathlib import Path


def get_file_hash(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()


def run_migration(db_path: str = "data/prospects.db") -> None:
    p = Path(db_path)
    if not p.exists():
        raise FileNotFoundError(f"Target database not found: {db_path}")

    pre_hash = get_file_hash(p)
    pre_size = p.stat().st_size
    print(f"=== Starting Remediation D.1 Database Migration on {db_path} ===")
    print(f"Pre-migration SHA-256: {pre_hash} ({pre_size:,} bytes)")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = OFF;")

    # 1. Lifecycle Reconciliation
    print("1. Reconciling lifecycle stages for 9 non-passing facilities...")
    
    # Demote Facilities 4 & 6 from SHORTLISTED to DISCOVERY
    cur.execute("""
        UPDATE prospect_lifecycle
        SET stage = 'DISCOVERY',
            qualified_at = NULL,
            shortlisted_at = NULL,
            qualification_notes = 'Demoted to Discovery in Remediation D.1: Equipment claim lacks SUPPORTS evidence (AUD-003).',
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE facility_id IN (4, 6)
    """)
    print("   Demoted facilities 4, 6 from SHORTLISTED to DISCOVERY.")

    # Demote Facilities 7, 35, 36, 38, 39, 48, 150 from QUALIFIED to DISCOVERY
    cur.execute("""
        UPDATE prospect_lifecycle
        SET stage = 'DISCOVERY',
            qualified_at = NULL,
            shortlisted_at = NULL,
            qualification_notes = 'Demoted to Discovery in Remediation D.1: Audited evidence non-passing (AUD-003 / AUD-010).',
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        WHERE facility_id IN (7, 35, 36, 38, 39, 48, 150)
    """)
    print("   Demoted facilities 7, 35, 36, 38, 39, 48, 150 from QUALIFIED to DISCOVERY.")

    # 2. Append-Only Ledger REPLACE Protection Trigger
    print("2. Installing trg_outreach_logs_no_replace trigger on outreach_logs...")
    cur.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_replace;")
    cur.execute("""
        CREATE TRIGGER trg_outreach_logs_no_replace
        BEFORE INSERT ON outreach_logs
        FOR EACH ROW
        WHEN NEW.id IS NOT NULL AND EXISTS (SELECT 1 FROM outreach_logs WHERE id = NEW.id)
        BEGIN
            SELECT RAISE(ABORT, 'outreach_logs is append-only: replacing or reusing existing id is strictly forbidden');
        END;
    """)
    print("   Created trigger trg_outreach_logs_no_replace.")

    conn.commit()
    conn.close()

    # Reconnect and run PRAGMAs
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    integ = cur.execute("PRAGMA integrity_check;").fetchone()[0]
    print(f"PRAGMA integrity_check: {integ}")
    if integ != "ok":
        raise RuntimeError(f"Database integrity check failed: {integ}")

    fk_violations = cur.execute("PRAGMA foreign_key_check;").fetchall()
    print(f"PRAGMA foreign_key_check violations: {len(fk_violations)}")
    if fk_violations:
        raise RuntimeError(f"Foreign key violations found: {fk_violations}")

    # Verify counts
    stage_counts = dict(cur.execute("SELECT stage, count(*) FROM prospect_lifecycle GROUP BY stage").fetchall())
    print(f"Post-migration facility stage counts: {stage_counts}")
    assert stage_counts == {"DISCOVERY": 462, "QUALIFIED": 124, "SHORTLISTED": 29}, f"Unexpected stage counts: {stage_counts}"

    conn.close()

    post_hash = get_file_hash(p)
    post_size = p.stat().st_size
    print(f"Post-migration SHA-256: {post_hash} ({post_size:,} bytes)")
    print("=== Remediation D.1 Database Migration Complete ===")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "data/prospects.db"
    run_migration(target)
