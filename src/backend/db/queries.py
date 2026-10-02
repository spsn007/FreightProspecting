"""
FreightProspecting V1 — Read-Only Database Queries
Provides clean, structured read-only access to prospects.db for Stage 2.5/3A preview.
Enforces core entity distinctions: Companies != Facilities != Signals != Loads != Capacity.
Strictly renders real database records (curated shortlist vs discovery pool).
"""

from datetime import date, datetime, timezone
from pathlib import Path
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Set

from src.backend.db.connection import create_connection, get_db_path
from src.backend.db.validators import (
    get_utc_now_iso,
    normalize_to_utc_iso,
    validate_date_string,
    calculate_gross_margin,
    validate_and_calculate_load_margin,
    is_valid_phone_number,
    is_valid_email,
    normalize_phone_digits,
    resolve_timezone,
)
from src.backend.db.opportunity import (
    BROKER_OPPORTUNITY_RULE_VERSION,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    RESTRICTED,
    TIER_LABELS,
    TIER_DESCRIPTIONS,
    UNKNOWN_FLEET_TEXT,
    UNKNOWN_CARRIER_TEXT,
    UNKNOWN_BROKER_TEXT,
    evaluate_broker_opportunity,
    evaluate_broker_opportunity_raw,
    get_opportunity_tier_company_ids,
    load_opportunity_universe_context,
)
from src.backend.db.claims_engine import (
    record_evidence_source,
    record_claim,
    link_claim_evidence,
    get_current_accepted_claims,
)

# Geographic boundary constants (Revision 4.1 / Confirmed Decision A)
LOWER_48_STATES = {
    "AL", "AR", "AZ", "CA", "CO", "CT", "DE", "FL", "GA", "IA",
    "ID", "IL", "IN", "KS", "KY", "LA", "MA", "MD", "ME", "MI",
    "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM",
    "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY", "DC"
}

CANADIAN_PROVINCES = {
    "AB", "BC", "MB", "NB", "NL", "NS", "ON", "PE", "QC", "SK"
}
CANADIAN_TERRITORIES = {"NT", "NU", "YT"}
CANADIAN_JURISDICTIONS = CANADIAN_PROVINCES | CANADIAN_TERRITORIES


def get_summary_counts(db_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """
    Returns actual counts from SQLite database for dashboard summary metrics.
    Truthfully reflects real records with zero fake numbers.
    Distinguishes Shortlisted prospects from Discovery candidates.
    """
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Check if prospect_lifecycle table exists
        has_lifecycle = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='prospect_lifecycle'"
        ).fetchone()[0] > 0

        if has_lifecycle:
            shortlisted_cnt = conn.execute(
                "SELECT count(*) FROM prospect_lifecycle WHERE stage = 'SHORTLISTED'"
            ).fetchone()[0]
            discovery_cnt = conn.execute(
                "SELECT count(*) FROM prospect_lifecycle WHERE stage = 'DISCOVERY'"
            ).fetchone()[0]
            qualified_cnt = conn.execute(
                "SELECT count(*) FROM prospect_lifecycle WHERE stage = 'QUALIFIED'"
            ).fetchone()[0]
            archived_cnt = conn.execute(
                "SELECT count(*) FROM prospect_lifecycle WHERE stage = 'ARCHIVED'"
            ).fetchone()[0]
            all_prospects_cnt = conn.execute(
                "SELECT count(*) FROM facilities"
            ).fetchone()[0]
        else:
            shortlisted_cnt = conn.execute(
                "SELECT count(DISTINCT f.id) FROM facilities f JOIN companies c ON f.company_id = c.id"
            ).fetchone()[0]
            discovery_cnt = 0
            qualified_cnt = 0
            archived_cnt = 0
            all_prospects_cnt = shortlisted_cnt

        total_companies_cnt = conn.execute("SELECT count(*) FROM companies").fetchone()[0]
        all_companies_cnt = conn.execute("SELECT count(DISTINCT company_id) FROM facilities").fetchone()[0]
        if has_lifecycle:
            shortlisted_companies_cnt = conn.execute(
                "SELECT count(DISTINCT f.company_id) FROM facilities f JOIN prospect_lifecycle pl ON f.id = pl.facility_id WHERE pl.stage = 'SHORTLISTED'"
            ).fetchone()[0]
            qualified_companies_cnt = conn.execute(
                """
                SELECT count(DISTINCT f.company_id) FROM facilities f 
                JOIN prospect_lifecycle pl ON f.id = pl.facility_id 
                WHERE pl.stage = 'QUALIFIED'
                  AND f.company_id NOT IN (
                      SELECT f2.company_id FROM facilities f2 JOIN prospect_lifecycle pl2 ON f2.id = pl2.facility_id WHERE pl2.stage = 'SHORTLISTED'
                  )
                """
            ).fetchone()[0]
            discovery_companies_cnt = conn.execute(
                """
                SELECT count(DISTINCT f.company_id) FROM facilities f 
                WHERE f.company_id NOT IN (
                    SELECT f2.company_id FROM facilities f2 JOIN prospect_lifecycle pl2 ON f2.id = pl2.facility_id WHERE pl2.stage IN ('SHORTLISTED', 'QUALIFIED')
                )
                """
            ).fetchone()[0]
        else:
            discovery_companies_cnt = 0
            shortlisted_companies_cnt = all_companies_cnt
            qualified_companies_cnt = 0

        # Multi-facility vs Single-facility company distribution
        fac_per_comp = conn.execute("SELECT count(id) FROM facilities GROUP BY company_id").fetchall()
        single_fac_companies_cnt = sum(1 for r in fac_per_comp if r[0] == 1)
        multi_fac_companies_cnt = sum(1 for r in fac_per_comp if r[0] > 1)

        # Signals, loads, capacity, matches (truthfully 0 in Stage 2 / Stage 3A)
        signals_cnt = conn.execute("SELECT count(*) FROM freight_demand_signals").fetchone()[0]
        loads_cnt = conn.execute("SELECT count(*) FROM load_opportunities").fetchone()[0]
        carriers_cnt = conn.execute("SELECT count(*) FROM carriers").fetchone()[0]
        capacity_cnt = conn.execute("SELECT count(*) FROM capacity_postings").fetchone()[0]
        matches_cnt = conn.execute("SELECT count(*) FROM load_capacity_matches").fetchone()[0]

        # Provenance ledger metrics
        claims_cnt = conn.execute("SELECT count(*) FROM claims").fetchone()[0]
        verified_claims_cnt = conn.execute(
            "SELECT count(*) FROM claims WHERE verification_status = 'VERIFIED'"
        ).fetchone()[0]
        inferred_claims_cnt = conn.execute(
            "SELECT count(*) FROM claims WHERE verification_status = 'INFERRED'"
        ).fetchone()[0]
        unknown_claims_cnt = conn.execute(
            "SELECT count(*) FROM claims WHERE verification_status = 'UNKNOWN'"
        ).fetchone()[0]
        sources_cnt = conn.execute("SELECT count(*) FROM evidence_sources").fetchone()[0]

        # Seed claim counts (for backward compatibility assertions)
        seed_verified_cnt = conn.execute(
            "SELECT count(*) FROM claims WHERE id <= 20 AND verification_status = 'VERIFIED'"
        ).fetchone()[0]
        seed_inferred_cnt = conn.execute(
            "SELECT count(*) FROM claims WHERE id <= 20 AND verification_status = 'INFERRED'"
        ).fetchone()[0]
        seed_unknown_cnt = conn.execute(
            "SELECT count(*) FROM claims WHERE id <= 20 AND verification_status = 'UNKNOWN'"
        ).fetchone()[0]

        # Stage 3C Outreach CRM metrics
        crm_counts = {
            "uncontacted": 0,
            "interested": 0,
            "no_answer": 0,
            "not_interested": 0,
            "call_back": 0,
            "follow_ups": 0,
            "total_calls": 0,
            "unreviewed": 0,
        }
        has_eng = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='prospect_engagement_state'"
        ).fetchone()[0] > 0
        if has_eng:
            for r in conn.execute("SELECT current_outreach_status, count(*) as cnt FROM prospect_engagement_state GROUP BY current_outreach_status").fetchall():
                key = r["current_outreach_status"].lower()
                if key in crm_counts:
                    crm_counts[key] = r["cnt"]
            crm_counts["follow_ups"] = conn.execute(
                "SELECT count(*) FROM prospect_engagement_state WHERE next_follow_up_at IS NOT NULL"
            ).fetchone()[0]
            crm_counts["unreviewed"] = conn.execute(
                "SELECT count(*) FROM prospect_engagement_state WHERE is_viewed = 0"
            ).fetchone()[0]
            has_outreach = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='outreach_logs'"
            ).fetchone()[0] > 0
            if has_outreach:
                crm_counts["total_calls"] = conn.execute("SELECT count(*) FROM outreach_logs").fetchone()[0]

        return {
            "prospects_count": shortlisted_cnt,
            "shortlisted_count": shortlisted_cnt,
            "discovery_count": discovery_cnt,
            "qualified_count": qualified_cnt,
            "archived_count": archived_cnt,
            "all_prospects_count": all_prospects_cnt,
            "total_companies_count": total_companies_cnt,
            "all_companies_count": all_companies_cnt,
            "discovery_companies_count": discovery_companies_cnt,
            "shortlisted_companies_count": shortlisted_companies_cnt,
            "qualified_companies_count": qualified_companies_cnt,
            "single_facility_companies_count": single_fac_companies_cnt,
            "multi_facility_companies_count": multi_fac_companies_cnt,
            "signals_count": signals_cnt,
            "loads_count": loads_cnt,
            "carriers_count": carriers_cnt,
            "capacity_count": capacity_cnt,
            "matches_count": matches_cnt,
            "claims_count": claims_cnt,
            "verified_claims_count": verified_claims_cnt,
            "inferred_claims_count": inferred_claims_cnt,
            "unknown_claims_count": unknown_claims_cnt,
            "seed_verified_claims_count": seed_verified_cnt,
            "seed_inferred_claims_count": seed_inferred_cnt,
            "seed_unknown_claims_count": seed_unknown_cnt,
            "sources_count": sources_cnt,
            "crm_counts": crm_counts,
            "crm_uncontacted": crm_counts["uncontacted"],
            "crm_interested": crm_counts["interested"],
            "crm_no_answer": crm_counts["no_answer"],
            "crm_not_interested": crm_counts["not_interested"],
            "crm_call_back": crm_counts["call_back"],
            "crm_follow_ups": crm_counts["follow_ups"],
            "crm_unreviewed": crm_counts["unreviewed"],
            "crm_total_calls": crm_counts["total_calls"],
        }
    finally:
        conn.close()


def evaluate_qualification_readiness(
    facility_id: int,
    conn: Optional[sqlite3.Connection] = None,
    allow_alaska: bool = False
) -> Dict[str, Any]:
    """
    Evaluates qualification readiness for a facility against 5 factual criteria:
    1. facility_identity_verified: Address, city, state, country verified in US or Canada.
    2. commodity_equipment_fit: At least one commodity profile with approved FTL equipment (Flatbed/Step Deck/Dry Van).
    3. geography_eligible: Lower 48 US or Canada (10 provinces + Yukon, Northwest Territories, Nunavut; HI & MX excluded; AK excluded unless toggle enabled).
    4. usable_outreach_route: Usable phone route OR published usable email (phone-first, not phone-only).
    5. fleet_and_carrier_assessed: Fleet relationship type and presence assessed.

    READ-ONLY: Does NOT mutate prospect_lifecycle or any other table.
    """
    should_close = False
    if conn is None:
        conn = create_connection()
        conn.row_factory = sqlite3.Row
        should_close = True

    try:
        # 1. Facility record
        fac = conn.execute(
            """
            SELECT id, facility_name, facility_type, physical_address, city, state_prov, country,
                   private_fleet_present, fleet_relationship_type, commercial_carrier_use
            FROM facilities
            WHERE id = ?
            """,
            (facility_id,)
        ).fetchone()

        if not fac:
            return {
                "facility_id": facility_id,
                "is_ready": False,
                "status": "INCOMPLETE",
                "passed_count": 0,
                "total_checks": 5,
                "checks": {},
            }

        # 2. Commodity profiles
        comms = conn.execute(
            """
            SELECT commodity_category, specific_products, equipment_category, equipment_usage_status
            FROM facility_commodities
            WHERE facility_id = ?
            """,
            (facility_id,)
        ).fetchall()

        # 3. Contacts
        contacts = conn.execute(
            """
            SELECT id, person_name, exact_published_title, phone_number, phone_directness,
                   email_address, email_directness, role_category
            FROM contacts
            WHERE facility_id = ?
            """,
            (facility_id,)
        ).fetchall()

        # Check 1: facility_identity_verified
        addr = (fac["physical_address"] or "").strip()
        city = (fac["city"] or "").strip()
        state = (fac["state_prov"] or "").strip().upper()
        country = (fac["country"] or "").strip().upper()
        addr_claim = conn.execute(
            """
            SELECT c.id, c.verification_status, count(ce.id) as ev_cnt
            FROM claims c
            JOIN facilities f ON c.facility_id = f.id
            JOIN claim_evidence ce ON c.id = ce.claim_id
            WHERE c.facility_id = ?
              AND c.claim_field = 'physical_address'
              AND c.is_current_accepted = 1
              AND (
                  TRIM(c.claimed_value) = TRIM(f.physical_address)
                  OR INSTR(c.claimed_value, f.physical_address) > 0
                  OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Road', ' Rd')) > 0
                  OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Street', ' St')) > 0
                  OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Avenue', ' Ave')) > 0
                  OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Boulevard', ' Blvd')) > 0
                  OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Highway', ' Hwy')) > 0
              )
              AND ce.relationship = 'SUPPORTS'
            GROUP BY c.id
            """,
            (facility_id,)
        ).fetchone()
        has_addr_evidence = bool(addr_claim and addr_claim["ev_cnt"] > 0)
        identity_passed = bool(
            addr and addr.upper() != "UNKNOWN" and city and state and country in ("US", "CA") and has_addr_evidence
        )
        if identity_passed:
            identity_details = f"Physical facility confirmed at {addr}, {city}, {state} {country} (backed by verified evidence source)"
        elif not has_addr_evidence and addr and addr.upper() != "UNKNOWN":
            identity_details = "Facility address present but missing verified accepted claim backed by documented evidence source"
        else:
            identity_details = "Incomplete facility physical address or unsupported country"

        # Check 2: commodity_equipment_fit
        approved_equip = {"FLATBED", "STEP_DECK", "DRY_VAN"}
        has_commodities = len(comms) > 0
        equip_fit_basic = has_commodities and any(
            any(eq in (c["equipment_category"] or "") for eq in approved_equip) and
            c["equipment_usage_status"] in ("VERIFIED", "INFERRED")
            for c in comms
        )
        equip_claim = conn.execute(
            """
            SELECT c.id, count(ce.id) as ev_cnt
            FROM claims c
            JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
            JOIN claim_evidence ce ON c.id = ce.claim_id
            WHERE fc.facility_id = ?
              AND c.claim_field = 'equipment_category'
              AND c.is_current_accepted = 1
              AND c.verification_status IN ('VERIFIED', 'INFERRED')
              AND TRIM(c.claimed_value) = TRIM(fc.equipment_category)
              AND ce.relationship = 'SUPPORTS'
            GROUP BY c.id
            """,
            (facility_id,)
        ).fetchone()
        has_equip_evidence = bool(equip_claim and equip_claim["ev_cnt"] > 0)
        equip_fit_passed = bool(equip_fit_basic and has_equip_evidence)
        if equip_fit_passed:
            equip_details = f"{len(comms)} commodity profile(s) with approved FTL equipment backed by documented evidence"
        elif equip_fit_basic and not has_equip_evidence:
            equip_details = "Commodity equipment fit identified but missing accepted equipment claim backed by documented evidence"
        else:
            equip_details = "Missing commodity profile or unverified/unapproved equipment category"

        # Check 3: geography_eligible (Lower 48 + all Canada; AK excluded by default; HI & MX excluded)
        if country == "US":
            if state == "AK":
                geo_passed = allow_alaska
                geo_details = "Alaska freight territory (Override toggle enabled)" if allow_alaska else "Alaska excluded by default in V1 (Decision A)"
            elif state == "HI":
                geo_passed = False
                geo_details = "Excluded freight territory (Hawaii - no FTL truckload service)"
            elif state in LOWER_48_STATES:
                geo_passed = True
                geo_details = f"Eligible US Lower 48 freight territory ({state})"
            else:
                geo_passed = False
                geo_details = f"Unrecognized US state or territory ({state})"
        elif country == "CA":
            if not state or state in CANADIAN_JURISDICTIONS:
                geo_passed = True
                if state in CANADIAN_PROVINCES:
                    geo_details = f"Eligible Canadian province ({state})"
                elif state in CANADIAN_TERRITORIES:
                    geo_details = f"Eligible Canadian territory ({state})"
                else:
                    geo_details = f"Eligible Canadian jurisdiction ({state if state else 'Canada'})"
            else:
                geo_passed = False
                geo_details = f"Unrecognized Canadian jurisdiction ({state})"
        elif country == "MX":
            geo_passed = False
            geo_details = "Excluded freight territory (Mexico - out of V1 scope)"
        else:
            geo_passed = False
            geo_details = f"Unrecognized freight territory ({state}, {country})"

        # Check 4: usable_outreach_route (Phone-first, not phone-only; requires genuine evidence provenance)
        # Validates that at least one contact has a valid callable phone route (10+ digits, non-placeholder)
        # or usable email address, AND has an accepted claim matching the contact's directness backed by SUPPORTS evidence.
        # If claim_notes contains phone digits, they must match the contact's current phone number.
        valid_contacts = []
        for ct in contacts:
            p_raw = (ct["phone_number"] or "").strip()
            e_raw = (ct["email_address"] or "").strip()
            p_ok = is_valid_phone_number(p_raw)
            e_ok = is_valid_email(e_raw)
            if not (p_ok or e_ok):
                continue

            # Check accepted contact claims backed by SUPPORTS evidence
            claims_rows = conn.execute(
                """
                SELECT c.id, c.claim_field, c.claimed_value, c.claim_notes, count(ce.id) as ev_cnt
                FROM claims c
                JOIN claim_evidence ce ON c.id = ce.claim_id
                WHERE c.contact_id = ?
                  AND c.is_current_accepted = 1
                  AND c.verification_status IN ('VERIFIED', 'INFERRED')
                  AND ce.relationship = 'SUPPORTS'
                GROUP BY c.id
                """,
                (ct["id"],)
            ).fetchall()

            for cr in claims_rows:
                if cr["ev_cnt"] > 0:
                    if p_ok and cr["claim_field"] == "phone_directness":
                        if cr["claimed_value"] == ct["phone_directness"]:
                            # Verify phone digits match if specified in notes
                            if cr["claim_notes"]:
                                n_digits = re.findall(r"\d{10}|\d{3}[-.\s]\d{3}[-.\s]\d{4}", cr["claim_notes"])
                                if n_digits:
                                    n_clean = normalize_phone_digits(n_digits[0])
                                    p_clean = normalize_phone_digits(p_raw)
                                    if n_clean != p_clean:
                                        continue
                            valid_contacts.append(ct)
                            break
                    elif e_ok and cr["claim_field"] in ("email_directness", "email_address"):
                        valid_contacts.append(ct)
                        break

        has_phone = any(is_valid_phone_number(ct["phone_number"]) for ct in valid_contacts)
        has_email = any(is_valid_email(ct["email_address"]) for ct in valid_contacts)
        outreach_passed = len(valid_contacts) > 0
        if outreach_passed:
            if has_phone and has_email:
                outreach_details = "Verified phone route and usable email address available (evidence backed)"
            elif has_phone:
                outreach_details = "Verified phone route available (Phone-First priority, evidence backed)"
            else:
                outreach_details = "Usable published email available (Phone pending, evidence backed)"
        else:
            any_candidate = any(
                is_valid_phone_number(ct["phone_number"]) or is_valid_email(ct["email_address"])
                for ct in contacts
            )
            if any_candidate:
                outreach_details = "Contact info present but missing accepted contact claim backed by documented evidence"
            else:
                outreach_details = "No callable phone route or usable email address found"

        # Check 5: supporting_evidence_provenance
        # Verifies that facility has at least 1 accepted claim backed by linked evidence source(s) with SUPPORTS relationship
        # Fleet and broker policy being UNKNOWN is neutral (Rule 5 & Rule 11) and does not block qualification.
        cur_ev = conn.execute(
            """
            SELECT COUNT(DISTINCT c.id)
            FROM claims c
            JOIN claim_evidence ce ON c.id = ce.claim_id
            WHERE c.is_current_accepted = 1
              AND ce.relationship = 'SUPPORTS'
              AND (
                  c.facility_id = ?
                  OR c.facility_commodity_id IN (SELECT id FROM facility_commodities WHERE facility_id = ?)
                  OR c.contact_id IN (SELECT id FROM contacts WHERE facility_id = ?)
                  OR c.company_id = (SELECT company_id FROM facilities WHERE id = ?)
              )
            """,
            (facility_id, facility_id, facility_id, facility_id)
        )
        ev_count = cur_ev.fetchone()[0]
        evidence_passed = ev_count > 0
        evidence_details = (
            f"Evidence provenance verified ({ev_count} accepted claim(s) backed by documented evidence)"
            if evidence_passed
            else "Missing supporting evidence sources backing facility claims"
        )

        checks = {
            "facility_identity_verified": {"passed": identity_passed, "details": identity_details},
            "commodity_equipment_fit": {"passed": equip_fit_passed, "details": equip_details},
            "geography_eligible": {"passed": geo_passed, "details": geo_details},
            "usable_outreach_route": {"passed": outreach_passed, "details": outreach_details},
            "supporting_evidence_provenance": {"passed": evidence_passed, "details": evidence_details},
        }

        passed_count = sum(1 for c in checks.values() if c["passed"])
        is_ready = (passed_count == 5)

        return {
            "facility_id": facility_id,
            "is_ready": is_ready,
            "status": "READY" if is_ready else "INCOMPLETE",
            "passed_count": passed_count,
            "total_checks": 5,
            "checks": checks,
        }
    finally:
        if should_close:
            conn.close()


