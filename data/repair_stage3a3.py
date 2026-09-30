import sqlite3
from pathlib import Path

def apply_stage3a3_repair(db_path: Path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    # 1. Reconcile Beasley (Facility #1 / Company #1)
    cur.execute("""
        UPDATE companies
        SET corporate_address = '770 Uvalda Hwy, Hazlehurst, GA 31539, USA'
        WHERE id = 1
    """)
    cur.execute("""
        UPDATE facilities
        SET physical_address = '770 Uvalda Hwy', postal_code = '31539'
        WHERE id = 1
    """)
    cur.execute("""
        UPDATE evidence_sources
        SET notes = 'Primary corporate website for Beasley Forest Products / Beasley Group. Hazlehurst Sawmill operating site verified at 770 Uvalda Hwy, Hazlehurst, GA 31539 (confirmed by official contact directory, OSHA 2024 inspection, and Georgia corporate registry).'
        WHERE id = 1
    """)

    # Check if a physical_address claim already exists for Beasley
    existing_b_claim = cur.execute(
        "SELECT id FROM claims WHERE facility_id = 1 AND claim_field = 'physical_address'"
    ).fetchone()

    if existing_b_claim:
        cur.execute("""
            UPDATE claims
            SET claimed_value = '770 Uvalda Hwy, Hazlehurst, GA 31539, US',
                verification_status = 'VERIFIED',
                is_current_accepted = 1,
                claim_notes = 'Verified operating facility address of Beasley Forest Products Hazlehurst Sawmill (confirmed by official corporate website, OSHA 2024 inspection, and Georgia corporate registry).'
            WHERE id = ?
        """, (existing_b_claim[0],))
    else:
        cur.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                1, 'physical_address', '770 Uvalda Hwy, Hazlehurst, GA 31539, US',
                'VERIFIED', 1,
                'Verified operating facility address of Beasley Forest Products Hazlehurst Sawmill (confirmed by official corporate website, OSHA 2024 inspection, and Georgia corporate registry).',
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
        """)
        b_claim_id = cur.lastrowid
        cur.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship)
            VALUES (?, 1, 'SUPPORTS')
        """, (b_claim_id,))

    # 2. Reconcile CSP (Facility #18 / Company #19)
    cur.execute("""
        UPDATE companies
        SET corporate_address = '1604 Prosperity Road, Toledo, OH 43612, USA'
        WHERE id = (SELECT company_id FROM facilities WHERE id = 18)
    """)
    cur.execute("""
        UPDATE facilities
        SET physical_address = '1604 Prosperity Road', postal_code = '43612'
        WHERE id = 18
    """)
    cur.execute("""
        UPDATE claims
        SET claimed_value = '1604 Prosperity Road, Toledo, OH 43612, US'
        WHERE id = 87
    """)
    cur.execute("""
        UPDATE evidence_sources
        SET source_url = 'https://coilsteelprocessing.com/shipping-receiving/',
            notes = 'Operating facility: 1604 Prosperity Road, Toledo, OH 43612. Explicit published operational rule mandates overhead crane or sheet lifter loading; box trucks and dry vans prohibited; flatbed requirement verified. Note: planned expansion at 5601 Enterprise Blvd targeted for Q4 2026 under development (not current operating plant).'
        WHERE id = 38
    """)

    conn.commit()

    # Integrity check
    fk_errors = cur.execute("PRAGMA foreign_key_check;").fetchall()
    integrity = cur.execute("PRAGMA integrity_check;").fetchall()
    print("FK errors:", fk_errors)
    print("Integrity check:", integrity)

    # Verification queries
    print("Beasley Company Corporate Address:", cur.execute("SELECT corporate_address FROM companies WHERE id = 1").fetchone()[0])
    print("Beasley Facility Address:", cur.execute("SELECT physical_address, city, state_prov, postal_code FROM facilities WHERE id = 1").fetchone())
    print("Beasley Address Claim:", cur.execute("SELECT id, claimed_value, verification_status, is_current_accepted FROM claims WHERE facility_id = 1 AND claim_field = 'physical_address'").fetchone())
    print()
    print("CSP Company Corporate Address:", cur.execute("SELECT corporate_address FROM companies WHERE id = (SELECT company_id FROM facilities WHERE id = 18)").fetchone()[0])
    print("CSP Facility Address:", cur.execute("SELECT physical_address, city, state_prov, postal_code FROM facilities WHERE id = 18").fetchone())
    print("CSP Address Claim (id 87):", cur.execute("SELECT id, claimed_value, verification_status, is_current_accepted FROM claims WHERE id = 87").fetchone())
    print("CSP Evidence Source (id 38):", cur.execute("SELECT source_url, notes FROM evidence_sources WHERE id = 38").fetchone())
    print("Total claims in DB:", cur.execute("SELECT count(*) FROM claims").fetchone()[0])

    conn.close()

if __name__ == "__main__":
    apply_stage3a3_repair(Path("data/prospects.db"))
