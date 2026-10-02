import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple

import sys
sys.path.insert(0, '.')
from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.claims_engine import record_claim, record_evidence_source, link_claim_evidence
from src.backend.db.opportunity import load_opportunity_universe_context
from scripts.build_identity_index import normalize_text, extract_domain, normalize_address

def compute_intake_fingerprint(brand: str, address: str, city: str, state_prov: str, country: str) -> str:
    raw = f"{brand}|{address}|{city}|{state_prov}|{country}"
    import re
    return re.sub(r"[^a-z0-9|]", "", raw.lower().strip())

def run_lightweight_integrity_gates(conn: sqlite3.Connection) -> Tuple[bool, str]:
    # 1. Integrity check
    res = conn.execute("PRAGMA integrity_check;").fetchall()
    if len(res) != 1 or res[0][0] != "ok":
        return False, f"Integrity check failed: {[tuple(r) for r in res]}"

    # 2. Foreign key check
    fks = conn.execute("PRAGMA foreign_key_check;").fetchall()
    if len(fks) > 0:
        return False, f"Foreign key check failed: {fks}"

    # 3. Orphan check for claims
    orphans = conn.execute("""
        SELECT count(*) FROM claims c
        WHERE (c.company_id IS NOT NULL AND c.company_id NOT IN (SELECT id FROM companies))
           OR (c.facility_id IS NOT NULL AND c.facility_id NOT IN (SELECT id FROM facilities))
           OR (c.contact_id IS NOT NULL AND c.contact_id NOT IN (SELECT id FROM contacts))
           OR (c.facility_commodity_id IS NOT NULL AND c.facility_commodity_id NOT IN (SELECT id FROM facility_commodities))
    """).fetchone()[0]
    if orphans > 0:
        return False, f"Found {orphans} orphan claims"

    # 4. Duplicate current claims check
    dup_claims = conn.execute("""
        SELECT facility_id, claim_field, count(*) FROM claims
        WHERE is_current_accepted = 1 AND facility_id IS NOT NULL
        GROUP BY facility_id, claim_field HAVING count(*) > 1
    """).fetchall()
    if len(dup_claims) > 0:
        return False, f"Found duplicate current accepted claims: {dup_claims}"

    return True, "ALL_GATES_PASSED"


