"""
FreightProspecting V1 — Batch 2 Final Surgical Correction
Surgically remediates Northern Concrete Pipe (Company 134, Facility 163) fleet claims:
- Conservatively downgrades unsupported VERIFIED fleet claims (2728, 2729) to UNKNOWN.
- Retains historical claim records (append-only supersession).
- Updates facilities row 163 attributes to UNKNOWN.
- Leaves all other entities, claims, lifecycles, and companies completely untouched.
"""

import hashlib
import sqlite3
from pathlib import Path

from src.backend.db.opportunity import (
    RESTRICTED,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    evaluate_broker_opportunity,
)

DB_PATH = Path("data/prospects.db")
EXPECTED_PRE_HASH = "CD3DE3D6485B27DE60392BA081349884781998676A66CD70D5AF23A6FE37F062"


def main():
    cur_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    print(f"[REMEDIATE] Current DB hash: {cur_hash}")
    assert cur_hash == EXPECTED_PRE_HASH, f"Hash mismatch! Expected {EXPECTED_PRE_HASH}, got {cur_hash}"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        # 1. Verify Facility 163 state before
        fac_before = conn.execute("SELECT * FROM facilities WHERE id = 163").fetchone()
        assert fac_before is not None, "Facility 163 not found"
        assert fac_before["company_id"] == 134, f"Expected company_id 134, got {fac_before['company_id']}"
        assert fac_before["private_fleet_present"] == "VERIFIED_PRESENT"
        assert fac_before["fleet_relationship_type"] == "IN_HOUSE_OWNED"

        # Verify old claims 2728 and 2729
        c2728 = conn.execute("SELECT * FROM claims WHERE id = 2728").fetchone()
        assert c2728 is not None and c2728["is_current_accepted"] == 1
        assert c2728["claim_field"] == "private_fleet_present"

        c2729 = conn.execute("SELECT * FROM claims WHERE id = 2729").fetchone()
        assert c2729 is not None and c2729["is_current_accepted"] == 1
        assert c2729["claim_field"] == "fleet_relationship_type"

        # Verify Evidence Source 217 exists (NCP official website)
        es217 = conn.execute("SELECT * FROM evidence_sources WHERE id = 217").fetchone()
        assert es217 is not None
        assert "ncp-inc.com" in es217["source_url"]

        print("[REMEDIATE] Deactivating old claims 2728 and 2729...")
        conn.execute("UPDATE claims SET is_current_accepted = 0, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id IN (2728, 2729)")

        print("[REMEDIATE] Updating facilities row 163 to UNKNOWN fleet...")
        conn.execute("""
            UPDATE facilities
            SET private_fleet_present = 'UNKNOWN',
                fleet_relationship_type = 'UNKNOWN',
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE id = 163
        """)

        print("[REMEDIATE] Inserting new superseding UNKNOWN claims for Facility 163...")
        # New claim for private_fleet_present
        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                163, 'private_fleet_present', 'UNKNOWN', 'UNKNOWN',
                1, 'No primary source documents in-house delivery fleet; previous claim cited non-existent delivery-policy URL; general corporate site (ncp-inc.com) reviewed.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c_fleet_id = cur.lastrowid

        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 217, 'CONTEXT', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c_fleet_id,))
        print(f"  New private_fleet_present claim ID: {new_c_fleet_id} (backed by source 217)")

        # New claim for fleet_relationship_type
        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                163, 'fleet_relationship_type', 'UNKNOWN', 'UNKNOWN',
                1, 'No primary source documents in-house delivery fleet; previous claim cited non-existent delivery-policy URL; general corporate site (ncp-inc.com) reviewed.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c_rel_id = cur.lastrowid

        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 217, 'CONTEXT', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c_rel_id,))
        print(f"  New fleet_relationship_type claim ID: {new_c_rel_id} (backed by source 217)")

        conn.commit()
        print("[REMEDIATE] Transaction committed successfully.")

    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

    # ------------------------------------------------------------------
    # POST-MUTATION INTEGRITY CHECKS
    # ------------------------------------------------------------------
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok", f"Integrity check failed: {integrity}"
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert len(fk) == 0, f"Foreign key check failed: {fk}"
    print("[CHECK] PRAGMA integrity_check and foreign_key_check clean.")

    # Check Facility 163 claims state
    fac163_claims = conn.execute("""
        SELECT id, claim_field, claimed_value, verification_status, is_current_accepted
        FROM claims WHERE facility_id = 163
    """).fetchall()
    print("[CHECK] Facility 163 claims:")
    for c in fac163_claims:
        print(f"  Claim {c['id']}: {c['claim_field']} = {c['claimed_value']} ({c['verification_status']}), accepted={c['is_current_accepted']}")

    # Assert exactly 1 current accepted claim for each field
    acc_fleet = [c for c in fac163_claims if c["claim_field"] == "private_fleet_present" and c["is_current_accepted"] == 1]
    assert len(acc_fleet) == 1 and acc_fleet[0]["claimed_value"] == "UNKNOWN"

    acc_rel = [c for c in fac163_claims if c["claim_field"] == "fleet_relationship_type" and c["is_current_accepted"] == 1]
    assert len(acc_rel) == 1 and acc_rel[0]["claimed_value"] == "UNKNOWN"

    # Evaluate Northern Concrete Pipe opportunity
    ncp_opp = evaluate_broker_opportunity(134, conn=conn)
    print(f"[CHECK] Northern Concrete Pipe opportunity tier: {ncp_opp['opportunity_tier']}")
    assert ncp_opp["opportunity_tier"] == TIER_B_WORTH_CALLING, f"Expected TIER_B_WORTH_CALLING, got {ncp_opp['opportunity_tier']}"

    # Evaluate all 565 companies
    comps = conn.execute("SELECT id FROM companies WHERE id IN (SELECT DISTINCT company_id FROM facilities)").fetchall()
    assert len(comps) == 565
    counts = {
        TIER_A_PRIORITY: 0,
        TIER_B_WORTH_CALLING: 0,
        TIER_C_SECONDARY: 0,
        TIER_D_RESEARCH_NEEDED: 0,
        RESTRICTED: 0,
    }
    for c in comps:
        res = evaluate_broker_opportunity(c["id"], conn=conn)
        counts[res["opportunity_tier"]] += 1

    print(f"[CHECK] Full opportunity tier distribution: {counts}")
    assert counts[TIER_A_PRIORITY] == 12
    assert counts[TIER_B_WORTH_CALLING] == 104
    assert counts[TIER_C_SECONDARY] == 4
    assert counts[TIER_D_RESEARCH_NEEDED] == 445
    assert counts[RESTRICTED] == 0

    # Verify lifecycle invariant (0 diff across all 653 facilities)
    total_facs = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]
    assert total_facs == 653
    total_life = conn.execute("SELECT count(*) FROM prospect_lifecycle").fetchone()[0]
    assert total_life == 653

    conn.close()

    new_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    print(f"[REMEDIATE] Final DB hash: {new_hash}")
    return new_hash


if __name__ == "__main__":
    main()
