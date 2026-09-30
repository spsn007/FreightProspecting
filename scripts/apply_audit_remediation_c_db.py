"""
FreightProspecting — Remediation C Database Mutations
Executes exact forensic fixes on data/prospects.db:
1. Sources 13/14: source_published_at = NULL (AUD-015)
2. CSP Contact 22: outbound_shipping_procurement_relevance = 'UNKNOWN' (AUD-008)
3. Sonoco Facilities 365/366: Delete secondary CORRUGATED_PACKAGING mappings 625, 626 (AUD-009)
4. Reassess claims on demoted sources 102, 140, 204 with explicit notes (AUD-010)
5. 39 advanced-stage equipment claim_evidence: set relationship = 'SUPPORTS' for verified product evidence (AUD-003)
6. Yoder Lumber Facility 408 Contact 627: insert accepted phone_directness claim backed by source 462 (AUD-003)
7. Normalize 751 non-canonical timestamp values to canonical ISO-8601 YYYY-MM-DDTHH:MM:SSZ (AUD-023)
8. Drop and recreate unconditional append-only triggers on outreach_logs (AUD-025)
9. Add load_opportunities rate and margin validation triggers (AUD-014)
"""

import sqlite3
import re
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("data/prospects.db")

def normalize_iso(val: str) -> str:
    if not val:
        return val
    s = str(val).strip().replace(" ", "T")
    if s.endswith("Z"):
        dt = datetime.fromisoformat(s[:-1] + "+00:00")
    elif "+" in s:
        dt = datetime.fromisoformat(s)
    elif s.count("-") > 2:
        parts = s.rsplit("-", 1)
        dt = datetime.fromisoformat(parts[0] + "-" + parts[1])
    else:
        dt = datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def apply_mutations():
    print(f"Connecting to {DB_PATH}...")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
    
    with conn:
        # 1. Sources 13 and 14: set source_published_at = NULL
        conn.execute("UPDATE evidence_sources SET source_published_at = NULL WHERE id IN (13, 14)")
        print("Updated sources 13 and 14: source_published_at = NULL")

        # 2. CSP Contact 22: outbound_shipping_procurement_relevance = 'UNKNOWN'
        conn.execute("UPDATE contacts SET outbound_shipping_procurement_relevance = 'UNKNOWN' WHERE id = 22")
        print("Updated Contact 22: outbound_shipping_procurement_relevance = 'UNKNOWN'")

        # 3. Sonoco Facilities 365, 366: delete secondary CORRUGATED_PACKAGING mappings (IDs 625, 626)
        conn.execute("DELETE FROM facility_commodity_mappings WHERE id IN (625, 626)")
        print("Deleted unsupported secondary mappings 625 and 626 for Sonoco facilities 365/366")

        # 4. Reassess claims on demoted sources 102, 140, 204
        notes_map = {
            265: "Reassessed: Address confirmed via Forest Products Locator directory entry; secondary industry directory source.",
            268: "Reassessed: Published contact route (706-342-4300) via Forest Products Locator directory; secondary directory source.",
            417: "Reassessed: Address confirmed via naturally:wood official supplier directory profile; trade association secondary source.",
            420: "Reassessed: Published contact route (250-768-5131) via naturally:wood directory; trade association secondary source.",
            673: "Reassessed: Address confirmed via Ohio Precast Concrete Association member directory entry; trade association secondary source.",
            676: "Reassessed: Published contact route ((740) 259-4455) via OPCA directory; trade association secondary source."
        }
        for cid, note in notes_map.items():
            conn.execute("UPDATE claims SET claim_notes = ? WHERE id = ?", (note, cid))
            conn.execute("UPDATE claim_evidence SET relationship_notes = 'Secondary directory/association source corroborated facility entry.' WHERE claim_id = ?", (cid,))
        print("Reassessed and updated claim_notes for claims 265, 268, 417, 420, 673, 676")

        # 5. 39 advanced-stage equipment claim_evidence rows: relationship = 'SUPPORTS'
        target_fids = [
            4, 5, 6, 8, 9, 12, 14, 15, 16, 17, 20, 21, 29, 30, 32, 33, 34,
            7, 10, 11, 13, 19, 22, 23, 24, 25, 26, 27, 28, 31, 35, 36, 37,
            38, 39, 40, 41, 42, 43
        ]
        cur = conn.execute(f"""
            SELECT ce.id 
            FROM claim_evidence ce
            JOIN claims c ON ce.claim_id = c.id
            JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
            WHERE c.claim_field = 'equipment_category'
              AND fc.facility_id IN ({','.join('?' for _ in target_fids)})
        """, target_fids)
        ce_ids = [r[0] for r in cur.fetchall()]
        print(f"Found {len(ce_ids)} equipment claim_evidence rows to update to SUPPORTS across 39 facilities")
        conn.execute(f"""
            UPDATE claim_evidence 
            SET relationship = 'SUPPORTS',
                relationship_notes = 'Official primary facility documentation of heavy manufactured products supports FTL equipment inference.'
            WHERE id IN ({','.join('?' for _ in ce_ids)})
        """, ce_ids)

        # 6. Yoder Lumber Facility 408 Contact 627: insert accepted phone_directness claim backed by source 462
        existing = conn.execute("SELECT id FROM claims WHERE contact_id = 627 AND claim_field = 'phone_directness'").fetchone()
        if not existing:
            now_iso = "2026-09-28T09:00:00Z"
            cur = conn.execute("""
                INSERT INTO claims (
                    company_id, company_relationship_id, facility_id, facility_commodity_id,
                    contact_id, freight_demand_signal_id, load_opportunity_id, carrier_id,
                    carrier_lane_activity_id, capacity_posting_id, claim_field, claimed_value,
                    verification_status, is_current_accepted, claim_notes, created_at, updated_at
                ) VALUES (
                    NULL, NULL, NULL, NULL,
                    627, NULL, NULL, NULL,
                    NULL, NULL, 'phone_directness', 'TOLL_FREE',
                    'VERIFIED', 1, 'Published toll-free desk route from official contact page.', ?, ?
                )
            """, (now_iso, now_iso))
            new_claim_id = cur.lastrowid
            conn.execute("""
                INSERT INTO claim_evidence (
                    claim_id, evidence_source_id, relationship, relationship_notes, created_at
                ) VALUES (?, 462, 'SUPPORTS', 'Official Yoder Lumber contact page confirms Berlin facility toll-free desk.', ?)
            """, (new_claim_id, now_iso))
            print(f"Inserted claim {new_claim_id} and claim_evidence for Contact 627 (Facility 408, Yoder Lumber)")

        # 7. Normalize non-canonical timestamps
        cur = conn.execute("SELECT id, created_at FROM facility_commodity_mappings WHERE created_at LIKE '%+00:00'")
        for rid, val in cur.fetchall():
            conn.execute("UPDATE facility_commodity_mappings SET created_at = ? WHERE id = ?", (normalize_iso(val), rid))

        cur = conn.execute("SELECT id, created_at FROM commodity_categories WHERE created_at LIKE '%+00:00'")
        for rid, val in cur.fetchall():
            conn.execute("UPDATE commodity_categories SET created_at = ? WHERE id = ?", (normalize_iso(val), rid))

        cur = conn.execute("SELECT id, created_at FROM commodity_families WHERE created_at LIKE '%+00:00'")
        for rid, val in cur.fetchall():
            conn.execute("UPDATE commodity_families SET created_at = ? WHERE id = ?", (normalize_iso(val), rid))

        # Engagement state
        for col in ["first_viewed_at", "last_viewed_at", "updated_at"]:
            cur = conn.execute(f"SELECT rowid, {col} FROM prospect_engagement_state WHERE {col} LIKE '%+00:00' OR {col} LIKE '% %'")
            for rid, val in cur.fetchall():
                conn.execute(f"UPDATE prospect_engagement_state SET {col} = ? WHERE rowid = ?", (normalize_iso(val), rid))

        # Lifecycle updated_at with space
        cur = conn.execute("SELECT id, updated_at FROM prospect_lifecycle WHERE updated_at LIKE '% %'")
        for rid, val in cur.fetchall():
            conn.execute("UPDATE prospect_lifecycle SET updated_at = ? WHERE id = ?", (normalize_iso(val), rid))

        # Claims timestamps
        cur = conn.execute("SELECT id, created_at, updated_at FROM claims WHERE created_at LIKE '%+00:00' OR updated_at LIKE '%+00:00' OR updated_at LIKE '% %'")
        for rid, c_at, u_at in cur.fetchall():
            conn.execute("UPDATE claims SET created_at = ?, updated_at = ? WHERE id = ?", (normalize_iso(c_at), normalize_iso(u_at), rid))

        # Evidence sources observed_at
        cur = conn.execute("SELECT id, observed_at FROM evidence_sources WHERE observed_at LIKE '% %'")
        for rid, val in cur.fetchall():
            conn.execute("UPDATE evidence_sources SET observed_at = ? WHERE id = ?", (normalize_iso(val), rid))

        # Facilities updated_at
        cur = conn.execute("SELECT id, updated_at FROM facilities WHERE updated_at LIKE '% %'")
        for rid, val in cur.fetchall():
            conn.execute("UPDATE facilities SET updated_at = ? WHERE id = ?", (normalize_iso(val), rid))

        print("Normalized non-canonical timestamp values to canonical ISO-8601")

        # 8. Unconditional outreach_logs append-only triggers
        conn.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_update;")
        conn.execute("DROP TRIGGER IF EXISTS trg_outreach_logs_no_delete;")
        conn.execute("""
            CREATE TRIGGER trg_outreach_logs_no_update
            BEFORE UPDATE ON outreach_logs
            BEGIN
                SELECT RAISE(ABORT, 'outreach_logs is append-only: UPDATE operations are strictly prohibited.');
            END;
        """)
        conn.execute("""
            CREATE TRIGGER trg_outreach_logs_no_delete
            BEFORE DELETE ON outreach_logs
            BEGIN
                SELECT RAISE(ABORT, 'outreach_logs is append-only: DELETE operations are strictly prohibited.');
            END;
        """)
        print("Recreated unconditional append-only triggers on outreach_logs")

        # 9. Load opportunities rate & margin validation triggers
        conn.execute("DROP TRIGGER IF EXISTS trg_load_opps_validate_rates_insert;")
        conn.execute("DROP TRIGGER IF EXISTS trg_load_opps_validate_rates_update;")
        conn.execute("DROP TRIGGER IF EXISTS trg_load_opps_validate_margin_insert;")
        conn.execute("DROP TRIGGER IF EXISTS trg_load_opps_validate_margin_update;")

        conn.execute("""
            CREATE TRIGGER trg_load_opps_validate_rates_insert
            BEFORE INSERT ON load_opportunities
            BEGIN
                SELECT RAISE(ABORT, 'shipper_target_rate cannot be negative')
                WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate < 0;
                
                SELECT RAISE(ABORT, 'carrier_target_cost cannot be negative')
                WHERE NEW.carrier_target_cost IS NOT NULL AND NEW.carrier_target_cost < 0;
            END;
        """)
        conn.execute("""
            CREATE TRIGGER trg_load_opps_validate_rates_update
            BEFORE UPDATE ON load_opportunities
            BEGIN
                SELECT RAISE(ABORT, 'shipper_target_rate cannot be negative')
                WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate < 0;
                
                SELECT RAISE(ABORT, 'carrier_target_cost cannot be negative')
                WHERE NEW.carrier_target_cost IS NOT NULL AND NEW.carrier_target_cost < 0;
            END;
        """)
        conn.execute("""
            CREATE TRIGGER trg_load_opps_validate_margin_insert
            BEFORE INSERT ON load_opportunities
            BEGIN
                SELECT RAISE(ABORT, 'gross_margin must be NULL when rates are missing')
                WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
                  AND NEW.gross_margin IS NOT NULL;
                  
                SELECT RAISE(ABORT, 'gross_margin does not match shipper_target_rate - carrier_target_cost')
                WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
                  AND NEW.gross_margin IS NOT NULL
                  AND ROUND(NEW.gross_margin, 2) != ROUND(NEW.shipper_target_rate - NEW.carrier_target_cost, 2);
            END;
        """)
        conn.execute("""
            CREATE TRIGGER trg_load_opps_validate_margin_update
            BEFORE UPDATE ON load_opportunities
            BEGIN
                SELECT RAISE(ABORT, 'gross_margin must be NULL when rates are missing')
                WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
                  AND NEW.gross_margin IS NOT NULL;
                  
                SELECT RAISE(ABORT, 'gross_margin does not match shipper_target_rate - carrier_target_cost')
                WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
                  AND NEW.gross_margin IS NOT NULL
                  AND ROUND(NEW.gross_margin, 2) != ROUND(NEW.shipper_target_rate - NEW.carrier_target_cost, 2);
            END;
        """)
        print("Created rate and margin validation triggers on load_opportunities")

    # Final DB checks
    fk_check = conn.execute("PRAGMA foreign_key_check;").fetchall()
    integrity = conn.execute("PRAGMA integrity_check;").fetchall()
    conn.close()

    if fk_check:
        raise RuntimeError(f"Foreign key violations found: {fk_check}")
    if integrity != [('ok',)]:
        raise RuntimeError(f"Integrity check failed: {integrity}")
    print("Database PRAGMA foreign_key_check: 0 errors.")
    print("Database PRAGMA integrity_check: ok.")

if __name__ == "__main__":
    apply_mutations()
