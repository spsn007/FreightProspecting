"""
FreightProspecting V1 — Stage 2.1 Schema Migration Script
Performs safe, transactional migration from suppression_status_records to suppressions.
1. Creates verified point-in-time backup.
2. Inspects row count of suppression_status_records.
3. Migrates table structure and any rows transactionally.
4. Verifies post-migration state.
"""

from pathlib import Path
import sqlite3
import sys

# Ensure project root is on sys.path
PROJECT_ROOT = Path("D:/FreightProspecting")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.backend.db.backup import create_backup
from src.backend.db.connection import create_connection, get_db_path

DB_PATH = get_db_path()


def run_migration():
    print("=" * 70)
    print("STAGE 2.1 SCHEMA MIGRATION: suppression_status_records -> suppressions")
    print(f"Target Database: {DB_PATH}")
    print("=" * 70)

    if not DB_PATH.exists():
        print(f"ERROR: Database file not found at {DB_PATH}")
        sys.exit(1)

    # 1. Create point-in-time SQLite backup
    print("\n[Step 1] Creating point-in-time backup...")
    backup_file = create_backup(DB_PATH)
    print(f"  Backup created: {backup_file}")

    # 2. Verify backup exists and is readable
    print("\n[Step 2] Verifying backup integrity...")
    if not backup_file.exists():
        print(f"  ERROR: Backup file {backup_file} does not exist!")
        sys.exit(1)
    backup_size = backup_file.stat().st_size
    print(f"  Backup file size: {backup_size} bytes")

    b_conn = sqlite3.connect(str(backup_file))
    b_cur = b_conn.cursor()
    b_tables = [r[0] for r in b_cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    print(f"  Backup readable, table count: {len(b_tables)}")
    b_conn.close()

    # 3. Inspect existing database & check if suppression_status_records has rows
    print("\n[Step 3] Inspecting production database...")
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Check sqlite_master for existing objects
    cur = conn.cursor()
    cur.execute("SELECT type, name FROM sqlite_master WHERE name IN ('suppression_status_records', 'suppressions')")
    found_objs = {r["name"]: r["type"] for r in cur.fetchall()}
    print(f"  Found objects in sqlite_master: {found_objs}")

    row_count = 0
    if "suppression_status_records" in found_objs and found_objs["suppression_status_records"] == "table":
        cur.execute("SELECT count(*) FROM suppression_status_records")
        row_count = cur.fetchone()[0]
        print(f"  Existing rows in 'suppression_status_records': {row_count}")
    else:
        print("  Table 'suppression_status_records' does not exist as a physical table.")

    # 4. Perform Transactional Migration
    print("\n[Step 4] Executing transactional migration...")
    try:
        conn.execute("BEGIN TRANSACTION;")

        # A. Drop view 'suppressions' if present
        if found_objs.get("suppressions") == "view":
            print("  Dropping view 'suppressions'...")
            conn.execute("DROP VIEW IF EXISTS suppressions;")

        # B. Create table 'suppressions' if not exists
        print("  Creating physical table 'suppressions'...")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS suppressions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_type TEXT NOT NULL CHECK(scope_type IN ('COMPANY', 'FACILITY', 'COMPANY_LANE', 'FACILITY_LANE', 'GLOBAL_LANE')),
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                facility_id INTEGER REFERENCES facilities(id) ON DELETE CASCADE,
                origin_country TEXT CHECK(origin_country IS NULL OR origin_country IN ('US', 'CA')),
                origin_state_prov TEXT,
                origin_city TEXT,
                dest_country TEXT CHECK(dest_country IS NULL OR dest_country IN ('US', 'CA')),
                dest_state_prov TEXT,
                dest_city TEXT,
                suppression_status TEXT NOT NULL CHECK(suppression_status IN ('NORMAL_PROSPECT', 'EXISTING_CUSTOMER', 'ALREADY_ROUTED', 'DO_NOT_CONTACT')),
                reason_notes TEXT NOT NULL,
                assigned_by TEXT NOT NULL DEFAULT 'USER',
                effective_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                CHECK (
                    (scope_type = 'COMPANY' AND company_id IS NOT NULL AND facility_id IS NULL AND origin_state_prov IS NULL) OR
                    (scope_type = 'FACILITY' AND facility_id IS NOT NULL AND company_id IS NULL AND origin_state_prov IS NULL) OR
                    (scope_type = 'COMPANY_LANE' AND company_id IS NOT NULL AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL) OR
                    (scope_type = 'FACILITY_LANE' AND facility_id IS NOT NULL AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL) OR
                    (scope_type = 'GLOBAL_LANE' AND company_id IS NULL AND facility_id IS NULL AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL)
                )
            );
            """
        )

        # C. Migrate rows if table existed and had rows
        if "suppression_status_records" in found_objs and found_objs["suppression_status_records"] == "table":
            if row_count > 0:
                print(f"  Migrating {row_count} rows from suppression_status_records to suppressions...")
                conn.execute(
                    """
                    INSERT INTO suppressions (
                        id, scope_type, company_id, facility_id,
                        origin_country, origin_state_prov, origin_city,
                        dest_country, dest_state_prov, dest_city,
                        suppression_status, reason_notes, assigned_by, effective_date
                    )
                    SELECT
                        id, scope_type, company_id, facility_id,
                        origin_country, origin_state_prov, origin_city,
                        dest_country, dest_state_prov, dest_city,
                        suppression_status, reason_notes, assigned_by, effective_date
                    FROM suppression_status_records;
                    """
                )
                print(f"  Successfully copied {row_count} rows.")
            else:
                print("  Zero rows to migrate.")

            # D. Drop old indexes and table
            print("  Dropping legacy indexes and table 'suppression_status_records'...")
            conn.execute("DROP INDEX IF EXISTS idx_suppression_company;")
            conn.execute("DROP INDEX IF EXISTS idx_suppression_facility;")
            conn.execute("DROP TABLE suppression_status_records;")

        # E. Create corrected indexes on 'suppressions'
        print("  Creating indexes on physical table 'suppressions'...")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_suppression_company ON suppressions(company_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_suppression_facility ON suppressions(facility_id);")

        conn.commit()
        print("  Transaction committed successfully.")
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"  MIGRATION FAILED: {e}. Transaction rolled back.")
        sys.exit(1)

    # 5. Verify Post-Migration State
    print("\n[Step 5] Verifying post-migration state...")
    cur = conn.cursor()
    cur.execute("SELECT type, name FROM sqlite_master WHERE name IN ('suppression_status_records', 'suppressions')")
    post_objs = {r["name"]: r["type"] for r in cur.fetchall()}
    print(f"  Post-migration objects in sqlite_master: {post_objs}")

    assert "suppressions" in post_objs and post_objs["suppressions"] == "table", (
        "ASSERTION FAILED: 'suppressions' is not a physical table!"
    )
    assert "suppression_status_records" not in post_objs, (
        "ASSERTION FAILED: 'suppression_status_records' still exists!"
    )

    cur.execute("SELECT count(*) FROM suppressions")
    new_count = cur.fetchone()[0]
    print(f"  Rows in new 'suppressions' table: {new_count} (expected: {row_count})")
    assert new_count == row_count, f"Row count mismatch! {new_count} != {row_count}"

    conn.close()
    print("\nSTAGE 2.1 MIGRATION SUCCESSFUL!")


if __name__ == "__main__":
    run_migration()
