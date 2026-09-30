"""
FreightProspecting V1 — Audit Remediation A Migration Script
Applies P0/P1 fixes:
1. Recreates prospect_engagement_state with expanded CHECK constraint for all 8 dispositions.
2. Recreates evidence_sources with expanded CHECK constraint for trade associations / directories / secondary sources.
3. Corrects CSP (Facility 18) Shipping Contact with official primary data (419-269-9706, shipping@coilsteelprocessing.com).
4. Corrects taxonomy misclassifications:
   - Removes bulk sawmill mulch from BAGGED_MULCH_SOIL for facilities 5 and 460.
   - Reclassifies StructureCraft (facility 613) from concrete to mass timber (ROOF_TRUSSES_WALL_PANELS primary).
5. Corrects source type mislabeling (Forest Products Locator, naturally:wood, Ohio Precast).
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import sys


def get_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_remediation_migration(db_path: Path) -> None:
    print(f"Running Audit Remediation A migration on: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Enforce foreign keys
    conn.execute("PRAGMA foreign_keys = OFF;")
    conn.execute("PRAGMA legacy_alter_table = ON;")

    try:
        cur = conn.cursor()

        # ---------------------------------------------------------------------
        # 1. Expand CHECK constraint on prospect_engagement_state
        # ---------------------------------------------------------------------
        print("1. Updating prospect_engagement_state schema for all 8 dispositions...")
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='prospect_engagement_state'")
        row = cur.fetchone()
        if row and ("'CONNECTED_DECISION_MAKER'" not in row[0]):
            conn.execute("ALTER TABLE prospect_engagement_state RENAME TO prospect_engagement_state_old;")
            conn.execute("""
            CREATE TABLE prospect_engagement_state (
                company_id INTEGER PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
                current_outreach_status TEXT NOT NULL DEFAULT 'UNCONTACTED' CHECK(current_outreach_status IN (
                    'UNCONTACTED', 'INTERESTED', 'NOT_INTERESTED', 'NO_ANSWER', 'CALL_BACK',
                    'CONNECTED_DECISION_MAKER', 'CONNECTED_GATEKEEPER', 'LEFT_VOICEMAIL', 'WRONG_CONTACT'
                )),
                status_source_outreach_log_id INTEGER REFERENCES outreach_logs(id) ON DELETE SET NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                last_contacted_at DATETIME,
                next_follow_up_at DATETIME,
                last_facility_id INTEGER REFERENCES facilities(id) ON DELETE SET NULL,
                last_feedback_notes TEXT,
                is_viewed INTEGER NOT NULL DEFAULT 0,
                first_viewed_at DATETIME,
                last_viewed_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.execute("""
            INSERT INTO prospect_engagement_state (
                company_id, current_outreach_status, status_source_outreach_log_id,
                attempt_count, last_contacted_at, next_follow_up_at, last_facility_id,
                last_feedback_notes, is_viewed, first_viewed_at, last_viewed_at, created_at, updated_at
            )
            SELECT 
                company_id, current_outreach_status, status_source_outreach_log_id,
                attempt_count, last_contacted_at, next_follow_up_at, last_facility_id,
                last_feedback_notes, is_viewed, first_viewed_at, last_viewed_at, created_at, updated_at
            FROM prospect_engagement_state_old;
            """)
            conn.execute("DROP TABLE prospect_engagement_state_old;")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_status ON prospect_engagement_state(current_outreach_status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_follow_up ON prospect_engagement_state(next_follow_up_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_engagement_viewed ON prospect_engagement_state(is_viewed);")
            print("  prospect_engagement_state successfully recreated with all 8 dispositions.")
        else:
            print("  prospect_engagement_state already supports all 8 dispositions.")

        # ---------------------------------------------------------------------
        # 2. Expand CHECK constraint on evidence_sources
        # ---------------------------------------------------------------------
        print("2. Updating evidence_sources schema for secondary / association source types...")
        cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='evidence_sources'")
        row = cur.fetchone()
        if row and ("'TRADE_ASSOCIATION'" not in row[0]):
            conn.execute("ALTER TABLE evidence_sources RENAME TO evidence_sources_old;")
            conn.execute("""
            CREATE TABLE evidence_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL CHECK(source_type IN (
                    'COMPANY_WEBSITE', 'FIRST_PARTY', 'GOVERNMENT_REGISTRY', 'GOVERNMENT_REGULATOR',
                    'TRADE_ASSOCIATION', 'INDUSTRY_DIRECTORY', 'DIRECTORY_AGGREGATOR', 'JOB_POSTING',
                    'PHONE_OUTREACH', 'EMAIL_CORRESPONDENCE', 'OTHER_SECONDARY', 'MANUAL_USER_OBSERVED'
                )),
                source_title_publisher TEXT NOT NULL,
                source_url TEXT,
                is_primary_source BOOLEAN,
                source_published_at DATETIME,
                event_at DATETIME,
                observed_at DATETIME NOT NULL,
                outreach_log_id INTEGER REFERENCES outreach_logs(id) ON DELETE SET NULL,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.execute("""
            INSERT INTO evidence_sources (
                id, source_type, source_title_publisher, source_url, is_primary_source,
                source_published_at, event_at, observed_at, outreach_log_id, notes, created_at
            )
            SELECT 
                id, source_type, source_title_publisher, source_url, is_primary_source,
                source_published_at, event_at, observed_at, outreach_log_id, notes, created_at
            FROM evidence_sources_old;
            """)
            conn.execute("DROP TABLE evidence_sources_old;")
            print("  evidence_sources successfully recreated with expanded source types.")
        else:
            print("  evidence_sources already supports expanded source types.")

        # ---------------------------------------------------------------------
        # 3. Correct CSP (Facility 18) Shipping Contact
        # ---------------------------------------------------------------------
        print("3. Correcting CSP (Facility 18) shipping contact to official shipping desk...")
        now = get_timestamp()

        # Update contact record for Facility 18
        cur.execute("""
            UPDATE contacts
            SET 
                contact_identity = 'DEPARTMENT',
                person_name = NULL,
                exact_published_title = 'Shipping & Receiving Desk',
                phone_number = '(419) 269-9706',
                phone_directness = 'DEPARTMENT_LINE',
                email_address = 'shipping@coilsteelprocessing.com',
                email_directness = 'DEPARTMENT',
                role_category = 'FREIGHT_LOGISTICS',
                department = 'Shipping & Receiving',
                outbound_shipping_procurement_relevance = 'VERIFIED',
                broker_procurement_relevance = 'UNKNOWN',
                is_primary_contact = 1
            WHERE facility_id = 18;
        """)

        # Ensure contact claim is updated
        csp_contact_id = cur.execute("SELECT id FROM contacts WHERE facility_id = 18").fetchone()[0]
        cur.execute("""
            UPDATE claims
            SET 
                claimed_value = 'DEPARTMENT_LINE',
                verification_status = 'VERIFIED',
                claim_notes = 'Direct Shipping & Receiving desk phone (419) 269-9706 verified via official CSP shipping page'
            WHERE contact_id = ? AND claim_field = 'phone_directness' AND is_current_accepted = 1;
        """, (csp_contact_id,))

        # Update evidence source for CSP
        cur.execute("""
            UPDATE evidence_sources
            SET 
                source_title_publisher = 'Coil Steel Processing Official Shipping & Receiving',
                source_url = 'https://coilsteelprocessing.com/shipping-and-receiving/',
                is_primary_source = 1
            WHERE id = (
                SELECT ce.evidence_source_id
                FROM claim_evidence ce
                JOIN claims c ON ce.claim_id = c.id
                WHERE c.contact_id = ?
                LIMIT 1
            );
        """, (csp_contact_id,))

        # Verify CSP equipment claim remains FLATBED VERIFIED
        csp_fc = cur.execute("""
            SELECT equipment_category, equipment_usage_status 
            FROM facility_commodities 
            WHERE facility_id = 18
        """).fetchone()
        assert csp_fc["equipment_category"] == "FLATBED", f"CSP equipment must remain FLATBED, got {csp_fc['equipment_category']}"
        assert csp_fc["equipment_usage_status"] == "VERIFIED", f"CSP equipment status must remain VERIFIED, got {csp_fc['equipment_usage_status']}"
        print("  CSP contact updated: (419) 269-9706, shipping@coilsteelprocessing.com, DEPARTMENT_LINE. FLATBED VERIFIED preserved.")

        # ---------------------------------------------------------------------
        # 4. Correct Taxonomy Misclassifications
        # ---------------------------------------------------------------------
        print("4. Correcting taxonomy misclassifications...")

        # 4a. Remove bulk mulch from BAGGED_MULCH_SOIL for Battle Lumber (#5) and Spray Lake Sawmills (#460)
        bagged_mulch_cat_id = cur.execute("SELECT id FROM commodity_categories WHERE category_code = 'BAGGED_MULCH_SOIL'").fetchone()[0]
        cur.execute("""
            DELETE FROM facility_commodity_mappings
            WHERE category_id = ? AND facility_id IN (5, 460);
        """, (bagged_mulch_cat_id,))
        print("  Removed invalid BAGGED_MULCH_SOIL secondary mappings from facilities 5 and 460.")

        # 4b. Reclassify StructureCraft (facility 613) from concrete to mass timber
        # Update facility_commodities
        cur.execute("""
            UPDATE facility_commodities
            SET 
                commodity_category = 'Lumber & Forest Products',
                specific_products = 'Dowel-laminated timber (DLT), mass timber hybrid girders, steel-timber trusses',
                equipment_category = 'FLATBED',
                equipment_usage_status = 'INFERRED'
            WHERE facility_id = 613;
        """)

        # Update mappings for Facility 613:
        # Delete CONCRETE_PRECAST_PRODUCTS mapping
        concrete_cat_id = cur.execute("SELECT id FROM commodity_categories WHERE category_code = 'CONCRETE_PRECAST_PRODUCTS'").fetchone()[0]
        cur.execute("""
            DELETE FROM facility_commodity_mappings
            WHERE facility_id = 613 AND category_id = ?;
        """, (concrete_cat_id,))

        # Promote ROOF_TRUSSES_WALL_PANELS to primary mapping
        truss_cat_id = cur.execute("SELECT id FROM commodity_categories WHERE category_code = 'ROOF_TRUSSES_WALL_PANELS'").fetchone()[0]
        cur.execute("""
            UPDATE facility_commodity_mappings
            SET is_primary = 1,
                source_evidence_notes = 'Primary audited facility classification: Engineered mass timber components, DLT, and timber-steel trusses (StructureCraft Abbotsford)'
            WHERE facility_id = 613 AND category_id = ?;
        """, (truss_cat_id,))

        # Add secondary mapping for LUMBER_FOREST_PRODUCTS
        lumber_cat_id = cur.execute("SELECT id FROM commodity_categories WHERE category_code = 'LUMBER_FOREST_PRODUCTS'").fetchone()[0]
        cur.execute("""
            INSERT INTO facility_commodity_mappings (facility_id, category_id, source_evidence_notes, is_primary, created_at)
            VALUES (613, ?, 'Secondary category: Mass timber raw materials and engineered forest products', 0, ?)
            ON CONFLICT(facility_id, category_id) DO UPDATE SET is_primary = 0;
        """, (lumber_cat_id, now))

        # Update commodity_category_id on facility_commodities for 613 to truss_cat_id
        cur.execute("""
            UPDATE facility_commodities
            SET commodity_category_id = ?, category_code = 'ROOF_TRUSSES_WALL_PANELS'
            WHERE facility_id = 613;
        """, (truss_cat_id,))
        print("  StructureCraft (613) reclassified: ROOF_TRUSSES_WALL_PANELS primary, LUMBER_FOREST_PRODUCTS secondary. Concrete removed.")

        # ---------------------------------------------------------------------
        # 5. Correct Source Type Mislabeling
        # ---------------------------------------------------------------------
        print("5. Correcting source type mislabeling in evidence_sources...")
        # Source 102: Forest Products Locator Directory
        cur.execute("""
            UPDATE evidence_sources
            SET source_type = 'INDUSTRY_DIRECTORY', is_primary_source = 0
            WHERE id = 102;
        """)

        # Source 140: naturally:wood Supplier Directory
        cur.execute("""
            UPDATE evidence_sources
            SET source_type = 'TRADE_ASSOCIATION', is_primary_source = 0
            WHERE id = 140;
        """)

        # Source 204: Ohio Precast Concrete Association Directory
        cur.execute("""
            UPDATE evidence_sources
            SET source_type = 'TRADE_ASSOCIATION', is_primary_source = 0
            WHERE id = 204;
        """)

        # All GFC sources: ensure is_primary_source = 0
        cur.execute("""
            UPDATE evidence_sources
            SET is_primary_source = 0
            WHERE source_url LIKE '%gatrees.org%';
        """)
        print("  Source types corrected for ID 102 (INDUSTRY_DIRECTORY), 140 (TRADE_ASSOCIATION), 204 (TRADE_ASSOCIATION), gatrees (is_primary=0).")

        # Re-enable foreign keys
        conn.execute("PRAGMA legacy_alter_table = OFF;")
        conn.execute("PRAGMA foreign_keys = ON;")

        # Run integrity checks
        fk_errors = conn.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_errors:
            for e in fk_errors:
                print("FK Error:", dict(e) if hasattr(e, 'keys') else tuple(e))
            raise RuntimeError(f"Foreign key integrity check failed after remediation migration: {len(fk_errors)} errors")
        integrity = conn.execute("PRAGMA integrity_check;").fetchall()
        if not integrity or integrity[0][0] != "ok":
            raise RuntimeError(f"Database integrity check failed after remediation migration: {integrity}")

        conn.commit()
        print("Remediation migration successfully committed. Foreign key & database integrity: OK.")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/prospects.db")
    run_remediation_migration(target)
