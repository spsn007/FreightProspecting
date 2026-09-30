"""
FreightProspecting V1 — Batch 3 Final Closure Remediation Script
Executes serialized database mutations to resolve Codex Batch 3 audit blockers:
1. Append-only supersession of Claim 2743 (Tolko Armstrong Division commercial carrier use -> UNKNOWN)
2. Append-only supersession of Claim 2747 (Precision Strip Minster fleet relationship type -> UNKNOWN)
3. Append-only supersession of Claim 2748 (O'Neal Steel Birmingham commercial carrier use -> UNKNOWN)
4. Append-only supersession of Claim 2752 (Peerless Steel Troy fleet relationship type -> UNKNOWN)
5. Conservative contact correction for Contact 666 (Rex Lumber Chris Brown: role -> OPERATIONS, procurement -> UNKNOWN)
6. Conservative contact correction for Contact 669 (Two Rivers Jody King: exact title -> 'Demopolis General Manager', phone_directness -> GENERAL_SWITCHBOARD, procurement -> UNKNOWN)
"""

import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path("data/prospects.db")
EXPECTED_STARTING_HASH = "321200AB1C3070A2CC233640D3E8ED8984645A42576321A8E14DEBCBE6B8C670"


def main():
    cur_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    print(f"[REMEDIATE] Starting DB hash: {cur_hash}")
    assert cur_hash == EXPECTED_STARTING_HASH, f"Hash mismatch! Expected {EXPECTED_STARTING_HASH}, got {cur_hash}"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        # Pre-checks
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok", f"Integrity check failed: {integrity}"
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert len(fk) == 0, f"Foreign key check failed: {fk}"

        # -------------------------------------------------------------
        # 1. TOLKO INDUSTRIES LTD (Company 71, Facility 81)
        # -------------------------------------------------------------
        c2743 = conn.execute("SELECT * FROM claims WHERE id = 2743").fetchone()
        assert c2743 is not None and c2743["is_current_accepted"] == 1
        assert c2743["facility_id"] == 81
        assert c2743["claim_field"] == "commercial_carrier_use"

        print("[REMEDIATE] Superseding Claim 2743 (Tolko Armstrong commercial_carrier_use)...")
        conn.execute("UPDATE claims SET is_current_accepted = 0, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = 2743")
        conn.execute("UPDATE facilities SET commercial_carrier_use = 'UNKNOWN', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = 81")
        
        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                81, 'commercial_carrier_use', 'UNKNOWN', 'UNKNOWN',
                1, 'Corporate logistics webpage (tolko.com/company/logistics/) describes general corporate transport partnerships but lacks facility-specific shipping/carrier instructions for Armstrong Division. Reverts to honest UNKNOWN.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c2743_id = cur.lastrowid
        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 749, 'CONTEXT', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c2743_id,))
        print(f"  -> New Claim {new_c2743_id} inserted, backed by Source 749.")

        # -------------------------------------------------------------
        # 2. PRECISION STRIP, INC. (Company 105, Facility 134)
        # -------------------------------------------------------------
        c2747 = conn.execute("SELECT * FROM claims WHERE id = 2747").fetchone()
        assert c2747 is not None and c2747["is_current_accepted"] == 1
        assert c2747["facility_id"] == 134
        assert c2747["claim_field"] == "fleet_relationship_type"

        print("[REMEDIATE] Superseding Claim 2747 (Precision Strip Minster fleet_relationship_type)...")
        conn.execute("UPDATE claims SET is_current_accepted = 0, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = 2747")
        conn.execute("UPDATE facilities SET fleet_relationship_type = 'UNKNOWN', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = 134")

        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                134, 'fleet_relationship_type', 'UNKNOWN', 'UNKNOWN',
                1, 'Official shipping & receiving page confirms fleet of over 200 trucks (verifying private_fleet_present = VERIFIED_PRESENT in Claim 2746), but provides no primary-source legal ownership structure for Minster Facility. Reverts to honest UNKNOWN.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c2747_id = cur.lastrowid
        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 752, 'CONTEXT', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c2747_id,))
        print(f"  -> New Claim {new_c2747_id} inserted, backed by Source 752.")

        # -------------------------------------------------------------
        # 3. O'NEAL STEEL (Company 217, Facility 262)
        # -------------------------------------------------------------
        c2748 = conn.execute("SELECT * FROM claims WHERE id = 2748").fetchone()
        assert c2748 is not None and c2748["is_current_accepted"] == 1
        assert c2748["facility_id"] == 262
        assert c2748["claim_field"] == "commercial_carrier_use"

        print("[REMEDIATE] Superseding Claim 2748 (O'Neal Steel Birmingham commercial_carrier_use)...")
        conn.execute("UPDATE claims SET is_current_accepted = 0, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = 2748")
        conn.execute("UPDATE facilities SET commercial_carrier_use = 'UNKNOWN', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = 262")

        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                262, 'commercial_carrier_use', 'UNKNOWN', 'UNKNOWN',
                1, 'Corporate sales terms (onealsteel.com/terms-and-conditions/) define customer pickup & common carrier delivery terms across O''Neal, but do not provide facility-specific outside carrier routing or operational carrier dispatch instructions for Birmingham. Reverts to honest UNKNOWN.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c2748_id = cur.lastrowid
        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 753, 'CONTEXT', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c2748_id,))
        print(f"  -> New Claim {new_c2748_id} inserted, backed by Source 753.")

        # -------------------------------------------------------------
        # 4. PEERLESS STEEL COMPANY (Company 395, Facility 482)
        # -------------------------------------------------------------
        c2752 = conn.execute("SELECT * FROM claims WHERE id = 2752").fetchone()
        assert c2752 is not None and c2752["is_current_accepted"] == 1
        assert c2752["facility_id"] == 482
        assert c2752["claim_field"] == "fleet_relationship_type"

        print("[REMEDIATE] Superseding Claim 2752 (Peerless Steel Troy fleet_relationship_type)...")
        conn.execute("UPDATE claims SET is_current_accepted = 0, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = 2752")
        conn.execute("UPDATE facilities SET fleet_relationship_type = 'UNKNOWN', updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = 482")

        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                482, 'fleet_relationship_type', 'UNKNOWN', 'UNKNOWN',
                1, 'Official website confirms operating fleet of trucks and common carrier delivery (preserving private_fleet_present = VERIFIED_PRESENT and commercial_carrier_use = VERIFIED), but does not document legal asset ownership structure. Reverts to honest UNKNOWN.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c2752_id = cur.lastrowid
        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 755, 'CONTEXT', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c2752_id,))
        print(f"  -> New Claim {new_c2752_id} inserted, backed by Source 755.")

        # -------------------------------------------------------------
        # 5. CONTACT 666 (Rex Lumber, Chris Brown)
        # -------------------------------------------------------------
        con666 = conn.execute("SELECT * FROM contacts WHERE id = 666").fetchone()
        assert con666 is not None
        assert con666["person_name"] == "Chris Brown"
        print("[REMEDIATE] Updating Contact 666 (Chris Brown: role -> OPERATIONS, procurement -> UNKNOWN)...")
        conn.execute("""
            UPDATE contacts
            SET role_category = 'OPERATIONS',
                outbound_shipping_procurement_relevance = 'UNKNOWN'
            WHERE id = 666
        """)

        # -------------------------------------------------------------
        # 6. CONTACT 669 (Two Rivers Lumber, Jody King)
        # -------------------------------------------------------------
        con669 = conn.execute("SELECT * FROM contacts WHERE id = 669").fetchone()
        assert con669 is not None
        assert con669["person_name"] == "Jody King"
        print("[REMEDIATE] Updating Contact 669 (Jody King: exact title -> 'Demopolis General Manager', phone_directness -> GENERAL_SWITCHBOARD, procurement -> UNKNOWN)...")
        conn.execute("""
            UPDATE contacts
            SET exact_published_title = 'Demopolis General Manager',
                phone_directness = 'GENERAL_SWITCHBOARD',
                outbound_shipping_procurement_relevance = 'UNKNOWN'
            WHERE id = 669
        """)

        conn.commit()
        print("[REMEDIATE] All mutations committed successfully.")

    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

    # -----------------------------------------------------------------
    # POST-MUTATION INTEGRITY CHECKS
    # -----------------------------------------------------------------
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok", f"Integrity check failed: {integrity}"
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert len(fk) == 0, f"Foreign key check failed: {fk}"
    print("[POST-CHECK] PRAGMA integrity_check = ok and foreign_key_check = 0.")

    # Check duplicate accepted claims across all 10 subject columns
    subjects = [
        "company_id", "company_relationship_id", "facility_id", "facility_commodity_id",
        "contact_id", "freight_demand_signal_id", "load_opportunity_id", "carrier_id",
        "carrier_lane_activity_id", "capacity_posting_id"
    ]
    for subj in subjects:
        dups = conn.execute(f"""
            SELECT {subj}, claim_field, count(*)
            FROM claims
            WHERE is_current_accepted = 1 AND {subj} IS NOT NULL
            GROUP BY {subj}, claim_field
            HAVING count(*) > 1
        """).fetchall()
        assert len(dups) == 0, f"Duplicate current accepted claims found for {subj}: {dups}"
    print("[POST-CHECK] 0 duplicate current accepted claims across all 10 subjects.")

    # Check orphan claims
    orphans = conn.execute("""
        SELECT c.id FROM claims c
        LEFT JOIN claim_evidence ce ON c.id = ce.claim_id
        WHERE ce.id IS NULL
    """).fetchall()
    assert len(orphans) == 0, f"Orphan claims found: {orphans}"
    print("[POST-CHECK] 0 orphan claims.")

    # Check orphan claim_evidence
    orphan_evidence = conn.execute("""
        SELECT ce.id FROM claim_evidence ce
        LEFT JOIN claims c ON ce.claim_id = c.id
        WHERE c.id IS NULL
    """).fetchall()
    assert len(orphan_evidence) == 0, f"Orphan claim_evidence found: {orphan_evidence}"
    print("[POST-CHECK] 0 orphan claim_evidence.")

    # Verify lifecycle invariant (0 diff across all 653 facilities)
    total_facs = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]
    assert total_facs == 653, f"Expected 653 facilities, got {total_facs}"
    total_life = conn.execute("SELECT count(*) FROM prospect_lifecycle").fetchone()[0]
    assert total_life == 653, f"Expected 653 lifecycle rows, got {total_life}"
    print("[POST-CHECK] Lifecycle invariant preserved: exactly 653 facilities and lifecycle rows.")

    # Verify operational tables strictly 0
    operational_tables = [
        "outreach_logs",
        "load_opportunities",
        "freight_demand_signals",
        "capacity_postings",
        "load_capacity_matches",
    ]
    for tbl in operational_tables:
        cnt = conn.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        assert cnt == 0, f"Operational table {tbl} has {cnt} rows! Must be 0."
    print("[POST-CHECK] All operational tables strictly 0.")

    # Verify SAFER-only active accepted VERIFIED claims = 0
    safer_only = conn.execute("""
        SELECT c.id
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.is_current_accepted = 1
          AND c.verification_status = 'VERIFIED'
        GROUP BY c.id
        HAVING count(DISTINCT es.source_type) = 1
           AND MAX(es.source_type) = 'FMCSA_SAFER'
    """).fetchall()
    assert len(safer_only) == 0, f"SAFER-only verified claims found: {safer_only}"
    print("[POST-CHECK] SAFER-only active verified claims = 0.")

    conn.close()

    new_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    print(f"[REMEDIATE] Final mutated DB hash: {new_hash}")
    return new_hash


if __name__ == "__main__":
    main()
