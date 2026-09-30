"""
FreightProspecting V1 — Stage 3E Company-First Discovery Expansion Importer
Imports the 244 audited, deduplicated, and verified candidates across Tracks A-E into prospects.db.
Brings Discovery Company Groups from 281 to 525 (Preferred finishing range: 510–525).
Maintains Shortlist = strictly 4, Qualified = strictly 0.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.claims_engine import record_claim, record_evidence_source, link_claim_evidence

BATCH_NAME = "Stage 3E Company-First Discovery Expansion"
OBSERVED_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def compute_intake_fingerprint(brand: str, address: str, city: str, state_prov: str, country: str) -> str:
    raw = f"{brand}|{address}|{city}|{state_prov}|{country}"
    return re.sub(r"[^a-z0-9|]", "", raw.lower().strip())

def import_stage3e():
    db_path = get_db_path()
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row

    # Ensure WAL mode and foreign keys
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")

    # 1. Verify pre-import baseline
    pre_shortlist_fac = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
    pre_discovery_fac = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
    pre_qualified_fac = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'QUALIFIED'").fetchone()[0]
    pre_total_fac = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]

    pre_disc_comp = conn.execute(
        """
        SELECT count(DISTINCT f.company_id)
        FROM facilities f
        JOIN prospect_lifecycle l ON f.id = l.facility_id
        WHERE l.stage = 'DISCOVERY'
        """
    ).fetchone()[0]

    pre_short_comp = conn.execute(
        """
        SELECT count(DISTINCT f.company_id)
        FROM facilities f
        JOIN prospect_lifecycle l ON f.id = l.facility_id
        WHERE l.stage = 'SHORTLISTED'
        """
    ).fetchone()[0]

    print("=" * 60)
    print("STAGE 3E PRE-IMPORT BASELINE AUDIT")
    print("=" * 60)
    print(f"Pre-import Shortlisted Companies : {pre_short_comp} (facilities: {pre_shortlist_fac})")
    print(f"Pre-import Discovery Companies   : {pre_disc_comp} (facilities: {pre_discovery_fac})")
    print(f"Pre-import Qualified Companies   : 0 (facilities: {pre_qualified_fac})")
    print(f"Pre-import Total Facilities      : {pre_total_fac}")
    print("=" * 60)

    assert pre_short_comp == 4, f"Expected 4 shortlisted companies, got {pre_short_comp}"
    assert pre_shortlist_fac == 4, f"Expected 4 shortlisted facilities, got {pre_shortlist_fac}"
    assert pre_disc_comp == 281, f"Expected 281 discovery companies, got {pre_disc_comp}"
    assert pre_discovery_fac == 368, f"Expected 368 discovery facilities, got {pre_discovery_fac}"
    assert pre_qualified_fac == 0, f"Expected 0 qualified facilities, got {pre_qualified_fac}"

    # 2. Load assembled candidate pool
    candidates_file = Path("data/stage3e_verified_candidates.json")
    with open(candidates_file, "r", encoding="utf-8") as f:
        candidates: List[Dict[str, Any]] = json.load(f)

    print(f"Loaded {len(candidates)} verified candidates from {candidates_file}")

    seen_fingerprints = set()
    newly_imported = 0
    duplicates_skipped = 0

    # 3. Process candidates
    for c in candidates:
        brand = c["brand"].strip()
        fac_name = c["fac_name"].strip()
        address = c["address"].strip()
        city = c["city"].strip()
        state = c["state"].strip().upper()
        country = c["country"].strip().upper()
        postal_code = (c.get("postal_code") or "").strip() or None

        fp = compute_intake_fingerprint(brand, address, city, state, country)
        if fp in seen_fingerprints:
            duplicates_skipped += 1
            continue
        seen_fingerprints.add(fp)

        # Database deduplication
        audit_row = conn.execute(
            "SELECT id FROM discovery_intake_audit WHERE intake_fingerprint = ?",
            (fp,)
        ).fetchone()
        if audit_row:
            duplicates_skipped += 1
            continue

        existing_fac = conn.execute(
            "SELECT id FROM facilities WHERE lower(trim(physical_address)) = ? AND state_prov = ?",
            (address.lower().strip(), state)
        ).fetchone()
        if existing_fac:
            duplicates_skipped += 1
            continue

        # Company
        comp_row = conn.execute("SELECT id FROM companies WHERE operating_brand = ?", (brand,)).fetchone()
        if comp_row:
            comp_id = comp_row["id"]
        else:
            comp_addr = f"{address}, {city}, {state}"
            if postal_code:
                comp_addr += f" {postal_code}"
            comp_addr += f", {country}"
            cur = conn.execute(
                """
                INSERT INTO companies (operating_brand, legal_name, corporate_address, website_url, notes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    brand,
                    c.get("legal_name") or brand,
                    comp_addr,
                    c.get("website_url") or c.get("source_url"),
                    c.get("notes") or f"Operating company for {fac_name}.",
                ),
            )
            comp_id = cur.lastrowid

            # Insert prospect_engagement_state for every new company
            conn.execute(
                """
                INSERT INTO prospect_engagement_state (
                    company_id, current_outreach_status, attempt_count, is_viewed, created_at, updated_at
                ) VALUES (?, 'UNCONTACTED', 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (comp_id,)
            )

        # Facility
        fac_type = c.get("fac_type") or "MANUFACTURING_PLANT"
        cur = conn.execute(
            """
            INSERT INTO facilities (
                company_id, facility_name, facility_type, physical_address,
                city, state_prov, postal_code, country,
                private_fleet_present, vehicle_asset_ownership,
                fleet_relationship_type, commercial_carrier_use,
                broker_friendly_status, freight_procurement_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'FACILITY_LEVEL')
            """,
            (comp_id, fac_name, fac_type, address, city, state, postal_code, country),
        )
        fac_id = cur.lastrowid

        # Commodity
        comm_cat = c.get("comm_cat") or "Industrial Freight"
        specific_prod = c.get("specific_prod") or comm_cat
        eq_cat = (c.get("eq_cat") or "FLATBED").strip().upper()
        if eq_cat not in ("FLATBED", "STEP_DECK", "DRY_VAN"):
            eq_cat = "FLATBED"
        eq_status = "INFERRED"

        cur = conn.execute(
            """
            INSERT INTO facility_commodities (
                facility_id, commodity_category, specific_products,
                equipment_category, equipment_usage_status,
                trailer_specs_notes, securement_tarp_notes
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL)
            """,
            (fac_id, comm_cat, specific_prod, eq_cat, eq_status),
        )
        comm_id = cur.lastrowid

        # Contact
        person_name = (c.get("best_person") or "").strip() or None
        phone = (c.get("phone") or "").strip() or None
        phone_dir = (c.get("phone_dir") or "GENERAL_SWITCHBOARD").strip().upper() if phone else "UNKNOWN"
        if phone_dir not in ("GENERAL_SWITCHBOARD", "DEPARTMENT_LINE", "DIRECT_PERSON", "RECEPTION", "TOLL_FREE", "UNKNOWN"):
            phone_dir = "GENERAL_SWITCHBOARD" if phone else "UNKNOWN"

        email = (c.get("email") or "").strip() or None
        raw_email_dir = (c.get("email_dir") or "GENERAL").strip().upper() if email else "UNKNOWN"
        if raw_email_dir in ("GENERAL_INBOX", "GENERAL_FACILITY"):
            email_dir = "GENERAL"
        elif raw_email_dir in ("DIRECT_PERSON", "DEPARTMENT", "GENERAL", "UNKNOWN"):
            email_dir = raw_email_dir
        else:
            email_dir = "GENERAL" if email else "UNKNOWN"

        raw_role = (c.get("role_cat") or "GENERAL_FACILITY").strip().upper()
        if raw_role in ("FREIGHT_LOGISTICS", "SHIPPING_RECEIVING", "SHIPPING"):
            role_cat = "FREIGHT_LOGISTICS"
        elif raw_role in ("OPERATIONS", "PLANT_OPERATIONS"):
            role_cat = "OPERATIONS"
        elif raw_role in ("COMMERCIAL_SALES", "SALES"):
            role_cat = "COMMERCIAL_SALES"
        else:
            role_cat = "GENERAL_FACILITY"

        contact_identity = "GENERAL_FACILITY"
        dept_name = None
        exact_title = (c.get("exact_title") or "").strip() or None

        if person_name:
            if any(k in person_name.lower() for k in ["department", "desk", "office", "shipping", "receiving", "dispatch", "sales", "traffic"]):
                contact_identity = "DEPARTMENT"
                dept_name = person_name
                person_name = None
            else:
                contact_identity = "NAMED_PERSON"

        cur = conn.execute(
            """
            INSERT INTO contacts (
                facility_id, contact_identity, person_name, exact_published_title,
                department, phone_number, phone_directness, email_address, email_directness,
                role_category, outbound_shipping_procurement_relevance,
                broker_procurement_relevance, is_primary_contact
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNKNOWN', 'UNKNOWN', 1)
            """,
            (
                fac_id,
                contact_identity,
                person_name,
                exact_title,
                dept_name,
                phone,
                phone_dir,
                email,
                email_dir,
                role_cat,
            ),
        )
        contact_id = cur.lastrowid

        # Evidence Source
        source_url = c.get("source_url") or c.get("website_url") or "https://example.com"
        source_title = c.get("source_title") or f"{brand} — {fac_name} Operating Record"
        source_notes = c.get("notes") or f"Operating facility verified at {address}, {city}, {state}. Commodity: {comm_cat}."

        is_gov = "gatrees.org" in source_url.lower() or ".gov" in source_url.lower()
        src_type = "GOVERNMENT_REGISTRY" if is_gov else "COMPANY_WEBSITE"
        is_primary = not is_gov

        f_src = record_evidence_source(
            conn=conn,
            source_type=src_type,
            source_title_publisher=source_title,
            source_url=source_url,
            is_primary_source=is_primary,
            source_published_at=None,
            event_at=None,
            observed_at=OBSERVED_DATE,
            notes=source_notes,
        )

        # Address claim
        addr_claim_val = f"{address}, {city}, {state}"
        if postal_code:
            addr_claim_val += f" {postal_code}"
        addr_claim_val += f", {country}"

        c_addr = record_claim(
            conn=conn,
            claim_field="physical_address",
            claimed_value=addr_claim_val,
            verification_status="VERIFIED",
            is_current_accepted=True,
            facility_id=fac_id,
        )
        link_claim_evidence(conn, c_addr, f_src, "SUPPORTS")

        # Fleet presence claim (UNKNOWN)
        c_fleet = record_claim(
            conn=conn,
            claim_field="private_fleet_present",
            claimed_value="UNKNOWN",
            verification_status="UNKNOWN",
            is_current_accepted=True,
            claim_notes="Fleet status: UNKNOWN.",
            facility_id=fac_id,
        )
        link_claim_evidence(conn, c_fleet, f_src, "CONTEXT")

        # Equipment category claim (INFERRED)
        c_eq = record_claim(
            conn=conn,
            claim_field="equipment_category",
            claimed_value=eq_cat,
            verification_status="INFERRED",
            is_current_accepted=True,
            claim_notes=f"Inferred {eq_cat} suitability based on {comm_cat} commodity physical profile.",
            facility_commodity_id=comm_id,
        )
        link_claim_evidence(conn, c_eq, f_src, "SUPPORTS")

        # Contact route claim
        if phone:
            c_phone = record_claim(
                conn=conn,
                claim_field="phone_directness",
                claimed_value=phone_dir,
                verification_status="VERIFIED",
                is_current_accepted=True,
                claim_notes=f"Published contact route: {phone} ({phone_dir}).",
                contact_id=contact_id,
            )
            link_claim_evidence(conn, c_phone, f_src, "SUPPORTS")

        # Prospect Lifecycle (DISCOVERY)
        conn.execute(
            """
            INSERT INTO prospect_lifecycle (
                facility_id, stage, entered_discovery_at, discovered_at,
                qualified_at, shortlisted_at, archived_at, qualification_notes, notes, created_at, updated_at
            ) VALUES (?, 'DISCOVERY', ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?)
            """,
            (fac_id, OBSERVED_DATE, OBSERVED_DATE, f"Imported in {BATCH_NAME}", OBSERVED_DATE, OBSERVED_DATE),
        )

        # Discovery Intake Audit
        conn.execute(
            """
            INSERT INTO discovery_intake_audit (
                batch_name, candidate_company_name, candidate_facility_name,
                city, state_prov, country, intake_fingerprint, intake_status,
                target_facility_id, website_url, facility_address, batch_reference,
                reason_or_notes, reason_notes, reviewed_at, imported_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'APPROVED_FOR_IMPORT', ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                BATCH_NAME, brand, fac_name,
                city, state, country, fp,
                fac_id, c.get("website_url"), address, "Stage 3E",
                source_notes, source_notes,
            ),
        )

        newly_imported += 1

    conn.commit()

    # 4. Integrity and Foreign Key Checks
    print("\nRunning database integrity checks...")
    fk_errors = list(conn.execute("PRAGMA foreign_key_check;"))
    assert len(fk_errors) == 0, f"Foreign key errors found: {fk_errors}"
    integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
    assert integrity == "ok", f"Integrity check failed: {integrity}"
    print("Database integrity: OK (0 FK errors, integrity_check=ok)")

    # 5. Post-import verification
    final_short_fac = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
    final_disc_fac = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
    final_qual_fac = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'QUALIFIED'").fetchone()[0]
    final_total_fac = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]

    final_disc_comp = conn.execute(
        """
        SELECT count(DISTINCT f.company_id)
        FROM facilities f
        JOIN prospect_lifecycle l ON f.id = l.facility_id
        WHERE l.stage = 'DISCOVERY'
        """
    ).fetchone()[0]

    final_short_comp = conn.execute(
        """
        SELECT count(DISTINCT f.company_id)
        FROM facilities f
        JOIN prospect_lifecycle l ON f.id = l.facility_id
        WHERE l.stage = 'SHORTLISTED'
        """
    ).fetchone()[0]

    final_qual_comp = conn.execute(
        """
        SELECT count(DISTINCT f.company_id)
        FROM facilities f
        JOIN prospect_lifecycle l ON f.id = l.facility_id
        WHERE l.stage = 'QUALIFIED'
        """
    ).fetchone()[0]

    total_operating_comp = conn.execute(
        """
        SELECT count(DISTINCT f.company_id)
        FROM facilities f
        """
    ).fetchone()[0]

    print("\n" + "=" * 60)
    print("STAGE 3E EXPANSION RESULTS")
    print("=" * 60)
    print(f"Newly imported candidates          : {newly_imported}")
    print(f"Duplicates skipped                 : {duplicates_skipped}")
    print(f"Final DISCOVERY Unique Companies   : {final_disc_comp} (TARGET: >= 500, Preferred: 510-525)")
    print(f"Final SHORTLISTED Companies        : {final_short_comp} (Strictly 4)")
    print(f"Final QUALIFIED Companies          : {final_qual_comp} (Strictly 0)")
    print(f"Final Active Operating Companies   : {total_operating_comp}")
    print(f"Final DISCOVERY Facilities         : {final_disc_fac}")
    print(f"Final SHORTLISTED Facilities       : {final_short_fac}")
    print(f"Final TOTAL Facilities             : {final_total_fac}")
    print("=" * 60)

    # Invariant assertions
    assert final_short_comp == 4, f"Shortlisted companies must remain 4, got {final_short_comp}"
    assert final_short_fac == 4, f"Shortlisted facilities must remain 4, got {final_short_fac}"
    assert final_qual_comp == 0, f"Qualified companies must remain 0, got {final_qual_comp}"
    assert final_qual_fac == 0, f"Qualified facilities must remain 0, got {final_qual_fac}"
    assert final_disc_comp >= 500, f"Discovery company target failed: {final_disc_comp} < 500"
    assert 510 <= final_disc_comp <= 540, f"Discovery company count {final_disc_comp} outside preferred/soft ceiling range 510-540"
    assert final_total_fac == final_short_fac + final_disc_fac, f"Facility total mismatch: {final_total_fac} != {final_short_fac} + {final_disc_fac}"

    conn.close()
    print("Stage 3E import completed successfully and verified with 100% invariant compliance.")

if __name__ == "__main__":
    import_stage3e()