def import_validated_batch(
    candidates_batch: List[Dict[str, Any]],
    batch_name: str,
    db_path: str = "data/prospects.db",
) -> Dict[str, Any]:
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Mapping category codes to commodity_categories.id
    cat_code_to_id = {}
    rows = conn.execute("SELECT id, category_code FROM commodity_categories").fetchall()
    for r in rows:
        cat_code_to_id[r["category_code"]] = r["id"]

    inserted_companies = 0
    inserted_facilities = 0
    inserted_contacts = 0
    inserted_claims = 0
    inserted_evidence = 0

    batch_company_ids = []

    try:
        conn.execute("BEGIN TRANSACTION")

        for c in candidates_batch:
            brand = c["operating_brand"]
            legal = c["legal_name"]
            fac_name = c["facility_name"]
            address = c["physical_address"]
            city = c["city"]
            state = c["state_prov"]
            postal = c["postal_code"]
            country = c["country"]
            website = c["website_url"]
            source_url = c["source_url"] or website or "https://example.com"
            source_title = c["source_title"]
            notes = c["notes"]

            # 1. Insert Company
            comp_addr = f"{address}, {city}, {state}"
            if postal:
                comp_addr += f" {postal}"
            comp_addr += f", {country}"

            cur = conn.execute(
                """
                INSERT INTO companies (
                    operating_brand, legal_name, corporate_address, website_url, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (brand, legal, comp_addr, website, notes, now_iso, now_iso)
            )
            company_id = cur.lastrowid
            inserted_companies += 1
            batch_company_ids.append(company_id)

            # 2. Insert Facility
            cur = conn.execute(
                """
                INSERT INTO facilities (
                    company_id, facility_name, facility_type, physical_address, city, state_prov,
                    postal_code, country, private_fleet_present, vehicle_asset_ownership,
                    fleet_relationship_type, commercial_carrier_use, broker_friendly_status,
                    freight_procurement_level, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', 'FACILITY_LEVEL', ?, ?)
                """,
                (company_id, fac_name, c.get("facility_type") or "MANUFACTURING_PLANT", address, city, state, postal, country, now_iso, now_iso)
            )
            facility_id = cur.lastrowid
            inserted_facilities += 1

            # 3. Determine Category ID
            cat_code = c.get("category_code")
            cat_id = c.get("commodity_category_id")
            if not cat_id and cat_code and cat_code in cat_code_to_id:
                cat_id = cat_code_to_id[cat_code]

            # 4. Insert Facility Commodity
            cur = conn.execute(
                """
                INSERT INTO facility_commodities (
                    facility_id, commodity_category, specific_products, equipment_category,
                    equipment_usage_status, trailer_specs_notes, securement_tarp_notes,
                    created_at, commodity_category_id, category_code, seasonality_profile, peak_months
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, NULL)
                """,
                (
                    facility_id, c["commodity_category"], c["specific_products"],
                    c["equipment_category"], c["equipment_usage_status"],
                    now_iso, cat_id, cat_code
                )
            )
            comm_id = cur.lastrowid

            # 5. Insert Facility Commodity Mapping (if cat_id is valid)
            if cat_id:
                conn.execute(
                    """
                    INSERT INTO facility_commodity_mappings (
                        facility_id, category_id, source_evidence_notes, is_primary, created_at
                    ) VALUES (?, ?, ?, 1, ?)
                    """,
                    (facility_id, cat_id, f"Expansion campaign primary classification: {c['commodity_category']}", now_iso)
                )

            # 6. Insert Contact
            cur = conn.execute(
                """
                INSERT INTO contacts (
                    facility_id, contact_identity, person_name, exact_published_title,
                    department, phone_number, phone_directness, email_address, email_directness,
                    role_category, outbound_shipping_procurement_relevance, broker_procurement_relevance,
                    is_primary_contact, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'UNKNOWN', 'UNKNOWN', 1, ?)
                """,
                (
                    facility_id, c["contact_identity"], c["person_name"],
                    c["exact_published_title"], c["department"], c["phone_number"],
                    c["phone_directness"], c["email_address"], c["email_directness"],
                    c["role_category"], now_iso
                )
            )
            contact_id = cur.lastrowid
            inserted_contacts += 1

            # 7. Record Evidence Source
            evidence_id = record_evidence_source(
                conn=conn,
                source_type="COMPANY_WEBSITE",
                source_title_publisher=source_title,
                source_url=source_url,
                is_primary_source=True,
                source_published_at=None,
                event_at=None,
                observed_at=c["observed_at"],
                notes=notes,
            )
            inserted_evidence += 1

            # 8. Record Claims & Link Evidence
            # A. Address claim
            c_addr = record_claim(
                conn=conn,
                claim_field="physical_address",
                claimed_value=f"{address}, {city}, {state} {postal or ''}, {country}".strip(),
                verification_status="VERIFIED",
                is_current_accepted=True,
                facility_id=facility_id,
            )
            link_claim_evidence(conn, c_addr, evidence_id, "SUPPORTS")
            inserted_claims += 1

            # B. Fleet presence claim (UNKNOWN)
            c_fleet = record_claim(
                conn=conn,
                claim_field="private_fleet_present",
                claimed_value="UNKNOWN",
                verification_status="UNKNOWN",
                is_current_accepted=True,
                claim_notes="Fleet status: UNKNOWN.",
                facility_id=facility_id,
            )
            link_claim_evidence(conn, c_fleet, evidence_id, "CONTEXT")
            inserted_claims += 1

            # C. Equipment claim
            c_eq = record_claim(
                conn=conn,
                claim_field="equipment_category",
                claimed_value=c["equipment_category"],
                verification_status=c["equipment_usage_status"],
                is_current_accepted=True,
                claim_notes=f"FTL equipment fit {c['equipment_category']} ({c['equipment_usage_status']}) based on product profile: {c['specific_products']}.",
                facility_commodity_id=comm_id,
            )
            link_claim_evidence(conn, c_eq, evidence_id, "SUPPORTS")
            inserted_claims += 1

            # D. Contact route claim (if phone exists)
            if c["phone_number"]:
                c_phone = record_claim(
                    conn=conn,
                    claim_field="phone_directness",
                    claimed_value=c["phone_directness"],
                    verification_status="VERIFIED",
                    is_current_accepted=True,
                    claim_notes=f"Published contact route: {c['phone_number']} ({c['phone_directness']}).",
                    contact_id=contact_id,
                )
                link_claim_evidence(conn, c_phone, evidence_id, "SUPPORTS")
                inserted_claims += 1

            # 9. Insert Prospect Lifecycle (DISCOVERY)
            conn.execute(
                """
                INSERT INTO prospect_lifecycle (
                    facility_id, stage, entered_discovery_at, discovered_at, notes, created_at, updated_at
                ) VALUES (?, 'DISCOVERY', ?, ?, ?, ?, ?)
                """,
                (facility_id, now_iso, now_iso, f"Imported in {batch_name}", now_iso, now_iso)
            )

            # 10. Insert Discovery Intake Audit
            fp = compute_intake_fingerprint(brand, address, city, state, country)
            conn.execute(
                """
                INSERT INTO discovery_intake_audit (
                    batch_name, candidate_company_name, candidate_facility_name, city, state_prov,
                    country, intake_fingerprint, intake_status, target_facility_id, website_url,
                    facility_address, batch_reference, reason_or_notes, reviewed_at, imported_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'APPROVED_FOR_IMPORT', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    batch_name, brand, fac_name, city, state, country, fp, facility_id,
                    website, address, batch_name, notes
                )
            )

        # Run lightweight integrity gates before committing
        passed, gate_msg = run_lightweight_integrity_gates(conn)
        if not passed:
            conn.rollback()
            raise RuntimeError(f"Lightweight integrity gate failed: {gate_msg}")

        conn.commit()

        # Engine recomputation check
        ctx = load_opportunity_universe_context(conn=conn)
        tiers = ctx["tier_company_ids"]
        tier_counts = {k: len(v) for k, v in tiers.items()}
        total_operating = sum(tier_counts.values())

        return {
            "batch_name": batch_name,
            "status": "COMMITTED",
            "inserted_companies": inserted_companies,
            "inserted_facilities": inserted_facilities,
            "inserted_contacts": inserted_contacts,
            "inserted_claims": inserted_claims,
            "inserted_evidence": inserted_evidence,
            "operating_universe_count": total_operating,
            "tier_distribution": tier_counts,
            "gate_status": gate_msg,
        }

    except Exception as e:
        conn.rollback()
        return {
            "batch_name": batch_name,
            "status": "ROLLED_BACK",
            "error": str(e),
        }
    finally:
        conn.close()

if __name__ == "__main__":
    print("Import Database Coordinator loaded successfully.")
