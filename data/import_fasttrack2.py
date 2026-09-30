"""
FreightProspecting V1 — Fast-Track Discovery Pool Expansion #2 Importer
Imports the 172 audited candidates across Tracks A2-F2 into prospects.db.
Brings Discovery Pool from 196 to 368 facilities (Preferred finishing range: 350-380).
Maintains Shortlist = strictly 4, Qualified = strictly 0.
"""

from datetime import datetime, timezone
import glob
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.claims_engine import record_claim, record_evidence_source, link_claim_evidence

BATCH_NAME = "Fast-Track Discovery Pool Expansion #2"
OBSERVED_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def compute_intake_fingerprint(brand: str, address: str, city: str, state_prov: str, country: str) -> str:
    raw = f"{brand}|{address}|{city}|{state_prov}|{country}"
    return re.sub(r"[^a-z0-9|]", "", raw.lower().strip())

def validate_candidate(c: Dict[str, Any]) -> Tuple[bool, str]:
    brand = (c.get("brand") or "").strip()
    if not brand:
        return False, "Missing company brand name"

    fac_name = (c.get("fac_name") or "").strip()
    if not fac_name:
        return False, "Missing facility name"

    address = (c.get("address") or "").strip()
    if not address or len(address) < 4:
        return False, "Missing valid physical street address"

    city = (c.get("city") or "").strip()
    state = (c.get("state") or "").strip()
    country = (c.get("country") or "").strip().upper()

    if not city or not state:
        return False, "Missing city or state/province"

    if country not in ("US", "CA"):
        return False, f"Country {country} outside US/Canada scope"

    phone = (c.get("phone") or "").strip()
    email = (c.get("email") or "").strip()
    if not phone and not email:
        return False, "Candidate lacks both callable phone and email route"

    source_url = (c.get("source_url") or c.get("website_url") or "").strip()
    if not source_url:
        return False, "Missing verification source URL"

    return True, "OK"

def load_batch2_files(data_dir: Path) -> List[Dict[str, Any]]:
    all_candidates = []
    track_files = sorted(data_dir.glob("raw_candidates_batch2_track_*.json"))
    for f in track_files:
        with open(f, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            if isinstance(data, list):
                for item in data:
                    item["_track_source_file"] = f.name
                all_candidates.extend(data)
                print(f"Loaded {len(data)} candidates from {f.name}")
    return all_candidates

def import_batch2():
    db_path = get_db_path()
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row

    # Verify pre-import state
    pre_shortlist = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
    pre_discovery = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
    pre_total = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]

    print(f"Pre-import state: SHORTLISTED={pre_shortlist}, DISCOVERY={pre_discovery}, TOTAL={pre_total}")
    assert pre_shortlist == 4, f"Expected 4 shortlisted, got {pre_shortlist}"
    assert pre_discovery == 196, f"Expected 196 discovery, got {pre_discovery}"

    candidates = load_batch2_files(Path("data"))
    print(f"Total Batch 2 candidates loaded: {len(candidates)}")

    seen_fingerprints = set()
    newly_imported = 0
    duplicates_skipped = 0

    for c in candidates:
        valid, reason = validate_candidate(c)
        if not valid:
            print(f"Rejected: {c.get('fac_name')} - {reason}")
            continue

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

        # Equipment category claim
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
        track_ref = c.get("_track_source_file") or BATCH_NAME
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
                fac_id, c.get("website_url"), address, track_ref,
                source_notes, source_notes,
            ),
        )

        newly_imported += 1

    conn.commit()

    # Post-import verification
    final_short = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
    final_disc = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
    final_qual = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'QUALIFIED'").fetchone()[0]
    final_total = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]

    print("\n================== IMPORT RESULTS ==================")
    print(f"Newly imported facilities: {newly_imported}")
    print(f"Duplicates skipped: {duplicates_skipped}")
    print(f"Final DISCOVERY count: {final_disc} (target range 350-380)")
    print(f"Final SHORTLISTED count: {final_short} (strictly 4)")
    print(f"Final QUALIFIED count: {final_qual} (strictly 0)")
    print(f"Final TOTAL facilities: {final_total}")
    print("====================================================")

    # Invariant assertions
    assert final_short == 4, f"Shortlist must remain 4, got {final_short}"
    assert final_qual == 0, f"Qualified must remain 0, got {final_qual}"
    assert 350 <= final_disc <= 380, f"Discovery count {final_disc} outside preferred range 350-380"
    assert final_total == final_short + final_disc, f"Total facilities mismatch: {final_total} != {final_short} + {final_disc}"

    conn.close()

if __name__ == "__main__":
    import_batch2()
