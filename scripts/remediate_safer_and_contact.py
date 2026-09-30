"""
FreightProspecting V1 — SAFER-Only Claim Remediation & Leslie Contact Directness Fix
Resolves the two final Batch 1 closure blockers:
1. Re-grounds or conservatively downgrades the 4 SAFER-only accepted claims (217, 232, 233, 237)
2. Sets Leslie Forest Products contact 11 email_directness to DIRECT_PERSON
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
EXPECTED_PRE_HASH = "A398DC9014B55388D40DE0E5CE68FD7CEAEF4692C55B2A121096D6C579A6AFCE"


def main():
    cur_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    print(f"[REMEDIATE] Current DB hash: {cur_hash}")
    assert cur_hash == EXPECTED_PRE_HASH, f"Hash mismatch! Expected {EXPECTED_PRE_HASH}, got {cur_hash}"

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        # ------------------------------------------------------------------
        # BLOCKER 2: Leslie Forest Products Contact 11 email_directness
        # ------------------------------------------------------------------
        print("[REMEDIATE] Updating Contact 11 (James Sangara) email_directness to DIRECT_PERSON...")
        c11_before = conn.execute("SELECT email_directness FROM contacts WHERE id = 11").fetchone()[0]
        assert c11_before == "DEPARTMENT", f"Expected Contact 11 email_directness to be DEPARTMENT, got {c11_before}"
        conn.execute("UPDATE contacts SET email_directness = 'DIRECT_PERSON' WHERE id = 11")
        c11_after = conn.execute("SELECT email_directness FROM contacts WHERE id = 11").fetchone()[0]
        assert c11_after == "DIRECT_PERSON"
        print(f"  Contact 11: {c11_before} -> {c11_after}")

        # ------------------------------------------------------------------
        # BLOCKER 1: Claim 217 — Edwards Wood Products (Facility 13)
        # ------------------------------------------------------------------
        print("[REMEDIATE] Re-grounding Claim 217 (Edwards Wood Products fleet relationship)...")
        # Verify current Claim 217
        c217 = conn.execute("SELECT * FROM claims WHERE id = 217").fetchone()
        assert c217 is not None
        # Deactivate old claim
        conn.execute("UPDATE claims SET is_current_accepted = 0 WHERE id = 217")
        # Insert new accepted claim backed by official transportation page (Source 732)
        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                13, 'fleet_relationship_type', 'IN_HOUSE_OWNED', 'VERIFIED',
                1, 'Edwards official transportation page explicitly confirms company-owned fleet of 130+ trucks dedicated to Edwards products operating within a 150 air mile radius from each facility.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c217_id = cur.lastrowid
        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 732, 'SUPPORTS', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c217_id,))
        print(f"  Claim 217 superseded by Claim {new_c217_id} (backed by Evidence Source 732: ewpi.com/services/transportation/)")

        # ------------------------------------------------------------------
        # BLOCKER 1: Claim 232 — Lindsay Precast (Facility 27)
        # ------------------------------------------------------------------
        print("[REMEDIATE] Downgrading Claim 232 (Lindsay Precast fleet relationship) to UNKNOWN...")
        c232 = conn.execute("SELECT * FROM claims WHERE id = 232").fetchone()
        assert c232 is not None
        conn.execute("UPDATE claims SET is_current_accepted = 0 WHERE id = 232")
        conn.execute("UPDATE facilities SET fleet_relationship_type = 'UNKNOWN' WHERE id = 27")
        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                27, 'fleet_relationship_type', 'UNKNOWN', 'UNKNOWN',
                1, 'No permitted corporate evidence proves an affiliated carrier entity; prior claim relied solely on SAFER registry.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c232_id = cur.lastrowid
        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 56, 'CONTEXT', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c232_id,))
        print(f"  Claim 232 superseded by Claim {new_c232_id} (UNKNOWN, backed by Evidence Source 56: lindsayprecast.com)")

        # ------------------------------------------------------------------
        # BLOCKER 1: Claim 233 — Tindall Corporation (Facility 28)
        # ------------------------------------------------------------------
        print("[REMEDIATE] Downgrading Claim 233 (Tindall Corporation fleet relationship) to UNKNOWN...")
        c233 = conn.execute("SELECT * FROM claims WHERE id = 233").fetchone()
        assert c233 is not None
        conn.execute("UPDATE claims SET is_current_accepted = 0 WHERE id = 233")
        conn.execute("UPDATE facilities SET fleet_relationship_type = 'UNKNOWN' WHERE id = 28")
        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                28, 'fleet_relationship_type', 'UNKNOWN', 'UNKNOWN',
                1, 'No permitted corporate evidence proves an affiliated carrier entity; prior claim relied solely on SAFER registry.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c233_id = cur.lastrowid
        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 58, 'CONTEXT', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c233_id,))
        print(f"  Claim 233 superseded by Claim {new_c233_id} (UNKNOWN, backed by Evidence Source 58: tindallcorp.com)")

        # ------------------------------------------------------------------
        # BLOCKER 1: Claim 237 — Bemis Manufacturing (Facility 41)
        # ------------------------------------------------------------------
        print("[REMEDIATE] Downgrading Claim 237 (Bemis Manufacturing fleet relationship) to UNKNOWN...")
        c237 = conn.execute("SELECT * FROM claims WHERE id = 237").fetchone()
        assert c237 is not None
        conn.execute("UPDATE claims SET is_current_accepted = 0 WHERE id = 237")
        conn.execute("UPDATE facilities SET fleet_relationship_type = 'UNKNOWN' WHERE id = 41")
        cur = conn.execute("""
            INSERT INTO claims (
                facility_id, claim_field, claimed_value, verification_status,
                is_current_accepted, claim_notes, created_at, updated_at
            ) VALUES (
                41, 'fleet_relationship_type', 'UNKNOWN', 'UNKNOWN',
                1, 'Permitted company documentation confirms shipping operations and commercial carrier use, but fleet asset ownership relies solely on SAFER; downgraded to UNKNOWN.',
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """)
        new_c237_id = cur.lastrowid
        conn.execute("""
            INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship, created_at)
            VALUES (?, 84, 'CONTEXT', strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (new_c237_id,))
        print(f"  Claim 237 superseded by Claim {new_c237_id} (UNKNOWN, backed by Evidence Source 84: bemismfg.com)")

        conn.commit()
        print("[REMEDIATE] All mutations committed successfully.")

    except Exception as e:
        conn.rollback()
        conn.close()
        raise e

    # ------------------------------------------------------------------
    # POST-MUTATION CHECKS
    # ------------------------------------------------------------------
    # Integrity
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok", f"Integrity check failed: {integrity}"
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert len(fk) == 0, f"Foreign key check failed: {fk}"
    print("[CHECK] PRAGMA integrity_check and foreign_key_check clean.")

    # SAFER-only active accepted verified claims check
    safer_active = conn.execute("""
        SELECT c.id, c.facility_id, c.claim_field, c.claimed_value, es.source_title_publisher
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE c.is_current_accepted = 1
          AND c.verification_status = 'VERIFIED'
          AND (es.source_title_publisher LIKE '%SAFER%' OR es.source_url LIKE '%safer%')
    """).fetchall()
    print(f"[CHECK] Active accepted VERIFIED claims solely supported by SAFER: {len(safer_active)}")
    assert len(safer_active) == 0, f"Expected 0 SAFER-only active claims, found: {safer_active}"

    # Broker opportunity evaluation across all 565 companies
    conn.row_factory = sqlite3.Row
    comps = conn.execute("""
        SELECT id FROM companies
        WHERE id IN (SELECT DISTINCT company_id FROM facilities)
    """).fetchall()
    assert len(comps) == 565, f"Expected 565 operating companies, got {len(comps)}"

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

    print(f"[CHECK] Opportunity tier distribution across 565 companies: {counts}")

    conn.close()

    new_hash = hashlib.sha256(DB_PATH.read_bytes()).hexdigest().upper()
    print(f"[REMEDIATE] Final DB hash: {new_hash}")


if __name__ == "__main__":
    main()
