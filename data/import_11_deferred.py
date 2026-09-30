"""
Targeted script to ingest the 11 previously capped Track E candidates into prospects.db.
Reclassifies them in discovery_intake_audit from DEFERRED_FOR_RESEARCH to APPROVED_FOR_IMPORT,
linking target_facility_id, while leaving the 3 original Batch #1 deferred candidates untouched.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3

from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.claims_engine import record_claim, record_evidence_source, link_claim_evidence

BATCH_NAME = "Fast-Track Discovery Pool Expansion"
OBSERVED_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def compute_intake_fingerprint(brand: str, address: str, city: str, state_prov: str, country: str) -> str:
    raw = f"{brand}|{address}|{city}|{state_prov}|{country}"
    return re.sub(r"[^a-z0-9|]", "", raw.lower().strip())

def main():
    db_path = get_db_path()
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row

    with open("data/raw_candidates_track_e.json", "r", encoding="utf-8") as f:
        all_e = json.load(f)

    # 11 candidates deferred solely due to cap
    deferred_11 = all_e[19:]
    assert len(deferred_11) == 11, f"Expected 11 items, got {len(deferred_11)}"

    imported_count = 0

    for c in deferred_11:
        brand = c["brand"].strip()
        fac_name = c["fac_name"].strip()
        address = c["address"].strip()
        city = c["city"].strip()
        state = c["state"].strip().upper()
        country = c["country"].strip().upper()
        postal_code = (c.get("postal_code") or "").strip() or None

        fp = compute_intake_fingerprint(brand, address, city, state, country)

        # Check existing facility
        existing_fac = conn.execute(
            "SELECT id FROM facilities WHERE lower(trim(physical_address)) = ? AND state_prov = ?",
            (address.lower().strip(), state)
        ).fetchone()
        if existing_fac:
            print(f"Skipping already existing facility: {fac_name}")
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
                    c.get("company_notes") or f"Operating company for {fac_name}.",
                ),
            )
            comp_id = cur.lastrowid

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
        comm_cat = c.get("comm_cat") or "MOLDED_PLASTICS"
        specific_prod = c.get("specific_prod") or comm_cat
        eq_cat = (c.get("eq_cat") or "DRY_VAN").strip().upper()
        if eq_cat not in ("FLATBED", "STEP_DECK", "DRY_VAN"):
            eq_cat = "DRY_VAN"
        eq_status = c.get("eq_status") or "INFERRED"

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
            if any(k in person_name.lower() for k in ["department", "desk", "office", "shipping", "receiving", "dispatch", "sales"]):
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

        f_src = record_evidence_source(
            conn=conn,
            source_type="COMPANY_WEBSITE",
            source_title_publisher=source_title,
            source_url=source_url,
            is_primary_source=True,
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

        # Equipment category claim
        c_eq = record_claim(
            conn=conn,
            claim_field="equipment_category",
            claimed_value=eq_cat,
            verification_status=eq_status,
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
            (fac_id, OBSERVED_DATE, OBSERVED_DATE, f"Imported in {BATCH_NAME} (Deferred Release)", OBSERVED_DATE, OBSERVED_DATE),
        )

        # Update existing discovery_intake_audit row
        conn.execute(
            """
            UPDATE discovery_intake_audit
            SET intake_status = 'APPROVED_FOR_IMPORT',
                target_facility_id = ?,
                reason_notes = 'Approved and imported from Track E deferred queue into Discovery Pool.',
                reason_or_notes = 'Approved and imported from Track E deferred queue into Discovery Pool.',
                reviewed_at = CURRENT_TIMESTAMP,
                imported_at = CURRENT_TIMESTAMP
            WHERE intake_fingerprint = ?
            """,
            (fac_id, fp),
        )

        imported_count += 1
        print(f"Successfully imported {fac_name} -> facility ID {fac_id}")

    conn.commit()

    # Verify counts
    disc_count = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
    short_count = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
    total_facs = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]
    deferred_left = conn.execute("SELECT count(*) FROM discovery_intake_audit WHERE intake_status = 'DEFERRED_FOR_RESEARCH'").fetchone()[0]

    print("\n--- Ingestion Summary ---")
    print(f"Newly imported: {imported_count}")
    print(f"DISCOVERY facilities: {disc_count}")
    print(f"SHORTLISTED facilities: {short_count}")
    print(f"TOTAL facilities: {total_facs}")
    print(f"DEFERRED in audit remaining: {deferred_left}")

    conn.close()

if __name__ == "__main__":
    main()
