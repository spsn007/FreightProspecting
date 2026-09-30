"""
FreightProspecting V1 — Audit Remediation D Database Migration
Executes surgical database-level corrections identified in Codex Final Independent Closure Verification:
1. Revert 7 unsupported/unverified equipment evidence relationships from SUPPORTS to CONTEXT (AUD-003).
2. Downgrade 6 secondary-source claims (265, 268, 417, 420, 673, 676) from VERIFIED to UNKNOWN, evidence to CONTEXT (AUD-010).
3. Reconcile Sonoco 365/366 taxonomy: add INDUSTRIAL_PAPER_PACKAGING category under PACKAGING_HIGH_CUBE and assign as primary (AUD-009).
4. Update Yoder facility 408 contact 627: set outbound_shipping_procurement_relevance to UNKNOWN.
5. Migrate 23 live SQLite column defaults from CURRENT_TIMESTAMP to canonical UTC (AUD-023).
6. Enforce comprehensive gross_margin and margin_pct validation triggers on load_opportunities for INSERT and UPDATE (AUD-014).
7. Ensure unconditional append-only triggers on outreach_logs (AUD-025).
"""

import os
import sqlite3
import sys
from pathlib import Path


def run_migration(db_path: str) -> None:
    print(f"=== Starting Remediation D Database Migration on {db_path} ===")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA foreign_keys = OFF;")

    # ------------------------------------------------------------------------
    # 1. AUD-003: Revert 7 non-passing equipment relationships to CONTEXT
    # ------------------------------------------------------------------------
    print("1. Reverting 7 unsupported/unverified equipment relationships to CONTEXT...")
    AUDIT_39_NON_PASSING = [
        # (claim_id, new_relationship, notes)
        (19, "CONTEXT", "Audited non-passing: WMG homepage describes generic tooling/injection molding without transport form or heavy FTL dimensions."),
        (29, "CONTEXT", "Audited non-passing: Stored 2019 GFC PDF returns 404; unverified against linked evidence record."),
        (34, "CONTEXT", "Audited non-passing: Stored GFC homepage is generic directory entry; unverified against specific facility source fact."),
        (174, "CONTEXT", "Audited non-passing: Cavalier Tool homepage describes generic tooling without heavy FTL dimensions/weights."),
        (179, "CONTEXT", "Audited non-passing: Crest Mold homepage describes injection molds without freight dimensions/weights."),
        (189, "CONTEXT", "Audited non-passing: Omega Tool lists automotive end-markets without mold freight dimensions."),
        (194, "CONTEXT", "Audited non-passing: Cascade Engineering homepage blocked direct fetch; product size insufficient for verified flatbed fit."),
    ]
    for cid, rel, note in AUDIT_39_NON_PASSING:
        cur.execute("""
            UPDATE claim_evidence
            SET relationship = ?, relationship_notes = ?
            WHERE claim_id = ?
        """, (rel, note, cid))
        print(f"   Claim {cid} relationship -> {rel}")

    # ------------------------------------------------------------------------
    # 2. AUD-010: Reassess 6 secondary-source claims
    # ------------------------------------------------------------------------
    print("2. Reassessing 6 secondary-source claims (265, 268, 417, 420, 673, 676)...")
    DEMOTED_CLAIMS = [
        (265, "UNKNOWN", "Reassessed in Remediation D: Forest Products Locator is an inaccessible secondary directory; physical address unverified by primary source."),
        (268, "UNKNOWN", "Reassessed in Remediation D: Forest Products Locator is an inaccessible secondary directory; phone directness unverified by primary source."),
        (417, "UNKNOWN", "Reassessed in Remediation D: naturally:wood trade association directory gives postal code V4T 1W4, not 1W5; exact claim unconfirmed by primary source."),
        (420, "UNKNOWN", "Reassessed in Remediation D: naturally:wood trade association directory does not substantiate switchboard directness classification."),
        (673, "UNKNOWN", "Reassessed in Remediation D: Ohio Precast Concrete Association homepage describes its own Tipp City HQ, not Lucasville plant address."),
        (676, "UNKNOWN", "Reassessed in Remediation D: OPCA directory does not publish or verify a Lucasville switchboard route."),
    ]
    for cid, status, note in DEMOTED_CLAIMS:
        cur.execute("""
            UPDATE claims
            SET verification_status = ?, claim_notes = ?
            WHERE id = ?
        """, (status, note, cid))
        cur.execute("""
            UPDATE claim_evidence
            SET relationship = 'CONTEXT',
                relationship_notes = 'Secondary directory/association source does not independently substantiate claim value; demoted to CONTEXT.'
            WHERE claim_id = ?
        """, (cid,))
        print(f"   Claim {cid} status -> {status}, evidence -> CONTEXT")

    # ------------------------------------------------------------------------
    # 3. AUD-009: Reconcile Sonoco 365/366 taxonomy
    # ------------------------------------------------------------------------
    print("3. Reconciling Sonoco 365/366 commodity category...")
    # Find family_id for PACKAGING_HIGH_CUBE
    cur.execute("SELECT id FROM commodity_families WHERE family_code = 'PACKAGING_HIGH_CUBE'")
    fam_row = cur.fetchone()
    fam_id = fam_row[0] if fam_row else 3

    # Check if INDUSTRIAL_PAPER_PACKAGING already exists
    cur.execute("SELECT id FROM commodity_categories WHERE category_code = 'INDUSTRIAL_PAPER_PACKAGING'")
    existing_cat = cur.fetchone()
    if existing_cat:
        cat_id = existing_cat[0]
    else:
        cur.execute("""
            INSERT INTO commodity_categories (
                family_id, category_code, display_name, description,
                typical_equipment_fit, seasonality_profile, peak_months,
                operating_characteristics, sort_order, is_active, deferred_status_note,
                created_at
            ) VALUES (
                ?, 'INDUSTRIAL_PAPER_PACKAGING', 'Industrial Paper & Rigid Packaging',
                'Industrial paper tubes, winding cores, spirally wound containers, composite cans, and rigid paper packaging.',
                'DRY_VAN', 'YEAR_ROUND', 'Year-round',
                'HIGH_CUBE, REGIONAL', 25, 1, NULL,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
        """, (fam_id,))
        cat_id = cur.lastrowid
        print(f"   Created category INDUSTRIAL_PAPER_PACKAGING with id {cat_id}")

    # Update facility_commodities for 365 and 366
    cur.execute("""
        UPDATE facility_commodities
        SET commodity_category_id = ?, category_code = 'INDUSTRIAL_PAPER_PACKAGING'
        WHERE facility_id IN (365, 366)
    """, (cat_id,))
    print(f"   Updated facility_commodities for facilities 365 and 366 to category_id {cat_id}")

    # Update facility_commodity_mappings for 365 and 366
    for fac_id in (365, 366):
        # Remove old primary mapping of INDUSTRIAL_MFG_EQUIPMENT
        cur.execute("""
            DELETE FROM facility_commodity_mappings
            WHERE facility_id = ? AND is_primary = 1
        """, (fac_id,))
        # Insert new primary mapping
        cur.execute("""
            INSERT INTO facility_commodity_mappings (facility_id, category_id, source_evidence_notes, is_primary, created_at)
            VALUES (?, ?, 'Primary audited facility commodity classification: Industrial paper & rigid packaging (Sonoco)', 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        """, (fac_id, cat_id))
    print("   Updated primary facility_commodity_mappings for facilities 365 and 366")

    # ------------------------------------------------------------------------
    # 4. Yoder Lumber Facility 408 Contact 627 procurement relevance
    # ------------------------------------------------------------------------
    print("4. Updating Yoder facility 408 contact 627 procurement relevance to UNKNOWN...")
    cur.execute("""
        UPDATE contacts
        SET outbound_shipping_procurement_relevance = 'UNKNOWN'
        WHERE id = 627
    """)
    print("   Contact 627 outbound_shipping_procurement_relevance -> UNKNOWN")

    # ------------------------------------------------------------------------
    # 5. AUD-023: Migrate 23 live SQLite column defaults from CURRENT_TIMESTAMP
    # ------------------------------------------------------------------------
    print("5. Migrating 23 live column defaults from CURRENT_TIMESTAMP to canonical UTC...")
    cur.execute("PRAGMA writable_schema = ON;")
    cur.execute("""
        UPDATE sqlite_master
        SET sql = REPLACE(sql, 'DEFAULT CURRENT_TIMESTAMP', 'DEFAULT (strftime(''%Y-%m-%dT%H:%M:%SZ'', ''now''))')
        WHERE type = 'table' AND sql LIKE '%CURRENT_TIMESTAMP%'
    """)
    cur.execute("PRAGMA writable_schema = OFF;")
    print("   Live column defaults updated in sqlite_master.")

    # ------------------------------------------------------------------------
    # 6. AUD-014: Enforce rate and margin triggers on load_opportunities
    # ------------------------------------------------------------------------
    print("6. Updating load_opportunities triggers for rates, gross_margin, and margin_pct...")
    cur.execute("DROP TRIGGER IF EXISTS trg_load_opps_validate_rates_insert;")
    cur.execute("DROP TRIGGER IF EXISTS trg_load_opps_validate_rates_update;")
    cur.execute("DROP TRIGGER IF EXISTS trg_load_opps_validate_margin_insert;")
    cur.execute("DROP TRIGGER IF EXISTS trg_load_opps_validate_margin_update;")

    cur.execute("""
        CREATE TRIGGER trg_load_opps_validate_rates_insert
        BEFORE INSERT ON load_opportunities
        BEGIN
            SELECT RAISE(ABORT, 'shipper_target_rate cannot be negative')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate < 0;
            
            SELECT RAISE(ABORT, 'carrier_target_cost cannot be negative')
            WHERE NEW.carrier_target_cost IS NOT NULL AND NEW.carrier_target_cost < 0;
        END;
    """)

    cur.execute("""
        CREATE TRIGGER trg_load_opps_validate_rates_update
        BEFORE UPDATE ON load_opportunities
        BEGIN
            SELECT RAISE(ABORT, 'shipper_target_rate cannot be negative')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate < 0;
            
            SELECT RAISE(ABORT, 'carrier_target_cost cannot be negative')
            WHERE NEW.carrier_target_cost IS NOT NULL AND NEW.carrier_target_cost < 0;
        END;
    """)

    cur.execute("""
        CREATE TRIGGER trg_load_opps_validate_margin_insert
        BEFORE INSERT ON load_opportunities
        BEGIN
            -- Missing rate checks: both gross_margin and margin_pct MUST be NULL
            SELECT RAISE(ABORT, 'gross_margin must be NULL when rates are missing')
            WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
              AND NEW.gross_margin IS NOT NULL;
              
            SELECT RAISE(ABORT, 'margin_pct must be NULL when rates are missing')
            WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
              AND NEW.margin_pct IS NOT NULL;

            -- Both rates present: gross_margin is required and must match difference
            SELECT RAISE(ABORT, 'gross_margin is required when both rates are present')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
              AND NEW.gross_margin IS NULL;

            SELECT RAISE(ABORT, 'gross_margin does not match shipper_target_rate - carrier_target_cost')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
              AND NEW.gross_margin IS NOT NULL
              AND ROUND(NEW.gross_margin, 2) != ROUND(NEW.shipper_target_rate - NEW.carrier_target_cost, 2);

            -- margin_pct rules:
            -- If shipper_target_rate == 0, margin_pct MUST be NULL (no division by zero)
            SELECT RAISE(ABORT, 'margin_pct must be NULL when shipper_target_rate is zero')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate = 0
              AND NEW.margin_pct IS NOT NULL;

            -- If shipper_target_rate > 0, margin_pct is required and must match calculation
            SELECT RAISE(ABORT, 'margin_pct is required when shipper_target_rate > 0')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
              AND NEW.shipper_target_rate > 0
              AND NEW.margin_pct IS NULL;

            SELECT RAISE(ABORT, 'margin_pct does not match calculated percentage')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
              AND NEW.shipper_target_rate > 0
              AND NEW.margin_pct IS NOT NULL
              AND ABS(ROUND(NEW.margin_pct, 2) - ROUND(((NEW.shipper_target_rate - NEW.carrier_target_cost) * 100.0) / NEW.shipper_target_rate, 2)) > 0.05;
        END;
    """)

    cur.execute("""
        CREATE TRIGGER trg_load_opps_validate_margin_update
        BEFORE UPDATE ON load_opportunities
        BEGIN
            -- Missing rate checks: both gross_margin and margin_pct MUST be NULL
            SELECT RAISE(ABORT, 'gross_margin must be NULL when rates are missing')
            WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
              AND NEW.gross_margin IS NOT NULL;
              
            SELECT RAISE(ABORT, 'margin_pct must be NULL when rates are missing')
            WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
              AND NEW.margin_pct IS NOT NULL;

            -- Both rates present: gross_margin is required and must match difference
            SELECT RAISE(ABORT, 'gross_margin is required when both rates are present')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
              AND NEW.gross_margin IS NULL;

            SELECT RAISE(ABORT, 'gross_margin does not match shipper_target_rate - carrier_target_cost')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
              AND NEW.gross_margin IS NOT NULL
              AND ROUND(NEW.gross_margin, 2) != ROUND(NEW.shipper_target_rate - NEW.carrier_target_cost, 2);

            -- margin_pct rules:
            -- If shipper_target_rate == 0, margin_pct MUST be NULL (no division by zero)
            SELECT RAISE(ABORT, 'margin_pct must be NULL when shipper_target_rate is zero')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate = 0
              AND NEW.margin_pct IS NOT NULL;

            -- If shipper_target_rate > 0, margin_pct is required and must match calculation
            SELECT RAISE(ABORT, 'margin_pct is required when shipper_target_rate > 0')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
              AND NEW.shipper_target_rate > 0
              AND NEW.margin_pct IS NULL;

            SELECT RAISE(ABORT, 'margin_pct does not match calculated percentage')
            WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
              AND NEW.shipper_target_rate > 0
              AND NEW.margin_pct IS NOT NULL
              AND ABS(ROUND(NEW.margin_pct, 2) - ROUND(((NEW.shipper_target_rate - NEW.carrier_target_cost) * 100.0) / NEW.shipper_target_rate, 2)) > 0.05;
        END;
    """)
    print("   Created comprehensive margin validation triggers on load_opportunities.")

    # ------------------------------------------------------------------------
    # 7. AUD-025: Unconditional append-only triggers on outreach_logs
    # ------------------------------------------------------------------------
    print("7. Ensuring unconditional append-only triggers on outreach_logs...")
    cur.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_update;")
    cur.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_delete;")
    cur.execute("""
        CREATE TRIGGER trg_outreach_logs_no_update
        BEFORE UPDATE ON outreach_logs
        BEGIN
            SELECT RAISE(ABORT, 'outreach_logs is append-only: UPDATE operations are strictly prohibited.');
        END;
    """)
    cur.execute("""
        CREATE TRIGGER trg_outreach_logs_no_delete
        BEFORE DELETE ON outreach_logs
        BEGIN
            SELECT RAISE(ABORT, 'outreach_logs is append-only: DELETE operations are strictly prohibited.');
        END;
    """)
    print("   Created unconditional append-only triggers on outreach_logs.")

    # Commit all changes
    conn.commit()
    conn.close()

    # Reconnect to run integrity checks
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")
    
    integ = cur.execute("PRAGMA integrity_check;").fetchone()[0]
    print(f"PRAGMA integrity_check: {integ}")
    if integ != "ok":
        raise RuntimeError(f"Database integrity check failed: {integ}")

    fk_violations = cur.execute("PRAGMA foreign_key_check;").fetchall()
    print(f"PRAGMA foreign_key_check violations: {len(fk_violations)}")
    if fk_violations:
        raise RuntimeError(f"Foreign key violations found: {fk_violations}")

    conn.close()
    print("=== Remediation D Database Migration Completed Successfully ===")


if __name__ == "__main__":
    target_db = sys.argv[1] if len(sys.argv) > 1 else "data/prospects.db"
    run_migration(target_db)
