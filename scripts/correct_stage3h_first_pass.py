"""
Stage 3H First-Pass Correction Script (OpenCode Audit Findings).
Surgically applies corrections to the 38 Stage 3H records:
1. Resets company_footprint_status to UNKNOWN for all 38 companies (IDs 530-567),
   clearing unsupported verified_operating_location_count and footprint_source_notes.
2. Reclassifies Facility 623 (Lignetics) to HEADQUARTERS truthfully.
3. Reconciles Facility 639 (Kempler) address drift from Elk Grove Village to
   current official corporate location: 2720 Dundee Rd, Suite 300, Northbrook, IL 60062.
   Atomically supersedes historical address claim (is_current_accepted = 0) and records
   the newly accepted address claim (is_current_accepted = 1) with evidence link.
4. Corrects UTF-8 encoding corruption for SCHÜTZ across companies, facilities, claims,
   and evidence_sources tables.
5. Verifies database integrity via PRAGMA integrity_check and PRAGMA foreign_key_check.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path("data/prospects.db")

def main():
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    try:
        with conn:
            # 1. Reset Footprint Truth for all 38 Stage 3H companies
            print("1. Resetting footprint truth for companies 530-567...")
            cur.execute("""
                UPDATE companies
                SET company_footprint_status = 'UNKNOWN',
                    verified_operating_location_count = NULL,
                    footprint_source_notes = NULL,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id >= 530 AND id <= 567;
            """)
            updated_companies = cur.rowcount
            print(f"   Updated {updated_companies} companies to company_footprint_status = 'UNKNOWN'.")
            assert updated_companies == 38, f"Expected 38 companies updated, got {updated_companies}"

            # 2. Facility 623 (Lignetics) - Reclassify to HEADQUARTERS
            print("2. Reclassifying Facility 623 (Lignetics)...")
            cur.execute("""
                UPDATE facilities
                SET facility_type = 'HEADQUARTERS',
                    facility_name = 'Lignetics Corporate Headquarters',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = 623;
            """)
            assert cur.rowcount == 1, "Failed to update facility 623"

            cur.execute("""
                UPDATE facility_commodities
                SET specific_products = 'Company-level commercial product line: bagged wood heating pellets, barbecue wood pellets, and compressed firelogs (corporate administrative location; production at regional mills)'
                WHERE facility_id = 623;
            """)
            assert cur.rowcount == 1, "Failed to update facility_commodities for facility 623"
            print("   Facility 623 reclassified to HEADQUARTERS; commodity description updated to corporate-level.")

            # 3. Facility 639 (Kempler) - Reconcile Address Drift to Northbrook, IL
            print("3. Reconciling Facility 639 (Kempler) address to Northbrook, IL...")
            cur.execute("""
                UPDATE facilities
                SET facility_name = 'Kempler Machinery Corporate Office & Operations',
                    physical_address = '2720 Dundee Rd, Suite 300',
                    city = 'Northbrook',
                    state_prov = 'IL',
                    postal_code = '60062',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = 639;
            """)
            assert cur.rowcount == 1, "Failed to update facility 639"

            cur.execute("""
                UPDATE companies
                SET corporate_address = '2720 Dundee Rd, Suite 300, Northbrook, IL 60062',
                    notes = 'Prominent stocking dealer of industrial hydraulic and mechanical presses. Corporate office in Northbrook, IL; offers used machinery surplus solutions nationwide requiring step-deck and open-deck transport.',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = 552;
            """)
            assert cur.rowcount == 1, "Failed to update company 552"

            # Supersede old claim 2635
            cur.execute("""
                UPDATE claims
                SET is_current_accepted = 0,
                    claim_notes = 'Superseded: Historical Elk Grove Village warehouse address superseded by current official corporate/operating address in Northbrook, IL.',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = 2635;
            """)
            assert cur.rowcount == 1, "Failed to supersede old claim 2635"

            # Insert new current accepted claim
            cur.execute("""
                INSERT INTO claims (
                    facility_id, claim_field, claimed_value, verification_status,
                    is_current_accepted, claim_notes, created_at, updated_at
                ) VALUES (
                    639, 'physical_address', '2720 Dundee Rd, Suite 300', 'VERIFIED',
                    1, 'Verified via official corporate contact page: 2720 Dundee Road, Suite 300, Northbrook, IL 60062.',
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                );
            """)
            new_claim_id = cur.lastrowid
            print(f"   Inserted new address claim {new_claim_id} for facility 639.")

            # Link to evidence source 695 (Kempler contact page)
            cur.execute("""
                INSERT INTO claim_evidence (
                    claim_id, evidence_source_id, relationship, relationship_notes, created_at
                ) VALUES (
                    ?, 695, 'SUPPORTS',
                    'Official Kempler Machinery contact page verifies 2720 Dundee Road, Suite 300, Northbrook, IL 60062',
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                );
            """, (new_claim_id,))
            print(f"   Linked claim {new_claim_id} to evidence source 695.")

            # Update discovery intake audit notes
            cur.execute("""
                UPDATE discovery_intake_audit
                SET facility_address = '2720 Dundee Rd, Suite 300',
                    city = 'Northbrook',
                    candidate_facility_name = 'Kempler Machinery Corporate Office & Operations',
                    reason_or_notes = 'Reconciled: Address updated from historical Elk Grove Village to current official Northbrook IL location per OpenCode audit.'
                WHERE target_facility_id = 639;
            """)

            # 4. Facility / Company 652 (SCHÜTZ) - Fix UTF-8 encoding
            print("4. Correcting UTF-8 encoding for SCHÜTZ...")
            cur.execute("""
                UPDATE companies
                SET operating_brand = 'SCHÜTZ Container Systems',
                    legal_name = 'SCHÜTZ Container Systems, Inc.',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = 565;
            """)
            assert cur.rowcount == 1, "Failed to update company 565"

            cur.execute("""
                UPDATE facilities
                SET facility_name = 'SCHÜTZ North Branch IBC Plant',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = 652;
            """)
            assert cur.rowcount == 1, "Failed to update facility 652"

            cur.execute("""
                UPDATE claims
                SET claimed_value = 'SCHÜTZ Container Systems',
                    claim_notes = 'Verified operating brand identity (UTF-8 encoding reconciled)',
                    updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                WHERE id = 2686;
            """)
            assert cur.rowcount == 1, "Failed to update claim 2686"

            cur.execute("""
                UPDATE evidence_sources
                SET source_title_publisher = 'SCHÜTZ Container Systems Official Website'
                WHERE id = 708;
            """)
            assert cur.rowcount == 1, "Failed to update evidence_sources 708"
            print("   UTF-8 encoding for SCHÜTZ successfully corrected across all tables.")

            # 5. Database Relational Checks
            print("5. Verifying database integrity...")
            integrity = cur.execute("PRAGMA integrity_check;").fetchall()
            fk_check = cur.execute("PRAGMA foreign_key_check;").fetchall()
            assert integrity == [("ok",)], f"Integrity check failed: {integrity}"
            assert fk_check == [], f"Foreign key violations found: {fk_check}"
            print("   PRAGMA integrity_check: ok")
            print("   PRAGMA foreign_key_check: 0 violations")

        print("\nAll Stage 3H surgical corrections successfully committed!")

    except Exception as e:
        conn.rollback()
        print(f"Error during correction: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
