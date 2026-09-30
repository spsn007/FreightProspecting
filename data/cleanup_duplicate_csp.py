import sqlite3
from pathlib import Path

def cleanup_duplicate_csp(db_path: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    # 1. Verify facility 44 exists and is indeed duplicate CSP
    f44 = cur.execute("SELECT id, facility_name, physical_address FROM facilities WHERE id = 44").fetchone()
    if not f44:
        print("No facility 44 found. Already clean.")
        conn.close()
        return

    print("Found facility 44:", f44)

    # 2. Delete claim evidence for claims of facility 44, commodity 44, contact 54
    cur.execute("""
        DELETE FROM claim_evidence
        WHERE claim_id IN (
            SELECT id FROM claims WHERE facility_id = 44 OR facility_commodity_id = 44 OR contact_id = 54
        )
    """)

    # 3. Delete claims
    cur.execute("""
        DELETE FROM claims
        WHERE facility_id = 44 OR facility_commodity_id = 44 OR contact_id = 54
    """)

    # 4. Delete contact 54
    cur.execute("DELETE FROM contacts WHERE id = 54")

    # 5. Delete facility commodity 44
    cur.execute("DELETE FROM facility_commodities WHERE id = 44")

    # 6. Delete prospect lifecycle for facility 44
    cur.execute("DELETE FROM prospect_lifecycle WHERE facility_id = 44")

    # 7. Delete evidence source 97
    cur.execute("DELETE FROM evidence_sources WHERE id = 97")

    # 8. Delete discovery intake audit duplicate row (id = 43)
    cur.execute("DELETE FROM discovery_intake_audit WHERE id = 43")

    # 9. Delete facility 44
    cur.execute("DELETE FROM facilities WHERE id = 44")

    # 10. Update discovery intake audit row 17 (the original CSP record) to reflect 1604 Prosperity Road
    cur.execute("""
        UPDATE discovery_intake_audit
        SET intake_fingerprint = 'coilsteelprocessingcsp|1604prosperityroad|toledo|oh|us',
            facility_address = '1604 Prosperity Road'
        WHERE id = 17
    """)

    # 11. Update sqlite_sequence
    cur.execute("UPDATE sqlite_sequence SET seq = 43 WHERE name = 'facilities'")
    cur.execute("UPDATE sqlite_sequence SET seq = 43 WHERE name = 'facility_commodities'")
    cur.execute("UPDATE sqlite_sequence SET seq = 53 WHERE name = 'contacts'")
    cur.execute("UPDATE sqlite_sequence SET seq = 42 WHERE name = 'discovery_intake_audit'")

    conn.commit()

    # Integrity verification
    fk_errors = cur.execute("PRAGMA foreign_key_check;").fetchall()
    integrity = cur.execute("PRAGMA integrity_check;").fetchall()
    print("FK errors:", fk_errors)
    print("Integrity check:", integrity)

    # Count verifications
    fac_count = cur.execute("SELECT count(*) FROM facilities").fetchone()[0]
    lifecycle_counts = cur.execute("SELECT stage, count(*) FROM prospect_lifecycle GROUP BY stage").fetchall()
    audit_counts = cur.execute("SELECT intake_status, count(*) FROM discovery_intake_audit GROUP BY intake_status").fetchall()
    print("Total facilities:", fac_count)
    print("Lifecycle counts:", lifecycle_counts)
    print("Discovery intake audit counts:", audit_counts)

    conn.close()

if __name__ == "__main__":
    cleanup_duplicate_csp(Path("data/prospects.db"))
