import sqlite3
import sys
from pathlib import Path

def normalize_space_timestamp(val: str) -> str:
    if val and len(val) == 19 and val[10] == ' ':
        return val[:10] + 'T' + val[11:] + 'Z'
    return val

def run_remediation(db_path: Path):
    print(f"Applying Database Remediation B to {db_path}...")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF;") # To allow timestamp format updates without FK cascade noise
    
    try:
        with conn:
            # 1. Sources 13 and 14 (AUD-015)
            conn.execute("""
                UPDATE evidence_sources 
                SET source_published_at = '2019-12-01T00:00:00Z' 
                WHERE id IN (13, 14) AND source_published_at IS NULL;
            """)
            print("  [AUD-015] Updated sources 13 & 14 published_at to 2019-12-01T00:00:00Z.")

            # 2. Canonicalize timestamps (AUD-023)
            # Find all tables and their datetime/text columns
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [r[0] for r in c.fetchall()]

            total_updated = 0
            for tbl in tables:
                c.execute(f"PRAGMA table_info({tbl})")
                cols = [col[1] for col in c.fetchall()]
                for col in cols:
                    if any(term in col for term in ['_at', 'date', 'time', 'valid_from', 'valid_to']):
                        # Check if any naive space timestamps exist
                        c.execute(f"""
                            SELECT rowid, {col} FROM {tbl} 
                            WHERE {col} GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'
                        """)
                        rows = c.fetchall()
                        if rows:
                            for rowid, val in rows:
                                norm_val = normalize_space_timestamp(val)
                                conn.execute(f"UPDATE {tbl} SET {col} = ? WHERE rowid = ?", (norm_val, rowid))
                            print(f"  [AUD-023] Normalized {len(rows)} timestamps in {tbl}.{col}")
                            total_updated += len(rows)

            print(f"  [AUD-023] Total timestamps canonicalized: {total_updated}")

            # 3. Outreach Logs Append-Only Protection Triggers (AUD-025)
            conn.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_update;")
            conn.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_delete;")
            conn.execute("""
                CREATE TRIGGER trg_outreach_logs_no_update
                BEFORE UPDATE ON outreach_logs
                BEGIN
                    SELECT RAISE(ABORT, 'outreach_logs is append-only: UPDATE operations are strictly prohibited.');
                END;
            """)
            conn.execute("""
                CREATE TRIGGER trg_outreach_logs_no_delete
                BEFORE DELETE ON outreach_logs
                BEGIN
                    SELECT RAISE(ABORT, 'outreach_logs is append-only: DELETE operations are strictly prohibited.');
                END;
            """)
            print("  [AUD-025] Created unconditional append-only triggers on outreach_logs (trg_outreach_logs_no_update, trg_outreach_logs_no_delete).")

        conn.execute("PRAGMA foreign_keys = ON;")
        res = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        fk_res = conn.execute("PRAGMA foreign_key_check;").fetchall()
        print(f"  Integrity Check: {res}, FK Violations: {len(fk_res)}")
        if res != "ok" or len(fk_res) > 0:
            raise RuntimeError("Database integrity check failed!")
        print("Database Remediation B successfully applied.")

    finally:
        conn.close()

if __name__ == '__main__':
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('data/prospects.db')
    run_remediation(target)