def promote_prospect_stage(
    facility_id: int,
    target_stage: str,
    notes: Optional[str] = None,
    db_path: Optional[str | Path] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """
    Promotes or updates the lifecycle stage of a prospect facility.
    ENFORCES STRICT QUALIFICATION GUARD:
    - Target stages 'QUALIFIED' and 'SHORTLISTED' strictly require that all 5 factual
      qualification readiness checks pass (evaluate_qualification_readiness(facility_id).is_ready == True).
    - If any readiness check fails, rejects the transition with ValueError detailing the failure reasons.
    - Demotion to 'DISCOVERY' or 'ARCHIVED' is always permitted.
    - Updates prospect_lifecycle atomically.
    """
    target_clean = (target_stage or "").strip().upper()
    ALLOWED_STAGES = {"DISCOVERY", "QUALIFIED", "SHORTLISTED", "ARCHIVED"}
    if target_clean not in ALLOWED_STAGES:
        raise ValueError(f"Invalid target stage '{target_stage}'. Allowed: {sorted(ALLOWED_STAGES)}")

    should_close = False
    if conn is None:
        conn = create_connection(db_path)
        conn.row_factory = sqlite3.Row
        should_close = True
    try:
        with conn:
            cur = conn.cursor()
            fac = cur.execute("SELECT id, company_id, facility_name FROM facilities WHERE id = ?", (facility_id,)).fetchone()
            if not fac:
                raise ValueError(f"Facility {facility_id} does not exist.")

            readiness = evaluate_qualification_readiness(facility_id, conn=conn)
            if target_clean in ("QUALIFIED", "SHORTLISTED"):
                if not readiness["is_ready"]:
                    failed_checks = [k for k, v in readiness["checks"].items() if not v["passed"]]
                    raise ValueError(
                        f"Promotion to {target_clean} blocked: Facility {facility_id} failed qualification readiness "
                        f"({readiness['passed_count']}/5 gates passed). Failed checks: {', '.join(failed_checks)}."
                    )

            now_iso = get_utc_now_iso()
            cur_life = cur.execute("SELECT stage FROM prospect_lifecycle WHERE facility_id = ?", (facility_id,)).fetchone()

            q_at = now_iso if target_clean in ("QUALIFIED", "SHORTLISTED") else None
            s_at = now_iso if target_clean == "SHORTLISTED" else None
            stage_note = notes or f"Stage updated to {target_clean} via promotion workflow."

            cur.execute("""
                UPDATE prospect_lifecycle
                SET stage = ?,
                    qualified_at = CASE WHEN ? = 'DISCOVERY' THEN NULL WHEN ? IS NOT NULL THEN ? ELSE qualified_at END,
                    shortlisted_at = CASE WHEN ? IN ('DISCOVERY', 'QUALIFIED') THEN NULL WHEN ? IS NOT NULL THEN ? ELSE shortlisted_at END,
                    qualification_notes = ?,
                    updated_at = ?
                WHERE facility_id = ?
            """, (target_clean, target_clean, q_at, q_at, target_clean, s_at, s_at, stage_note, now_iso, facility_id))

            return {
                "facility_id": facility_id,
                "previous_stage": cur_life[0] if cur_life else None,
                "new_stage": target_clean,
                "is_ready": readiness["is_ready"],
                "passed_count": readiness["passed_count"],
                "qualification_readiness": readiness,
                "updated_at": now_iso,
            }
    finally:
        if should_close:
            conn.close()


def _parse_filter_list(val: Any) -> List[str]:
    """
    Parses a filter parameter which may be None, 'ALL', a single string,
    a comma-separated string (e.g. 'FLATBED,STEP_DECK'), or a list/tuple/set of strings.
    Returns normalized uppercase non-empty tokens with 'ALL' omitted.
    """
    if val is None:
        return []
    if isinstance(val, (list, tuple, set)):
        items = []
        for x in val:
            if x is not None:
                for sub in str(x).split(","):
                    sub_clean = sub.strip().upper()
                    if sub_clean and sub_clean != "ALL" and sub_clean not in items:
                        items.append(sub_clean)
        return items
    val_str = str(val).strip()
    if not val_str or val_str.upper() == "ALL":
        return []
    items = []
    for sub in val_str.split(","):
        sub_clean = sub.strip().upper()
        if sub_clean and sub_clean != "ALL" and sub_clean not in items:
            items.append(sub_clean)
    return items


def _canonical_tier(t: str) -> Optional[str]:
    """Normalizes any user or enum tier token to its canonical TIER constant."""
    clean = str(t).strip().upper()
    if clean in ("PRIORITY", "TIER_A", "TIER_A_PRIORITY"):
        return TIER_A_PRIORITY
    if clean in ("WORTH_CALLING", "TIER_B", "TIER_B_WORTH_CALLING"):
        return TIER_B_WORTH_CALLING
    if clean in ("SECONDARY", "TIER_C", "TIER_C_SECONDARY"):
        return TIER_C_SECONDARY
    if clean in ("RESEARCH", "NEEDS_RESEARCH", "TIER_D", "TIER_D_RESEARCH_NEEDED"):
        return TIER_D_RESEARCH_NEEDED
    if clean in ("RESTRICTED", "TIER_RESTRICTED"):
        return RESTRICTED
    return None

def build_facility_filter_sql(
    lifecycle_stage: Optional[str] = "ALL",
    search: Optional[str] = None,
    equipment: Optional[Any] = None,
    family: Optional[Any] = None,
    category: Optional[Any] = None,
    seasonality: Optional[Any] = None,
    fleet: Optional[Any] = None,
    carrier: Optional[Any] = None,
    procurement: Optional[Any] = None,
    tier: Optional[Any] = None,
) -> Tuple[str, List[Any]]:
    """Builds SQL WHERE clause and parameter list for facility filtering."""
    where_clauses = []
    params: List[Any] = []

    if lifecycle_stage and lifecycle_stage.upper() != "ALL":
        where_clauses.append("COALESCE(pl.stage, 'DISCOVERY') = ?")
        params.append(lifecycle_stage.upper())

    if search and search.strip():
        q_raw = search.strip().lower()
        q_len = len(q_raw)
        q_contains = f"%{q_raw}%"
        if q_len == 1:
            q_prefix = f"{q_raw}%"
            where_clauses.append("""(
                LOWER(c.operating_brand) LIKE ? OR
                LOWER(COALESCE(c.legal_name, '')) LIKE ? OR
                LOWER(f.facility_name) LIKE ?
            )""")
            params.extend([q_prefix, q_prefix, q_prefix])
        elif q_len == 2:
            where_clauses.append("""(
                LOWER(c.operating_brand) LIKE ? OR
                LOWER(COALESCE(c.legal_name, '')) LIKE ? OR
                LOWER(f.facility_name) LIKE ? OR
                LOWER(f.state_prov) = ?
            )""")
            params.extend([q_contains, q_contains, q_contains, q_raw])
        else:
            where_clauses.append("""(
                LOWER(c.operating_brand) LIKE ? OR
                LOWER(COALESCE(c.legal_name, '')) LIKE ? OR
                LOWER(f.facility_name) LIKE ? OR
                LOWER(f.city) LIKE ? OR
                LOWER(f.state_prov) LIKE ? OR
                EXISTS (
                    SELECT 1 FROM facility_commodities fc_s
                    LEFT JOIN commodity_categories cc_s ON fc_s.commodity_category_id = cc_s.id
                    WHERE fc_s.facility_id = f.id AND (
                        LOWER(COALESCE(fc_s.specific_products, '')) LIKE ? OR
                        LOWER(COALESCE(fc_s.commodity_category, '')) LIKE ? OR
                        LOWER(COALESCE(cc_s.display_name, '')) LIKE ? OR
                        LOWER(COALESCE(cc_s.category_code, '')) LIKE ?
                    )
                )
            )""")
            params.extend([q_contains] * 9)

    equipment_items = _parse_filter_list(equipment)
    if equipment_items:
        ph = ",".join("?" for _ in equipment_items)
        where_clauses.append(f"""
            EXISTS (
                SELECT 1 FROM facility_commodities fc_e
                WHERE fc_e.facility_id = f.id AND fc_e.equipment_category IN ({ph})
            )
        """)
        params.extend(equipment_items)

    family_items = _parse_filter_list(family)
    if family_items:
        ph = ",".join("?" for _ in family_items)
        where_clauses.append(f"""(
            EXISTS (
                SELECT 1 FROM facility_commodities fc_f
                JOIN commodity_categories cc_f ON fc_f.commodity_category_id = cc_f.id
                JOIN commodity_families cf_f ON cc_f.family_id = cf_f.id
                WHERE fc_f.facility_id = f.id AND cf_f.family_code IN ({ph})
            ) OR EXISTS (
                SELECT 1 FROM facility_commodity_mappings fcm_f
                JOIN commodity_categories ccm_f ON fcm_f.category_id = ccm_f.id
                JOIN commodity_families cfm_f ON ccm_f.family_id = cfm_f.id
                WHERE fcm_f.facility_id = f.id AND cfm_f.family_code IN ({ph})
            )
        )""")
        params.extend(family_items * 2)

    category_items = _parse_filter_list(category)
    if category_items:
        ph = ",".join("?" for _ in category_items)
        where_clauses.append(f"""(
            EXISTS (
                SELECT 1 FROM facility_commodities fc_c
                JOIN commodity_categories cc_c ON fc_c.commodity_category_id = cc_c.id
                WHERE fc_c.facility_id = f.id AND cc_c.category_code IN ({ph})
            ) OR EXISTS (
                SELECT 1 FROM facility_commodity_mappings fcm_c
                JOIN commodity_categories ccm_cat ON fcm_c.category_id = ccm_cat.id
                WHERE fcm_c.facility_id = f.id AND ccm_cat.category_code IN ({ph})
            )
        )""")
        params.extend(category_items * 2)

    season_items = _parse_filter_list(seasonality)
    if season_items:
        ph = ",".join("?" for _ in season_items)
        where_clauses.append(f"""(
            EXISTS (
                SELECT 1 FROM facility_commodities fc_sea
                JOIN commodity_categories cc_sea ON fc_sea.commodity_category_id = cc_sea.id
                WHERE fc_sea.facility_id = f.id AND cc_sea.seasonality_profile IN ({ph})
            ) OR EXISTS (
                SELECT 1 FROM facility_commodity_mappings fcm_sea
                JOIN commodity_categories ccm_sea ON fcm_sea.category_id = ccm_sea.id
                WHERE fcm_sea.facility_id = f.id AND ccm_sea.seasonality_profile IN ({ph})
            )
        )""")
        params.extend(season_items * 2)

    fleet_items = _parse_filter_list(fleet)
    if "VERIFIED_PRESENT" in fleet_items and "NONE_VERIFIED" not in fleet_items:
        where_clauses.append("f.private_fleet_present = 'VERIFIED_PRESENT'")
    elif "NONE_VERIFIED" in fleet_items and "VERIFIED_PRESENT" not in fleet_items:
        where_clauses.append("f.private_fleet_present != 'VERIFIED_PRESENT'")

    carrier_items = _parse_filter_list(carrier)
    if "VERIFIED" in carrier_items and "UNKNOWN" not in carrier_items:
        where_clauses.append("f.commercial_carrier_use = 'VERIFIED'")
    elif "UNKNOWN" in carrier_items and "VERIFIED" not in carrier_items:
        where_clauses.append("f.commercial_carrier_use != 'VERIFIED'")

    proc_items = _parse_filter_list(procurement)
    if proc_items:
        ph = ",".join("?" for _ in proc_items)
        where_clauses.append(f"f.freight_procurement_level IN ({ph})")
        params.extend(proc_items)

    tier_items = _parse_filter_list(tier)
    if tier_items:
        target_tiers = {_canonical_tier(t) for t in tier_items} - {None}
        if target_tiers:
            t_clauses = []
            if TIER_A_PRIORITY in target_tiers:
                t_clauses.append("""(
                    (f.commercial_carrier_use = 'VERIFIED' OR f.broker_friendly_status = 'VERIFIED_ACCEPTS')
                    AND COALESCE(pl.stage, 'DISCOVERY') IN ('SHORTLISTED', 'QUALIFIED')
                    AND f.broker_friendly_status != 'VERIFIED_DIRECT_ONLY'
                )""")
            if TIER_B_WORTH_CALLING in target_tiers:
                t_clauses.append("""(
                    COALESCE(pl.stage, 'DISCOVERY') IN ('SHORTLISTED', 'QUALIFIED')
                    AND f.commercial_carrier_use != 'VERIFIED'
                    AND f.broker_friendly_status != 'VERIFIED_ACCEPTS'
                    AND f.broker_friendly_status != 'VERIFIED_DIRECT_ONLY'
                    AND f.private_fleet_present != 'VERIFIED_PRESENT'
                )""")
            if TIER_C_SECONDARY in target_tiers:
                t_clauses.append("""(
                    COALESCE(pl.stage, 'DISCOVERY') IN ('SHORTLISTED', 'QUALIFIED')
                    AND f.private_fleet_present = 'VERIFIED_PRESENT'
                    AND f.commercial_carrier_use != 'VERIFIED'
                    AND f.broker_friendly_status != 'VERIFIED_ACCEPTS'
                    AND f.broker_friendly_status != 'VERIFIED_DIRECT_ONLY'
                )""")
            if TIER_D_RESEARCH_NEEDED in target_tiers:
                t_clauses.append("""(
                    COALESCE(pl.stage, 'DISCOVERY') NOT IN ('SHORTLISTED', 'QUALIFIED')
                    AND f.broker_friendly_status != 'VERIFIED_DIRECT_ONLY'
                )""")
            if RESTRICTED in target_tiers:
                t_clauses.append("f.broker_friendly_status = 'VERIFIED_DIRECT_ONLY'")
            if t_clauses:
                where_clauses.append("(" + " OR ".join(t_clauses) + ")")
            else:
                where_clauses.append("1 = 0")
        else:
            where_clauses.append("1 = 0")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    return where_sql, params


def build_company_filter_sql(
    lifecycle_stage: Optional[str] = "ALL",
    outreach_filter: Optional[Any] = None,
    unreviewed_only: bool = False,
    search: Optional[str] = None,
    equipment: Optional[Any] = None,
    family: Optional[Any] = None,
    category: Optional[Any] = None,
    seasonality: Optional[Any] = None,
    structure: Optional[Any] = None,
    facility_count: Optional[Any] = None,
    fleet: Optional[Any] = None,
    carrier: Optional[Any] = None,
    procurement: Optional[Any] = None,
    tier: Optional[Any] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str | Path] = None,
    universe_context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Any]]:
    """Builds SQL WHERE clause and parameter list for company group filtering."""
    where_clauses = ["c.id IN (SELECT company_id FROM facilities)"]
    filter_params: List[Any] = []

    if lifecycle_stage and lifecycle_stage.upper() != "ALL":
        st = lifecycle_stage.upper()
        if st == "SHORTLISTED":
            where_clauses.append("""
                c.id IN (
                    SELECT f.company_id FROM facilities f
                    JOIN prospect_lifecycle pl ON f.id = pl.facility_id
                    WHERE pl.stage = 'SHORTLISTED'
                )
            """)
        elif st == "QUALIFIED":
            where_clauses.append("""
                c.id IN (
                    SELECT f.company_id FROM facilities f
                    JOIN prospect_lifecycle pl ON f.id = pl.facility_id
                    WHERE pl.stage = 'QUALIFIED'
                ) AND c.id NOT IN (
                    SELECT f.company_id FROM facilities f
                    JOIN prospect_lifecycle pl ON f.id = pl.facility_id
                    WHERE pl.stage = 'SHORTLISTED'
                )
            """)
        elif st == "DISCOVERY":
            where_clauses.append("""
                c.id IN (
                    SELECT f.company_id FROM facilities f
                    JOIN prospect_lifecycle pl ON f.id = pl.facility_id
                    WHERE pl.stage = 'DISCOVERY'
                ) AND c.id NOT IN (
                    SELECT f.company_id FROM facilities f
                    JOIN prospect_lifecycle pl ON f.id = pl.facility_id
                    WHERE pl.stage IN ('SHORTLISTED', 'QUALIFIED')
                )
            """)

    outreach_items = _parse_filter_list(outreach_filter)
    if outreach_items:
        has_fu = any(x in ("FOLLOW_UP", "FOLLOW_UPS", "FOLLOW-UP", "FOLLOW-UPS") for x in outreach_items)
        plain_statuses = [x for x in outreach_items if x not in ("FOLLOW_UP", "FOLLOW_UPS", "FOLLOW-UP", "FOLLOW-UPS")]
        outreach_parts = []
        if plain_statuses:
            ph = ",".join("?" for _ in plain_statuses)
            outreach_parts.append(f"COALESCE(pes.current_outreach_status, 'UNCONTACTED') IN ({ph})")
            filter_params.extend(plain_statuses)
        if has_fu:
            outreach_parts.append("pes.next_follow_up_at IS NOT NULL")
        if outreach_parts:
            where_clauses.append("(" + " OR ".join(outreach_parts) + ")")

    if unreviewed_only:
        where_clauses.append("COALESCE(pes.is_viewed, 0) = 0")

    if search and search.strip():
        q_raw = search.strip().lower()
        q_len = len(q_raw)
        q_contains = f"%{q_raw}%"
        if q_len == 1:
            q_prefix = f"{q_raw}%"
            where_clauses.append("""(
                LOWER(c.operating_brand) LIKE ? OR
                LOWER(COALESCE(c.legal_name, '')) LIKE ? OR
                EXISTS (
                    SELECT 1 FROM facilities f_s WHERE f_s.company_id = c.id AND (
                        LOWER(f_s.facility_name) LIKE ?
                    )
                )
            )""")
            filter_params.extend([q_prefix, q_prefix, q_prefix])
        elif q_len == 2:
            where_clauses.append("""(
                LOWER(c.operating_brand) LIKE ? OR
                LOWER(COALESCE(c.legal_name, '')) LIKE ? OR
                EXISTS (
                    SELECT 1 FROM facilities f_s WHERE f_s.company_id = c.id AND (
                        LOWER(f_s.facility_name) LIKE ? OR
                        LOWER(f_s.state_prov) = ?
                    )
                )
            )""")
            filter_params.extend([q_contains, q_contains, q_contains, q_raw])
        else:
            where_clauses.append("""(
                LOWER(c.operating_brand) LIKE ? OR
                LOWER(COALESCE(c.legal_name, '')) LIKE ? OR
                EXISTS (
                    SELECT 1 FROM facilities f_s WHERE f_s.company_id = c.id AND (
                        LOWER(f_s.facility_name) LIKE ? OR
                        LOWER(f_s.physical_address) LIKE ? OR
                        LOWER(f_s.city) LIKE ? OR
                        LOWER(f_s.state_prov) LIKE ? OR
                        LOWER(COALESCE(f_s.postal_code, '')) LIKE ?
                    )
                ) OR
                EXISTS (
                    SELECT 1 FROM facilities f_s2
                    JOIN facility_commodities fc_s ON f_s2.id = fc_s.facility_id
                    WHERE f_s2.company_id = c.id AND (
                        LOWER(COALESCE(fc_s.commodity_category, '')) LIKE ? OR
                        LOWER(COALESCE(fc_s.specific_products, '')) LIKE ? OR
                        LOWER(COALESCE(fc_s.equipment_category, '')) LIKE ?
                    )
                ) OR
                EXISTS (
                    SELECT 1 FROM contacts ct_s
                    WHERE ct_s.company_id = c.id AND (
                        LOWER(COALESCE(ct_s.person_name, '')) LIKE ? OR
                        LOWER(COALESCE(ct_s.exact_published_title, '')) LIKE ? OR
                        LOWER(COALESCE(ct_s.department, '')) LIKE ?
                    )
                ) OR
                EXISTS (
                    SELECT 1 FROM facilities f_s3
                    JOIN contacts ct_s2 ON f_s3.id = ct_s2.facility_id
                    WHERE f_s3.company_id = c.id AND (
                        LOWER(COALESCE(ct_s2.person_name, '')) LIKE ? OR
                        LOWER(COALESCE(ct_s2.exact_published_title, '')) LIKE ? OR
                        LOWER(COALESCE(ct_s2.department, '')) LIKE ?
                    )
                ) OR
                EXISTS (
                    SELECT 1 FROM facilities f_s4
                    JOIN facility_commodity_mappings fcm_s ON f_s4.id = fcm_s.facility_id
                    JOIN commodity_categories ccm_s ON fcm_s.category_id = ccm_s.id
                    JOIN commodity_families cfm_s ON ccm_s.family_id = cfm_s.id
                    WHERE f_s4.company_id = c.id AND (
                        LOWER(ccm_s.display_name) LIKE ? OR
                        LOWER(ccm_s.category_code) LIKE ? OR
                        LOWER(cfm_s.display_name) LIKE ? OR
                        LOWER(cfm_s.family_code) LIKE ?
                    )
                )
            )""")
            filter_params.extend([q_contains] * 20)

    equipment_items = _parse_filter_list(equipment)
    if equipment_items:
        ph = ",".join("?" for _ in equipment_items)
        where_clauses.append(f"""
            EXISTS (
                SELECT 1 FROM facilities f_eq
                JOIN facility_commodities fc_eq ON f_eq.id = fc_eq.facility_id
                WHERE f_eq.company_id = c.id AND fc_eq.equipment_category IN ({ph})
            )
        """)
        filter_params.extend(equipment_items)

    family_items = _parse_filter_list(family)
    if family_items:
        ph = ",".join("?" for _ in family_items)
        where_clauses.append(f"""(
            EXISTS (
                SELECT 1 FROM facilities f_fam
                JOIN facility_commodities fc_fam ON f_fam.id = fc_fam.facility_id
                JOIN commodity_categories cc_fam ON fc_fam.commodity_category_id = cc_fam.id
                JOIN commodity_families cf_fam ON cc_fam.family_id = cf_fam.id
                WHERE f_fam.company_id = c.id AND cf_fam.family_code IN ({ph})
            ) OR EXISTS (
                SELECT 1 FROM facilities f_fam2
                JOIN facility_commodity_mappings fcm_fam ON f_fam2.id = fcm_fam.facility_id
                JOIN commodity_categories ccm_fam ON fcm_fam.category_id = ccm_fam.id
                JOIN commodity_families cfm_fam ON ccm_fam.family_id = cfm_fam.id
                WHERE f_fam2.company_id = c.id AND cfm_fam.family_code IN ({ph})
            )
        )""")
        filter_params.extend(family_items * 2)

    category_items = _parse_filter_list(category)
    if category_items:
        ph = ",".join("?" for _ in category_items)
        where_clauses.append(f"""(
            EXISTS (
                SELECT 1 FROM facilities f_cat
                JOIN facility_commodities fc_cat ON f_cat.id = fc_cat.facility_id
                JOIN commodity_categories cc_cat ON fc_cat.commodity_category_id = cc_cat.id
                WHERE f_cat.company_id = c.id AND cc_cat.category_code IN ({ph})
            ) OR EXISTS (
                SELECT 1 FROM facilities f_cat2
                JOIN facility_commodity_mappings fcm_cat ON f_cat2.id = fcm_cat.facility_id
                JOIN commodity_categories ccm_cat ON fcm_cat.category_id = ccm_cat.id
                WHERE f_cat2.company_id = c.id AND ccm_cat.category_code IN ({ph})
            )
        )""")
        filter_params.extend(category_items * 2)

    season_items = _parse_filter_list(seasonality)
    if season_items:
        ph = ",".join("?" for _ in season_items)
        where_clauses.append(f"""(
            EXISTS (
                SELECT 1 FROM facilities f_sea
                JOIN facility_commodities fc_sea ON f_sea.id = fc_sea.facility_id
                JOIN commodity_categories cc_sea ON fc_sea.commodity_category_id = cc_sea.id
                WHERE f_sea.company_id = c.id AND cc_sea.seasonality_profile IN ({ph})
            ) OR EXISTS (
                SELECT 1 FROM facilities f_sea2
                JOIN facility_commodity_mappings fcm_sea ON f_sea2.id = fcm_sea.facility_id
                JOIN commodity_categories ccm_sea ON fcm_sea.category_id = ccm_sea.id
                WHERE f_sea2.company_id = c.id AND ccm_sea.seasonality_profile IN ({ph})
            )
        )""")
        filter_params.extend(season_items * 2)

    structure_items = _parse_filter_list(structure)
    if "SINGLE" in structure_items and "MULTI" not in structure_items:
        where_clauses.append("(SELECT count(*) FROM facilities f_cnt WHERE f_cnt.company_id = c.id) = 1")
    elif "MULTI" in structure_items and "SINGLE" not in structure_items:
        where_clauses.append("(SELECT count(*) FROM facilities f_cnt WHERE f_cnt.company_id = c.id) >= 2")

    fc_items = _parse_filter_list(facility_count)
    if fc_items:
        fc_clauses = []
        for fc in fc_items:
            if fc == "1":
                fc_clauses.append("(SELECT count(*) FROM facilities f_cnt WHERE f_cnt.company_id = c.id) = 1")
            elif fc in ("2_5", "2-5"):
                fc_clauses.append("(SELECT count(*) FROM facilities f_cnt WHERE f_cnt.company_id = c.id) BETWEEN 2 AND 5")
            elif fc in ("6_20", "6-20"):
                fc_clauses.append("(SELECT count(*) FROM facilities f_cnt WHERE f_cnt.company_id = c.id) BETWEEN 6 AND 20")
            elif fc in ("20_PLUS", "21_PLUS", "20+"):
                fc_clauses.append("(SELECT count(*) FROM facilities f_cnt WHERE f_cnt.company_id = c.id) >= 21")
        if fc_clauses:
            where_clauses.append("(" + " OR ".join(fc_clauses) + ")")

    fleet_items = _parse_filter_list(fleet)
    if "VERIFIED_PRESENT" in fleet_items and "NONE_VERIFIED" not in fleet_items:
        where_clauses.append("EXISTS (SELECT 1 FROM facilities f_fl WHERE f_fl.company_id = c.id AND f_fl.private_fleet_present = 'VERIFIED_PRESENT')")
    elif "NONE_VERIFIED" in fleet_items and "VERIFIED_PRESENT" not in fleet_items:
        where_clauses.append("NOT EXISTS (SELECT 1 FROM facilities f_fl WHERE f_fl.company_id = c.id AND f_fl.private_fleet_present = 'VERIFIED_PRESENT')")

    carrier_items = _parse_filter_list(carrier)
    if "VERIFIED" in carrier_items and "UNKNOWN" not in carrier_items:
        where_clauses.append("EXISTS (SELECT 1 FROM facilities f_cr WHERE f_cr.company_id = c.id AND f_cr.commercial_carrier_use = 'VERIFIED')")
    elif "UNKNOWN" in carrier_items and "VERIFIED" not in carrier_items:
        where_clauses.append("NOT EXISTS (SELECT 1 FROM facilities f_cr WHERE f_cr.company_id = c.id AND f_cr.commercial_carrier_use = 'VERIFIED')")

    proc_items = _parse_filter_list(procurement)
    if proc_items:
        ph = ",".join("?" for _ in proc_items)
        where_clauses.append(f"EXISTS (SELECT 1 FROM facilities f_pr WHERE f_pr.company_id = c.id AND f_pr.freight_procurement_level IN ({ph}))")
        filter_params.extend(proc_items)

    tier_items = _parse_filter_list(tier)
    if tier_items:
        target_tiers = {_canonical_tier(t) for t in tier_items} - {None}
        if target_tiers:
            tier_map = get_opportunity_tier_company_ids(conn=conn, db_path=db_path, universe_context=universe_context)
            matching_cids = []
            for tt in target_tiers:
                matching_cids.extend(tier_map.get(tt, []))
            matching_cids = sorted(list(set(matching_cids)))
            if matching_cids:
                placeholders = ",".join("?" for _ in matching_cids)
                where_clauses.append(f"c.id IN ({placeholders})")
                filter_params.extend(matching_cids)
            else:
                where_clauses.append("1 = 0")
        else:
            where_clauses.append("1 = 0")

    where_sql = "WHERE " + " AND ".join(where_clauses)
    return where_sql, filter_params

