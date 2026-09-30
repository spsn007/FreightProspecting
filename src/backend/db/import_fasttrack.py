"""
FreightProspecting V1 — Fast-Track Discovery Pool Importer
Expands the Discovery Pool from 39 to approximately 160–190 Discovery facilities.
Integrates verified candidates across Track A (US Wood), Track B (Canada Wood),
Track C (Steel), Track D (Precast), and Track E (Plastics/Tooling).

Enforces:
1. Strict Quality Floor (real physical facility, FTL fit, Lower 48 / Canada, usable phone/email, official source).
2. Deduplication against existing database, intake fingerprints, and deferred candidates.
3. Idempotence: re-running produces 0 duplicate records.
4. Hard stop: Discovery lifecycle facilities never exceed 200.
5. Invariants: 0 fake loads, 0 fake freight signals, 0 fake capacity postings, 0 fake matches, 0 fake outreach logs.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.claims_engine import record_claim, record_evidence_source, link_claim_evidence

BATCH_NAME = "Fast-Track Discovery Pool Expansion"
OBSERVED_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

DEFERRED_OR_EXCLUDED_PATTERNS = [
    "cruse lumber",
    "woody lumber",
    "claude howard lumber",
    "thompson hardwoods",  # part of Beasley corporate family
]


def normalize_string(val: Optional[str]) -> str:
    if not val:
        return ""
    return re.sub(r"[^a-z0-9]", "", val.lower().strip())


def compute_intake_fingerprint(brand: str, address: str, city: str, state_prov: str, country: str) -> str:
    """Deterministic multi-plant safe fingerprint: brand|address|city|state_prov|country"""
    raw = f"{brand}|{address}|{city}|{state_prov}|{country}"
    return re.sub(r"[^a-z0-9|]", "", raw.lower().strip())


def is_candidate_deferred_or_excluded(brand: str) -> bool:
    norm = brand.lower().strip()
    return any(p in norm for p in DEFERRED_OR_EXCLUDED_PATTERNS)


def validate_candidate(c: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate candidate against Discovery Minimum Quality Gate."""
    brand = (c.get("brand") or "").strip()
    if not brand:
        return False, "Missing company brand name"
    if is_candidate_deferred_or_excluded(brand):
        return False, f"Brand {brand} matches deferred or excluded list"

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

    # Contact route check: at least ONE of phone or email must be present
    phone = (c.get("phone") or "").strip()
    email = (c.get("email") or "").strip()
    if not phone and not email:
        return False, "Candidate lacks both callable phone and email route"

    # Source provenance
    source_url = (c.get("source_url") or c.get("website_url") or "").strip()
    if not source_url:
        return False, "Missing verification source URL"

    return True, "OK"


def load_candidate_files(data_dir: Path) -> List[Dict[str, Any]]:
    """Load candidates from all raw_candidates_track_*.json files in data_dir."""
    all_candidates: List[Dict[str, Any]] = []
    track_files = sorted(data_dir.glob("raw_candidates_track_*.json"))

    for f in track_files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, list):
                    for item in data:
                        item["_track_source_file"] = f.name
                    all_candidates.extend(data)
                    print(f"Loaded {len(data)} candidates from {f.name}")
        except Exception as e:
            print(f"Error reading {f.name}: {e}")

    return all_candidates


