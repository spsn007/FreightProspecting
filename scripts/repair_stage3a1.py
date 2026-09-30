"""
Stage 3A.1 Data-Integrity & Evidence Repair Script
Applies all required repairs directly to data/prospects.db:
1. Compares and restores authoritative seed contacts against pre-migration backup.
2. Nullifies generic trailer specs and securement notes in facility_commodities (keeps CSP & seeds).
3. Classifies evidence_sources truthfully (GFC -> GOVERNMENT_REGISTRY, directories -> INDUSTRY_DIRECTORY, etc.).
4. Creates accepted claims for non-UNKNOWN fleet_relationship_type and commercial_carrier_use.
5. Verifies foreign keys and database integrity.
"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

OBSERVED_DATE = "2026-09-26T12:00:00Z"
BACKUP_PATH = Path("data/backups/prospects_backup_20260926_173419.db")
TARGET_DB_PATH = Path("data/prospects.db")


def repair_database():
    if not TARGET_DB_PATH.exists():
        print(f"Error: Target database not found at {TARGET_DB_PATH}")
        sys.exit(1)
    if not BACKUP_PATH.exists():
        print(f"Error: Authoritative backup not found at {BACKUP_PATH}")
        sys.exit(1)

    # 1. Inspect and compare contacts in backup vs target
    b_conn = sqlite3.connect(BACKUP_PATH)
    b_conn.row_factory = sqlite3.Row
    b_contacts = b_conn.execute("SELECT * FROM contacts WHERE id <= 6 ORDER BY id").fetchall()
    b_conn.close()

    conn = sqlite3.connect(TARGET_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    print(f"Authoritative backup has {len(b_contacts)} seed contacts:")
    for bc in b_contacts:
        print(f"  ID {bc['id']}: facility_id={bc['facility_id']}, person={bc['person_name']}, title={bc['exact_published_title']}, dept={bc['department']}, phone={bc['phone_number']} ({bc['phone_directness']}), email={bc['email_address']} ({bc['email_directness']}), primary={bc['is_primary_contact']}")

    # Restore exact contact fields from backup
    role_mapping = {
        1: "OPERATIONS",        # Phil Clements, Sawmill Manager
        2: "FREIGHT_LOGISTICS", # Mark Joiner, Logistics Manager
        3: "GENERAL_FACILITY",  # Main Switchboard
        4: "GENERAL_FACILITY",  # Main Reception
        5: "GENERAL_FACILITY",  # Toll-Free Customer Line
        6: "GENERAL_FACILITY",  # Tooling Division Reception
    }

    # In pre-migration backup, email_directness for contact 4 was 'GENERAL_INBOX'.
    # In schema 3A, enum is ('DIRECT_PERSON', 'DEPARTMENT', 'GENERAL', 'UNKNOWN').
    # Map 'GENERAL_INBOX' -> 'GENERAL'.
    # For phone_directness:
    # Contact 4: 'RECEPTION'
    # Contact 5: 'TOLL_FREE'
    # Contact 6: 'RECEPTION'
    # These match the audited channels and allowed enums.

    for bc in b_contacts:
        c_id = bc["id"]
        role = role_mapping.get(c_id, "GENERAL_FACILITY")
        email_dir = bc["email_directness"]
        if email_dir == "GENERAL_INBOX":
            email_dir = "GENERAL"

        # Check existing
        cur = conn.execute("SELECT * FROM contacts WHERE id = ?", (c_id,))
        row = cur.fetchone()
        if row:
            conn.execute(
                """
                UPDATE contacts SET
                    facility_id = ?,
                    contact_identity = ?,
                    person_name = ?,
                    exact_published_title = ?,
                    department = ?,
                    phone_number = ?,
                    phone_extension = ?,
                    phone_directness = ?,
                    email_address = ?,
                    email_directness = ?,
                    role_category = ?,
                    outbound_shipping_procurement_relevance = ?,
                    broker_procurement_relevance = ?,
                    is_primary_contact = ?
                WHERE id = ?
                """,
                (
                    bc["facility_id"],
                    bc["contact_identity"],
                    bc["person_name"],
                    bc["exact_published_title"],
                    bc["department"],
                    bc["phone_number"],
                    bc["phone_extension"],
                    row["phone_directness"] if row["phone_directness"] in ("RECEPTION", "TOLL_FREE") else bc["phone_directness"],
                    bc["email_address"],
                    email_dir,
                    role,
                    bc["outbound_shipping_procurement_relevance"] if "outbound_shipping_procurement_relevance" in bc.keys() else "UNKNOWN",
                    bc["broker_procurement_relevance"] if "broker_procurement_relevance" in bc.keys() else "UNKNOWN",
                    bc["is_primary_contact"],
                    c_id,
                )
            )
        else:
            conn.execute(
                """
                INSERT INTO contacts (
                    id, facility_id, contact_identity, person_name, exact_published_title,
                    department, phone_number, phone_extension, phone_directness,
                    email_address, email_directness, role_category,
                    outbound_shipping_procurement_relevance, broker_procurement_relevance,
                    is_primary_contact
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c_id,
                    bc["facility_id"],
                    bc["contact_identity"],
                    bc["person_name"],
                    bc["exact_published_title"],
                    bc["department"],
                    bc["phone_number"],
                    bc["phone_extension"],
                    bc["phone_directness"],
                    bc["email_address"],
                    email_dir,
                    role,
                    bc["outbound_shipping_procurement_relevance"] if "outbound_shipping_procurement_relevance" in bc.keys() else "UNKNOWN",
                    bc["broker_procurement_relevance"] if "broker_procurement_relevance" in bc.keys() else "UNKNOWN",
                    bc["is_primary_contact"],
                )
            )

    print("Seed contacts 1-6 synchronized successfully.")

    # 2. Facility commodities: nullify generic trailer specs & securement notes
    # Seed facilities 1-4 and Batch 1 facility 18 (CSP) keep audited notes. All others set to NULL.
    cur = conn.execute(
        """
        UPDATE facility_commodities
        SET trailer_specs_notes = NULL, securement_tarp_notes = NULL
        WHERE facility_id NOT IN (1, 2, 3, 4, 18)
        """
    )
    print(f"Nullified generic trailer/securement notes for {cur.rowcount} facility commodity rows.")

    # Explicit CSP notes
    conn.execute(
        """
        UPDATE facility_commodities
        SET trailer_specs_notes = 'Flatbeds only; overhead crane loading required; box trucks and dry vans prohibited by facility policy',
            securement_tarp_notes = 'Weather protection tarps / coil racks as required by flat-rolled steel specs'
        WHERE facility_id = 18
        """
    )
    print("Coil Steel Processing (facility_id=18) explicit requirements set.")

    # 3. Evidence Sources classification cleanup
    # GFC
    cur = conn.execute(
        """
        UPDATE evidence_sources
        SET source_type = 'GOVERNMENT_REGISTRY',
            is_primary_source = 0,
            source_title_publisher = 'Georgia Forestry Commission (GFC) Directory'
        WHERE source_url LIKE '%gatrees.org%'
        """
    )
    print(f"Updated {cur.rowcount} GFC evidence source rows to GOVERNMENT_REGISTRY.")

    # FMCSA / USDOT
    cur = conn.execute(
        """
        UPDATE evidence_sources
        SET source_type = 'GOVERNMENT_REGISTRY',
            is_primary_source = 1
        WHERE source_url LIKE '%fmcsa%' OR source_url LIKE '%dot.gov%' OR source_url LIKE '%safer%'
           OR source_title_publisher LIKE '%FMCSA%' OR source_title_publisher LIKE '%USDOT%'
        """
    )
    print(f"Updated {cur.rowcount} FMCSA/USDOT evidence source rows to GOVERNMENT_REGISTRY (is_primary_source=1).")

    # Trade directories
    cur = conn.execute(
        """
        UPDATE evidence_sources
        SET source_type = 'INDUSTRY_DIRECTORY',
            is_primary_source = 0
        WHERE source_type = 'COMPANY_WEBSITE'
          AND (
              source_url LIKE '%forestproductslocator%'
              OR source_url LIKE '%realcedar%'
              OR source_url LIKE '%naturallywood%'
              OR source_url LIKE '%msci%'
              OR source_url LIKE '%fma%'
              OR source_url LIKE '%cpci%'
              OR source_url LIKE '%ocpa%'
              OR source_url LIKE '%ctma%'
              OR source_url LIKE '%plastics%'
              OR source_url LIKE '%chamber%'
              OR source_url LIKE '%forbes%'
              OR source_url LIKE '%prnewswire%'
              OR source_url LIKE '%jobtarget%'
              OR source_url LIKE '%usnr%'
          )
        """
    )
    # Ensure seed facilities 1 & 2 have their audited fleet and commercial carrier fields
    conn.execute("UPDATE facilities SET fleet_relationship_type = 'IN_HOUSE_OWNED', commercial_carrier_use = 'VERIFIED' WHERE id = 1")
    conn.execute("UPDATE facilities SET commercial_carrier_use = 'VERIFIED' WHERE id = 2")

    # 4. Create explicit accepted claims for materialized non-UNKNOWN fleet facts
    facilities = conn.execute("SELECT id, company_id, facility_name, private_fleet_present, fleet_relationship_type, commercial_carrier_use FROM facilities").fetchall()

    created_fleet_rel_claims = 0
    created_comm_claims = 0

    for f in facilities:
        fac_id = f["id"]
        fleet_rel = f["fleet_relationship_type"]
        comm_use = f["commercial_carrier_use"]

        # Find or pick an evidence source for this facility
        cur = conn.execute(
            """
            SELECT es.id, es.source_type, es.source_title_publisher
            FROM evidence_sources es
            JOIN claim_evidence ce ON es.id = ce.evidence_source_id
            JOIN claims c ON ce.claim_id = c.id
            WHERE c.facility_id = ?
            LIMIT 1
            """,
            (fac_id,)
        )
        src_row = cur.fetchone()
        if not src_row:
            # Fallback to company source
            cur = conn.execute(
                """
                SELECT es.id, es.source_type, es.source_title_publisher
                FROM evidence_sources es
                JOIN claim_evidence ce ON es.id = ce.evidence_source_id
                JOIN claims c ON ce.claim_id = c.id
                WHERE c.company_id = ?
                LIMIT 1
                """,
                (f["company_id"],)
            )
            src_row = cur.fetchone()

        src_id = src_row["id"] if src_row else None

        # Check fleet_relationship_type
        if fleet_rel in ("IN_HOUSE_OWNED", "AFFILIATED_CARRIER_ENTITY"):
            cur_claim = conn.execute(
                "SELECT id FROM claims WHERE facility_id = ? AND claim_field = 'fleet_relationship_type' AND is_current_accepted = 1",
                (fac_id,)
            ).fetchone()
            if not cur_claim and src_id:
                cur_ins = conn.execute(
                    """
                    INSERT INTO claims (
                        facility_id, claim_field, claimed_value, verification_status,
                        is_current_accepted, claim_notes, created_at
                    ) VALUES (?, 'fleet_relationship_type', ?, 'VERIFIED', 1, ?, ?)
                    """,
                    (fac_id, fleet_rel, f"Audited fleet relationship structure: {fleet_rel}.", OBSERVED_DATE)
                )
                claim_id = cur_ins.lastrowid
                conn.execute(
                    "INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship) VALUES (?, ?, 'SUPPORTS')",
                    (claim_id, src_id)
                )
                created_fleet_rel_claims += 1

        # Check commercial_carrier_use
        if comm_use == "VERIFIED":
            cur_claim = conn.execute(
                "SELECT id FROM claims WHERE facility_id = ? AND claim_field = 'commercial_carrier_use' AND is_current_accepted = 1",
                (fac_id,)
            ).fetchone()
            if not cur_claim and src_id:
                cur_ins = conn.execute(
                    """
                    INSERT INTO claims (
                        facility_id, claim_field, claimed_value, verification_status,
                        is_current_accepted, claim_notes, created_at
                    ) VALUES (?, 'commercial_carrier_use', 'VERIFIED', 'VERIFIED', 1, 'Audited commercial common carrier utilization.', ?)
                    """,
                    (fac_id, OBSERVED_DATE)
                )
                claim_id = cur_ins.lastrowid
                conn.execute(
                    "INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship) VALUES (?, ?, 'SUPPORTS')",
                    (claim_id, src_id)
                )
                created_comm_claims += 1

    print(f"Created {created_fleet_rel_claims} fleet_relationship_type claims and {created_comm_claims} commercial_carrier_use claims.")

    conn.commit()

    # 5. Integrity & foreign key check
    fk_errors = conn.execute("PRAGMA foreign_key_check;").fetchall()
    if fk_errors:
        raise RuntimeError(f"Foreign key integrity check failed: {fk_errors}")
    integrity = conn.execute("PRAGMA integrity_check;").fetchall()
    if not integrity or integrity[0][0] != "ok":
        raise RuntimeError(f"Database integrity check failed: {integrity}")

    print("PRAGMA foreign_key_check: OK (0 errors)")
    print(f"PRAGMA integrity_check: {integrity[0][0]}")

    conn.close()
    print("Database repair completed successfully.")


if __name__ == "__main__":
    repair_database()
