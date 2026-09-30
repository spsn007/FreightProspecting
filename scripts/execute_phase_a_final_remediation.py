import sqlite3
import datetime
import hashlib
from pathlib import Path

DB_PATH = Path("data/prospects.db")
EXPECTED_START_HASH = "635DA7D4AEDD0BB01E1A8DB317DA473F17B91E317582661E0973BE31AD260792"

def main():
    # 1. Verify starting hash
    with open(DB_PATH, "rb") as f:
        curr_hash = hashlib.sha256(f.read()).hexdigest().upper()
    assert curr_hash == EXPECTED_START_HASH, f"Hash mismatch: expected {EXPECTED_START_HASH}, got {curr_hash}"
    print(f"Verified starting DB hash: {curr_hash}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        with conn:
            # =========================================================================
            # BLOCKER 1: Precision Strip (CID 105, FID 134) Claim 2762
            # Supersede 2762 (broker_friendly_status = VERIFIED_ACCEPTS) to UNKNOWN
            # =========================================================================
            conn.execute("""
                UPDATE claims
                SET is_current_accepted = 0, updated_at = ?
                WHERE id = 2762
            """, (now_iso,))
            print("Superseded Claim 2762 (is_current_accepted = 0)")

            cur = conn.execute("""
                INSERT INTO claims (
                    facility_id, claim_field, claimed_value, verification_status,
                    is_current_accepted, claim_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                134, "broker_friendly_status", "UNKNOWN", "UNKNOWN",
                1, "Precision Strip provides 3PL services as a logistics provider; primary source does not prove shipper accepts outside freight brokers.",
                now_iso, now_iso
            ))
            new_claim_2762_id = cur.lastrowid
            conn.execute("""
                INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
                VALUES (?, ?, ?, ?)
            """, (new_claim_2762_id, 758, "SUPPORTS", now_iso))
            print(f"Inserted replacement Claim {new_claim_2762_id} for FID 134 broker_friendly_status = UNKNOWN")

            conn.execute("""
                UPDATE facilities
                SET broker_friendly_status = 'UNKNOWN', updated_at = ?
                WHERE id = 134
            """, (now_iso,))
            print("Updated FID 134 broker_friendly_status = 'UNKNOWN'")

            # =========================================================================
            # BLOCKER 2: Precision Strip Contact 671 (Jamey Eilerman) Claim 2763
            # Supersede 2763 (phone with source 758) -> replacement claim with source 188
            # Correct Contact 671 exact_published_title and broker_procurement_relevance
            # =========================================================================
            conn.execute("""
                UPDATE claims
                SET is_current_accepted = 0, updated_at = ?
                WHERE id = 2763
            """, (now_iso,))
            print("Superseded Claim 2763 (is_current_accepted = 0)")

            cur = conn.execute("""
                INSERT INTO claims (
                    contact_id, claim_field, claimed_value, verification_status,
                    is_current_accepted, claim_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                671, "phone_number", "419-628-2343", "VERIFIED",
                1, "Minster facility general switchboard route published on corporate locations directory.",
                now_iso, now_iso
            ))
            new_claim_2763_id = cur.lastrowid
            conn.execute("""
                INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
                VALUES (?, ?, ?, ?)
            """, (new_claim_2763_id, 188, "SUPPORTS", now_iso))
            print(f"Inserted replacement Claim {new_claim_2763_id} for Contact 671 phone_number with source 188")

            conn.execute("""
                UPDATE contacts
                SET exact_published_title = 'Main Contact',
                    broker_procurement_relevance = 'UNKNOWN'
                WHERE id = 671
            """)
            print("Updated Contact 671: exact_published_title = 'Main Contact', broker_procurement_relevance = 'UNKNOWN'")

            # =========================================================================
            # BLOCKERS 3 & 4: Worthington Steel (CID 91, FID 111) Claims 2767 & 2768
            # Rescope to company scope (CID 91); revert FID 111 carrier/broker to UNKNOWN
            # =========================================================================
            conn.execute("""
                UPDATE claims
                SET is_current_accepted = 0, updated_at = ?
                WHERE id = 2767
            """, (now_iso,))
            print("Superseded Claim 2767 (is_current_accepted = 0)")

            cur = conn.execute("""
                INSERT INTO claims (
                    company_id, claim_field, claimed_value, verification_status,
                    is_current_accepted, claim_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                91, "commercial_carrier_use", "VERIFIED", "VERIFIED",
                1, "Company-wide carrier information portal onboards outside fleet companies and owner operators across dry van and flatbed modes.",
                now_iso, now_iso
            ))
            new_claim_2767_id = cur.lastrowid
            conn.execute("""
                INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
                VALUES (?, ?, ?, ?)
            """, (new_claim_2767_id, 760, "SUPPORTS", now_iso))
            print(f"Inserted company-level Claim {new_claim_2767_id} for CID 91 commercial_carrier_use = VERIFIED")

            conn.execute("""
                UPDATE claims
                SET is_current_accepted = 0, updated_at = ?
                WHERE id = 2768
            """, (now_iso,))
            print("Superseded Claim 2768 (is_current_accepted = 0)")

            cur = conn.execute("""
                INSERT INTO claims (
                    company_id, claim_field, claimed_value, verification_status,
                    is_current_accepted, claim_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                91, "broker_friendly_status", "VERIFIED_ACCEPTS", "VERIFIED",
                1, "Official carrier onboarding form explicitly provides 'Broker' option under Company Type.",
                now_iso, now_iso
            ))
            new_claim_2768_id = cur.lastrowid
            conn.execute("""
                INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
                VALUES (?, ?, ?, ?)
            """, (new_claim_2768_id, 760, "SUPPORTS", now_iso))
            print(f"Inserted company-level Claim {new_claim_2768_id} for CID 91 broker_friendly_status = VERIFIED_ACCEPTS")

            conn.execute("""
                UPDATE facilities
                SET commercial_carrier_use = 'UNKNOWN',
                    broker_friendly_status = 'UNKNOWN',
                    updated_at = ?
                WHERE id = 111
            """, (now_iso,))
            print("Updated FID 111: commercial_carrier_use = 'UNKNOWN', broker_friendly_status = 'UNKNOWN'")

            # =========================================================================
            # BLOCKER 5: Metals USA (CID 218, FID 264) Claim 2775
            # Rescope to company scope (CID 218); revert FID 264 carrier to UNKNOWN
            # =========================================================================
            conn.execute("""
                UPDATE claims
                SET is_current_accepted = 0, updated_at = ?
                WHERE id = 2775
            """, (now_iso,))
            print("Superseded Claim 2775 (is_current_accepted = 0)")

            cur = conn.execute("""
                INSERT INTO claims (
                    company_id, claim_field, claimed_value, verification_status,
                    is_current_accepted, claim_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                218, "commercial_carrier_use", "VERIFIED", "VERIFIED",
                1, "Corporate website explicitly documents partnership with freight carriers and common carriers for customer shipments.",
                now_iso, now_iso
            ))
            new_claim_2775_id = cur.lastrowid
            conn.execute("""
                INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
                VALUES (?, ?, ?, ?)
            """, (new_claim_2775_id, 763, "SUPPORTS", now_iso))
            print(f"Inserted company-level Claim {new_claim_2775_id} for CID 218 commercial_carrier_use = VERIFIED")

            conn.execute("""
                UPDATE facilities
                SET commercial_carrier_use = 'UNKNOWN',
                    updated_at = ?
                WHERE id = 264
            """, (now_iso,))
            print("Updated FID 264: commercial_carrier_use = 'UNKNOWN'")

        # PRAGMA checks and WAL truncate checkpoint
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok", f"Integrity check failed: {integrity}"
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert len(fk_violations) == 0, f"Foreign key violations: {fk_violations}"
        print("Database passed PRAGMA integrity_check and PRAGMA foreign_key_check (0 violations)")

    finally:
        conn.close()

    # Calculate and report new candidate hash
    with open(DB_PATH, "rb") as f:
        new_hash = hashlib.sha256(f.read()).hexdigest().upper()
    print(f"\nNEW CANDIDATE HASH: {new_hash}")

if __name__ == "__main__":
    main()