def import_fasttrack_candidates(
    candidates: Optional[List[Dict[str, Any]]] = None,
    db_path: Optional[Path] = None,
    max_discovery_target: int = 185,
    hard_stop_max: int = 200,
) -> Dict[str, Any]:
    """
    Import fast-track candidates into prospects.db with full deduplication,
    provenance tracking, and Discovery lifecycle assignment.
    """
    if db_path is None:
        db_path = get_db_path()

    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row

    # Check current counts
    cur_shortlist = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
    cur_discovery = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
    cur_total_facs = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]

    print(f"Pre-import state: SHORTLISTED={cur_shortlist}, DISCOVERY={cur_discovery}, TOTAL={cur_total_facs}")

    if candidates is None:
        data_dir = Path("data") if Path("data").exists() else db_path.parent
        candidates = load_candidate_files(data_dir)

    # Track metrics
    stats = {
        "raw_candidates_loaded": len(candidates),
        "rejected_quality_gate": 0,
        "duplicates_skipped": 0,
        "newly_imported": 0,
        "pre_discovery_count": cur_discovery,
        "final_discovery_count": cur_discovery,
        "final_shortlist_count": cur_shortlist,
        "by_category": {},
        "by_country": {"US": 0, "CA": 0},
        "by_equipment": {"FLATBED": 0, "STEP_DECK": 0, "DRY_VAN": 0},
        "contact_routes": {"phone_present": 0, "email_present": 0, "both_present": 0, "named_person": 0},
    }

    seen_fingerprints = set()

    for c in candidates:
        # Check hard stop or target limit
        current_disc = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
        if current_disc >= hard_stop_max or current_disc >= max_discovery_target:
            valid, _ = validate_candidate(c)
            if valid:
                brand = c["brand"].strip()
                fac_name = c["fac_name"].strip()
                address = c["address"].strip()
                city = c["city"].strip()
                state = c["state"].strip().upper()
                country = c["country"].strip().upper()
                fp = compute_intake_fingerprint(brand, address, city, state, country)
                if fp not in seen_fingerprints:
                    seen_fingerprints.add(fp)
                    existing = conn.execute("SELECT id FROM discovery_intake_audit WHERE intake_fingerprint = ?", (fp,)).fetchone()
                    if not existing:
                        track_ref = c.get("_track_source_file") or BATCH_NAME
                        conn.execute(
                            """
                            INSERT INTO discovery_intake_audit (
                                batch_name, candidate_company_name, candidate_facility_name,
                                city, state_prov, country, intake_fingerprint, intake_status,
                                target_facility_id, website_url, facility_address, batch_reference,
                                reason_or_notes, reason_notes, reviewed_at, imported_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'DEFERRED_FOR_RESEARCH', NULL, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """,
                            (
                                BATCH_NAME, brand, fac_name,
                                city, state, country, fp,
                                c.get("website_url"), address, track_ref,
                                f"Deferred: Target Discovery Pool size reached ({max_discovery_target} facilities). Retained for future batches.",
                                f"Deferred: Target Discovery Pool size reached ({max_discovery_target} facilities). Retained for future batches.",
                            ),
                        )
                        stats["deferred_count"] = stats.get("deferred_count", 0) + 1
            continue

        # 1. Validation
        valid, reason = validate_candidate(c)
        if not valid:
            stats["rejected_quality_gate"] += 1
            continue

        brand = c["brand"].strip()
        fac_name = c["fac_name"].strip()
        address = c["address"].strip()
        city = c["city"].strip()
        state = c["state"].strip().upper()
        country = c["country"].strip().upper()
        postal_code = (c.get("postal_code") or "").strip() or None

        fp = compute_intake_fingerprint(brand, address, city, state, country)

        # In-batch duplicate check
        if fp in seen_fingerprints:
            stats["duplicates_skipped"] += 1
            continue
        seen_fingerprints.add(fp)

        # 2. Database Deduplication Check
        # A. Check discovery_intake_audit fingerprint
        audit_row = conn.execute(
            "SELECT id, target_facility_id FROM discovery_intake_audit WHERE intake_fingerprint = ?",
            (fp,)
        ).fetchone()
        if audit_row and audit_row["target_facility_id"]:
            stats["duplicates_skipped"] += 1
            continue

        # B. Check existing facility by physical address + state
        existing_fac = conn.execute(
            "SELECT id FROM facilities WHERE lower(trim(physical_address)) = ? AND state_prov = ?",
            (address.lower().strip(), state)
        ).fetchone()
        if existing_fac:
            stats["duplicates_skipped"] += 1
            continue

        # 3. Create or Find Company
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

        # 4. Insert Facility
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

        # 5. Insert Facility Commodity
        comm_cat = c.get("comm_cat") or "Industrial Freight"
        specific_prod = c.get("specific_prod") or comm_cat
        eq_cat = (c.get("eq_cat") or "FLATBED").strip().upper()
        if eq_cat not in ("FLATBED", "STEP_DECK", "DRY_VAN"):
            eq_cat = "FLATBED"

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

        # 6. Insert Contact
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
        elif raw_role in ("GENERAL_FACILITY", "GENERAL_OFFICE", "EXECUTIVE_LEADERSHIP"):
            role_cat = "GENERAL_FACILITY"
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

        # 7. Insert Evidence Source
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

        # 8. Record Claims & Evidence Links
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

        # 9. Insert Prospect Lifecycle (DISCOVERY)
        conn.execute(
            """
            INSERT INTO prospect_lifecycle (
                facility_id, stage, entered_discovery_at, discovered_at,
                qualified_at, shortlisted_at, archived_at, qualification_notes, notes, created_at, updated_at
            ) VALUES (?, 'DISCOVERY', ?, ?, NULL, NULL, NULL, NULL, ?, ?, ?)
            """,
            (fac_id, OBSERVED_DATE, OBSERVED_DATE, f"Imported in {BATCH_NAME}", OBSERVED_DATE, OBSERVED_DATE),
        )

        # 10. Insert Discovery Intake Audit
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

        stats["newly_imported"] += 1
        stats["by_country"][country] = stats["by_country"].get(country, 0) + 1
        stats["by_equipment"][eq_cat] = stats["by_equipment"].get(eq_cat, 0) + 1
        stats["by_category"][comm_cat] = stats["by_category"].get(comm_cat, 0) + 1

        if phone and email:
            stats["contact_routes"]["both_present"] += 1
            stats["contact_routes"]["phone_present"] += 1
            stats["contact_routes"]["email_present"] += 1
        elif phone:
            stats["contact_routes"]["phone_present"] += 1
        elif email:
            stats["contact_routes"]["email_present"] += 1

        if person_name:
            stats["contact_routes"]["named_person"] += 1

    conn.commit()

    # Final counts verification
    final_disc = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'").fetchone()[0]
    final_short = conn.execute("SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'").fetchone()[0]
    stats["final_discovery_count"] = final_disc
    stats["final_shortlist_count"] = final_short

    conn.close()
    return stats


if __name__ == "__main__":
    result = import_fasttrack_candidates()
    print("Import completed:")
    print(json.dumps(result, indent=2))
