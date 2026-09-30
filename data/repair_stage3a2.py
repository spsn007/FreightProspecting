import sqlite3
from pathlib import Path

def apply_repair(db_path: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    # 1. Update facility_commodities for seeds 1-4: trailer_specs_notes and securement_tarp_notes to NULL
    cur.execute("""
        UPDATE facility_commodities
        SET trailer_specs_notes = NULL, securement_tarp_notes = NULL
        WHERE facility_id IN (1, 2, 3, 4)
    """)

    # 2. Update facility_commodities for CSP (facility 18)
    cur.execute("""
        UPDATE facility_commodities
        SET trailer_specs_notes = 'Flatbeds only; overhead crane or sheet lifter loading; dry vans/box trucks cannot be loaded.',
            securement_tarp_notes = NULL
        WHERE facility_id = 18
    """)

    # 3. Update facilities commercial_carrier_use for Beasley (1) and Kenwal (2)
    cur.execute("""
        UPDATE facilities
        SET commercial_carrier_use = 'UNKNOWN'
        WHERE id IN (1, 2)
    """)

    # 4. Remove spurious commercial_carrier_use claims for Beasley (1) and Kenwal (2)
    cur.execute("""
        DELETE FROM claim_evidence
        WHERE claim_id IN (
            SELECT id FROM claims
            WHERE facility_id IN (1, 2) AND claim_field = 'commercial_carrier_use'
        )
    """)
    cur.execute("""
        DELETE FROM claims
        WHERE facility_id IN (1, 2) AND claim_field = 'commercial_carrier_use'
    """)

    conn.commit()

    # Integrity check
    fk_errors = cur.execute("PRAGMA foreign_key_check;").fetchall()
    integrity = cur.execute("PRAGMA integrity_check;").fetchall()
    print("FK errors:", fk_errors)
    print("Integrity check:", integrity)

    # Verification queries
    print("Seeds non-null trailer/securement notes:", cur.execute(
        "SELECT count(*) FROM facility_commodities WHERE facility_id IN (1,2,3,4) AND (trailer_specs_notes IS NOT NULL OR securement_tarp_notes IS NOT NULL)"
    ).fetchone()[0])
    print("CSP commodity notes:", cur.execute(
        "SELECT trailer_specs_notes, securement_tarp_notes FROM facility_commodities WHERE facility_id = 18"
    ).fetchone())
    print("Seeds commercial_carrier_use:", cur.execute(
        "SELECT id, commercial_carrier_use FROM facilities WHERE id <= 4"
    ).fetchall())
    print("Claims for comm_carrier on seeds 1-4:", cur.execute(
        "SELECT count(*) FROM claims WHERE facility_id IN (1,2,3,4) AND claim_field = 'commercial_carrier_use'"
    ).fetchone()[0])
    print("Total claims in DB:", cur.execute("SELECT count(*) FROM claims").fetchone()[0])

    conn.close()

if __name__ == "__main__":
    apply_repair(Path("data/prospects.db"))
