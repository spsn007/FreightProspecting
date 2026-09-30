"""
FreightProspecting V1 — Seed Missing Address Claims for Facility 2 and 3
Audit Remediation A: Completes 100% address claim provenance across all 615 facilities.
Facility 2 (Dearborn Steel Service Center) linked to Source 4 (Kenwal Steel Official Website).
Facility 3 (Utopia Precast Plant) linked to Source 5 (DECAST Ltd. Official Website).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("data/prospects.db")

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    now_iso = datetime.now(timezone.utc).isoformat()

    with conn:
        # Check facility 2
        f2_claim = conn.execute(
            "SELECT id FROM claims WHERE facility_id = 2 AND claim_field = 'physical_address'"
        ).fetchone()
        if not f2_claim:
            cur = conn.execute(
                """
                INSERT INTO claims (
                    company_id, company_relationship_id, facility_id, facility_commodity_id,
                    contact_id, freight_demand_signal_id, load_opportunity_id, carrier_id,
                    carrier_lane_activity_id, capacity_posting_id, claim_field, claimed_value,
                    verification_status, is_current_accepted, claim_notes, created_at, updated_at
                ) VALUES (
                    NULL, NULL, 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                    'physical_address', '8223 W. Warren, Dearborn, MI 48126, US',
                    'VERIFIED', 1, 'Primary corporate website confirmation for Dearborn Service Center location.',
                    ?, ?
                )
                """,
                (now_iso, now_iso)
            )
            c2_id = cur.lastrowid
            conn.execute(
                "INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship) VALUES (?, 4, 'SUPPORTS')",
                (c2_id,)
            )
            print(f"Added address claim {c2_id} for facility 2 linked to source 4")
        else:
            print("Facility 2 already has address claim")

        # Check facility 3
        f3_claim = conn.execute(
            "SELECT id FROM claims WHERE facility_id = 3 AND claim_field = 'physical_address'"
        ).fetchone()
        if not f3_claim:
            cur = conn.execute(
                """
                INSERT INTO claims (
                    company_id, company_relationship_id, facility_id, facility_commodity_id,
                    contact_id, freight_demand_signal_id, load_opportunity_id, carrier_id,
                    carrier_lane_activity_id, capacity_posting_id, claim_field, claimed_value,
                    verification_status, is_current_accepted, claim_notes, created_at, updated_at
                ) VALUES (
                    NULL, NULL, 3, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                    'physical_address', '8807 County Road 56, Utopia, ON L0M 1T0, CA',
                    'VERIFIED', 1, 'Primary corporate website confirmation for DECAST Utopia plant location.',
                    ?, ?
                )
                """,
                (now_iso, now_iso)
            )
            c3_id = cur.lastrowid
            conn.execute(
                "INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship) VALUES (?, 5, 'SUPPORTS')",
                (c3_id,)
            )
            print(f"Added address claim {c3_id} for facility 3 linked to source 5")
        else:
            print("Facility 3 already has address claim")

    # Run PRAGMA checks
    fks = conn.execute("PRAGMA foreign_key_check").fetchall()
    integ = conn.execute("PRAGMA integrity_check").fetchall()
    print("FK check errors:", len(fks))
    print("Integrity check:", integ)
    conn.close()

if __name__ == "__main__":
    main()