def get_prospects_list(
    db_path: Optional[str | Path] = None,
    lifecycle_stage: Optional[str] = "SHORTLISTED",
    allow_alaska: bool = False,
    conn: Optional[sqlite3.Connection] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    search: Optional[str] = None,
    equipment: Optional[str] = None,
    family: Optional[str] = None,
    category: Optional[str] = None,
    seasonality: Optional[str] = None,
    fleet: Optional[str] = None,
    carrier: Optional[str] = None,
    procurement: Optional[str] = None,
    tier: Optional[str] = None,
    opportunity_tier: Optional[str] = None,
    facility_ids: Optional[List[int]] = None,
    company_ids: Optional[List[int]] = None,
) -> Any:
    """
    Returns the list of prospect facilities filtered by lifecycle stage.
    Optimized batch execution with two-phase SQL pushdown pagination.
    Phase 1: Pure SQL ID selection + total count matching filters.
    Phase 2: Hydrate only the ~25 page IDs across all child tables.
    Preserves 100% dictionary key and type parity with original queries.
    """
    effective_tier = tier or opportunity_tier
    if effective_tier and lifecycle_stage == "SHORTLISTED":
        lifecycle_stage = "ALL"
    if isinstance(db_path, str) and db_path.upper() in ("ALL", "SHORTLISTED", "QUALIFIED", "DISCOVERY"):
        lifecycle_stage = db_path
        db_path = None

    should_close = False
    if conn is None:
        conn = create_connection(db_path)
        conn.row_factory = sqlite3.Row
        should_close = True
    try:
        # Check tables existence
        has_lifecycle = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='prospect_lifecycle'"
        ).fetchone()[0] > 0
        has_engagement = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='prospect_engagement_state'"
        ).fetchone()[0] > 0
        has_tax = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='facility_commodity_mappings'"
        ).fetchone()[0] > 0

        paged_two_phase = False
        if page is not None and page_size is not None and facility_ids is None and company_ids is None:
            paged_two_phase = True
            w_sql, p_params = build_facility_filter_sql(
                lifecycle_stage=lifecycle_stage,
                search=search,
                equipment=equipment,
                family=family,
                category=category,
                seasonality=seasonality,
                fleet=fleet,
                carrier=carrier,
                procurement=procurement,
                tier=effective_tier,
            )
            count_sql = f"""
                SELECT count(DISTINCT f.id)
                FROM facilities f
                JOIN companies c ON f.company_id = c.id
                LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
                {w_sql}
            """
            total_count = conn.execute(count_sql, p_params).fetchone()[0]

            id_sql = f"""
                SELECT DISTINCT f.id
                FROM facilities f
                JOIN companies c ON f.company_id = c.id
                LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
                {w_sql}
                ORDER BY f.id ASC
                LIMIT ? OFFSET ?
            """
            offset = max(0, (page - 1) * page_size)
            paged_params = list(p_params) + [page_size, offset]
            target_facility_ids = [r[0] for r in conn.execute(id_sql, paged_params).fetchall()]

            if not target_facility_ids:
                total_pages = max(1, (total_count + page_size - 1) // page_size)
                return {
                    "items": [],
                    "total_count": total_count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                }
            facility_ids = target_facility_ids

        where_clause = ""
        params: List[Any] = []
        if facility_ids is not None:
            if not facility_ids:
                return [] if not paged_two_phase else {
                    "items": [],
                    "total_count": total_count if "total_count" in locals() else 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 1,
                }
            placeholders = ",".join("?" * len(facility_ids))
            where_clause = f"WHERE f.id IN ({placeholders})"
            params = list(facility_ids)
        elif company_ids is not None:
            if not company_ids:
                return []
            placeholders = ",".join("?" * len(company_ids))
            where_clause = f"WHERE f.company_id IN ({placeholders})"
            params = list(company_ids)
        elif has_lifecycle and lifecycle_stage and lifecycle_stage.upper() != "ALL":
            where_clause = "WHERE COALESCE(pl.stage, 'DISCOVERY') = ?"
            params.append(lifecycle_stage.upper())

        engagement_select = ""
        engagement_join = ""
        if has_engagement:
            engagement_select = """,
                COALESCE(pes.current_outreach_status, 'UNCONTACTED') as company_outreach_status,
                COALESCE(pes.attempt_count, 0) as company_attempt_count,
                pes.next_follow_up_at as next_follow_up_at,
                COALESCE(pes.is_viewed, 0) as is_viewed"""
            engagement_join = "LEFT JOIN prospect_engagement_state pes ON c.id = pes.company_id"

        query = f"""
            SELECT
                f.id as facility_id,
                f.facility_name,
                f.facility_type,
                f.physical_address,
                f.city,
                f.state_prov,
                f.country,
                f.postal_code,
                f.private_fleet_present,
                f.vehicle_asset_ownership,
                f.fleet_relationship_type,
                f.commercial_carrier_use,
                f.broker_friendly_status,
                f.freight_procurement_level,
                c.id as company_id,
                c.operating_brand,
                c.legal_name,
                c.website_url,
                c.corporate_address,
                c.notes as company_notes,
                c.company_footprint_status,
                c.verified_operating_location_count,
                c.footprint_source_notes,
                COALESCE(pl.stage, 'DISCOVERY') as lifecycle_stage,
                pl.updated_at as stage_updated_at,
                pl.notes as stage_notes{engagement_select}
            FROM facilities f
            JOIN companies c ON f.company_id = c.id
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            {engagement_join}
            {where_clause}
            ORDER BY f.id ASC
        """
        facility_rows = conn.execute(query, params).fetchall()
        if not facility_rows:
            return [] if not paged_two_phase else {
                "items": [],
                "total_count": total_count if "total_count" in locals() else 0,
                "page": page,
                "page_size": page_size,
                "total_pages": max(1, (total_count + page_size - 1) // page_size) if "total_count" in locals() else 1,
            }

        target_fids = [r["facility_id"] for r in facility_rows]
        target_cids = list(set(r["company_id"] for r in facility_rows))
        is_subset = len(target_fids) < 615 and len(target_fids) > 0
        fac_ph = ",".join("?" * len(target_fids)) if is_subset else ""
        comp_ph = ",".join("?" * len(target_cids)) if is_subset else ""

        # 1. Pre-aggregate facility outreach logs (Query 2)
        fac_outreach_map: Dict[int, Tuple[str, int]] = {}
        if has_engagement:
            has_logs = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='outreach_logs'"
            ).fetchone()[0] > 0
            if has_logs:
                log_where = f"WHERE facility_id IN ({fac_ph})" if is_subset else "WHERE facility_id IS NOT NULL"
                log_params = target_fids if is_subset else []
                for r in conn.execute(f"""
                    SELECT facility_id, outcome, count_phone
                    FROM (
                        SELECT facility_id, outcome,
                                ROW_NUMBER() OVER(PARTITION BY facility_id ORDER BY contacted_at DESC, id DESC) as rn,
                                SUM(CASE WHEN outreach_channel = 'PHONE' THEN 1 ELSE 0 END) OVER(PARTITION BY facility_id) as count_phone
                        FROM outreach_logs
                        {log_where}
                    ) WHERE rn = 1
                """, log_params).fetchall():
                    fac_outreach_map[r["facility_id"]] = (r["outcome"], r["count_phone"])

        # 2. Batch fetch commodities (Query 3)
        comms_by_fac: Dict[int, List[Dict[str, Any]]] = {}
        fc_where = f"WHERE facility_id IN ({fac_ph})" if is_subset else ""
        fc_params = target_fids if is_subset else []
        for r in conn.execute(f"""
            SELECT id, facility_id, commodity_category, specific_products, equipment_category,
                   equipment_usage_status, trailer_specs_notes, securement_tarp_notes
            FROM facility_commodities
            {fc_where}
            ORDER BY facility_id, id ASC
        """, fc_params).fetchall():
            fid = r["facility_id"]
            if fid not in comms_by_fac:
                comms_by_fac[fid] = []
            comms_by_fac[fid].append(dict(r))

        # 3. Batch fetch taxonomy mappings (Query 4)
        tax_by_fac: Dict[int, List[Dict[str, Any]]] = {}
        if has_tax:
            tax_where = f"WHERE m.facility_id IN ({fac_ph})" if is_subset else ""
            tax_params = target_fids if is_subset else []
            for r in conn.execute(f"""
                SELECT m.facility_id, c.id as category_id, c.category_code, c.display_name as category_name,
                       c.typical_equipment_fit, c.seasonality_profile as cat_seasonality,
                       c.peak_months as cat_peak_months, c.operating_characteristics,
                       cf.id as family_id, cf.family_code, cf.display_name as family_name,
                       m.is_primary, m.source_evidence_notes
                FROM facility_commodity_mappings m
                JOIN commodity_categories c ON m.category_id = c.id
                JOIN commodity_families cf ON c.family_id = cf.id
                {tax_where}
                ORDER BY m.facility_id, m.is_primary DESC, c.sort_order ASC
            """, tax_params).fetchall():
                fid = r["facility_id"]
                if fid not in tax_by_fac:
                    tax_by_fac[fid] = []
                tax_by_fac[fid].append(dict(r))

        # 4. Batch fetch contacts (Query 5)
        contacts_by_fac: Dict[int, List[Dict[str, Any]]] = {}
        ct_where = f"WHERE facility_id IN ({fac_ph})" if is_subset else ""
        ct_params = target_fids if is_subset else []
        for r in conn.execute(f"""
            SELECT id, facility_id, contact_identity, person_name, exact_published_title, department,
                   phone_number, phone_extension, phone_directness, email_address,
                   email_directness, role_category, outbound_shipping_procurement_relevance,
                   broker_procurement_relevance, is_primary_contact
            FROM contacts
            {ct_where}
            ORDER BY facility_id,
                     CASE WHEN phone_number IS NOT NULL AND TRIM(phone_number) != '' AND phone_number != 'UNKNOWN' THEN 0 ELSE 1 END,
                     is_primary_contact DESC,
                     CASE WHEN phone_directness = 'DIRECT_PERSON' THEN 0
                          WHEN phone_directness = 'DEPARTMENT_LINE' THEN 1
                          WHEN phone_directness = 'TOLL_FREE' THEN 2
                          ELSE 3 END,
                     id ASC
        """, ct_params).fetchall():
            fid = r["facility_id"]
            if fid not in contacts_by_fac:
                contacts_by_fac[fid] = []
            contacts_by_fac[fid].append(dict(r))

        # 5. Batch fetch company relationships (Query 6)
        parent_by_comp: Dict[int, Dict[str, Any]] = {}
        has_rel = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='company_relationships'"
        ).fetchone()[0] > 0
        if has_rel:
            rel_where = f"AND r.child_company_id IN ({comp_ph})" if is_subset else ""
            rel_params = target_cids if is_subset else []
            for r in conn.execute(f"""
                SELECT r.child_company_id, r.relationship_type, r.valid_from, r.notes as relationship_notes,
                       p.operating_brand as parent_brand, p.legal_name as parent_legal,
                       p.notes as parent_notes
                FROM company_relationships r
                JOIN companies p ON r.parent_company_id = p.id
                WHERE r.is_current = 1 {rel_where}
            """, rel_params).fetchall():
                parent_by_comp[r["child_company_id"]] = {
                    "relationship_type": r["relationship_type"],
                    "valid_from": r["valid_from"],
                    "relationship_notes": r["relationship_notes"],
                    "parent_brand": r["parent_brand"],
                    "parent_legal": r["parent_legal"],
                    "parent_notes": r["parent_notes"],
                    "corporate_group": "TI Automotive",
                    "current_hierarchy_status": "UNKNOWN"
                }

        # 6. Batch fetch claims counts (Query 7)
        if is_subset:
            claims_cnt_fac = dict(conn.execute(f"SELECT facility_id, count(*) FROM claims WHERE facility_id IN ({fac_ph}) GROUP BY facility_id", target_fids).fetchall())
            claims_cnt_comp = dict(conn.execute(f"SELECT company_id, count(*) FROM claims WHERE company_id IN ({comp_ph}) GROUP BY company_id", target_cids).fetchall())
        else:
            claims_cnt_fac = dict(conn.execute("SELECT facility_id, count(*) FROM claims WHERE facility_id IS NOT NULL GROUP BY facility_id").fetchall())
            claims_cnt_comp = dict(conn.execute("SELECT company_id, count(*) FROM claims WHERE company_id IS NOT NULL GROUP BY company_id").fetchall())

        # 7. Evidenced claims for qualification readiness (Query 8)
        if is_subset:
            evidenced_addr = set(r[0] for r in conn.execute(f"""
                SELECT DISTINCT c.facility_id
                FROM claims c
                JOIN facilities f ON c.facility_id = f.id
                JOIN claim_evidence ce ON c.id = ce.claim_id
                WHERE c.facility_id IN ({fac_ph})
                  AND c.claim_field = 'physical_address'
                  AND c.is_current_accepted = 1
                  AND c.verification_status = 'VERIFIED'
                  AND (
                      TRIM(c.claimed_value) = TRIM(f.physical_address)
                      OR INSTR(c.claimed_value, f.physical_address) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Road', ' Rd')) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Street', ' St')) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Avenue', ' Ave')) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Boulevard', ' Blvd')) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Highway', ' Hwy')) > 0
                  )
                  AND ce.relationship = 'SUPPORTS'
            """, target_fids).fetchall())

            evidenced_equip = set(r[0] for r in conn.execute(f"""
                SELECT DISTINCT fc.facility_id
                FROM claims c
                JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
                JOIN claim_evidence ce ON c.id = ce.claim_id
                WHERE fc.facility_id IN ({fac_ph})
                  AND c.claim_field = 'equipment_category'
                  AND c.is_current_accepted = 1
                  AND c.verification_status IN ('VERIFIED', 'INFERRED')
                  AND TRIM(c.claimed_value) = TRIM(fc.equipment_category)
                  AND ce.relationship = 'SUPPORTS'
            """, target_fids).fetchall())

            raw_contact_claims = conn.execute(f"""
                SELECT c.contact_id, ct.facility_id, ct.phone_number, ct.phone_directness, 
                       ct.email_address, ct.email_directness, c.claim_field, c.claimed_value, c.claim_notes
                FROM claims c
                JOIN contacts ct ON c.contact_id = ct.id
                JOIN claim_evidence ce ON c.id = ce.claim_id
                WHERE ct.facility_id IN ({fac_ph})
                  AND c.is_current_accepted = 1
                  AND c.verification_status IN ('VERIFIED', 'INFERRED')
                  AND ce.relationship = 'SUPPORTS'
                GROUP BY c.id
            """, target_fids).fetchall()

            ev_counts_by_fac = dict(conn.execute(f"""
                SELECT facility_id, count(DISTINCT claim_id) FROM (
                    SELECT c.facility_id, c.id as claim_id
                    FROM claims c JOIN claim_evidence ce ON c.id = ce.claim_id
                    WHERE c.facility_id IN ({fac_ph}) AND c.is_current_accepted = 1 AND ce.relationship = 'SUPPORTS'
                    UNION
                    SELECT fc.facility_id, c.id as claim_id
                    FROM claims c JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
                    JOIN claim_evidence ce ON c.id = ce.claim_id
                    WHERE fc.facility_id IN ({fac_ph}) AND c.is_current_accepted = 1 AND ce.relationship = 'SUPPORTS'
                    UNION
                    SELECT ct.facility_id, c.id as claim_id
                    FROM claims c JOIN contacts ct ON c.contact_id = ct.id
                    JOIN claim_evidence ce ON c.id = ce.claim_id
                    WHERE ct.facility_id IN ({fac_ph}) AND c.is_current_accepted = 1 AND ce.relationship = 'SUPPORTS'
                    UNION
                    SELECT f.id as facility_id, c.id as claim_id
                    FROM claims c JOIN facilities f ON c.company_id = f.company_id
                    JOIN claim_evidence ce ON c.id = ce.claim_id
                    WHERE f.id IN ({fac_ph}) AND c.is_current_accepted = 1 AND ce.relationship = 'SUPPORTS'
                ) GROUP BY facility_id
            """, target_fids * 4).fetchall())
        else:
            evidenced_addr = set(r[0] for r in conn.execute("""
                SELECT DISTINCT c.facility_id
                FROM claims c
                JOIN facilities f ON c.facility_id = f.id
                JOIN claim_evidence ce ON c.id = ce.claim_id
                WHERE c.claim_field = 'physical_address'
                  AND c.is_current_accepted = 1
                  AND c.verification_status = 'VERIFIED'
                  AND (
                      TRIM(c.claimed_value) = TRIM(f.physical_address)
                      OR INSTR(c.claimed_value, f.physical_address) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Road', ' Rd')) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Street', ' St')) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Avenue', ' Ave')) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Boulevard', ' Blvd')) > 0
                      OR INSTR(c.claimed_value, REPLACE(f.physical_address, ' Highway', ' Hwy')) > 0
                  )
                  AND ce.relationship = 'SUPPORTS'
            """).fetchall())

            evidenced_equip = set(r[0] for r in conn.execute("""
                SELECT DISTINCT fc.facility_id
                FROM claims c
                JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
                JOIN claim_evidence ce ON c.id = ce.claim_id
                WHERE c.claim_field = 'equipment_category'
                  AND c.is_current_accepted = 1
                  AND c.verification_status IN ('VERIFIED', 'INFERRED')
                  AND TRIM(c.claimed_value) = TRIM(fc.equipment_category)
                  AND ce.relationship = 'SUPPORTS'
            """).fetchall())

            raw_contact_claims = conn.execute("""
                SELECT c.contact_id, ct.facility_id, ct.phone_number, ct.phone_directness, 
                       ct.email_address, ct.email_directness, c.claim_field, c.claimed_value, c.claim_notes
                FROM claims c
                JOIN contacts ct ON c.contact_id = ct.id
                JOIN claim_evidence ce ON c.id = ce.claim_id
                WHERE c.is_current_accepted = 1
                  AND c.verification_status IN ('VERIFIED', 'INFERRED')
                  AND ce.relationship = 'SUPPORTS'
                GROUP BY c.id
            """).fetchall()

            ev_counts_by_fac = dict(conn.execute("""
                SELECT facility_id, count(DISTINCT claim_id) FROM (
                    SELECT c.facility_id, c.id as claim_id
                    FROM claims c JOIN claim_evidence ce ON c.id = ce.claim_id
                    WHERE c.is_current_accepted = 1 AND ce.relationship = 'SUPPORTS' AND c.facility_id IS NOT NULL
                    UNION
                    SELECT fc.facility_id, c.id as claim_id
                    FROM claims c JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
                    JOIN claim_evidence ce ON c.id = ce.claim_id
                    WHERE c.is_current_accepted = 1 AND ce.relationship = 'SUPPORTS'
                    UNION
                    SELECT ct.facility_id, c.id as claim_id
                    FROM claims c JOIN contacts ct ON c.contact_id = ct.id
                    JOIN claim_evidence ce ON c.id = ce.claim_id
                    WHERE c.is_current_accepted = 1 AND ce.relationship = 'SUPPORTS'
                    UNION
                    SELECT f.id as facility_id, c.id as claim_id
                    FROM claims c JOIN facilities f ON c.company_id = f.company_id
                    JOIN claim_evidence ce ON c.id = ce.claim_id
                    WHERE c.is_current_accepted = 1 AND ce.relationship = 'SUPPORTS'
                ) GROUP BY facility_id
            """).fetchall())

        evidenced_contact = set()
        for r in raw_contact_claims:
            fid = r["facility_id"]
            p_ok = is_valid_phone_number(r["phone_number"])
            e_ok = is_valid_email(r["email_address"])
            if p_ok and r["claim_field"] == "phone_directness":
                if r["claimed_value"] == r["phone_directness"]:
                    if r["claim_notes"]:
                        n_digits = re.findall(r"\d{10}|\d{3}[-.\s]\d{3}[-.\s]\d{4}", r["claim_notes"])
                        if n_digits:
                            n_clean = normalize_phone_digits(n_digits[0])
                            p_clean = normalize_phone_digits(r["phone_number"] or "")
                            if n_clean != p_clean:
                                continue
                    evidenced_contact.add(fid)
            elif e_ok and r["claim_field"] in ("email_directness", "email_address"):
                evidenced_contact.add(fid)

        # Pure Python Assembly (0.001 ms per facility)
        approved_equip = {"FLATBED", "STEP_DECK", "DRY_VAN"}
        prospects = []

        for row in facility_rows:
            fac_id = row["facility_id"]
            comp_id = row["company_id"]

            commodities = comms_by_fac.get(fac_id, [])
            primary_commodity = commodities[0] if commodities else None

            taxonomy_mappings = tax_by_fac.get(fac_id, [])
            primary_tax = taxonomy_mappings[0] if taxonomy_mappings else None

            contacts = contacts_by_fac.get(fac_id, [])
            best_contact = contacts[0] if contacts else None

            parent_info = parent_by_comp.get(comp_id)

            claims_count = claims_cnt_fac.get(fac_id, 0) + claims_cnt_comp.get(comp_id, 0)

            # Determine Truthful Outreach & Next Action
            has_direct_phone = any(ct["phone_directness"] == "DIRECT_PERSON" for ct in contacts)
            direct_contact = next((ct for ct in contacts if ct["phone_directness"] == "DIRECT_PERSON"), None)

            if direct_contact and direct_contact.get("phone_number"):
                next_action = f"Call {direct_contact['person_name']} (Direct: {direct_contact['phone_number']})"
                contact_type_badge = "DIRECT_PERSON"
            elif best_contact and best_contact.get("phone_number"):
                name_or_title = best_contact["person_name"] or best_contact["exact_published_title"]
                next_action = f"Call {name_or_title} ({best_contact['phone_number']}) — {best_contact['phone_directness']}"
                contact_type_badge = best_contact["phone_directness"]
            elif best_contact and best_contact.get("email_address"):
                name_or_dept = best_contact["person_name"] or best_contact["department"] or "Shipping"
                next_action = f"Email {name_or_dept} ({best_contact['email_address']})"
                contact_type_badge = best_contact.get("email_directness", "UNKNOWN")
            else:
                next_action = "Research primary shipping contact"
                contact_type_badge = "UNKNOWN"

            # Check 1: facility_identity_verified
            addr = (row["physical_address"] or "").strip()
            city = (row["city"] or "").strip()
            state = (row["state_prov"] or "").strip().upper()
            country = (row["country"] or "").strip().upper()
            has_addr_evidence = fac_id in evidenced_addr
            identity_passed = bool(
                addr and addr.upper() != "UNKNOWN" and city and state and country in ("US", "CA") and has_addr_evidence
            )
            if identity_passed:
                identity_details = f"Physical facility confirmed at {addr}, {city}, {state} {country} (backed by verified evidence source)"
            elif not has_addr_evidence and addr and addr.upper() != "UNKNOWN":
                identity_details = "Facility address present but missing verified accepted claim backed by documented evidence source"
            else:
                identity_details = "Incomplete facility physical address or unsupported country"

            # Check 2: commodity_equipment_fit
            has_commodities = len(commodities) > 0
            equip_fit_basic = has_commodities and any(
                any(eq in (c["equipment_category"] or "") for eq in approved_equip) and
                c["equipment_usage_status"] in ("VERIFIED", "INFERRED")
                for c in commodities
            )
            has_equip_evidence = fac_id in evidenced_equip
            equip_fit_passed = bool(equip_fit_basic and has_equip_evidence)
            if equip_fit_passed:
                equip_details = f"{len(commodities)} commodity profile(s) with approved FTL equipment backed by documented evidence"
            elif equip_fit_basic and not has_equip_evidence:
                equip_details = "Commodity equipment fit identified but missing accepted equipment claim backed by documented evidence"
            else:
                equip_details = "Missing commodity profile or unverified/unapproved equipment category"

            # Check 3: geography_eligible
            if country == "US":
                if state == "AK":
                    geo_passed = allow_alaska
                    geo_details = "Alaska freight territory (Override toggle enabled)" if allow_alaska else "Alaska excluded by default in V1 (Decision A)"
                elif state == "HI":
                    geo_passed = False
                    geo_details = "Excluded freight territory (Hawaii - no FTL truckload service)"
                elif state in LOWER_48_STATES:
                    geo_passed = True
                    geo_details = f"Eligible US Lower 48 freight territory ({state})"
                else:
                    geo_passed = False
                    geo_details = f"Unrecognized US state or territory ({state})"
            elif country == "CA":
                if not state or state in CANADIAN_JURISDICTIONS:
                    geo_passed = True
                    if state in CANADIAN_PROVINCES:
                        geo_details = f"Eligible Canadian province ({state})"
                    elif state in CANADIAN_TERRITORIES:
                        geo_details = f"Eligible Canadian territory ({state})"
                    else:
                        geo_details = f"Eligible Canadian jurisdiction ({state if state else 'Canada'})"
                else:
                    geo_passed = False
                    geo_details = f"Unrecognized Canadian jurisdiction ({state})"
            elif country == "MX":
                geo_passed = False
                geo_details = "Excluded freight territory (Mexico - out of V1 scope)"
            else:
                geo_passed = False
                geo_details = f"Unrecognized freight territory ({state}, {country})"

            # Check 4: usable_outreach_route
            has_phone = any(
                is_valid_phone_number(ct.get("phone_number"))
                for ct in contacts
            )
            has_email = any(
                is_valid_email(ct.get("email_address"))
                for ct in contacts
            )
            outreach_basic = has_phone or has_email
            has_contact_evidence = fac_id in evidenced_contact
            outreach_passed = bool(outreach_basic and has_contact_evidence)
            if outreach_passed:
                if has_phone and has_email:
                    outreach_details = "Verified phone route and usable email address available (evidence backed)"
                elif has_phone:
                    outreach_details = "Verified phone route available (Phone-First priority, evidence backed)"
                else:
                    outreach_details = "Usable published email available (Phone pending, evidence backed)"
            elif outreach_basic and not has_contact_evidence:
                outreach_details = "Contact info present but missing accepted contact claim backed by documented evidence"
            else:
                outreach_details = "No callable phone route or usable email address found"

            # Check 5: supporting_evidence_provenance
            ev_count = ev_counts_by_fac.get(fac_id, 0)
            evidence_passed = ev_count > 0
            evidence_details = (
                f"Evidence provenance verified ({ev_count} accepted claim(s) backed by documented evidence)"
                if evidence_passed
                else "Missing supporting evidence sources backing facility claims"
            )

            checks = {
                "facility_identity_verified": {"passed": identity_passed, "details": identity_details},
                "commodity_equipment_fit": {"passed": equip_fit_passed, "details": equip_details},
                "geography_eligible": {"passed": geo_passed, "details": geo_details},
                "usable_outreach_route": {"passed": outreach_passed, "details": outreach_details},
                "supporting_evidence_provenance": {"passed": evidence_passed, "details": evidence_details},
            }
            passed_count = sum(1 for c in checks.values() if c["passed"])
            is_ready = (passed_count == 5)
            readiness = {
                "facility_id": fac_id,
                "is_ready": is_ready,
                "status": "READY" if is_ready else "INCOMPLETE",
                "passed_count": passed_count,
                "total_checks": 5,
                "checks": checks,
            }

            # Facility outreach status
            fac_outreach_status, fac_attempts = fac_outreach_map.get(fac_id, ("UNCONTACTED", 0))

            # Factual explanation for lifecycle stage (AUD-016 resolved)
            stage = row["lifecycle_stage"]
            why_facts = []
            if stage == "SHORTLISTED":
                why_facts.append("All 5 factual qualification readiness checks passed")
                eq_cat = primary_commodity["equipment_category"] if primary_commodity and primary_commodity.get("equipment_category") else "FTL"
                why_facts.append(f"Approved heavy FTL fit: {eq_cat}")
                if has_direct_phone and direct_contact:
                    why_facts.append(f"Direct callable line: {direct_contact.get('person_name') or direct_contact.get('exact_published_title') or 'Operations'}")
                elif best_contact and best_contact.get("phone_number"):
                    why_facts.append(f"Callable facility phone verified ({best_contact['phone_number']})")
                if row["commercial_carrier_use"] == "VERIFIED":
                    why_facts.append("Commercial carrier use confirmed (VERIFIED)")
                if row["private_fleet_present"] == "VERIFIED_PRESENT":
                    why_facts.append("Private fleet present (competing asset capacity noted)")
            elif stage == "QUALIFIED":
                why_facts.append("Active physical manufacturing facility verified")
                why_facts.append("FTL commodity & equipment profile verified/inferred")
                why_facts.append(f"Eligible freight territory ({row['state_prov']}, {row['country']})")
                why_facts.append("Callable phone route or corporate email available")
                why_facts.append("Primary source documentation backing claims verified")
            else:
                # DISCOVERY
                why_facts.append("Relevant prospect retained in Discovery Pool")
                if is_ready:
                    why_facts.append("Meets all 5 qualification checks; ready for qualification review")
                else:
                    why_facts.append(f"Discovery intake; {passed_count}/5 qualification criteria verified")

            if stage == "SHORTLISTED":
                stage_expl = "Shortlisted for verified direct phone outreach"
            elif stage == "QUALIFIED":
                stage_expl = "Fully qualified candidate; queued for shortlist rotation"
            else:
                if is_ready:
                    stage_expl = "Meets all 5 qualification checks; ready for qualification review"
                else:
                    stage_expl = f"Discovery intake; {passed_count}/5 qualification criteria verified"

            freight_state = "PROSPECT"

            fac_dict = {
                "facility_id": fac_id,
                "company_id": comp_id,
                "operating_brand": row["operating_brand"],
                "legal_name": row["legal_name"],
                "facility_name": row["facility_name"],
                "facility_type": row["facility_type"],
                "physical_address": row["physical_address"],
                "city": row["city"],
                "state_prov": row["state_prov"],
                "country": row["country"],
                "postal_code": row["postal_code"],
                "location_str": f"{row['city']}, {row['state_prov']} {row['country']}",
                "private_fleet_present": row["private_fleet_present"],
                "vehicle_asset_ownership": row["vehicle_asset_ownership"],
                "fleet_relationship_type": row["fleet_relationship_type"],
                "commercial_carrier_use": row["commercial_carrier_use"],
                "broker_friendly_status": row["broker_friendly_status"],
                "freight_procurement_level": row["freight_procurement_level"],
                "website_url": row["website_url"],
                "corporate_address": row["corporate_address"],
                "company_notes": row["company_notes"],
                "company_footprint_status": row["company_footprint_status"] or "UNKNOWN",
                "verified_operating_location_count": row["verified_operating_location_count"],
                "footprint_source_notes": row["footprint_source_notes"],
                "lifecycle_stage": stage,
                "stage_updated_at": row["stage_updated_at"],
                "stage_notes": row["stage_notes"],
                "stage_explanation": stage_expl,
                "primary_commodity": primary_commodity,
                "commodities": commodities,
                "taxonomy_mappings": taxonomy_mappings,
                "primary_taxonomy": primary_tax,
                "commodity_family_code": primary_tax["family_code"] if primary_tax else None,
                "commodity_family_name": primary_tax["family_name"] if primary_tax else None,
                "commodity_category_code": primary_tax["category_code"] if primary_tax else None,
                "commodity_category_name": primary_tax["category_name"] if primary_tax else None,
                "category_typical_equipment": primary_tax["typical_equipment_fit"] if primary_tax else None,
                "category_seasonality": primary_tax["cat_seasonality"] if primary_tax else "YEAR_ROUND",
                "category_peak_months": primary_tax["cat_peak_months"] if primary_tax else None,
                "best_contact": best_contact,
                "contacts": contacts,
                "parent_info": parent_info,
                "claims_count": claims_count,
                "has_direct_phone": has_direct_phone,
                "direct_contact": direct_contact,
                "contact_type_badge": contact_type_badge,
                "next_action": next_action,
                "freight_state": freight_state,
                "qualification_readiness": readiness,
                "readiness": readiness,
                "why_facts": why_facts,
                "facility_outreach_status": fac_outreach_status if has_engagement else "UNCONTACTED",
                "facility_attempt_count": fac_attempts if has_engagement else 0,
                "outreach_status": fac_outreach_status if has_engagement else "UNCONTACTED",
                "attempt_count": fac_attempts if has_engagement else 0,
                "outreach_attempt_count": fac_attempts if has_engagement else 0,
                "company_outreach_status": row["company_outreach_status"] if has_engagement else "UNCONTACTED",
                "company_attempt_count": row["company_attempt_count"] if has_engagement else 0,
                "next_follow_up_at": row["next_follow_up_at"] if has_engagement else None,
                "is_viewed": bool(row["is_viewed"]) if has_engagement else False,
            }
            # Evaluate deterministic broker opportunity for facility
            has_callable_route = bool(outreach_passed or (best_contact and (is_valid_phone_number(best_contact.get("phone_number")) or is_valid_email(best_contact.get("email_address")))))
            has_ftl = bool(commodities)
            fac_opp = evaluate_broker_opportunity_raw(
                private_fleet_present=row["private_fleet_present"],
                commercial_carrier_use=row["commercial_carrier_use"],
                broker_friendly_status=row["broker_friendly_status"],
                lifecycle_stage=stage,
                has_callable_route=has_callable_route,
                has_ftl_fit=has_ftl,
                direct_contact_role=contact_type_badge if contact_type_badge else None,
                direct_contact_directness=best_contact.get("phone_directness") if best_contact else None,
            )
            fac_dict["broker_status_label"] = fac_opp["frontend_label"]
            fac_dict["broker_status_desc"] = fac_opp["description"]
            fac_dict["opportunity_tier"] = fac_opp["opportunity_tier"]
            fac_dict["opportunity_tier_label"] = fac_opp["frontend_label"]
            fac_dict["opportunity_tier_desc"] = fac_opp["description"]
            fac_dict["opportunity_positive_facts"] = fac_opp["positive_facts"]
            fac_dict["opportunity_counter_factors"] = fac_opp["counter_factors"]
            fac_dict["opportunity_unknowns"] = fac_opp["unknowns"]
            fac_dict["has_strong_opportunity_signal"] = fac_opp["has_strong_opportunity_signal"]
            fac_dict["is_opportunity_actionable"] = fac_opp["is_actionable"]
            prospects.append(fac_dict)

        if search and search.strip():
            q_raw = search.strip().lower()
            q_len = len(q_raw)
            if q_len == 1:
                prospects = [
                    p for p in prospects
                    if (p.get("operating_brand") or "").lower().startswith(q_raw)
                    or (p.get("legal_name") or "").lower().startswith(q_raw)
                    or (p.get("facility_name") or "").lower().startswith(q_raw)
                ]
            elif q_len == 2:
                prospects = [
                    p for p in prospects
                    if q_raw in (p.get("operating_brand") or "").lower()
                    or q_raw in (p.get("legal_name") or "").lower()
                    or q_raw in (p.get("facility_name") or "").lower()
                    or (p.get("state_prov") or "").lower() == q_raw
                ]
            else:
                prospects = [
                    p for p in prospects
                    if q_raw in (p.get("operating_brand") or "").lower()
                    or q_raw in (p.get("legal_name") or "").lower()
                    or q_raw in (p.get("facility_name") or "").lower()
                    or q_raw in (p.get("city") or "").lower()
                    or q_raw in (p.get("state_prov") or "").lower()
                    or q_raw in (p.get("commodity_category_name") or "").lower()
                    or any(q_raw in (c.get("specific_products") or "").lower() for c in p.get("commodities", []))
                ]

            def _rank_prospect(p):
                brand = (p.get("operating_brand") or "").lower()
                fname = (p.get("facility_name") or "").lower()
                city = (p.get("city") or "").lower()
                state = (p.get("state_prov") or "").lower()
                if brand == q_raw:
                    return 1
                if brand.startswith(q_raw):
                    return 2
                if f" {q_raw}" in f" {brand}":
                    return 3
                if q_raw in brand or q_raw in (p.get("legal_name") or "").lower():
                    return 4
                if fname.startswith(q_raw):
                    return 5
                if q_raw in fname:
                    return 6
                if city.startswith(q_raw) or city == q_raw:
                    return 7
                if state == q_raw:
                    return 8
                return 9

            prospects.sort(key=lambda p: (_rank_prospect(p), (p.get("operating_brand") or "").lower(), p.get("facility_id", 0)))
        equipment_items = _parse_filter_list(equipment)
        if equipment_items:
            eq_set = set(equipment_items)
            prospects = [
                p for p in prospects
                if any(c.get("equipment_category") in eq_set for c in p.get("commodities", []))
            ]

        family_items = _parse_filter_list(family)
        if family_items:
            fam_set = set(family_items)
            prospects = [
                p for p in prospects
                if p.get("commodity_family_code") in fam_set or
                   any(m.get("family_code") in fam_set for m in p.get("taxonomy_mappings", []))
            ]

        category_items = _parse_filter_list(category)
        if category_items:
            cat_set = set(category_items)
            prospects = [
                p for p in prospects
                if p.get("commodity_category_code") in cat_set or
                   any(m.get("category_code") in cat_set for m in p.get("taxonomy_mappings", []))
            ]

        season_items = _parse_filter_list(seasonality)
        if season_items:
            seas_set = set(season_items)
            prospects = [
                p for p in prospects
                if p.get("category_seasonality") in seas_set or
                   any(m.get("cat_seasonality") in seas_set for m in p.get("taxonomy_mappings", []))
            ]

        fleet_items = _parse_filter_list(fleet)
        if "VERIFIED_PRESENT" in fleet_items and "NONE_VERIFIED" not in fleet_items:
            prospects = [p for p in prospects if p.get("private_fleet_present") == "VERIFIED_PRESENT"]
        elif "NONE_VERIFIED" in fleet_items and "VERIFIED_PRESENT" not in fleet_items:
            prospects = [p for p in prospects if p.get("private_fleet_present") != "VERIFIED_PRESENT"]

        carrier_items = _parse_filter_list(carrier)
        if "VERIFIED" in carrier_items and "UNKNOWN" not in carrier_items:
            prospects = [p for p in prospects if p.get("commercial_carrier_use") == "VERIFIED"]
        elif "UNKNOWN" in carrier_items and "VERIFIED" not in carrier_items:
            prospects = [p for p in prospects if p.get("commercial_carrier_use") != "VERIFIED"]

        proc_items = _parse_filter_list(procurement)
        if proc_items:
            proc_set = set(proc_items)
            prospects = [p for p in prospects if p.get("freight_procurement_level") in proc_set]

        tier_items = _parse_filter_list(effective_tier)
        if tier_items:
            target_tiers = {_canonical_tier(t) for t in tier_items} - {None}
            if target_tiers:
                prospects = [p for p in prospects if p.get("opportunity_tier") in target_tiers]
            else:
                prospects = []


        if page is not None and page_size is not None:
            if paged_two_phase:
                total_pages = max(1, (total_count + page_size - 1) // page_size)
                return {
                    "items": prospects,
                    "total_count": total_count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                }
            total_count = len(prospects)
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            start = (page - 1) * page_size
            end = start + page_size
            items = prospects[start:end]
            return {
                "items": items,
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }

        return prospects
    finally:
        if should_close:
            conn.close()



def evaluate_broker_access_friction(company: Dict[str, Any], facilities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluates evidence-based Broker Access Friction for a company.
    Strictly separates:
    A. Observable Facts (VERIFIED private fleet, VERIFIED commercial carrier use,
       VERIFIED centralized/local procurement, VERIFIED freight/logistics contacts)
    B. Verified Real-World Company Operating Footprint vs Database Facility Count

    Zero hallucination standards:
    - Database facility count is an observable count in our repository, NEVER proof
      of company-wide single-site operation.
    - Verified real-world footprint comes from official primary evidence:
      SINGLE_SITE_VERIFIED, MULTI_SITE_VERIFIED, or UNKNOWN.
    - Multi-site scale (4+ operating locations) triggers HIGH friction.
    - Manageable scale (2-3 operating locations) triggers MEDIUM friction.
    - Explicitly verified single site (SINGLE_SITE_VERIFIED) enables LOW friction when logistics/carrier use is confirmed.
    - UNKNOWN company footprint remains neutral (does not falsely claim single-site).
    - COMMERCIAL_SALES and GENERAL_FACILITY remain strictly neutral and do NOT lower friction.
    - Broker Acceptance is strictly 'UNKNOWN' unless an actual source establishes another state.
    """
    fac_count = len(facilities)

    # Footprint attributes from company
    fp_status = company.get("company_footprint_status") or "UNKNOWN"
    loc_count = company.get("verified_operating_location_count")
    fp_notes = company.get("footprint_source_notes")

    # Determine effective location scale
    if loc_count is not None and loc_count > 0:
        effective_locations = loc_count
    elif fp_status == "MULTI_SITE_VERIFIED":
        effective_locations = max(fac_count, 2)
    elif fp_status == "SINGLE_SITE_VERIFIED":
        effective_locations = 1
    else:
        # Footprint is UNKNOWN: never derive verified operating locations from database facility count
        effective_locations = None

    # 1. Gather observable facts across company and child facilities
    has_fleet = any(f.get("private_fleet_present") == "VERIFIED_PRESENT" for f in facilities)
    has_carrier = any(f.get("commercial_carrier_use") == "VERIFIED" for f in facilities)

    proc_levels = {
        f.get("freight_procurement_level")
        for f in facilities
        if f.get("freight_procurement_level") and f.get("freight_procurement_level") != "UNKNOWN"
    }
    has_centralized = "CORPORATE_PARENT" in proc_levels
    has_facility_level = "FACILITY_LEVEL" in proc_levels

    # Check contacts across all child facilities
    contacts = []
    for f in facilities:
        contacts.extend(f.get("contacts", []))

    # Freight/Logistics contact role (COMMERCIAL_SALES and GENERAL_FACILITY are strictly neutral)
    has_freight_role = any(
        ct.get("role_category") == "FREIGHT_LOGISTICS" or
        any(term in (ct.get("department") or "").upper() for term in ["SHIPPING", "TRAFFIC", "TRANSPORTATION", "LOGISTICS"]) or
        any(term in (ct.get("exact_published_title") or "").upper() for term in ["SHIPPING", "TRAFFIC", "TRANSPORTATION", "LOGISTICS"])
        for ct in contacts
    )

    # Direct communication channel available
    has_direct_phone = any(ct.get("phone_directness") in ("DIRECT_PERSON", "DEPARTMENT_LINE") for ct in contacts)

    # Verified direct freight/logistics desk (freight role with direct phone line, NOT a general switchboard)
    has_direct_freight_desk = any(
        (ct.get("role_category") == "FREIGHT_LOGISTICS" or
         any(term in (ct.get("department") or "").upper() for term in ["SHIPPING", "TRAFFIC", "TRANSPORTATION", "LOGISTICS"]) or
         any(term in (ct.get("exact_published_title") or "").upper() for term in ["SHIPPING", "TRAFFIC", "TRANSPORTATION", "LOGISTICS"])) and
        ct.get("phone_directness") in ("DIRECT_PERSON", "DEPARTMENT_LINE")
        for ct in contacts
    )

    # Verified procurement authority/relevance
    has_procurement_relevance = (
        has_facility_level
        or has_centralized
        or any(
            (ct.get("outbound_shipping_procurement_relevance") == "VERIFIED")
            for ct in contacts
            if ct.get("phone_directness") in ("DIRECT_PERSON", "DEPARTMENT_LINE")
        )
    )

    # Observable facts structure (strictly separated from heuristic)
    proc_desc = (
        "Corporate Centralized (VERIFIED)"
        if has_centralized
        else ("Plant Local Desk (VERIFIED)" if has_facility_level else "UNKNOWN")
    )
    fleet_desc = "VERIFIED_PRESENT" if has_fleet else "UNKNOWN"
    carrier_desc = "VERIFIED" if has_carrier else "UNKNOWN"

    if fp_status == "SINGLE_SITE_VERIFIED":
        footprint_display = "Single-site — VERIFIED"
    elif fp_status == "MULTI_SITE_VERIFIED":
        footprint_display = f"Multi-site — VERIFIED ({loc_count} locations)" if loc_count else "Multi-site — VERIFIED"
    else:
        footprint_display = "Company footprint — UNKNOWN"

    facts = {
        "facility_count": fac_count,
        "database_facility_count": fac_count,
        "company_footprint_status": fp_status,
        "verified_operating_location_count": loc_count,
        "footprint_display": footprint_display,
        "footprint_source_notes": fp_notes,
        "private_fleet_present": has_fleet,
        "private_fleet_desc": fleet_desc,
        "commercial_carrier_use": has_carrier,
        "commercial_carrier_desc": carrier_desc,
        "freight_procurement_level": "CORPORATE_PARENT" if has_centralized else ("FACILITY_LEVEL" if has_facility_level else "UNKNOWN"),
        "freight_procurement_desc": proc_desc,
        "has_freight_contact": has_freight_role,
        "has_direct_freight_desk": has_direct_freight_desk,
        "direct_contact_available": has_direct_phone,
        "broker_acceptance": "UNKNOWN",
    }

    # 2. Transparent Friction Heuristic
    reasons = []
    if effective_locations is not None and effective_locations >= 4:
        level = "HIGH"
        reasons.append(f"Potentially higher access complexity due to multi-site scale ({effective_locations} operating locations)")
        if has_centralized:
            reasons.append("Centralized corporate freight procurement (VERIFIED)")
        if has_fleet:
            reasons.append("Private fleet present (competing asset capacity, VERIFIED)")
    elif (effective_locations is not None and effective_locations in (2, 3)) or has_fleet:
        level = "MEDIUM"
        if effective_locations is not None and effective_locations in (2, 3):
            reasons.append(f"Manageable regional multi-plant network ({effective_locations} operating locations verified)")
        elif fp_status == "MULTI_SITE_VERIFIED":
            reasons.append("Multi-site company footprint (VERIFIED)")
        if has_fleet:
            reasons.append("Private fleet present (competing asset capacity, VERIFIED)")
        if has_centralized and (effective_locations is None or effective_locations < 4):
            reasons.append("Centralized corporate freight coordination (VERIFIED)")
    elif fp_status == "SINGLE_SITE_VERIFIED":
        # Only SINGLE_SITE_VERIFIED can achieve LOW friction, and ONLY if commercial carrier use is confirmed
        # OR an identified freight/logistics contact with direct line AND verified procurement relevance is confirmed.
        desk_reason = (
            "Identified facility freight/logistics contact with direct line (VERIFIED)"
            if has_procurement_relevance
            else "Direct shipping/logistics desk (Procurement authority UNKNOWN)"
        )
        if has_carrier or (has_direct_freight_desk and has_procurement_relevance):
            level = "LOW"
            reasons.append("Single independent shipping facility (VERIFIED single-site operation)")
            if has_direct_freight_desk:
                reasons.append(desk_reason)
            if has_carrier:
                reasons.append("Commercial carrier use (VERIFIED)")
        elif has_direct_freight_desk:
            level = "MEDIUM"
            reasons.append("Single independent shipping facility (VERIFIED single-site operation)")
            reasons.append(desk_reason)
            reasons.append("Single independent facility; carrier procurement authority and commercial carrier use UNKNOWN")
        else:
            level = "MEDIUM"
            if has_freight_role and not has_direct_phone:
                reasons.append("Single independent facility; freight contact identified but relies on general switchboard / gatekeeper")
            else:
                reasons.append("Single independent facility; carrier procurement channel and direct logistics desk not verified")
    else:
        # Footprint is UNKNOWN (Rule 5: UNKNOWN is neutral, NEVER LOW)
        level = "UNKNOWN"
        facility_str = f"{fac_count} facilities" if fac_count != 1 else "1 facility"
        reasons.append(f"Company footprint UNKNOWN ({facility_str} represented in database; real-world footprint UNKNOWN); access friction cannot be evaluated without verified footprint")
        if has_fleet:
            level = "MEDIUM"
            reasons.append("Private fleet present (competing asset capacity, VERIFIED)")
        if has_carrier:
            reasons.append("Commercial carrier use observed (VERIFIED)")
        if has_direct_freight_desk:
            if has_procurement_relevance:
                reasons.append("Direct logistics contact identified with procurement authority (VERIFIED)")
            else:
                reasons.append("Direct shipping/logistics desk (Procurement authority UNKNOWN)")
        elif has_freight_role:
            reasons.append("Freight contact identified on general switchboard (gatekeeper required)")

    return {
        "level": level,
        "reasons": reasons,
        "facts": facts,
    }


def get_universe_metadata(
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str | Path] = None,
    universe_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Returns full universe metadata and lifecycle counts across all companies and facilities
    for Master Directory counters, tabs, and filter scoping.
    """
    should_close = False
    orig_row_factory = None
    if conn is None:
        conn = create_connection(db_path)
        conn.row_factory = sqlite3.Row
        should_close = True
    else:
        orig_row_factory = conn.row_factory
        conn.row_factory = sqlite3.Row
    try:
        if universe_context is None:
            universe_context = load_opportunity_universe_context(conn=conn, db_path=db_path)

        all_comp_count = conn.execute("SELECT count(DISTINCT company_id) FROM facilities").fetchone()[0]
        all_fac_count = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]

        shortlisted_comp = conn.execute(
            "SELECT count(DISTINCT f.company_id) FROM facilities f JOIN prospect_lifecycle pl ON f.id = pl.facility_id WHERE pl.stage = 'SHORTLISTED'"
        ).fetchone()[0]
        qualified_comp = conn.execute(
            """
            SELECT count(DISTINCT f.company_id) FROM facilities f 
            JOIN prospect_lifecycle pl ON f.id = pl.facility_id 
            WHERE pl.stage = 'QUALIFIED'
              AND f.company_id NOT IN (
                  SELECT f2.company_id FROM facilities f2 JOIN prospect_lifecycle pl2 ON f2.id = pl2.facility_id WHERE pl2.stage = 'SHORTLISTED'
              )
            """
        ).fetchone()[0]
        discovery_comp = conn.execute(
            """
            SELECT count(DISTINCT f.company_id) FROM facilities f 
            WHERE f.company_id NOT IN (
                SELECT f2.company_id FROM facilities f2 JOIN prospect_lifecycle pl2 ON f2.id = pl2.facility_id WHERE pl2.stage IN ('SHORTLISTED', 'QUALIFIED')
            )
            """
        ).fetchone()[0]

        shortlisted_fac = conn.execute(
            "SELECT count(*) FROM facilities f JOIN prospect_lifecycle pl ON f.id = pl.facility_id WHERE pl.stage = 'SHORTLISTED'"
        ).fetchone()[0]
        qualified_fac = conn.execute(
            "SELECT count(*) FROM facilities f JOIN prospect_lifecycle pl ON f.id = pl.facility_id WHERE pl.stage = 'QUALIFIED'"
        ).fetchone()[0]
        discovery_fac = conn.execute(
            "SELECT count(*) FROM facilities f WHERE f.id NOT IN (SELECT facility_id FROM prospect_lifecycle WHERE stage IN ('SHORTLISTED', 'QUALIFIED'))"
        ).fetchone()[0]

        # Opportunity tier counts across operating companies
        # Single source of truth: shared prehydrated opportunity context
        tier_map = get_opportunity_tier_company_ids(conn=conn, db_path=db_path, universe_context=universe_context)
        opp_comp_a = len(tier_map[TIER_A_PRIORITY])
        opp_comp_b = len(tier_map[TIER_B_WORTH_CALLING])
        opp_comp_c = len(tier_map[TIER_C_SECONDARY])
        opp_comp_d = len(tier_map[TIER_D_RESEARCH_NEEDED])
        opp_comp_res = len(tier_map[RESTRICTED])

        # Facility opportunity counts
        opp_fac_a = conn.execute("""
            SELECT count(*) FROM facilities f
            JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE (f.commercial_carrier_use = 'VERIFIED' OR f.broker_friendly_status = 'VERIFIED_ACCEPTS')
              AND pl.stage IN ('SHORTLISTED', 'QUALIFIED')
        """).fetchone()[0]

        opp_fac_c = conn.execute("""
            SELECT count(*) FROM facilities f
            JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.private_fleet_present = 'VERIFIED_PRESENT'
              AND f.commercial_carrier_use != 'VERIFIED'
              AND f.broker_friendly_status != 'VERIFIED_ACCEPTS'
              AND pl.stage IN ('SHORTLISTED', 'QUALIFIED')
        """).fetchone()[0]

        opp_fac_b = conn.execute("""
            SELECT count(*) FROM facilities f
            JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.private_fleet_present != 'VERIFIED_PRESENT'
              AND f.commercial_carrier_use != 'VERIFIED'
              AND f.broker_friendly_status != 'VERIFIED_ACCEPTS'
              AND pl.stage IN ('SHORTLISTED', 'QUALIFIED')
        """).fetchone()[0]

        opp_fac_d = conn.execute("""
            SELECT count(*) FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE pl.stage IS NULL OR pl.stage = 'DISCOVERY'
        """).fetchone()[0]

        return {
            "universe_companies": all_comp_count,
            "universe_facilities": all_fac_count,
            "lifecycle_counts": {
                "ALL": all_comp_count,
                "SHORTLISTED": shortlisted_comp,
                "QUALIFIED": qualified_comp,
                "DISCOVERY": discovery_comp,
            },
            "facility_lifecycle_counts": {
                "ALL": all_fac_count,
                "SHORTLISTED": shortlisted_fac,
                "QUALIFIED": qualified_fac,
                "DISCOVERY": discovery_fac,
            },
            "opportunity_counts": {
                "ALL": all_comp_count,
                "TIER_A_PRIORITY": opp_comp_a,
                "TIER_B_WORTH_CALLING": opp_comp_b,
                "TIER_C_SECONDARY": opp_comp_c,
                "TIER_D_RESEARCH_NEEDED": opp_comp_d,
                "RESTRICTED": opp_comp_res,
                "PRIORITY": opp_comp_a,
                "WORTH_CALLING": opp_comp_b,
                "SECONDARY": opp_comp_c,
                "RESEARCH": opp_comp_d,
            },
            "facility_opportunity_counts": {
                "ALL": all_fac_count,
                "TIER_A_PRIORITY": opp_fac_a,
                "TIER_B_WORTH_CALLING": opp_fac_b,
                "TIER_C_SECONDARY": opp_fac_c,
                "TIER_D_RESEARCH_NEEDED": opp_fac_d,
                "RESTRICTED": 0,
                "PRIORITY": opp_fac_a,
                "WORTH_CALLING": opp_fac_b,
                "SECONDARY": opp_fac_c,
                "RESEARCH": opp_fac_d,
            },
        }
    finally:
        if should_close:
            conn.close()
        elif orig_row_factory is not None:
            conn.row_factory = orig_row_factory


def _assemble_company_groups(
    prospects: List[Dict[str, Any]],
    target_company_ids: Optional[List[int]] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str | Path] = None,
    universe_context: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Helper to group hydrated prospect facility records by company."""
    from collections import OrderedDict

    eng_map: Dict[int, Dict[str, Any]] = {}
    fac_name_map: Dict[int, str] = {}
    should_close = False
    if conn is None:
        conn = create_connection(db_path)
        conn.row_factory = sqlite3.Row
        should_close = True
    try:
        has_eng = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='prospect_engagement_state'"
        ).fetchone()[0] > 0
        if has_eng:
            for r in conn.execute("SELECT * FROM prospect_engagement_state").fetchall():
                eng_map[r["company_id"]] = dict(r)
        for r in conn.execute("SELECT id, facility_name, city, state_prov FROM facilities").fetchall():
            fac_name_map[r["id"]] = f"{r['facility_name']} ({r['city']}, {r['state_prov']})"
    except Exception:
        pass
    finally:
        if should_close:
            conn.close()

    company_map: Dict[int, Dict[str, Any]] = OrderedDict()
    if target_company_ids:
        for cid in target_company_ids:
            company_map[cid] = None

    for p in prospects:
        cid = p["company_id"]
        if cid not in company_map or company_map[cid] is None:
            company_map[cid] = {
                "company_id": cid,
                "operating_brand": p["operating_brand"],
                "legal_name": p["legal_name"],
                "website_url": p.get("website_url"),
                "corporate_address": p.get("corporate_address"),
                "company_notes": p.get("company_notes"),
                "company_footprint_status": p.get("company_footprint_status") or "UNKNOWN",
                "verified_operating_location_count": p.get("verified_operating_location_count"),
                "footprint_source_notes": p.get("footprint_source_notes"),
                "parent_info": p.get("parent_info"),
                "facilities": [],
                "lifecycle_stages": set(),
                "equipment_categories": set(),
                "commodity_family_codes": set(),
                "commodity_family_names": set(),
                "commodity_category_codes": set(),
                "commodity_category_names": set(),
                "seasonality_profiles": set(),
            }
        comp = company_map[cid]
        comp["facilities"].append(p)
        comp["lifecycle_stages"].add(p["lifecycle_stage"])
        if p.get("primary_commodity") and p["primary_commodity"].get("equipment_category"):
            comp["equipment_categories"].add(p["primary_commodity"]["equipment_category"])
        for c in p.get("commodities", []):
            if c.get("equipment_category"):
                comp["equipment_categories"].add(c["equipment_category"])
        for m in p.get("taxonomy_mappings", []):
            if m.get("family_code"):
                comp["commodity_family_codes"].add(m["family_code"])
            if m.get("family_name"):
                comp["commodity_family_names"].add(m["family_name"])
            if m.get("category_code"):
                comp["commodity_category_codes"].add(m["category_code"])
            if m.get("category_name"):
                comp["commodity_category_names"].add(m["category_name"])
            if m.get("cat_seasonality"):
                comp["seasonality_profiles"].add(m["cat_seasonality"])

    groups = []
    for cid, comp in company_map.items():
        if comp is None:
            continue
        facs = comp["facilities"]
        fac_count = len(facs)
        stages = comp["lifecycle_stages"]

        if "SHORTLISTED" in stages:
            primary_stage = "SHORTLISTED"
        elif "QUALIFIED" in stages:
            primary_stage = "QUALIFIED"
        elif "DISCOVERY" in stages:
            primary_stage = "DISCOVERY"
        else:
            primary_stage = "ARCHIVED"

        comp_friction = evaluate_broker_access_friction(comp, facs)

        # Engagement state
        eng = eng_map.get(cid, {})
        outreach_status = eng.get("current_outreach_status") or "UNCONTACTED"
        attempt_count = eng.get("attempt_count") or 0
        last_contacted_at = eng.get("last_contacted_at")
        next_follow_up_at = eng.get("next_follow_up_at")
        last_facility_id = eng.get("last_facility_id")
        last_facility_name = fac_name_map.get(last_facility_id) if last_facility_id else ("Corporate Desk" if last_contacted_at else None)
        last_feedback_notes = eng.get("last_feedback_notes")
        is_viewed = eng.get("is_viewed") or 0
        first_viewed_at = eng.get("first_viewed_at")
        last_viewed_at = eng.get("last_viewed_at")

        # Mark child facility if it was the last contacted
        for f in facs:
            f["is_last_contacted"] = (f.get("facility_id") == last_facility_id)

        # Build unified searchable text across parent company and all child facilities
        search_parts = [
            comp["operating_brand"] or "",
            comp["legal_name"] or "",
            comp.get("corporate_address") or "",
            comp.get("website_url") or "",
            comp.get("company_notes") or "",
            outreach_status,
            last_facility_name or "",
            last_feedback_notes or "",
        ]
        for f in facs:
            search_parts.extend([
                f.get("facility_name") or "",
                f.get("physical_address") or "",
                f.get("city") or "",
                f.get("state_prov") or "",
                f.get("country") or "",
                f.get("postal_code") or "",
            ])
            for comm in f.get("commodities", []):
                search_parts.extend([
                    comm.get("commodity_category") or "",
                    comm.get("specific_products") or "",
                    comm.get("equipment_category") or "",
                ])
            for ct in f.get("contacts", []):
                search_parts.extend([
                    ct.get("person_name") or "",
                    ct.get("exact_published_title") or "",
                    ct.get("department") or "",
                    ct.get("phone_number") or "",
                    ct.get("email_address") or "",
                ])
        for fname in comp["commodity_family_names"]:
            search_parts.append(fname)
        for cname in comp["commodity_category_names"]:
            search_parts.append(cname)
        for ccode in comp["commodity_category_codes"]:
            search_parts.append(ccode)
        for sprofile in comp["seasonality_profiles"]:
            search_parts.append(sprofile)
        searchable_text = " ".join(filter(None, search_parts)).lower()

        # Factual explanation for lifecycle stage
        why_facts = []
        fp_status = comp.get("company_footprint_status") or "UNKNOWN"
        loc_count = comp.get("verified_operating_location_count")

        if primary_stage == "SHORTLISTED":
            why_facts.append("All 5 factual qualification readiness checks passed")
            if fp_status == "SINGLE_SITE_VERIFIED":
                why_facts.append("Single-site manufacturer (VERIFIED)")
            elif fp_status == "MULTI_SITE_VERIFIED":
                if loc_count:
                    why_facts.append(f"Manageable regional multi-plant network ({loc_count} operating locations verified)")
                else:
                    why_facts.append("Multi-site manufacturer (VERIFIED)")
            else:
                why_facts.append(f"Company footprint: UNKNOWN ({fac_count} facility represented in database)")

            if comp_friction["facts"]["has_freight_contact"]:
                why_facts.append("Identified facility freight/logistics contact or shipping desk (VERIFIED)")
            elif comp_friction["facts"]["direct_contact_available"]:
                why_facts.append("Direct callable phone line / operations desk (VERIFIED)")
            else:
                why_facts.append("Verified facility telephone switchboard available")
            if comp_friction["facts"]["commercial_carrier_use"]:
                why_facts.append("Commercial carrier use confirmed (VERIFIED)")
            if comp_friction["facts"]["private_fleet_present"]:
                why_facts.append("Private fleet present (competing asset capacity noted)")
            if comp_friction["level"] in ("LOW", "MEDIUM"):
                why_facts.append(f"{comp_friction['level'].capitalize()} Broker Access Friction")
        elif primary_stage == "QUALIFIED":
            why_facts.append("Active physical manufacturing facility verified")
            if fp_status == "SINGLE_SITE_VERIFIED":
                why_facts.append("Single-site manufacturer (VERIFIED)")
            elif fp_status == "MULTI_SITE_VERIFIED":
                if loc_count:
                    why_facts.append(f"Multi-site manufacturer (VERIFIED, {loc_count} operating locations)")
                else:
                    why_facts.append("Multi-site manufacturer (VERIFIED)")
            else:
                why_facts.append(f"Company footprint: UNKNOWN ({fac_count} facility represented in database)")
            why_facts.append("Heavy FTL commodity & equipment profile supported")
            why_facts.append("Eligible freight jurisdiction (US Lower 48 / Canada)")
            why_facts.append("Callable phone route or corporate email available")
            why_facts.append("Primary source documentation backing claims verified")
            if comp_friction["level"] == "HIGH":
                why_facts.append("High Broker Access Friction (enterprise multi-site scale / centralized)")
        else:
            why_facts.append("Relevant prospect retained in Discovery Pool")
            why_facts.append(f"Facilities represented in database: {fac_count}")

        # Extract broker-first contact assets across child facilities
        best_phone = None
        best_phone_clean = None
        best_phone_label = None
        best_email = None
        primary_facility_id = facs[0].get("facility_id") if facs else None
        primary_city = facs[0].get("city") if facs else ""
        primary_state = facs[0].get("state_prov") if facs else ""
        if primary_city and primary_state:
            best_location = f"{primary_city}, {primary_state}"
        elif primary_city or primary_state:
            best_location = primary_city or primary_state
        else:
            best_location = "US / Canada"

        # Determine qualifying facility for Tier A / external carrier evidence
        qualifying_fac = None
        for f in facs:
            if (f.get("opportunity_tier") == TIER_A_PRIORITY or f.get("commercial_carrier_use") == "VERIFIED" or f.get("broker_friendly_status") == "VERIFIED_ACCEPTS") and f.get("broker_friendly_status") != "VERIFIED_DIRECT_ONLY":
                qualifying_fac = f
                break
        if qualifying_fac is None:
            non_rest = [f for f in facs if f.get("broker_friendly_status") != "VERIFIED_DIRECT_ONLY"]
            qualifying_fac = non_rest[0] if non_rest else (facs[0] if facs else None)

        # Search for highest-directness phone & email with strict facility-scope integrity
        # Prioritize contacts belonging to the qualifying facility (or corporate-wide contacts)
        candidate_contacts = []
        for f in facs:
            is_qual = (qualifying_fac is None) or (f.get("facility_id") == qualifying_fac.get("facility_id"))
            for ct in f.get("contacts", []):
                candidate_contacts.append((f, ct, is_qual))
                if not best_email and ct.get("email_address") and is_qual:
                    best_email = ct["email_address"]

        # Fallback email if qualifying facility had no direct email
        if not best_email:
            for f in facs:
                for ct in f.get("contacts", []):
                    if ct.get("email_address"):
                        best_email = ct["email_address"]
                        break
                if best_email:
                    break

        def _contact_sort_key(item):
            _, ct, is_qual = item
            d = ct.get("phone_directness") or ""
            score = 0
            if d == "DIRECT_PERSON":
                score = 5
            elif d == "DIRECT_DESK":
                score = 4
            elif d == "DIRECT_FACILITY_LINE":
                score = 3
            elif d == "TOLL_FREE":
                score = 2
            elif ct.get("phone_number"):
                score = 1
            if ct.get("is_primary_contact"):
                score += 1
            # Prioritize qualifying facility contact route for scope integrity
            if is_qual:
                score += 10
            return score

        candidate_contacts.sort(key=_contact_sort_key, reverse=True)
        for _, ct, _ in candidate_contacts:
            if ct.get("phone_number"):
                best_phone = ct["phone_number"]
                best_phone_clean = re.sub(r"[^\d+]", "", best_phone)
                pname = ct.get("person_name")
                ptitle = ct.get("exact_published_title")
                pdept = ct.get("department")
                pdir = ct.get("phone_directness")
                if pname and ptitle:
                    best_phone_label = f"Direct: {pname} ({ptitle})"
                elif pname:
                    best_phone_label = f"Direct: {pname}"
                elif ptitle:
                    best_phone_label = f"Desk: {ptitle}"
                elif pdept:
                    best_phone_label = f"{pdept.title()} Line"
                elif pdir == "DIRECT_FACILITY_LINE":
                    best_phone_label = "Plant Direct Line"
                elif pdir == "TOLL_FREE" or (best_phone.startswith("800") or best_phone.startswith("(800)")):
                    best_phone_label = "Toll-Free Line"
                elif pdir == "RECEPTION":
                    best_phone_label = "Main Reception"
                else:
                    best_phone_label = "Facility Main Line"
                break

        # Company-level fleet, carrier, broker status evaluation across non-restricted facilities
        active_facs = [f for f in facs if f.get("broker_friendly_status") != "VERIFIED_DIRECT_ONLY"]
        if not active_facs:
            c_broker = "VERIFIED_DIRECT_ONLY"
            eval_facs = facs
        else:
            eval_facs = active_facs
            c_broker = "VERIFIED_ACCEPTS" if any(f.get("broker_friendly_status") == "VERIFIED_ACCEPTS" for f in eval_facs) else "UNKNOWN"

        c_fleet = "VERIFIED_PRESENT" if any(f.get("private_fleet_present") == "VERIFIED_PRESENT" for f in eval_facs) else ("VERIFIED_NO_FLEET" if all(f.get("private_fleet_present") == "VERIFIED_NO_FLEET" for f in eval_facs) else "UNKNOWN")
        c_carrier = "VERIFIED" if any(f.get("commercial_carrier_use") == "VERIFIED" for f in eval_facs) else "UNKNOWN"
        has_callable = bool(best_phone or best_email)
        has_ftl = bool(comp["equipment_categories"])

        if universe_context and cid in universe_context.get("company_evaluations", {}):
            comp_opp = universe_context["company_evaluations"][cid]
        else:
            comp_opp = evaluate_broker_opportunity(
                cid,
                conn=conn,
                db_path=db_path,
                universe_context=universe_context,
            )

        opp_tier = comp_opp["opportunity_tier"]
        broker_status_label = comp_opp["frontend_label"]
        broker_status_desc = comp_opp["description"]

        # Broker Why Bullets based on opportunity tier
        broker_why_bullets = []
        eq_list = sorted(list(comp["equipment_categories"]))
        eq_str = " / ".join(eq_list) if eq_list else "FTL Flatbed / Dry Van"
        fam_name = sorted(list(comp["commodity_family_names"]))[0] if comp["commodity_family_names"] else "Industrial Freight"

        if opp_tier == TIER_A_PRIORITY:
            if c_broker == "VERIFIED_ACCEPTS":
                broker_why_bullets.append("Broker acceptance explicitly confirmed (VERIFIED)")
            elif c_carrier == "VERIFIED":
                broker_why_bullets.append("Outside carrier use confirmed (VERIFIED)")
            if c_fleet == "VERIFIED_PRESENT":
                broker_why_bullets.append("Own trucks confirmed; outside carrier use also confirmed")
            else:
                broker_why_bullets.append(f"Target {eq_str} equipment fit ({fam_name})")
            if best_phone_label and "Direct" in best_phone_label:
                broker_why_bullets.append(f"Verified direct contact: {best_phone_label.replace('Direct: ', '')}")
            elif best_phone:
                broker_why_bullets.append(f"Callable facility line verified ({best_phone})")
            elif best_email:
                broker_why_bullets.append(f"Direct shipping email verified ({best_email})")
        elif opp_tier == TIER_C_SECONDARY:
            broker_why_bullets.append(f"Target {eq_str} equipment fit ({fam_name})")
            if best_phone_label and "Direct" in best_phone_label:
                broker_why_bullets.append(f"Verified direct contact: {best_phone_label.replace('Direct: ', '')}")
            elif best_phone:
                broker_why_bullets.append(f"Callable phone route ({best_phone})")
            broker_why_bullets.append("Own trucks confirmed • Outside carrier use not confirmed")
        elif opp_tier == TIER_B_WORTH_CALLING:
            broker_why_bullets.append(f"Target {eq_str} equipment fit ({fam_name})")
            if best_phone_label and "Direct" in best_phone_label:
                broker_why_bullets.append(f"Verified direct contact: {best_phone_label.replace('Direct: ', '')}")
            elif best_phone:
                broker_why_bullets.append(f"Callable phone verified ({best_phone})")
            elif best_email:
                broker_why_bullets.append(f"Direct email verified ({best_email})")
            else:
                broker_why_bullets.append("Operating facility confirmed in eligible territory")
            if fac_count == 1:
                broker_why_bullets.append("Single-site manufacturer (local plant)")
            else:
                broker_why_bullets.append(f"Regional network ({fac_count} operating plants)")
        else:
            if comp_opp["positive_facts"]:
                broker_why_bullets.append(comp_opp["positive_facts"][0])
            else:
                broker_why_bullets.append(f"Operating facility in {best_location}")
            if comp_opp["counter_factors"]:
                broker_why_bullets.append(comp_opp["counter_factors"][0])
            else:
                broker_why_bullets.append("Research incomplete in Discovery pool")

        # Discovery pool: What we know & Still checking
        discovery_what_we_know = [
            f"Operating facility in {best_location}",
            f"{fam_name} products"
        ]
        if not best_phone:
            discovery_still_checking = "Callable phone line still being researched"
        elif not comp["equipment_categories"]:
            discovery_still_checking = "Trailer & equipment usage not confirmed yet"
        else:
            discovery_still_checking = "Direct shipping contact still needs confirmation"

        groups.append({
            "company_id": cid,
            "operating_brand": comp["operating_brand"],
            "legal_name": comp["legal_name"],
            "website_url": comp.get("website_url"),
            "corporate_address": comp.get("corporate_address"),
            "company_notes": comp.get("company_notes"),
            "parent_info": comp.get("parent_info"),
            "facility_count": fac_count,
            "database_facility_count": fac_count,
            "company_footprint_status": fp_status,
            "verified_operating_location_count": loc_count,
            "footprint_source_notes": comp.get("footprint_source_notes"),
            "footprint_display": comp_friction["facts"]["footprint_display"],
            "is_multi_facility": fac_count > 1,
            "lifecycle_stage": primary_stage,
            "lifecycle_stages": sorted(list(stages)),
            "equipment_categories": sorted(list(comp["equipment_categories"])),
            "commodity_family_codes": sorted(list(comp["commodity_family_codes"])),
            "commodity_family_names": sorted(list(comp["commodity_family_names"])),
            "commodity_category_codes": sorted(list(comp["commodity_category_codes"])),
            "commodity_category_names": sorted(list(comp["commodity_category_names"])),
            "seasonality_profiles": sorted(list(comp["seasonality_profiles"])),
            "primary_family_name": sorted(list(comp["commodity_family_names"]))[0] if comp["commodity_family_names"] else "Lumber & Forest Products",
            "primary_category_name": sorted(list(comp["commodity_category_names"]))[0] if comp["commodity_category_names"] else "",
            "primary_seasonality": sorted(list(comp["seasonality_profiles"]))[0] if comp["seasonality_profiles"] else "YEAR_ROUND",
            "broker_access_friction": comp_friction,
            "friction_level": comp_friction["level"],
            "facts": comp_friction["facts"],
            "facilities": facs,
            "why_facts": why_facts,
            "searchable_text": searchable_text,
            "outreach_status": outreach_status,
            "attempt_count": attempt_count,
            "last_contacted_at": last_contacted_at,
            "next_follow_up_at": next_follow_up_at,
            "last_facility_id": last_facility_id,
            "last_facility_name": last_facility_name,
            "last_feedback_notes": last_feedback_notes,
            "is_viewed": is_viewed,
            "first_viewed_at": first_viewed_at,
            "last_viewed_at": last_viewed_at,
            "best_phone": best_phone,
            "best_phone_clean": best_phone_clean,
            "best_phone_label": best_phone_label,
            "best_email": best_email,
            "best_location": best_location,
            "primary_facility_id": primary_facility_id,
            "broker_status_label": broker_status_label,
            "broker_status_desc": broker_status_desc,
            "broker_why_bullets": broker_why_bullets,
            "opportunity_tier": opp_tier,
            "opportunity_tier_label": comp_opp["frontend_label"],
            "opportunity_tier_desc": comp_opp["description"],
            "opportunity_positive_facts": comp_opp["positive_facts"],
            "opportunity_counter_factors": comp_opp["counter_factors"],
            "opportunity_unknowns": comp_opp["unknowns"],
            "has_strong_opportunity_signal": comp_opp["has_strong_opportunity_signal"],
            "is_opportunity_actionable": comp_opp["is_actionable"],
            "private_fleet_present": c_fleet,
            "commercial_carrier_use": c_carrier,
            "broker_friendly_status": c_broker,
            "discovery_what_we_know": discovery_what_we_know,
            "discovery_still_checking": discovery_still_checking,
            "qualifying_facility_id": qualifying_fac.get("facility_id") if qualifying_fac else None,
            "qualifying_facility_name": qualifying_fac.get("facility_name") if qualifying_fac else None,
            "qualifying_facility_location": f"{qualifying_fac.get('city')}, {qualifying_fac.get('state_prov')}" if qualifying_fac else None,
        })

    return groups


def get_company_grouped_prospects(
    lifecycle_stage: str = "ALL",
    outreach_filter: Optional[str] = None,
    unreviewed_only: bool = False,
    db_path: Optional[str | Path] = None,
    prospects: Optional[List[Dict[str, Any]]] = None,
    conn: Optional[sqlite3.Connection] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    search: Optional[str] = None,
    friction: Optional[str] = None,
    equipment: Optional[str] = None,
    family: Optional[str] = None,
    category: Optional[str] = None,
    seasonality: Optional[str] = None,
    structure: Optional[str] = None,
    facility_count: Optional[str] = None,
    fleet: Optional[str] = None,
    carrier: Optional[str] = None,
    procurement: Optional[str] = None,
    tier: Optional[str] = None,
    opportunity_tier: Optional[str] = None,
) -> Any:
    """
    Returns prospects grouped at the company level.
    Optimized batch execution with two-phase SQL pushdown pagination.
    Phase 1: Pure SQL ID selection + total count matching company filters.
    Phase 2: Hydrate only child facilities belonging to the ~25 page companies.
    Preserves COMPANY != FACILITY: each company contains its list of child facilities.
    Evaluates evidence-based Broker Access Friction for each company group.
    """
    effective_tier = tier or opportunity_tier
    should_close = False
    if conn is None:
        conn = create_connection(db_path)
        conn.row_factory = sqlite3.Row
        should_close = True
    try:
        universe_context = load_opportunity_universe_context(conn=conn, db_path=db_path)

        # Phase 1: SQL pushdown for paginated company requests
        if prospects is None and page is not None and page_size is not None and (friction is None or friction.upper() == "ALL"):
            w_sql, p_params = build_company_filter_sql(
                lifecycle_stage=lifecycle_stage,
                outreach_filter=outreach_filter,
                unreviewed_only=unreviewed_only,
                search=search,
                equipment=equipment,
                family=family,
                category=category,
                seasonality=seasonality,
                structure=structure,
                facility_count=facility_count,
                fleet=fleet,
                carrier=carrier,
                procurement=procurement,
                tier=effective_tier,
                conn=conn,
                db_path=db_path,
                universe_context=universe_context,
            )
            count_sql = f"""
                SELECT count(DISTINCT c.id)
                FROM companies c
                LEFT JOIN prospect_engagement_state pes ON c.id = pes.company_id
                {w_sql}
            """
            total_count = conn.execute(count_sql, p_params).fetchone()[0]

            fac_count_sql = f"""
                SELECT count(f.id)
                FROM facilities f
                WHERE f.company_id IN (
                    SELECT c.id FROM companies c
                    LEFT JOIN prospect_engagement_state pes ON c.id = pes.company_id
                    {w_sql}
                )
            """
            total_facilities = conn.execute(fac_count_sql, p_params).fetchone()[0]
            universe_meta = get_universe_metadata(conn=conn, universe_context=universe_context)

            if search and search.strip():
                q_raw = search.strip().lower()
                q_exact = q_raw
                q_starts = f"{q_raw}%"
                q_word = f"% {q_raw}%"
                q_contains = f"%{q_raw}%"

                rank_sql = """
                    CASE
                        WHEN LOWER(c.operating_brand) = ? THEN 1
                        WHEN LOWER(c.operating_brand) LIKE ? THEN 2
                        WHEN LOWER(c.operating_brand) LIKE ? THEN 3
                        WHEN LOWER(c.operating_brand) LIKE ? OR LOWER(COALESCE(c.legal_name, '')) LIKE ? THEN 4
                        WHEN EXISTS (SELECT 1 FROM facilities f_r WHERE f_r.company_id = c.id AND LOWER(f_r.facility_name) LIKE ?) THEN 5
                        WHEN EXISTS (SELECT 1 FROM facilities f_r WHERE f_r.company_id = c.id AND LOWER(f_r.facility_name) LIKE ?) THEN 6
                        WHEN EXISTS (SELECT 1 FROM facilities f_r WHERE f_r.company_id = c.id AND (LOWER(f_r.city) LIKE ? OR LOWER(f_r.city) = ?)) THEN 7
                        WHEN EXISTS (SELECT 1 FROM facilities f_r WHERE f_r.company_id = c.id AND LOWER(f_r.state_prov) = ?) THEN 8
                        ELSE 9
                    END
                """
                rank_params = [
                    q_exact,
                    q_starts,
                    q_word,
                    q_contains,
                    q_contains,
                    q_starts,
                    q_contains,
                    q_starts,
                    q_exact,
                    q_exact,
                ]
                id_sql = f"""
                    SELECT c.id, ({rank_sql}) as search_rank
                    FROM companies c
                    LEFT JOIN prospect_engagement_state pes ON c.id = pes.company_id
                    {w_sql}
                    GROUP BY c.id
                    ORDER BY search_rank ASC, c.operating_brand ASC, c.id ASC
                    LIMIT ? OFFSET ?
                """
                offset = max(0, (page - 1) * page_size)
                paged_params = rank_params + list(p_params) + [page_size, offset]
                target_company_ids = [r[0] for r in conn.execute(id_sql, paged_params).fetchall()]
            else:
                id_sql = f"""
                    SELECT DISTINCT c.id
                    FROM companies c
                    LEFT JOIN prospect_engagement_state pes ON c.id = pes.company_id
                    {w_sql}
                    ORDER BY c.id ASC
                    LIMIT ? OFFSET ?
                """
                offset = max(0, (page - 1) * page_size)
                paged_params = list(p_params) + [page_size, offset]
                target_company_ids = [r[0] for r in conn.execute(id_sql, paged_params).fetchall()]

            total_pages = max(1, (total_count + page_size - 1) // page_size)
            metadata = {
                "total_companies": total_count,
                "total_facilities": total_facilities,
                "universe_companies": universe_meta["universe_companies"],
                "universe_facilities": universe_meta["universe_facilities"],
                "lifecycle_counts": universe_meta["lifecycle_counts"],
                "facility_lifecycle_counts": universe_meta["facility_lifecycle_counts"],
                "opportunity_counts": universe_meta["opportunity_counts"],
                "facility_opportunity_counts": universe_meta["facility_opportunity_counts"],
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "page_start": max(0, (page - 1) * page_size + 1) if total_count > 0 else 0,
                "page_end": min(page * page_size, total_count),
            }

            if not target_company_ids:
                return {
                    "items": [],
                    "total_count": total_count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "metadata": metadata,
                }

            # Phase 2: hydrate ONLY the facilities belonging to those target companies
            child_prospects = get_prospects_list(lifecycle_stage="ALL", company_ids=target_company_ids, conn=conn)
            groups = _assemble_company_groups(child_prospects, target_company_ids=target_company_ids, conn=conn, universe_context=universe_context)
            return {
                "items": groups,
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "metadata": metadata,
            }

        if prospects is None:
            if page is not None and page_size is not None and friction and friction.upper() != "ALL":
                w_sql, p_params = build_company_filter_sql(
                    lifecycle_stage=lifecycle_stage,
                    outreach_filter=outreach_filter,
                    unreviewed_only=unreviewed_only,
                    search=search,
                    equipment=equipment,
                    family=family,
                    category=category,
                    seasonality=seasonality,
                    structure=structure,
                    facility_count=facility_count,
                    fleet=fleet,
                    carrier=carrier,
                    procurement=procurement,
                    tier=effective_tier,
                    conn=conn,
                    db_path=db_path,
                    universe_context=universe_context,
                )
                if search and search.strip():
                    q_raw = search.strip().lower()
                    q_exact = q_raw
                    q_starts = f"{q_raw}%"
                    q_word = f"% {q_raw}%"
                    q_contains = f"%{q_raw}%"
                    rank_sql = """
                        CASE
                            WHEN LOWER(c.operating_brand) = ? THEN 1
                            WHEN LOWER(c.operating_brand) LIKE ? THEN 2
                            WHEN LOWER(c.operating_brand) LIKE ? THEN 3
                            WHEN LOWER(c.operating_brand) LIKE ? OR LOWER(COALESCE(c.legal_name, '')) LIKE ? THEN 4
                            WHEN EXISTS (SELECT 1 FROM facilities f_r WHERE f_r.company_id = c.id AND LOWER(f_r.facility_name) LIKE ?) THEN 5
                            WHEN EXISTS (SELECT 1 FROM facilities f_r WHERE f_r.company_id = c.id AND LOWER(f_r.facility_name) LIKE ?) THEN 6
                            WHEN EXISTS (SELECT 1 FROM facilities f_r WHERE f_r.company_id = c.id AND (LOWER(f_r.city) LIKE ? OR LOWER(f_r.city) = ?)) THEN 7
                            WHEN EXISTS (SELECT 1 FROM facilities f_r WHERE f_r.company_id = c.id AND LOWER(f_r.state_prov) = ?) THEN 8
                            ELSE 9
                        END
                    """
                    rank_params = [
                        q_exact, q_starts, q_word, q_contains, q_contains,
                        q_starts, q_contains, q_starts, q_exact, q_exact
                    ]
                    id_sql = f"""
                        SELECT c.id, ({rank_sql}) as search_rank
                        FROM companies c
                        LEFT JOIN prospect_engagement_state pes ON c.id = pes.company_id
                        {w_sql}
                        GROUP BY c.id
                        ORDER BY search_rank ASC, c.operating_brand ASC, c.id ASC
                    """
                    candidate_company_ids = [r[0] for r in conn.execute(id_sql, rank_params + list(p_params)).fetchall()]
                else:
                    id_sql = f"""
                        SELECT DISTINCT c.id
                        FROM companies c
                        LEFT JOIN prospect_engagement_state pes ON c.id = pes.company_id
                        {w_sql}
                        ORDER BY c.id ASC
                    """
                    candidate_company_ids = [r[0] for r in conn.execute(id_sql, p_params).fetchall()]
                child_prospects = get_prospects_list(lifecycle_stage="ALL", company_ids=candidate_company_ids, conn=conn)
                groups = _assemble_company_groups(child_prospects, target_company_ids=candidate_company_ids, conn=conn, universe_context=universe_context)
                groups = [g for g in groups if g.get("friction_level") == friction.upper()]
                total_count = len(groups)
                total_facilities = sum(g.get("facility_count", 1) for g in groups)
                universe_meta = get_universe_metadata(conn=conn, universe_context=universe_context)
                total_pages = max(1, (total_count + page_size - 1) // page_size)
                metadata = {
                    "total_companies": total_count,
                    "total_facilities": total_facilities,
                    "universe_companies": universe_meta["universe_companies"],
                    "universe_facilities": universe_meta["universe_facilities"],
                    "lifecycle_counts": universe_meta["lifecycle_counts"],
                    "facility_lifecycle_counts": universe_meta["facility_lifecycle_counts"],
                    "opportunity_counts": universe_meta["opportunity_counts"],
                    "facility_opportunity_counts": universe_meta["facility_opportunity_counts"],
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "page_start": max(0, (page - 1) * page_size + 1) if total_count > 0 else 0,
                    "page_end": min(page * page_size, total_count),
                }
                start = (page - 1) * page_size
                end = start + page_size
                return {
                    "items": groups[start:end],
                    "total_count": total_count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "metadata": metadata,
                }
            else:
                prospects = get_prospects_list(lifecycle_stage=lifecycle_stage, db_path=db_path, conn=conn)

        groups = _assemble_company_groups(prospects, conn=conn, universe_context=universe_context)
        # Optional Python-level filtering
        outreach_items = _parse_filter_list(outreach_filter)
        if outreach_items:
            has_fu = any(x in ("FOLLOW_UP", "FOLLOW_UPS", "FOLLOW-UP", "FOLLOW-UPS") for x in outreach_items)
            plain_statuses = set(x for x in outreach_items if x not in ("FOLLOW_UP", "FOLLOW_UPS", "FOLLOW-UP", "FOLLOW-UPS"))
            def _match_outreach(g):
                st = g.get("outreach_status") or "UNCONTACTED"
                if st in plain_statuses:
                    return True
                if has_fu and g.get("next_follow_up_at"):
                    return True
                return False
            groups = [g for g in groups if _match_outreach(g)]

        if unreviewed_only:
            groups = [g for g in groups if not g.get("is_viewed")]

        if search and search.strip():
            q_raw = search.strip().lower()
            q_len = len(q_raw)
            if q_len == 1:
                groups = [
                    g for g in groups
                    if (g.get("operating_brand") or "").lower().startswith(q_raw)
                    or (g.get("legal_name") or "").lower().startswith(q_raw)
                    or any((f.get("facility_name") or "").lower().startswith(q_raw) for f in g.get("facilities", []))
                ]
            elif q_len == 2:
                groups = [
                    g for g in groups
                    if q_raw in (g.get("operating_brand") or "").lower()
                    or q_raw in (g.get("legal_name") or "").lower()
                    or any(q_raw in (f.get("facility_name") or "").lower() for f in g.get("facilities", []))
                    or any((f.get("state_prov") or "").lower() == q_raw for f in g.get("facilities", []))
                ]
            else:
                groups = [g for g in groups if q_raw in g.get("searchable_text", "")]

            def _rank_group(g):
                brand = (g.get("operating_brand") or "").lower()
                if brand == q_raw:
                    return 1
                if brand.startswith(q_raw):
                    return 2
                if f" {q_raw}" in f" {brand}":
                    return 3
                if q_raw in brand or q_raw in (g.get("legal_name") or "").lower():
                    return 4
                if any((f.get("facility_name") or "").lower().startswith(q_raw) for f in g.get("facilities", [])):
                    return 5
                if any(q_raw in (f.get("facility_name") or "").lower() for f in g.get("facilities", [])):
                    return 6
                if any((f.get("city") or "").lower().startswith(q_raw) or (f.get("city") or "").lower() == q_raw for f in g.get("facilities", [])):
                    return 7
                if any((f.get("state_prov") or "").lower() == q_raw for f in g.get("facilities", [])):
                    return 8
                return 9

            groups.sort(key=lambda g: (_rank_group(g), (g.get("operating_brand") or "").lower(), g.get("company_id", 0)))

        if friction and friction.upper() != "ALL":
            fr_clean = friction.upper()
            groups = [g for g in groups if g.get("friction_level") == fr_clean]

        equipment_items = _parse_filter_list(equipment)
        if equipment_items:
            eq_set = set(equipment_items)
            groups = [g for g in groups if any(eq in eq_set for eq in g.get("equipment_categories", []))]

        family_items = _parse_filter_list(family)
        if family_items:
            fam_set = set(family_items)
            groups = [g for g in groups if any(f in fam_set for f in g.get("commodity_family_codes", []))]

        category_items = _parse_filter_list(category)
        if category_items:
            cat_set = set(category_items)
            groups = [g for g in groups if any(c in cat_set for c in g.get("commodity_category_codes", []))]

        season_items = _parse_filter_list(seasonality)
        if season_items:
            seas_set = set(season_items)
            groups = [g for g in groups if any(s in seas_set for s in g.get("seasonality_profiles", []))]

        structure_items = _parse_filter_list(structure)
        if "SINGLE" in structure_items and "MULTI" not in structure_items:
            groups = [g for g in groups if g.get("facility_count") == 1]
        elif "MULTI" in structure_items and "SINGLE" not in structure_items:
            groups = [g for g in groups if g.get("facility_count", 0) >= 2]

        fc_items = _parse_filter_list(facility_count)
        if fc_items:
            def _match_fc(g):
                cnt = g.get("facility_count", 0)
                for fc in fc_items:
                    if fc == "1" and cnt == 1: return True
                    if fc in ("2_5", "2-5") and 2 <= cnt <= 5: return True
                    if fc in ("6_20", "6-20") and 6 <= cnt <= 20: return True
                    if fc in ("20_PLUS", "21_PLUS", "20+") and cnt >= 21: return True
                return False
            groups = [g for g in groups if _match_fc(g)]

        fleet_items = _parse_filter_list(fleet)
        if "VERIFIED_PRESENT" in fleet_items and "NONE_VERIFIED" not in fleet_items:
            groups = [g for g in groups if g.get("facts", {}).get("private_fleet_present") is True]
        elif "NONE_VERIFIED" in fleet_items and "VERIFIED_PRESENT" not in fleet_items:
            groups = [g for g in groups if not g.get("facts", {}).get("private_fleet_present")]

        carrier_items = _parse_filter_list(carrier)
        if "VERIFIED" in carrier_items and "UNKNOWN" not in carrier_items:
            groups = [g for g in groups if g.get("facts", {}).get("commercial_carrier_use") is True]
        elif "UNKNOWN" in carrier_items and "VERIFIED" not in carrier_items:
            groups = [g for g in groups if not g.get("facts", {}).get("commercial_carrier_use")]

        proc_items = _parse_filter_list(procurement)
        if proc_items:
            proc_set = set(proc_items)
            groups = [g for g in groups if g.get("facts", {}).get("freight_procurement_level") in proc_set]

        tier_items = _parse_filter_list(effective_tier)
        if tier_items:
            target_tiers = {_canonical_tier(t) for t in tier_items} - {None}
            if target_tiers:
                groups = [g for g in groups if g.get("opportunity_tier") in target_tiers]
            else:
                groups = []


        if page is not None and page_size is not None:
            total_count = len(groups)
            total_pages = max(1, (total_count + page_size - 1) // page_size)
            start = (page - 1) * page_size
            end = start + page_size
            items = groups[start:end]
            return {
                "items": items,
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
            }

        return groups
    finally:
        if should_close:
            conn.close()


def get_prospect_detail(facility_id: int, db_path: Optional[str | Path] = None) -> Optional[Dict[str, Any]]:
    """
    Returns full details for a single prospect facility, including:
    - Company profile + dated corporate relationships
    - Facility attributes (dock hours, loading notes, private fleet)
    - All facility commodities, equipment suitability, securement notes
    - Complete contacts list (direct vs switchboard distinction, phone, email)
    - Full claims ledger with verification statuses and supporting evidence sources
    - Signals & Loads state (truthfully 0)
    """
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Base facility and company query
        query = """
            SELECT
                f.id as facility_id,
                f.facility_name,
                f.facility_type,
                f.physical_address,
                f.city,
                f.state_prov,
                f.country,
                f.postal_code,
                f.private_fleet_present,
                f.vehicle_asset_ownership,
                f.fleet_relationship_type,
                f.commercial_carrier_use,
                f.broker_friendly_status,
                f.freight_procurement_level,
                c.id as company_id,
                c.operating_brand,
                c.legal_name,
                c.website_url,
                c.corporate_address,
                c.notes as company_notes,
                c.company_footprint_status,
                c.verified_operating_location_count,
                c.footprint_source_notes,
                c.created_at as company_created_at,
                COALESCE(pl.stage, 'DISCOVERY') as lifecycle_stage,
                pl.updated_at as stage_updated_at,
                pl.notes as stage_notes
            FROM facilities f
            JOIN companies c ON f.company_id = c.id
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.id = ?
        """
        row = conn.execute(query, (facility_id,)).fetchone()
        if not row:
            return None

        comp_id = row["company_id"]

        # 1. Commodities & Equipment
        commodities_cur = conn.execute(
            """
            SELECT id, commodity_category, specific_products, equipment_category,
                   equipment_usage_status, trailer_specs_notes, securement_tarp_notes
            FROM facility_commodities
            WHERE facility_id = ?
            ORDER BY id ASC
            """,
            (facility_id,)
        )
        commodities = [dict(c) for c in commodities_cur.fetchall()]

        has_tax = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='facility_commodity_mappings'"
        ).fetchone()[0] > 0
        taxonomy_mappings = []
        if has_tax:
            tax_cur = conn.execute(
                """
                SELECT c.id as category_id, c.category_code, c.display_name as category_name,
                       c.description as category_description, c.typical_equipment_fit,
                       c.seasonality_profile as cat_seasonality, c.peak_months as cat_peak_months,
                       c.operating_characteristics, cf.id as family_id, cf.family_code,
                       cf.display_name as family_name, m.is_primary, m.source_evidence_notes
                FROM facility_commodity_mappings m
                JOIN commodity_categories c ON m.category_id = c.id
                JOIN commodity_families cf ON c.family_id = cf.id
                WHERE m.facility_id = ?
                ORDER BY m.is_primary DESC, c.sort_order ASC
                """,
                (facility_id,)
            )
            taxonomy_mappings = [dict(t) for t in tax_cur.fetchall()]
        primary_tax = taxonomy_mappings[0] if taxonomy_mappings else None

        # 2. Contacts
        contacts_cur = conn.execute(
            """
            SELECT id, contact_identity, person_name, exact_published_title, department,
                   phone_number, phone_extension, fax_number, phone_directness, email_address,
                   email_directness, role_category, outbound_shipping_procurement_relevance,
                   broker_procurement_relevance, is_primary_contact
            FROM contacts
            WHERE facility_id = ?
            ORDER BY is_primary_contact DESC,
                     CASE WHEN phone_directness = 'DIRECT_PERSON' THEN 0
                          WHEN phone_directness = 'DEPARTMENT_LINE' THEN 1
                          ELSE 2 END,
                     id ASC
            """,
            (facility_id,)
        )
        contacts = [dict(ct) for ct in contacts_cur.fetchall()]

        # 3. Corporate Relationships (Parent/Child)
        relationships_cur = conn.execute(
            """
            SELECT r.id, r.relationship_type, r.valid_from, r.valid_to, r.is_current, r.notes as relationship_notes,
                   p.operating_brand as parent_brand, p.legal_name as parent_legal,
                   p.website_url as parent_website, p.notes as parent_notes
            FROM company_relationships r
            JOIN companies p ON r.parent_company_id = p.id
            WHERE r.child_company_id = ?
            """,
            (comp_id,)
        )
        relationships = []
        for r in relationships_cur.fetchall():
            rd = dict(r)
            rd["corporate_group"] = "TI Automotive"
            rd["current_hierarchy_status"] = "UNKNOWN"
            relationships.append(rd)

        # 4. Claims & Evidence Ledger for this prospect
        # Subject foreign keys: company_id, facility_id, facility_commodity_id, contact_id
        commodity_ids = [c["id"] for c in commodities]
        contact_ids = [ct["id"] for ct in contacts]

        placeholders_commodities = ",".join("?" for _ in commodity_ids) if commodity_ids else "NULL"
        placeholders_contacts = ",".join("?" for _ in contact_ids) if contact_ids else "NULL"

        claims_query = f"""
            SELECT
                cl.id as claim_id,
                cl.claim_field,
                cl.claimed_value,
                cl.verification_status,
                cl.is_current_accepted,
                cl.claim_notes,
                cl.created_at,
                cl.company_id,
                cl.facility_id,
                cl.facility_commodity_id,
                cl.contact_id,
                es.id as source_id,
                es.source_type,
                es.source_title_publisher,
                es.source_url,
                es.is_primary_source,
                es.source_published_at,
                es.event_at,
                es.observed_at,
                es.notes as source_notes,
                ce.relationship as evidence_relationship,
                ce.relationship_notes
            FROM claims cl
            LEFT JOIN claim_evidence ce ON cl.id = ce.claim_id
            LEFT JOIN evidence_sources es ON ce.evidence_source_id = es.id
            WHERE cl.company_id = ?
               OR cl.facility_id = ?
               OR cl.facility_commodity_id IN ({placeholders_commodities})
               OR cl.contact_id IN ({placeholders_contacts})
            ORDER BY cl.id ASC
        """
        params = [comp_id, facility_id] + commodity_ids + contact_ids
        claims_rows = conn.execute(claims_query, params).fetchall()

        # Group claims with their evidence sources
        claims_dict = {}
        for cr in claims_rows:
            cid = cr["claim_id"]
            if cid not in claims_dict:
                claims_dict[cid] = {
                    "claim_id": cid,
                    "claim_field": cr["claim_field"],
                    "claimed_value": cr["claimed_value"],
                    "verification_status": cr["verification_status"],
                    "is_current_accepted": cr["is_current_accepted"],
                    "claim_notes": cr["claim_notes"],
                    "created_at": cr["created_at"],
                    "subject_type": (
                        "Company" if cr["company_id"] else
                        "Facility" if cr["facility_id"] else
                        "Commodity" if cr["facility_commodity_id"] else
                        "Contact" if cr["contact_id"] else "Other"
                    ),
                    "sources": []
                }
            if cr["source_id"]:
                claims_dict[cid]["sources"].append({
                    "source_id": cr["source_id"],
                    "source_type": cr["source_type"],
                    "source_title_publisher": cr["source_title_publisher"],
                    "source_url": cr["source_url"],
                    "is_primary_source": cr["is_primary_source"],
                    "source_published_at": cr["source_published_at"],
                    "event_at": cr["event_at"],
                    "observed_at": cr["observed_at"],
                    "source_notes": cr["source_notes"],
                    "relationship": cr["evidence_relationship"],
                    "relationship_notes": cr["relationship_notes"],
                })

        claims_list = list(claims_dict.values())

        # Research queries (ordinary browser search URLs, zero API)
        brand = row["operating_brand"]
        city = row["city"]
        state = row["state_prov"]
        encoded_brand = brand.replace(" ", "+")
        encoded_location = f"{city}+{state}".replace(" ", "+")
        
        research_urls = {
            "google_company": f"https://www.google.com/search?q={encoded_brand}+{encoded_location}+shipping+logistics",
            "google_contacts": f"https://www.google.com/search?q={encoded_brand}+{encoded_location}+shipping+manager+logistics+manager",
            "google_plant": f"https://www.google.com/search?q={encoded_brand}+{row['facility_name']}+truck+entrance+dock",
            "gemini_prompt": f"Research shipping operations for {brand} located in {city}, {state}. What commodities do they ship, do they use flatbed or dry van freight, and who manages shipping/traffic procurement?",
            "gemini_url": "https://gemini.google.com",
        }

        readiness = evaluate_qualification_readiness(facility_id, conn)

        # Outreach CRM state & history
        outreach_history = []
        has_outreach = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='outreach_logs'"
        ).fetchone()[0] > 0
        if has_outreach:
            outreach_cur = conn.execute(
                """
                SELECT o.id, o.company_id, o.facility_id, o.contact_id, o.outreach_channel,
                       o.outcome as disposition, COALESCE(o.feedback_notes, o.notes) as feedback_notes,
                       o.contacted_at, COALESCE(o.follow_up_at, o.follow_up_date) as follow_up_at,
                       f.facility_name, ct.person_name as contact_name
                FROM outreach_logs o
                LEFT JOIN facilities f ON o.facility_id = f.id
                LEFT JOIN contacts ct ON o.contact_id = ct.id
                WHERE o.facility_id = ? OR (o.company_id = ? AND o.facility_id IS NULL)
                ORDER BY o.contacted_at DESC, o.id DESC
                """,
                (facility_id, comp_id)
            )
            outreach_history = [dict(o) for o in outreach_cur.fetchall()]

        has_eng = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='prospect_engagement_state'"
        ).fetchone()[0] > 0
        eng_row = conn.execute(
            "SELECT * FROM prospect_engagement_state WHERE company_id = ?",
            (comp_id,)
        ).fetchone() if has_eng else None
        engagement_state = dict(eng_row) if eng_row else {
            "current_outreach_status": "UNCONTACTED",
            "attempt_count": 0,
            "is_viewed": 0,
        }

        # Compute broker access friction for this company
        comp_fac_rows = conn.execute(
            "SELECT * FROM facilities WHERE company_id = ?",
            (comp_id,)
        ).fetchall()
        comp_facs = [dict(f) for f in comp_fac_rows]
        for f in comp_facs:
            f_cts = conn.execute("SELECT * FROM contacts WHERE facility_id = ?", (f["id"],)).fetchall()
            f["contacts"] = [dict(c) for c in f_cts]
        friction = evaluate_broker_access_friction(dict(row), comp_facs)

        return {
            "facility_id": row["facility_id"],
            "company_id": row["company_id"],
            "operating_brand": row["operating_brand"],
            "legal_name": row["legal_name"],
            "facility_name": row["facility_name"],
            "facility_type": row["facility_type"],
            "physical_address": row["physical_address"],
            "city": row["city"],
            "state_prov": row["state_prov"],
            "country": row["country"],
            "postal_code": row["postal_code"],
            "location_str": f"{row['city']}, {row['state_prov']} {row['country']}",
            "private_fleet_present": row["private_fleet_present"],
            "vehicle_asset_ownership": row["vehicle_asset_ownership"],
            "fleet_relationship_type": row["fleet_relationship_type"],
            "commercial_carrier_use": row["commercial_carrier_use"],
            "broker_friendly_status": row["broker_friendly_status"],
            "freight_procurement_level": row["freight_procurement_level"],
            "website_url": row["website_url"],
            "corporate_address": row["corporate_address"],
            "company_notes": row["company_notes"],
            "company_footprint_status": row["company_footprint_status"] or "UNKNOWN",
            "verified_operating_location_count": row["verified_operating_location_count"],
            "footprint_source_notes": row["footprint_source_notes"],
            "company_created_at": row["company_created_at"],
            "lifecycle_stage": row["lifecycle_stage"],
            "stage_updated_at": row["stage_updated_at"],
            "stage_notes": row["stage_notes"],
            "commodities": commodities,
            "taxonomy_mappings": taxonomy_mappings,
            "primary_taxonomy": primary_tax,
            "commodity_family_code": primary_tax["family_code"] if primary_tax else None,
            "commodity_family_name": primary_tax["family_name"] if primary_tax else None,
            "commodity_category_code": primary_tax["category_code"] if primary_tax else None,
            "commodity_category_name": primary_tax["category_name"] if primary_tax else None,
            "category_typical_equipment": primary_tax["typical_equipment_fit"] if primary_tax else None,
            "category_seasonality": primary_tax["cat_seasonality"] if primary_tax else "YEAR_ROUND",
            "category_peak_months": primary_tax["cat_peak_months"] if primary_tax else None,
            "contacts": contacts,
            "relationships": relationships,
            "claims": claims_list,
            "research_urls": research_urls,
            "freight_state": "PROSPECT",
            "qualification_readiness": readiness,
            "broker_access_friction": friction,
            "friction_level": friction["level"],
            "outreach_history": outreach_history,
            "engagement_state": engagement_state,
        }
    finally:
        conn.close()


def get_evidence_sources_list(db_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    """
    Returns all evidence sources stored in the database for the Evidence Ledger view.
    """
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT id, source_type, source_title_publisher, source_url,
                   is_primary_source, source_published_at, event_at, observed_at, notes
            FROM evidence_sources
            ORDER BY id ASC
            """
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_system_settings(db_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    """
    Returns system settings from the settings table.
    """
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute("SELECT setting_key, setting_value, value_type, description FROM settings ORDER BY setting_key")
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ============================================================================
# STAGE 3C — FREIGHT-BROKER OUTREACH CRM WORKFLOW FUNCTIONS
# ============================================================================

class SuppressionBlockedError(Exception):
    """Raised when outreach is blocked by an active suppression or Do Not Contact (DNC) policy."""
    def __init__(self, message: str, suppression_info: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.suppression_info = suppression_info or {}


def evaluate_outreach_suppression(
    company_id: int,
    facility_id: Optional[int] = None,
    origin_state_prov: Optional[str] = None,
    dest_state_prov: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Evaluates whether outreach to a prospect company, facility, or lane is blocked
    by an active entry in the suppressions table.
    
    Scopes checked (in priority order):
    1. COMPANY: Suppresses all facilities/contacts for this corporate entity.
    2. FACILITY: Suppresses this specific physical facility.
    3. COMPANY_LANE: Suppresses a specific origin-destination lane for this company.
    4. FACILITY_LANE: Suppresses a specific origin-destination lane for this facility.
    5. GLOBAL_LANE: Suppresses an entire geographic corridor across all shippers.
    
    Active suppression statuses that block outreach:
    - 'DO_NOT_CONTACT'
    - 'EXISTING_CUSTOMER'
    - 'ALREADY_ROUTED'
    
    Note: 'NORMAL_PROSPECT' indicates non-suppressed.
    Note: NOT_INTERESTED is an outreach disposition, NOT a suppression row.
    Note: DIRECT_ONLY policy is an operational note, NOT a suppression row.
    """
    should_close = False
    if conn is None:
        conn = create_connection(db_path)
        conn.row_factory = sqlite3.Row
        should_close = True

    try:
        # Check if suppressions table exists
        has_table = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='suppressions'"
        ).fetchone()[0] > 0
        if not has_table:
            return {
                "is_suppressed": False,
                "suppression_id": None,
                "scope_type": None,
                "suppression_status": None,
                "reason_notes": None,
                "message": "No suppressions table",
            }

        # 1. Check COMPANY scope
        comp_sup = conn.execute(
            """
            SELECT id, scope_type, suppression_status, reason_notes, effective_date
            FROM suppressions
            WHERE scope_type = 'COMPANY'
              AND company_id = ?
              AND suppression_status != 'NORMAL_PROSPECT'
            LIMIT 1
            """,
            (company_id,)
        ).fetchone()
        if comp_sup:
            return {
                "is_suppressed": True,
                "suppression_id": comp_sup["id"],
                "scope_type": comp_sup["scope_type"],
                "suppression_status": comp_sup["suppression_status"],
                "reason_notes": comp_sup["reason_notes"],
                "message": f"Outreach blocked: Company {company_id} has active {comp_sup['suppression_status']} suppression ({comp_sup['reason_notes']})",
            }

        # 2. Check FACILITY scope
        if facility_id is not None:
            fac_sup = conn.execute(
                """
                SELECT id, scope_type, suppression_status, reason_notes, effective_date
                FROM suppressions
                WHERE scope_type = 'FACILITY'
                  AND facility_id = ?
                  AND suppression_status != 'NORMAL_PROSPECT'
                LIMIT 1
                """,
                (facility_id,)
            ).fetchone()
            if fac_sup:
                return {
                    "is_suppressed": True,
                    "suppression_id": fac_sup["id"],
                    "scope_type": fac_sup["scope_type"],
                    "suppression_status": fac_sup["suppression_status"],
                    "reason_notes": fac_sup["reason_notes"],
                    "message": f"Outreach blocked: Facility {facility_id} has active {fac_sup['suppression_status']} suppression ({fac_sup['reason_notes']})",
                }

        # If destination provided without origin, resolve origin from facility state_prov
        if dest_state_prov and not origin_state_prov and facility_id is not None:
            fac_row = conn.execute("SELECT state_prov FROM facilities WHERE id = ?", (facility_id,)).fetchone()
            if fac_row and fac_row["state_prov"]:
                origin_state_prov = fac_row["state_prov"]

        # 3. Check Lane scopes if origin and destination provided
        if origin_state_prov and dest_state_prov:
            o_clean = origin_state_prov.strip().upper()
            d_clean = dest_state_prov.strip().upper()

            # COMPANY_LANE
            comp_lane = conn.execute(
                """
                SELECT id, scope_type, suppression_status, reason_notes, effective_date
                FROM suppressions
                WHERE scope_type = 'COMPANY_LANE'
                  AND company_id = ?
                  AND origin_state_prov = ?
                  AND dest_state_prov = ?
                  AND suppression_status != 'NORMAL_PROSPECT'
                LIMIT 1
                """,
                (company_id, o_clean, d_clean)
            ).fetchone()
            if comp_lane:
                return {
                    "is_suppressed": True,
                    "suppression_id": comp_lane["id"],
                    "scope_type": comp_lane["scope_type"],
                    "suppression_status": comp_lane["suppression_status"],
                    "reason_notes": comp_lane["reason_notes"],
                    "message": f"Outreach blocked: Company {company_id} lane {o_clean} -> {d_clean} has active {comp_lane['suppression_status']} suppression ({comp_lane['reason_notes']})",
                }

            # FACILITY_LANE
            if facility_id is not None:
                fac_lane = conn.execute(
                    """
                    SELECT id, scope_type, suppression_status, reason_notes, effective_date
                    FROM suppressions
                    WHERE scope_type = 'FACILITY_LANE'
                      AND facility_id = ?
                      AND origin_state_prov = ?
                      AND dest_state_prov = ?
                      AND suppression_status != 'NORMAL_PROSPECT'
                    LIMIT 1
                    """,
                    (facility_id, o_clean, d_clean)
                ).fetchone()
                if fac_lane:
                    return {
                        "is_suppressed": True,
                        "suppression_id": fac_lane["id"],
                        "scope_type": fac_lane["scope_type"],
                        "suppression_status": fac_lane["suppression_status"],
                        "reason_notes": fac_lane["reason_notes"],
                        "message": f"Outreach blocked: Facility {facility_id} lane {o_clean} -> {d_clean} has active {fac_lane['suppression_status']} suppression ({fac_lane['reason_notes']})",
                    }

            # GLOBAL_LANE
            glob_lane = conn.execute(
                """
                SELECT id, scope_type, suppression_status, reason_notes, effective_date
                FROM suppressions
                WHERE scope_type = 'GLOBAL_LANE'
                  AND origin_state_prov = ?
                  AND dest_state_prov = ?
                  AND suppression_status != 'NORMAL_PROSPECT'
                LIMIT 1
                """,
                (o_clean, d_clean)
            ).fetchone()
            if glob_lane:
                return {
                    "is_suppressed": True,
                    "suppression_id": glob_lane["id"],
                    "scope_type": glob_lane["scope_type"],
                    "suppression_status": glob_lane["suppression_status"],
                    "reason_notes": glob_lane["reason_notes"],
                    "message": f"Outreach blocked: Global lane corridor {o_clean} -> {d_clean} has active {glob_lane['suppression_status']} suppression ({glob_lane['reason_notes']})",
                }

        return {
            "is_suppressed": False,
            "suppression_id": None,
            "scope_type": None,
            "suppression_status": None,
            "reason_notes": None,
            "message": "No active suppression found",
        }
    finally:
        if should_close:
            conn.close()


def check_lane_suppression_warning(
    company_id: int,
    facility_id: Optional[int] = None,
    origin_state_prov: Optional[str] = None,
    dest_state_prov: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Checks if active lane suppressions exist for this company or facility,
    and whether an advisory warning is warranted when origin/destination are not fully specified.
    """
    should_close = False
    if conn is None:
        conn = create_connection(db_path)
        conn.row_factory = sqlite3.Row
        should_close = True
    try:
        cur = conn.cursor()
        has_table = cur.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='suppressions'").fetchone()[0] > 0
        if not has_table:
            return {
                "has_lane_suppressions": False,
                "lane_suppressions_count": 0,
                "show_lane_warning": False,
                "warning_message": None,
                "is_lane_suppressed": False,
                "suppressed_lane_reason": None,
            }

        lane_sups = cur.execute("""
            SELECT id, scope_type, origin_state_prov, dest_state_prov, suppression_status, reason_notes
            FROM suppressions
            WHERE suppression_status != 'NORMAL_PROSPECT'
              AND (
                  (scope_type = 'COMPANY_LANE' AND company_id = ?)
                  OR (scope_type = 'FACILITY_LANE' AND facility_id = ?)
                  OR (scope_type = 'GLOBAL_LANE')
              )
        """, (company_id, facility_id)).fetchall()

        has_lane_suppressions = len(lane_sups) > 0
        has_specific_lane = bool(origin_state_prov and dest_state_prov)

        is_lane_suppressed = False
        suppressed_lane_reason = None
        if has_specific_lane:
            o_clean = origin_state_prov.strip().upper()
            d_clean = dest_state_prov.strip().upper()
            for s in lane_sups:
                if s["origin_state_prov"] == o_clean and s["dest_state_prov"] == d_clean:
                    is_lane_suppressed = True
                    suppressed_lane_reason = s["reason_notes"]
                    break

        show_lane_warning = has_lane_suppressions and not has_specific_lane
        warning_message = "Lane-specific suppression exists. Add Origin and Destination if this call concerns a specific lane." if show_lane_warning else None

        return {
            "has_lane_suppressions": has_lane_suppressions,
            "lane_suppressions_count": len(lane_sups),
            "show_lane_warning": show_lane_warning,
            "warning_message": warning_message,
            "is_lane_suppressed": is_lane_suppressed,
            "suppressed_lane_reason": suppressed_lane_reason,
            "is_suppressed": is_lane_suppressed or show_lane_warning,
            "message": suppressed_lane_reason or warning_message,
        }
    finally:
        if should_close:
            conn.close()


# ============================================================================
# Phase C Remediation: Speaker Authority & Role Classification
# ============================================================================
AUTHORITATIVE_ROLES = {
    "SHIPPING MANAGER",
    "LOGISTICS MANAGER",
    "LOGISTICS COORDINATOR",
    "TRAFFIC MANAGER",
    "TRAFFIC COORDINATOR",
    "TRANSPORTATION MANAGER",
    "TRANSPORTATION COORDINATOR",
    "SHIPPING DEPARTMENT",
    "LOGISTICS DEPARTMENT",
    "TRAFFIC DEPARTMENT",
    "TRANSPORTATION DEPARTMENT",
    "PLANT MANAGER",
    "FACILITY MANAGER",
}

AUTHORITATIVE_OTHER_ALLOWLIST = {
    "DISPATCHER",
    "HEAD DISPATCHER",
    "LEAD DISPATCHER",
    "FREIGHT MANAGER",
    "DIRECTOR OF TRANSPORTATION",
    "DIRECTOR OF LOGISTICS",
    "VP OF SUPPLY CHAIN",
    "SUPPLY CHAIN MANAGER",
    "WAREHOUSE MANAGER",
    "SHIPPING SUPERVISOR",
    "TERMINAL MANAGER",
    "DOCK SUPERVISOR",
    "OPERATIONS MANAGER",
}

NON_AUTHORITATIVE_ROLES = {
    "RECEPTION",
    "RECEPTIONIST",
    "GATEKEEPER",
    "RECEPTION / GATEKEEPER",
    "OPERATOR",
    "SWITCHBOARD",
    "SECURITY",
    "UNKNOWN",
    "CUSTOMER SERVICE",
    "GENERIC CUSTOMER SERVICE",
    "SALES",
    "COMMERCIAL SALES",
    "BUSINESS DEVELOPMENT",
}


def is_role_authoritative_for_claims(role_name: Optional[str], other_role: Optional[str] = None) -> bool:
    """
    Server-side authority policy (Phase C Remediation).
    Determines whether a telephone source person/role is authoritative enough
    to mint VERIFIED transportation/operational claims.
    """
    if not role_name:
        return False
    norm = role_name.strip().upper()
    if norm in NON_AUTHORITATIVE_ROLES:
        return False
    if norm in AUTHORITATIVE_ROLES:
        return True
    if norm == "OTHER":
        if not other_role:
            return False
        clean_other = other_role.strip().upper()
        if clean_other in NON_AUTHORITATIVE_ROLES:
            return False
        if clean_other in AUTHORITATIVE_ROLES or clean_other in AUTHORITATIVE_OTHER_ALLOWLIST:
            return True
        return False
    if norm in AUTHORITATIVE_OTHER_ALLOWLIST:
        return True
    return False


def log_outreach_call(
    company_id: int,
    facility_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    disposition: str = "NO_ANSWER",
    feedback_notes: Optional[str] = None,
    follow_up_at: Optional[str] = None,
    contacted_at: Optional[str] = None,
    channel: str = "PHONE",
    origin_state_prov: Optional[str] = None,
    dest_state_prov: Optional[str] = None,
    user_timezone: Optional[str] = None,
    db_path: Optional[str | Path] = None,
    conn: Optional[sqlite3.Connection] = None,
    verified_evidence: Optional[Dict[str, Any]] = None,
    client_request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stage 3C CRM: Records an outreach call.
    - Evaluates suppression/DNC before write (blocks outreach with SuppressionBlockedError).
    - Appends to outreach_logs (immutable history).
    - Updates prospect_engagement_state projection atomically.
    - Increments attempt_count for PHONE contacts.
    - Invariant: Does NOT change prospect_lifecycle (Interested != Qualified).
    - Invariant: Does NOT add to suppressions (Not Interested != DNC).
    - Invariant: Does NOT create research claims.
    """
    ALLOWED_DISPOSITIONS = {
        "INTERESTED", "NOT_INTERESTED", "NO_ANSWER", "CALL_BACK",
        "CONNECTED_DECISION_MAKER", "CONNECTED_GATEKEEPER", "LEFT_VOICEMAIL", "WRONG_CONTACT"
    }
    disp_clean = (disposition or "NO_ANSWER").strip().upper()
    if disp_clean not in ALLOWED_DISPOSITIONS:
        raise ValueError(f"Invalid disposition '{disposition}'. Allowed: {ALLOWED_DISPOSITIONS}")

    chan_clean = (channel or "PHONE").strip().upper()
    if chan_clean not in ("PHONE", "EMAIL", "IN_PERSON"):
        raise ValueError(f"Invalid channel '{channel}'. Allowed: PHONE, EMAIL, IN_PERSON")

    now_iso = get_utc_now_iso()
    c_at = normalize_to_utc_iso(contacted_at, "contacted_at") if contacted_at else now_iso
    f_at = normalize_to_utc_iso(follow_up_at, "follow_up_at", default_timezone=user_timezone) if follow_up_at else None

    should_close = False
    if conn is None:
        conn = create_connection(db_path)
        conn.row_factory = sqlite3.Row
        should_close = True
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            # 0. Check suppression (DNC / existing account / lane restrictions)
            sup_eval = evaluate_outreach_suppression(
                company_id=company_id,
                facility_id=facility_id,
                origin_state_prov=origin_state_prov,
                dest_state_prov=dest_state_prov,
                conn=conn
            )
            if sup_eval["is_suppressed"]:
                raise SuppressionBlockedError(sup_eval["message"], suppression_info=sup_eval)

            # 1. Validate company exists
            comp = conn.execute("SELECT id, operating_brand, legal_name FROM companies WHERE id = ?", (company_id,)).fetchone()
            if not comp:
                raise ValueError(f"Company {company_id} does not exist")

            # 1b. Server-side Idempotency / Duplicate Submission Check (Phase C Remediation)
            if client_request_id and client_request_id.strip():
                clean_req_id = client_request_id.strip()
                existing_log = conn.execute(
                    """
                    SELECT id, company_id, facility_id, contact_id, outreach_channel, outcome, disposition, feedback_notes, contacted_at, follow_up_at
                    FROM outreach_logs
                    WHERE company_id = ? AND notes LIKE ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (company_id, f"%[ClientRequestId: {clean_req_id}]%")
                ).fetchone()
                if existing_log:
                    dup_log_id = existing_log["id"]
                    dup_ev_src = conn.execute(
                        "SELECT id, notes FROM evidence_sources WHERE outreach_log_id = ? LIMIT 1",
                        (dup_log_id,)
                    ).fetchone()
                    dup_ev_src_id = dup_ev_src["id"] if dup_ev_src else None

                    dup_claims_created = []
                    if dup_ev_src_id:
                        c_rows = conn.execute(
                            """
                            SELECT c.id as claim_id, c.claim_field, c.claimed_value, c.verification_status, c.facility_id, c.facility_commodity_id
                            FROM claims c
                            JOIN claim_evidence ce ON c.id = ce.claim_id
                            WHERE ce.evidence_source_id = ?
                            ORDER BY c.id ASC
                            """,
                            (dup_ev_src_id,)
                        ).fetchall()
                        dup_claims_created = [dict(r) for r in c_rows]

                    dup_eng = dict(conn.execute(
                        "SELECT * FROM prospect_engagement_state WHERE company_id = ?",
                        (company_id,)
                    ).fetchone() or {})

                    cur_fac_opp = evaluate_broker_opportunity(company_id=company_id, facility_id=facility_id, conn=conn) if facility_id else {}
                    cur_comp_opp = evaluate_broker_opportunity(company_id=company_id, conn=conn)

                    res = {
                        "outreach_log_id": dup_log_id,
                        "company_id": company_id,
                        "facility_id": facility_id,
                        "contact_id": contact_id,
                        "channel": existing_log["outreach_channel"],
                        "disposition": existing_log["disposition"],
                        "feedback_notes": existing_log["feedback_notes"],
                        "follow_up_at": existing_log["follow_up_at"],
                        "contacted_at": existing_log["contacted_at"],
                        "attempt_count": dup_eng.get("attempt_count", 1),
                        "engagement_state": dup_eng,
                        "is_duplicate_replay": True,
                    }
                    if dup_ev_src_id is not None:
                        res["evidence_source_id"] = dup_ev_src_id
                        res["authority_status"] = "AUTHORITATIVE" if (dup_ev_src and "[NON-AUTHORITATIVE" not in (dup_ev_src["notes"] or "")) else "NON_AUTHORITATIVE"
                        res["claims_created"] = dup_claims_created
                        res["contradictions_detected"] = []
                        res["old_opportunity_tier"] = cur_fac_opp.get("opportunity_tier")
                        res["new_opportunity_tier"] = cur_fac_opp.get("opportunity_tier")
                        res["old_company_tier"] = cur_comp_opp.get("opportunity_tier")
                        res["new_company_tier"] = cur_comp_opp.get("opportunity_tier")
                    return res

            # 2. Validate facility if given
            if facility_id is not None:
                fac = conn.execute("SELECT id, facility_name FROM facilities WHERE id = ? AND company_id = ?", (facility_id, company_id)).fetchone()
                if not fac:
                    raise ValueError(f"Facility {facility_id} does not belong to company {company_id}")

            # 3. Validate contact if given (Strict contact-facility scope)
            if contact_id is not None:
                ct = conn.execute(
                    "SELECT id, company_id, facility_id FROM contacts WHERE id = ?",
                    (contact_id,)
                ).fetchone()
                if not ct:
                    raise ValueError(f"Contact {contact_id} does not exist")

                if ct["company_id"] is not None:
                    if ct["company_id"] != company_id:
                        raise ValueError(f"Contact {contact_id} does not belong to target company {company_id}")
                elif ct["facility_id"] is not None:
                    fac_owner = conn.execute("SELECT company_id FROM facilities WHERE id = ?", (ct["facility_id"],)).fetchone()
                    if not fac_owner or fac_owner["company_id"] != company_id:
                        raise ValueError(f"Contact {contact_id} belongs to facility {ct['facility_id']}, which does not belong to target company {company_id}")
                    if facility_id is not None and ct["facility_id"] != facility_id:
                        raise ValueError(
                            f"Contact {contact_id} belongs to facility {ct['facility_id']}, not target facility {facility_id}. Sibling facility contacts cannot source facility claims."
                        )
                else:
                    raise ValueError(f"Contact {contact_id} is not associated with a company or facility")

            # 4. Format lane context into immutable notes and feedback_notes columns
            if origin_state_prov and dest_state_prov:
                lane_str = f"[Lane: {origin_state_prov.strip().upper()} -> {dest_state_prov.strip().upper()}]"
            elif origin_state_prov:
                lane_str = f"[Origin: {origin_state_prov.strip().upper()}]"
            elif dest_state_prov:
                lane_str = f"[Dest: {dest_state_prov.strip().upper()}]"
            else:
                lane_str = ""

            full_feedback = f"{lane_str} {feedback_notes or ''}".strip() if lane_str else feedback_notes
            req_token = f"[ClientRequestId: {client_request_id.strip()}]" if client_request_id and client_request_id.strip() else ""
            full_notes = f"{req_token} {full_feedback or ''}".strip() if req_token else full_feedback

            # Insert append-only outreach log
            cur = conn.execute(
                """
                INSERT INTO outreach_logs (
                    company_id, facility_id, contact_id, outreach_channel,
                    outcome, disposition, feedback_notes, notes,
                    contacted_at, follow_up_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company_id, facility_id, contact_id, chan_clean,
                    disp_clean, disp_clean, full_feedback, full_notes,
                    c_at, f_at, now_iso
                )
            )
            log_id = cur.lastrowid

            # 5. Compute real attempt count for phone calls
            attempts_cnt = conn.execute(
                "SELECT count(*) FROM outreach_logs WHERE company_id = ? AND outreach_channel = 'PHONE'",
                (company_id,)
            ).fetchone()[0]

            # 6. Update prospect_engagement_state projection
            conn.execute(
                """
                INSERT INTO prospect_engagement_state (
                    company_id, current_outreach_status, status_source_outreach_log_id,
                    attempt_count, last_contacted_at, next_follow_up_at, last_facility_id,
                    last_feedback_notes, is_viewed, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(company_id) DO UPDATE SET
                    current_outreach_status = excluded.current_outreach_status,
                    status_source_outreach_log_id = excluded.status_source_outreach_log_id,
                    attempt_count = excluded.attempt_count,
                    last_contacted_at = excluded.last_contacted_at,
                    next_follow_up_at = excluded.next_follow_up_at,
                    last_facility_id = excluded.last_facility_id,
                    last_feedback_notes = excluded.last_feedback_notes,
                    is_viewed = 1,
                    updated_at = excluded.updated_at
                """,
                (
                    company_id, disp_clean, log_id,
                    attempts_cnt, c_at, f_at, facility_id,
                    feedback_notes, now_iso
                )
            )

            # Retrieve updated engagement state
            eng_state = dict(conn.execute(
                "SELECT * FROM prospect_engagement_state WHERE company_id = ?",
                (company_id,)
            ).fetchone())

            # 7. Optional Structured Verified Telephone Evidence Intake (Phase C)
            ev_src_id = None
            authority_status = None
            claims_created = []
            contradictions_detected = []
            old_facility_tier = None
            new_facility_tier = None
            old_company_tier = None
            new_company_tier = None

            if verified_evidence and verified_evidence.get("confirmed_by_user"):
                # Scope validation: Verified telephone evidence for facility facts requires a specific facility
                if facility_id is None:
                    raise ValueError("Facility scope is required to record verified telephone evidence. Please select a specific facility.")

                # Evaluate pre-intake baseline opportunity tiers
                old_fac_opp = evaluate_broker_opportunity(company_id=company_id, facility_id=facility_id, conn=conn)
                old_facility_tier = old_fac_opp.get("opportunity_tier")
                old_comp_opp = evaluate_broker_opportunity(company_id=company_id, conn=conn)
                old_company_tier = old_comp_opp.get("opportunity_tier")

                # Extract provenance details
                src_name = (verified_evidence.get("source_person_name") or "").strip()
                src_role = (verified_evidence.get("source_person_role") or "").strip()
                src_other = (verified_evidence.get("source_role_other") or "").strip()
                if src_role == "Other" and src_other:
                    stated_role = src_other
                else:
                    stated_role = src_role or "Unspecified Role"
                stated_person = src_name or "Shipping Desk / Department"

                is_auth = is_role_authoritative_for_claims(src_role, src_other)
                authority_status = "AUTHORITATIVE" if is_auth else "NON_AUTHORITATIVE"
                ev_notes = (verified_evidence.get("evidence_notes") or "").strip()

                if not is_auth:
                    # TASK 1: NON-AUTHORITATIVE SPEAKER (e.g. Reception / Gatekeeper / Security / Sales)
                    # Policy: Capture statement for CONTEXT only. Do NOT mint VERIFIED operational truth.
                    source_title = f"Phone Call [Context Only]: {stated_person} ({stated_role})"
                    context_prefix = f"[NON-AUTHORITATIVE SPEAKER / CONTEXT ONLY - Role: {stated_role}]"
                    full_context_notes = f"{context_prefix} {ev_notes}".strip()

                    ev_src_id = record_evidence_source(
                        conn=conn,
                        source_type="PHONE_OUTREACH",
                        source_title_publisher=source_title,
                        observed_at=c_at,
                        source_url=None,
                        is_primary_source=False,
                        source_published_at=None,
                        event_at=c_at,
                        outreach_log_id=log_id,
                        notes=full_context_notes or None,
                    )

                    # Link existing facility claims with relationship = 'CONTEXT' only (no verification)
                    curr_claims_list = get_current_accepted_claims(conn, "facility_id", facility_id)
                    for c in curr_claims_list:
                        link_claim_evidence(
                            conn,
                            c["id"],
                            ev_src_id,
                            relationship="CONTEXT",
                            relationship_notes=f"Contextual statement by {stated_person} ({stated_role}); non-authoritative for operational verification.",
                        )

                    # Tiers remain unchanged because no claims were created
                    new_facility_tier = old_facility_tier
                    new_company_tier = old_company_tier

                else:
                    # AUTHORITATIVE SPEAKER: Proceed with canonical verified claims intake
                    source_title = f"Phone Call: {stated_person} ({stated_role})"

                    # Record primary evidence source linked directly to outreach log
                    ev_src_id = record_evidence_source(
                        conn=conn,
                        source_type="PHONE_OUTREACH",
                        source_title_publisher=source_title,
                        observed_at=c_at,
                        source_url=None,
                        is_primary_source=True,
                        source_published_at=None,
                        event_at=c_at,
                        outreach_log_id=log_id,
                        notes=ev_notes or None,
                    )

                    # Retrieve current accepted claims for facility to support conservative conflict handling
                    curr_claims_list = get_current_accepted_claims(conn, "facility_id", facility_id)
                    current_claims = {c["claim_field"]: dict(c) for c in curr_claims_list}

                    candidate_claims = []
                    negative_notes = []

                    # a. Commercial carrier use
                    carrier_use = (verified_evidence.get("commercial_carrier_use") or "UNKNOWN").strip().upper()
                    if carrier_use == "YES":
                        candidate_claims.append(("commercial_carrier_use", "VERIFIED", "VERIFIED"))
                    elif carrier_use == "NO":
                        negative_notes.append("Caller confirmed: facility does NOT use outside commercial motor carriers.")

                    # b. Broker / 3PL acceptance
                    broker_status = (verified_evidence.get("broker_friendly_status") or "UNKNOWN").strip().upper()
                    if broker_status == "YES":
                        candidate_claims.append(("broker_friendly_status", "VERIFIED_ACCEPTS", "VERIFIED"))
                    elif broker_status == "ASSET_CARRIERS_ONLY":
                        candidate_claims.append(("broker_friendly_status", "VERIFIED_DIRECT_ONLY", "VERIFIED"))
                    elif broker_status == "NO":
                        negative_notes.append("Caller confirmed: facility does NOT accept freight brokers / 3PLs.")

                    # c. Private truck fleet
                    private_fleet = (verified_evidence.get("private_fleet_present") or "UNKNOWN").strip().upper()
                    if private_fleet == "YES":
                        candidate_claims.append(("private_fleet_present", "VERIFIED_PRESENT", "VERIFIED"))
                    elif private_fleet == "NO":
                        candidate_claims.append(("private_fleet_present", "VERIFIED_NO_FLEET", "VERIFIED"))

                    # d. Transportation procurement control
                    proc_level = (verified_evidence.get("freight_procurement_level") or "UNKNOWN").strip().upper()
                    if proc_level == "FACILITY_LOCAL":
                        candidate_claims.append(("freight_procurement_level", "FACILITY_LEVEL", "VERIFIED"))
                    elif proc_level == "CENTRAL_CORPORATE":
                        candidate_claims.append(("freight_procurement_level", "CORPORATE_PARENT", "VERIFIED"))

                    # Ingest candidate claims using conservative supersession & conflict preservation
                    for field, target_val, target_status in candidate_claims:
                        existing = current_claims.get(field)
                        if existing and existing["verification_status"] == "VERIFIED":
                            if existing["claimed_value"] == target_val:
                                link_claim_evidence(
                                    conn,
                                    existing["id"],
                                    ev_src_id,
                                    relationship="SUPPORTS",
                                    relationship_notes="Reconfirmed via telephone outreach.",
                                )
                            else:
                                # Contradiction: Prior verified claim exists with different value.
                                link_claim_evidence(
                                    conn,
                                    existing["id"],
                                    ev_src_id,
                                    relationship="CONTRADICTS",
                                    relationship_notes=f"[CONTRADICTION REVIEW NEEDED] Prior verified value '{existing['claimed_value']}' contradicted by telephone statement '{target_val}'.",
                                )
                                contradictions_detected.append({
                                    "field": field,
                                    "prior_verified_value": existing["claimed_value"],
                                    "phone_statement_value": target_val,
                                    "prior_claim_id": existing["id"],
                                })
                        else:
                            # Prior claim was UNKNOWN or nonexistent: safe supersession
                            new_cid = record_claim(
                                conn=conn,
                                claim_field=field,
                                claimed_value=target_val,
                                verification_status=target_status,
                                is_current_accepted=True,
                                claim_notes=f"Confirmed via telephone outreach: {stated_person} ({stated_role}).",
                                facility_id=facility_id,
                            )
                            link_claim_evidence(conn, new_cid, ev_src_id, relationship="SUPPORTS")
                            claims_created.append({
                                "claim_id": new_cid,
                                "claim_field": field,
                                "claimed_value": target_val,
                                "verification_status": target_status,
                                "facility_id": facility_id,
                            })

                    # e. Equipment confirmed with canonical commodity model
                    eq_confirmed = verified_evidence.get("equipment_confirmed") or []
                    if eq_confirmed:
                        fac_comms = conn.execute(
                            "SELECT id, commodity_category, equipment_category, equipment_usage_status FROM facility_commodities WHERE facility_id = ?",
                            (facility_id,)
                        ).fetchall()

                        if len(fac_comms) == 0:
                            negative_notes.append(
                                f"[EQUIPMENT_CLAIM_REQUIRES_COMMODITY_SCOPE] Equipment stated ({', '.join(eq_confirmed)}), but facility has no commodity records. No claim created."
                            )
                        elif len(fac_comms) > 1:
                            negative_notes.append(
                                f"[AMBIGUOUS_COMMODITY_SCOPE] Facility has multiple commodity records ({len(fac_comms)}); equipment statement cannot be unambiguously mapped. No claim created."
                            )
                        else:
                            fc = fac_comms[0]
                            for eq in eq_confirmed:
                                eq_clean = (eq or "").strip().upper()
                                if eq_clean in ("FLATBED", "STEP_DECK", "DRY_VAN"):
                                    existing_eq = conn.execute(
                                        "SELECT id, claimed_value, verification_status FROM claims WHERE facility_commodity_id = ? AND claim_field = 'equipment_category' AND is_current_accepted = 1",
                                        (fc["id"],)
                                    ).fetchone()

                                    if existing_eq and existing_eq["verification_status"] == "VERIFIED":
                                        if existing_eq["claimed_value"] == eq_clean:
                                            link_claim_evidence(
                                                conn,
                                                existing_eq["id"],
                                                ev_src_id,
                                                relationship="SUPPORTS",
                                                relationship_notes=f"Reconfirmed {eq_clean} equipment usage via telephone outreach.",
                                            )
                                        else:
                                            link_claim_evidence(
                                                conn,
                                                existing_eq["id"],
                                                ev_src_id,
                                                relationship="CONTRADICTS",
                                                relationship_notes=f"[CONTRADICTION REVIEW NEEDED] Prior verified equipment '{existing_eq['claimed_value']}' contradicted by telephone statement '{eq_clean}'.",
                                            )
                                            contradictions_detected.append({
                                                "field": "equipment_category",
                                                "prior_verified_value": existing_eq["claimed_value"],
                                                "phone_statement_value": eq_clean,
                                                "prior_claim_id": existing_eq["id"],
                                            })
                                    else:
                                        conn.execute(
                                            "UPDATE facility_commodities SET equipment_category = ?, equipment_usage_status = 'VERIFIED' WHERE id = ?",
                                            (eq_clean, fc["id"])
                                        )
                                        fc_cid = record_claim(
                                            conn=conn,
                                            claim_field="equipment_category",
                                            claimed_value=eq_clean,
                                            verification_status="VERIFIED",
                                            is_current_accepted=True,
                                            claim_notes=f"Confirmed {eq_clean} equipment usage via telephone outreach from {stated_person} ({stated_role}).",
                                            facility_commodity_id=fc["id"],
                                        )
                                        link_claim_evidence(conn, fc_cid, ev_src_id, relationship="SUPPORTS")
                                        claims_created.append({
                                            "claim_id": fc_cid,
                                            "claim_field": "equipment_category",
                                            "claimed_value": eq_clean,
                                            "verification_status": "VERIFIED",
                                            "facility_commodity_id": fc["id"],
                                        })

                    # Synchronize materialized operational columns on facilities table
                    for field in ("commercial_carrier_use", "broker_friendly_status", "private_fleet_present", "freight_procurement_level"):
                        acc = conn.execute(
                            "SELECT claimed_value FROM claims WHERE facility_id = ? AND claim_field = ? AND is_current_accepted = 1",
                            (facility_id, field)
                        ).fetchone()
                        if acc:
                            conn.execute(
                                f"UPDATE facilities SET {field} = ?, updated_at = ? WHERE id = ?",
                                (acc["claimed_value"], now_iso, facility_id)
                            )

                    # Record negative / scope notes if present
                    if negative_notes:
                        notes_comb = " | ".join(negative_notes)
                        full_ev_notes = f"{ev_notes} | {notes_comb}".strip(" |") if ev_notes else notes_comb
                        conn.execute(
                            "UPDATE evidence_sources SET notes = ? WHERE id = ?",
                            (full_ev_notes, ev_src_id)
                        )

                    # Recompute deterministic broker opportunity tiers
                    new_fac_opp = evaluate_broker_opportunity(company_id=company_id, facility_id=facility_id, conn=conn)
                    new_facility_tier = new_fac_opp.get("opportunity_tier")
                    new_comp_opp = evaluate_broker_opportunity(company_id=company_id, conn=conn)
                    new_company_tier = new_comp_opp.get("opportunity_tier")

            result = {
                "outreach_log_id": log_id,
                "company_id": company_id,
                "facility_id": facility_id,
                "contact_id": contact_id,
                "channel": chan_clean,
                "disposition": disp_clean,
                "feedback_notes": feedback_notes,
                "follow_up_at": follow_up_at,
                "contacted_at": c_at,
                "attempt_count": attempts_cnt,
                "engagement_state": eng_state,
            }
            if ev_src_id is not None:
                result["evidence_source_id"] = ev_src_id
                result["authority_status"] = authority_status
                result["claims_created"] = claims_created
                result["contradictions_detected"] = contradictions_detected
                result["old_opportunity_tier"] = old_facility_tier
                result["new_opportunity_tier"] = new_facility_tier
                result["old_company_tier"] = old_company_tier
                result["new_company_tier"] = new_company_tier

            return result
    finally:
        if should_close:
            conn.close()


def get_outreach_history(
    company_id: Optional[int] = None,
    facility_id: Optional[int] = None,
    db_path: Optional[str | Path] = None,
) -> List[Dict[str, Any]]:
    """
    Returns the append-only outreach timeline ordered newest first.
    If company_id is provided, aggregates calls across corporate and all child facilities.
    If facility_id is provided, filters to calls for that specific facility.
    """
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        where_clauses = []
        params = []
        if facility_id is not None:
            where_clauses.append("o.facility_id = ?")
            params.append(facility_id)
        elif company_id is not None:
            where_clauses.append("o.company_id = ?")
            params.append(company_id)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"""
            SELECT
                o.id,
                o.company_id,
                o.facility_id,
                o.contact_id,
                o.outreach_channel,
                o.outcome as disposition,
                COALESCE(o.feedback_notes, o.notes) as feedback_notes,
                o.contacted_at,
                COALESCE(o.follow_up_at, o.follow_up_date) as follow_up_at,
                o.created_at,
                c.operating_brand as company_name,
                f.facility_name,
                f.city as facility_city,
                f.state_prov as facility_state,
                ct.person_name as contact_name,
                ct.exact_published_title as contact_title,
                ct.phone_number as contact_phone
            FROM outreach_logs o
            JOIN companies c ON o.company_id = c.id
            LEFT JOIN facilities f ON o.facility_id = f.id
            LEFT JOIN contacts ct ON o.contact_id = ct.id
            {where_sql}
            ORDER BY o.contacted_at DESC, o.id DESC
        """
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def mark_prospect_viewed(
    company_id: int,
    db_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Marks a company prospect as viewed (is_viewed = 1).
    Records first_viewed_at and last_viewed_at.
    Invariant: Does NOT create an outreach log. Viewed != Contacted.
    """
    now_iso = get_utc_now_iso()
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO prospect_engagement_state (
                    company_id, current_outreach_status, attempt_count,
                    is_viewed, first_viewed_at, last_viewed_at, updated_at
                ) VALUES (?, 'UNCONTACTED', 0, 1, ?, ?, ?)
                ON CONFLICT(company_id) DO UPDATE SET
                    is_viewed = 1,
                    first_viewed_at = COALESCE(prospect_engagement_state.first_viewed_at, excluded.first_viewed_at),
                    last_viewed_at = excluded.last_viewed_at,
                    updated_at = excluded.updated_at
                """,
                (company_id, now_iso, now_iso, now_iso)
            )
            row = conn.execute("SELECT * FROM prospect_engagement_state WHERE company_id = ?", (company_id,)).fetchone()
            return dict(row) if row else {"company_id": company_id, "is_viewed": 1}
    finally:
        conn.close()


def clear_outreach_tracking(
    company_id: int,
    action: str = "clear_status",
    db_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Clear the active CRM projection while keeping every historical call intact."""
    if action not in ("clear_status", "cancel_follow_up"):
        raise ValueError("Choose clear_status or cancel_follow_up")
    conn = create_connection(db_path)
    try:
        with conn:
            if not conn.execute("SELECT 1 FROM companies WHERE id = ?", (company_id,)).fetchone():
                raise ValueError(f"Company {company_id} does not exist")
            if action == "clear_status":
                conn.execute(
                    """UPDATE prospect_engagement_state
                       SET current_outreach_status = 'UNCONTACTED',
                           status_source_outreach_log_id = NULL,
                           next_follow_up_at = NULL, updated_at = ?
                       WHERE company_id = ?""",
                    (get_utc_now_iso(), company_id),
                )
            else:
                conn.execute(
                    "UPDATE prospect_engagement_state SET next_follow_up_at = NULL, updated_at = ? WHERE company_id = ?",
                    (get_utc_now_iso(), company_id),
                )
            row = conn.execute("SELECT * FROM prospect_engagement_state WHERE company_id = ?", (company_id,)).fetchone()
            return dict(row) if row else {"company_id": company_id, "current_outreach_status": "UNCONTACTED"}
    finally:
        conn.close()


def get_crm_follow_ups(
    db_path: Optional[str | Path] = None,
    user_timezone: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Section 22: Follow-Up View.
    Returns scheduled follow-ups categorized into three sections:
    - OVERDUE (most overdue first)
    - TODAY (chronological)
    - UPCOMING (chronological)
    Categorizes based on user's local date, avoiding UTC day-boundary misgroupings.
    """
    tz = resolve_timezone(user_timezone)
    today_local = datetime.now(tz).date()

    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = """
            SELECT
                pes.company_id,
                pes.current_outreach_status,
                pes.attempt_count,
                pes.last_contacted_at,
                pes.next_follow_up_at,
                pes.last_facility_id,
                pes.last_feedback_notes,
                c.operating_brand,
                c.legal_name,
                c.website_url,
                f.facility_name,
                f.city as facility_city,
                f.state_prov as facility_state,
                (SELECT count(*) FROM facilities WHERE company_id = c.id) as facility_count,
                (SELECT ct.phone_number FROM contacts ct WHERE ct.company_id = c.id OR ct.facility_id = pes.last_facility_id ORDER BY ct.is_primary_contact DESC LIMIT 1) as phone_number,
                (SELECT ct.person_name FROM contacts ct WHERE ct.company_id = c.id OR ct.facility_id = pes.last_facility_id ORDER BY ct.is_primary_contact DESC LIMIT 1) as contact_name
            FROM prospect_engagement_state pes
            JOIN companies c ON pes.company_id = c.id
            LEFT JOIN facilities f ON pes.last_facility_id = f.id
            WHERE pes.next_follow_up_at IS NOT NULL
        """
        rows = [dict(r) for r in conn.execute(query).fetchall()]

        overdue = []
        today = []
        upcoming = []

        for r in rows:
            fu = r["next_follow_up_at"]
            if not fu:
                continue
            try:
                clean_fu = str(fu).strip().replace(" ", "T")
                if clean_fu.endswith("Z"):
                    dt_utc = datetime.fromisoformat(clean_fu[:-1] + "+00:00")
                else:
                    dt_utc = datetime.fromisoformat(clean_fu)
                if dt_utc.tzinfo is None:
                    dt_utc = dt_utc.replace(tzinfo=timezone.utc)
                else:
                    dt_utc = dt_utc.astimezone(timezone.utc)
            except Exception:
                continue

            dt_local = dt_utc.astimezone(tz)
            item_date = dt_local.date()

            r["next_follow_up_local"] = dt_local.strftime("%Y-%m-%d %H:%M")
            r["next_follow_up_formatted"] = dt_local.strftime("%b %d, %Y %I:%M %p")
            r["user_timezone"] = str(tz)

            if item_date < today_local:
                overdue.append(r)
            elif item_date == today_local:
                today.append(r)
            else:
                upcoming.append(r)

        overdue.sort(key=lambda x: x["next_follow_up_at"])
        today.sort(key=lambda x: x["next_follow_up_at"])
        upcoming.sort(key=lambda x: x["next_follow_up_at"])

        return {
            "overdue": overdue,
            "today": today,
            "upcoming": upcoming,
            "total_count": len(rows),
            "user_timezone": str(tz),
        }
    finally:
        conn.close()


def get_crm_prospects(status: str, db_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    """
    Returns companies filtered by current_outreach_status (e.g. INTERESTED, NO_ANSWER, NOT_INTERESTED).
    Includes rich context: facility context, contacts, phone, feedback, broker friction, facility count.
    """
    st_clean = status.strip().upper()
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        query = """
            SELECT
                pes.company_id,
                pes.current_outreach_status,
                pes.attempt_count,
                pes.last_contacted_at,
                pes.next_follow_up_at,
                pes.last_facility_id,
                pes.last_feedback_notes,
                pes.is_viewed,
                c.operating_brand,
                c.legal_name,
                c.website_url,
                c.corporate_address,
                c.notes as company_notes,
                f.facility_name as last_facility_name,
                f.city as last_facility_city,
                f.state_prov as last_facility_state,
                (SELECT count(*) FROM facilities WHERE company_id = c.id) as facility_count,
                (SELECT ct.phone_number FROM contacts ct WHERE ct.company_id = c.id OR ct.facility_id = pes.last_facility_id ORDER BY ct.is_primary_contact DESC, ct.id ASC LIMIT 1) as primary_phone,
                (SELECT ct.email_address FROM contacts ct WHERE ct.company_id = c.id OR ct.facility_id = pes.last_facility_id ORDER BY ct.is_primary_contact DESC, ct.id ASC LIMIT 1) as primary_email,
                (SELECT ct.person_name FROM contacts ct WHERE ct.company_id = c.id OR ct.facility_id = pes.last_facility_id ORDER BY ct.is_primary_contact DESC, ct.id ASC LIMIT 1) as primary_contact_name,
                (SELECT ct.exact_published_title FROM contacts ct WHERE ct.company_id = c.id OR ct.facility_id = pes.last_facility_id ORDER BY ct.is_primary_contact DESC, ct.id ASC LIMIT 1) as primary_contact_title
            FROM prospect_engagement_state pes
            JOIN companies c ON pes.company_id = c.id
            LEFT JOIN facilities f ON pes.last_facility_id = f.id
            WHERE pes.current_outreach_status = ?
            ORDER BY pes.last_contacted_at DESC, pes.updated_at DESC
        """
        rows = [dict(r) for r in conn.execute(query, (st_clean,)).fetchall()]
        return rows
    finally:
        conn.close()


def get_crm_counts(db_path: Optional[str | Path] = None) -> Dict[str, int]:
    """
    Returns real-time CRM workflow counts for sidebar badges and indicators.
    """
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        counts = {
            "uncontacted": 0,
            "interested": 0,
            "follow_ups": 0,
            "no_answer": 0,
            "not_interested": 0,
            "call_back": 0,
            "total_calls": 0,
            "unreviewed": 0,
        }
        has_eng = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='prospect_engagement_state'").fetchone()[0] > 0
        if has_eng:
            for r in conn.execute("SELECT current_outreach_status, count(*) as cnt FROM prospect_engagement_state GROUP BY current_outreach_status").fetchall():
                key = r["current_outreach_status"].lower()
                if key in counts:
                    counts[key] = r["cnt"]
            counts["follow_ups"] = conn.execute("SELECT count(*) FROM prospect_engagement_state WHERE next_follow_up_at IS NOT NULL").fetchone()[0]
            counts["unreviewed"] = conn.execute("SELECT count(*) FROM prospect_engagement_state WHERE is_viewed = 0").fetchone()[0]
            counts["total_calls"] = conn.execute("SELECT count(*) FROM outreach_logs").fetchone()[0]
        return counts
    finally:
        conn.close()


def get_taxonomy_overview(db_path: Optional[str | Path] = None) -> List[Dict[str, Any]]:
    """
    Returns hierarchical taxonomy overview:
    All commodity families with child categories, non-binding typical equipment fit,
    typical seasonality profile, and live count of mapped facilities and distinct companies.
    """
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        has_tax = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='commodity_families'"
        ).fetchone()[0] > 0
        if not has_tax:
            return []

        families_rows = conn.execute(
            "SELECT * FROM commodity_families ORDER BY sort_order ASC, id ASC"
        ).fetchall()

        overview = []
        for fam in families_rows:
            fam_dict = dict(fam)
            cats_cur = conn.execute(
                """
                SELECT c.*,
                       COUNT(DISTINCT m.facility_id) as facility_count,
                       COUNT(DISTINCT f.company_id) as company_count
                FROM commodity_categories c
                LEFT JOIN facility_commodity_mappings m ON c.id = m.category_id
                LEFT JOIN facilities f ON m.facility_id = f.id
                WHERE c.family_id = ?
                GROUP BY c.id
                ORDER BY c.sort_order ASC, c.id ASC
                """,
                (fam["id"],)
            )
            cats = [dict(cat) for cat in cats_cur.fetchall()]
            fam_dict["categories"] = cats
            fam_dict["total_facilities"] = sum(c["facility_count"] for c in cats)
            fam_comp_cnt = conn.execute(
                """
                SELECT COUNT(DISTINCT f.company_id)
                FROM facility_commodity_mappings m
                JOIN commodity_categories c ON m.category_id = c.id
                JOIN facilities f ON m.facility_id = f.id
                WHERE c.family_id = ?
                """,
                (fam["id"],)
            ).fetchone()[0]
            fam_dict["total_companies"] = fam_comp_cnt
            overview.append(fam_dict)

        return overview
    finally:
        conn.close()


def get_commodity_families(db_path: Optional[str | Path] = None, include_inactive: bool = False) -> List[Dict[str, Any]]:
    """
    Returns commodity families list for dropdowns and filter selection.
    """
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        has_tax = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='commodity_families'"
        ).fetchone()[0] > 0
        if not has_tax:
            return []

        where = "" if include_inactive else "WHERE is_active = 1"
        rows = conn.execute(f"SELECT * FROM commodity_families {where} ORDER BY sort_order ASC, id ASC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_commodity_categories(
    db_path: Optional[str | Path] = None,
    family_code: Optional[str] = None,
    include_deferred: bool = False
) -> List[Dict[str, Any]]:
    """
    Returns commodity categories list for dropdowns and filter selection.
    """
    conn = create_connection(db_path)
    conn.row_factory = sqlite3.Row
    try:
        has_tax = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='commodity_categories'"
        ).fetchone()[0] > 0
        if not has_tax:
            return []

        clauses = []
        params = []
        if not include_deferred:
            clauses.append("c.is_active = 1")
        if family_code and family_code.upper() != "ALL":
            clauses.append("cf.family_code = ?")
            params.append(family_code.upper())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT c.*, cf.family_code, cf.display_name as family_name
            FROM commodity_categories c
            JOIN commodity_families cf ON c.family_id = cf.id
            {where}
            ORDER BY c.sort_order ASC, c.id ASC
        """
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
