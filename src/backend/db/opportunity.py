"""
FreightProspecting V1 — Deterministic Broker Opportunity Engine
Rule Version: 1.1 (BROKER_OPPORTUNITY_RULE_VERSION = "1.1")

Separates Research Readiness (Lifecycle) from Broker Opportunity (Call Priority).
Calculates derived opportunity tiers at query time with zero database mutations,
preserving raw source evidence and provenance ledger integrity.

Enforces real-world freight brokerage reality:
- Private fleet is NOT an automatic disqualification.
- UNKNOWN private fleet is NEVER "no fleet" (absence of evidence != evidence of absence).
- Commercial carrier use != broker acceptance.
- UNKNOWN carrier use is NEVER "does not use outside carriers".
- UNKNOWN broker acceptance is NEVER "refuses brokers".
- Private fleet verified + commercial carrier verified can remain Tier A Priority Prospect.
"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Set

BROKER_OPPORTUNITY_RULE_VERSION = "1.1"

# Target Broker Opportunity Tiers
TIER_A_PRIORITY = "TIER_A_PRIORITY"           # Frontend: "Priority Prospect"
TIER_B_WORTH_CALLING = "TIER_B_WORTH_CALLING"   # Frontend: "Worth Calling"
TIER_C_SECONDARY = "TIER_C_SECONDARY"           # Frontend: "Secondary Prospect"
TIER_D_RESEARCH_NEEDED = "TIER_D_RESEARCH_NEEDED" # Frontend: "Needs More Research"
RESTRICTED = "RESTRICTED"                       # Frontend: "Restricted"

TIER_LABELS = {
    TIER_A_PRIORITY: "Priority Prospect",
    TIER_B_WORTH_CALLING: "Worth Calling",
    TIER_C_SECONDARY: "Secondary Prospect",
    TIER_D_RESEARCH_NEEDED: "Needs More Research",
    RESTRICTED: "Restricted",
}

TIER_DESCRIPTIONS = {
    TIER_A_PRIORITY: "Strong evidence of outside transportation capacity & ready to contact",
    TIER_B_WORTH_CALLING: "Plausible FTL fit & callable route; outside carrier use unconfirmed",
    TIER_C_SECONDARY: "Own trucks confirmed • Use of outside carriers not confirmed",
    TIER_D_RESEARCH_NEEDED: "Important research facts missing or evidence verification pending",
    RESTRICTED: "Do Not Contact, active corporate suppression, or verified direct-only policy",
}

# Honest UNKNOWN wording constants (Zero-hallucination compliance)
UNKNOWN_FLEET_TEXT = "Own trucks not confirmed"
UNKNOWN_CARRIER_TEXT = "Outside carrier use not confirmed"
UNKNOWN_BROKER_TEXT = "Broker use not confirmed"


def evaluate_broker_opportunity_raw(
    private_fleet_present: str = "UNKNOWN",
    commercial_carrier_use: str = "UNKNOWN",
    broker_friendly_status: str = "UNKNOWN",
    lifecycle_stage: str = "DISCOVERY",
    has_callable_route: bool = True,
    has_ftl_fit: bool = True,
    suppression_status: Optional[str] = None,
    direct_contact_role: Optional[str] = None,
    direct_contact_directness: Optional[str] = None,
    is_lane_suppression_only: bool = False,
) -> Dict[str, Any]:
    """
    Pure deterministic functional evaluation of broker opportunity tier.
    Accepts explicit raw parameters for unit testability and query-time calculation.
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Check Restrictions (DNC, Company/Facility Suppression, Direct-Only Policy)
    # Note: Lane-only restrictions do NOT disqualify the company globally.
    if suppression_status == "DO_NOT_CONTACT" and not is_lane_suppression_only:
        return {
            "opportunity_tier": RESTRICTED,
            "frontend_label": TIER_LABELS[RESTRICTED],
            "description": TIER_DESCRIPTIONS[RESTRICTED],
            "reason_codes": ["RESTRICTED_DO_NOT_CONTACT"],
            "positive_facts": [],
            "counter_factors": ["Company marked Do Not Contact (DNC)"],
            "unknowns": [],
            "restricted_reason": "Company or facility is marked DO_NOT_CONTACT in suppressions.",
            "rule_version": BROKER_OPPORTUNITY_RULE_VERSION,
            "evaluated_at": now_iso,
            "has_strong_opportunity_signal": False,
            "is_actionable": False,
        }

    if broker_friendly_status == "VERIFIED_DIRECT_ONLY":
        return {
            "opportunity_tier": RESTRICTED,
            "frontend_label": TIER_LABELS[RESTRICTED],
            "description": TIER_DESCRIPTIONS[RESTRICTED],
            "reason_codes": ["RESTRICTED_DIRECT_ONLY_POLICY"],
            "positive_facts": ["Operating facility verified"],
            "counter_factors": ["Verified company policy: asset carriers direct only (no brokers)"],
            "unknowns": [],
            "restricted_reason": "Verified direct-only broker procurement policy.",
            "rule_version": BROKER_OPPORTUNITY_RULE_VERSION,
            "evaluated_at": now_iso,
            "has_strong_opportunity_signal": False,
            "is_actionable": False,
        }

    # 2. Check Actionable Readiness (Usable contact route)
    # If no callable phone or email exists, cannot be Tier A or Tier B
    if not has_callable_route:
        pos = []
        if has_ftl_fit:
            pos.append("Relevant FTL equipment fit")
        if commercial_carrier_use == "VERIFIED":
            pos.append("Outside carrier use confirmed (VERIFIED)")
        if broker_friendly_status == "VERIFIED_ACCEPTS":
            pos.append("Broker acceptance explicitly confirmed (VERIFIED)")

        return {
            "opportunity_tier": TIER_D_RESEARCH_NEEDED,
            "frontend_label": TIER_LABELS[TIER_D_RESEARCH_NEEDED],
            "description": TIER_DESCRIPTIONS[TIER_D_RESEARCH_NEEDED],
            "reason_codes": ["RESEARCH_NEEDED_NO_CALLABLE_ROUTE"],
            "positive_facts": pos,
            "counter_factors": ["No callable phone or email outreach route available"],
            "unknowns": ["Direct contact route unconfirmed"],
            "restricted_reason": None,
            "rule_version": BROKER_OPPORTUNITY_RULE_VERSION,
            "evaluated_at": now_iso,
            "has_strong_opportunity_signal": (commercial_carrier_use == "VERIFIED" or broker_friendly_status == "VERIFIED_ACCEPTS"),
            "is_actionable": False,
        }

    # 3. Assess Opportunity Signal vs Research Completeness
    is_ready_stage = lifecycle_stage in ("SHORTLISTED", "QUALIFIED")
    has_carrier_verified = (commercial_carrier_use == "VERIFIED")
    has_broker_verified = (broker_friendly_status == "VERIFIED_ACCEPTS")
    has_fleet_verified = (private_fleet_present == "VERIFIED_PRESENT")

    # Positive facts construction
    positive_facts = []
    if has_broker_verified:
        positive_facts.append("Broker acceptance explicitly confirmed (VERIFIED)")
    if has_carrier_verified:
        positive_facts.append("Outside carrier use confirmed (VERIFIED)")
    if has_fleet_verified and has_carrier_verified:
        positive_facts.append("Own trucks confirmed; outside carrier use also confirmed.")
    if has_ftl_fit:
        positive_facts.append("Target FTL equipment fit")
    if has_callable_route:
        positive_facts.append("Callable outreach route verified")

    # Contactability signal (secondary differentiator, does NOT invent capacity evidence)
    if direct_contact_role == "FREIGHT_LOGISTICS":
        if direct_contact_directness == "DIRECT_PERSON":
            positive_facts.append("Direct logistics manager / decision maker verified")
        else:
            positive_facts.append("Shipping / logistics desk contact verified")
    elif direct_contact_role == "COMMERCIAL_SALES":
        positive_facts.append("Commercial sales contact route verified")

    # Unknowns list construction (honest wording)
    unknowns = []
    if not has_broker_verified:
        unknowns.append(UNKNOWN_BROKER_TEXT)
    if not has_carrier_verified:
        unknowns.append(UNKNOWN_CARRIER_TEXT)
    if not has_fleet_verified and private_fleet_present != "VERIFIED_NO_FLEET":
        unknowns.append(UNKNOWN_FLEET_TEXT)

    # CASE A: Strong External Opportunity Evidence (Carrier verified OR Broker accepted)
    if has_carrier_verified or has_broker_verified:
        if is_ready_stage:
            # TIER A: Priority Prospect!
            reason_codes = ["VERIFIED_EXTERNAL_CAPACITY_READY"]
            if has_broker_verified:
                reason_codes.append("BROKER_ACCEPTANCE_CONFIRMED")
            if has_carrier_verified:
                reason_codes.append("COMMERCIAL_CARRIER_CONFIRMED")
            if has_fleet_verified:
                reason_codes.append("PRIVATE_FLEET_AND_CARRIER_CONFIRMED")

            return {
                "opportunity_tier": TIER_A_PRIORITY,
                "frontend_label": TIER_LABELS[TIER_A_PRIORITY],
                "description": TIER_DESCRIPTIONS[TIER_A_PRIORITY],
                "reason_codes": reason_codes,
                "positive_facts": positive_facts,
                "counter_factors": [],
                "unknowns": unknowns,
                "restricted_reason": None,
                "rule_version": BROKER_OPPORTUNITY_RULE_VERSION,
                "evaluated_at": now_iso,
                "has_strong_opportunity_signal": True,
                "is_actionable": True,
            }
        else:
            # Strong opportunity signal, but research incomplete (in Discovery pool)
            return {
                "opportunity_tier": TIER_D_RESEARCH_NEEDED,
                "frontend_label": TIER_LABELS[TIER_D_RESEARCH_NEEDED],
                "description": TIER_DESCRIPTIONS[TIER_D_RESEARCH_NEEDED],
                "reason_codes": ["STRONG_OPPORTUNITY_RESEARCH_INCOMPLETE"],
                "positive_facts": positive_facts,
                "counter_factors": ["Research incomplete (in Discovery pool / Pending evidence verification)"],
                "unknowns": unknowns + ["Full qualification verification pending"],
                "restricted_reason": None,
                "rule_version": BROKER_OPPORTUNITY_RULE_VERSION,
                "evaluated_at": now_iso,
                "has_strong_opportunity_signal": True,
                "is_actionable": False,
            }

    # CASE B: Discovery Pool without carrier evidence -> TIER D (Needs More Research)
    if not is_ready_stage:
        return {
            "opportunity_tier": TIER_D_RESEARCH_NEEDED,
            "frontend_label": TIER_LABELS[TIER_D_RESEARCH_NEEDED],
            "description": TIER_DESCRIPTIONS[TIER_D_RESEARCH_NEEDED],
            "reason_codes": ["DISCOVERY_RESEARCH_INCOMPLETE"],
            "positive_facts": ["Operating facility in US/Canada", "FTL freight fit"],
            "counter_factors": ["Research incomplete in Discovery pool"],
            "unknowns": unknowns,
            "restricted_reason": None,
            "rule_version": BROKER_OPPORTUNITY_RULE_VERSION,
            "evaluated_at": now_iso,
            "has_strong_opportunity_signal": False,
            "is_actionable": False,
        }

    # CASE C: Ready to Contact + Private Fleet Verified + Carrier Use Unknown -> TIER C (Secondary Prospect)
    if has_fleet_verified:
        return {
            "opportunity_tier": TIER_C_SECONDARY,
            "frontend_label": TIER_LABELS[TIER_C_SECONDARY],
            "description": TIER_DESCRIPTIONS[TIER_C_SECONDARY],
            "reason_codes": ["PRIVATE_FLEET_CARRIER_UNKNOWN"],
            "positive_facts": positive_facts,
            "counter_factors": [
                "Own trucks confirmed",
                "Use of outside carriers not confirmed",
            ],
            "unknowns": unknowns,
            "restricted_reason": None,
            "rule_version": BROKER_OPPORTUNITY_RULE_VERSION,
            "evaluated_at": now_iso,
            "has_strong_opportunity_signal": False,
            "is_actionable": True,
        }

    # CASE D: Ready to Contact + Fleet Unknown + Carrier Unknown -> TIER B (Worth Calling)
    return {
        "opportunity_tier": TIER_B_WORTH_CALLING,
        "frontend_label": TIER_LABELS[TIER_B_WORTH_CALLING],
        "description": TIER_DESCRIPTIONS[TIER_B_WORTH_CALLING],
        "reason_codes": ["CALLABLE_OPPORTUNITY_UNCONFIRMED"],
        "positive_facts": positive_facts,
        "counter_factors": [],
        "unknowns": unknowns,
        "restricted_reason": None,
        "rule_version": BROKER_OPPORTUNITY_RULE_VERSION,
        "evaluated_at": now_iso,
        "has_strong_opportunity_signal": False,
        "is_actionable": True,
    }


def evaluate_company_opportunity_from_context(
    company_id: int,
    facilities: List[Dict[str, Any]],
    contacts: List[Dict[str, Any]],
    ftl_facility_ids: Set[int],
    is_dnc: bool = False,
    suppression_status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministic pure evaluation of broker opportunity for a company from in-memory context.
    Operates with ZERO SQL queries. Single source of truth across engine, metadata, and directory.
    """
    supp_status = "DO_NOT_CONTACT" if is_dnc else suppression_status

    if not facilities:
        return evaluate_broker_opportunity_raw(
            has_callable_route=False,
            has_ftl_fit=False,
            lifecycle_stage="DISCOVERY",
            suppression_status=supp_status,
        )

    # Mixed-facility partition:
    # A company is RESTRICTED only if all active/ready operating facilities are VERIFIED_DIRECT_ONLY
    # (or if a company-level restriction exists). When mixed, non-restricted facilities determine opportunity.
    active_fac_rows = [f for f in facilities if f.get("broker_friendly_status") != "VERIFIED_DIRECT_ONLY"]
    if not active_fac_rows:
        c_broker = "VERIFIED_DIRECT_ONLY"
        eval_facs = facilities
    else:
        eval_facs = active_fac_rows
        broker_statuses = {f.get("broker_friendly_status") for f in eval_facs}
        if "VERIFIED_ACCEPTS" in broker_statuses:
            c_broker = "VERIFIED_ACCEPTS"
        else:
            c_broker = "UNKNOWN"

    fleet_statuses = {f.get("private_fleet_present") for f in eval_facs}
    c_fleet = "VERIFIED_PRESENT" if "VERIFIED_PRESENT" in fleet_statuses else ("VERIFIED_NO_FLEET" if "VERIFIED_NO_FLEET" in fleet_statuses else "UNKNOWN")

    carrier_statuses = {f.get("commercial_carrier_use") for f in eval_facs}
    c_carrier = "VERIFIED" if "VERIFIED" in carrier_statuses else "UNKNOWN"

    stages = {f.get("stage") or f.get("lifecycle_stage") for f in eval_facs if (f.get("stage") or f.get("lifecycle_stage"))}
    if "SHORTLISTED" in stages:
        c_stage = "SHORTLISTED"
    elif "QUALIFIED" in stages:
        c_stage = "QUALIFIED"
    elif "DISCOVERY" in stages:
        c_stage = "DISCOVERY"
    else:
        c_stage = "ARCHIVED"

    has_callable = any(
        (c.get("phone_number") and str(c["phone_number"]).strip()) or
        (c.get("email_address") and str(c["email_address"]).strip())
        for c in contacts
    )

    best_role = None
    best_dir = None
    for c in contacts:
        if c.get("role_category") == "FREIGHT_LOGISTICS":
            best_role = "FREIGHT_LOGISTICS"
            best_dir = c.get("phone_directness")
            break
        elif c.get("role_category") == "COMMERCIAL_SALES" and not best_role:
            best_role = "COMMERCIAL_SALES"
            best_dir = c.get("phone_directness")

    fac_ids = set(f.get("id") or f.get("facility_id") for f in facilities)
    has_ftl = any(fid in ftl_facility_ids for fid in fac_ids)

    return evaluate_broker_opportunity_raw(
        private_fleet_present=c_fleet,
        commercial_carrier_use=c_carrier,
        broker_friendly_status=c_broker,
        lifecycle_stage=c_stage,
        has_callable_route=has_callable,
        has_ftl_fit=has_ftl,
        suppression_status=supp_status,
        direct_contact_role=best_role,
        direct_contact_directness=best_dir,
        is_lane_suppression_only=False,
    )


def load_opportunity_universe_context(
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """
    Bulk-loads all suppression, facility, contact, and commodity facts across the entire universe
    and evaluates opportunity for all operating companies in memory. Runs exactly 4 SQL queries.
    """
    from collections import defaultdict
    from src.backend.db.connection import create_connection

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
        # 1. Suppressions
        supp_rows = conn.execute("""
            SELECT scope_type, company_id, facility_id, suppression_status
            FROM suppressions
            WHERE suppression_status = 'DO_NOT_CONTACT'
        """).fetchall()
        dnc_companies = set()
        dnc_facilities = set()
        for s in supp_rows:
            if s["scope_type"] == "COMPANY" and s["company_id"]:
                dnc_companies.add(s["company_id"])
            elif s["scope_type"] == "FACILITY" and s["facility_id"]:
                dnc_facilities.add(s["facility_id"])

        # 2. Facilities + Lifecycle
        fac_rows = conn.execute("""
            SELECT f.id, f.company_id, f.facility_name, f.private_fleet_present, f.fleet_relationship_type,
                   f.commercial_carrier_use, f.broker_friendly_status, pl.stage
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            ORDER BY f.company_id, f.id
        """).fetchall()
        facs_by_comp = defaultdict(list)
        for f in fac_rows:
            facs_by_comp[f["company_id"]].append(dict(f))

        # 3. Contacts
        ct_rows = conn.execute("""
            SELECT id, company_id, facility_id, role_category, phone_directness, phone_number, email_address
            FROM contacts
        """).fetchall()
        cts_by_comp = defaultdict(list)
        cts_by_fac = defaultdict(list)
        for c in ct_rows:
            cd = dict(c)
            if c["company_id"]:
                cts_by_comp[c["company_id"]].append(cd)
            if c["facility_id"]:
                cts_by_fac[c["facility_id"]].append(cd)

        # 4. Commodities
        comm_rows = conn.execute("""
            SELECT DISTINCT fc.facility_id, fc.equipment_category
            FROM facility_commodities fc
            WHERE fc.equipment_category IN ('FLATBED', 'STEP_DECK', 'DRY_VAN')
        """).fetchall()
        ftl_facility_ids = set(r["facility_id"] for r in comm_rows)

        company_evaluations: Dict[int, Dict[str, Any]] = {}
        tier_company_ids: Dict[str, List[int]] = {
            TIER_A_PRIORITY: [],
            TIER_B_WORTH_CALLING: [],
            TIER_C_SECONDARY: [],
            TIER_D_RESEARCH_NEEDED: [],
            RESTRICTED: [],
        }
        company_contexts: Dict[int, Dict[str, Any]] = {}

        all_comp_ids = sorted(list(facs_by_comp.keys()))
        for cid in all_comp_ids:
            facs = facs_by_comp[cid]
            fac_ids = set(f["id"] for f in facs)

            comp_cts = list(cts_by_comp.get(cid, []))
            for fid in fac_ids:
                comp_cts.extend(cts_by_fac.get(fid, []))
            seen_ids = set()
            unique_cts = []
            for ct in comp_cts:
                if ct["id"] not in seen_ids:
                    seen_ids.add(ct["id"])
                    unique_cts.append(ct)

            is_dnc = (cid in dnc_companies) or (len(fac_ids) > 0 and fac_ids.issubset(dnc_facilities))

            res = evaluate_company_opportunity_from_context(
                company_id=cid,
                facilities=facs,
                contacts=unique_cts,
                ftl_facility_ids=ftl_facility_ids,
                is_dnc=is_dnc,
            )

            company_evaluations[cid] = res
            tier = res["opportunity_tier"]
            tier_company_ids[tier].append(cid)
            company_contexts[cid] = {
                "company_id": cid,
                "facilities": facs,
                "contacts": unique_cts,
                "is_dnc": is_dnc,
                "ftl_facility_ids": ftl_facility_ids,
                "evaluation": res,
            }

        return {
            "company_evaluations": company_evaluations,
            "tier_company_ids": tier_company_ids,
            "company_contexts": company_contexts,
        }
    finally:
        if should_close:
            conn.close()
        elif orig_row_factory is not None:
            conn.row_factory = orig_row_factory


def evaluate_broker_opportunity(
    company_id: int,
    facility_id: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str | Path] = None,
    universe_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Evaluates broker opportunity for a company (or specific facility) from live database facts.
    READ-ONLY: Performs zero mutations.
    """
    if facility_id is None and universe_context and "company_evaluations" in universe_context:
        if company_id in universe_context["company_evaluations"]:
            return universe_context["company_evaluations"][company_id]

    from src.backend.db.connection import create_connection

    should_close = False
    if conn is None:
        conn = create_connection(db_path)
        should_close = True

    old_row_factory = conn.row_factory
    conn.row_factory = sqlite3.Row

    try:
        if facility_id:
            # Specific facility evaluation
            supp_rows = conn.execute("""
                SELECT scope_type, suppression_status, reason_notes
                FROM suppressions
                WHERE (scope_type = 'COMPANY' AND company_id = ?)
                   OR (scope_type = 'FACILITY' AND facility_id = ?)
            """, (company_id, facility_id)).fetchall()

            supp_status = None
            for s in supp_rows:
                if s["suppression_status"] == "DO_NOT_CONTACT":
                    supp_status = "DO_NOT_CONTACT"
                    break

            fac_rows = conn.execute("""
                SELECT f.id, f.private_fleet_present, f.fleet_relationship_type,
                       f.commercial_carrier_use, f.broker_friendly_status,
                       pl.stage
                FROM facilities f
                LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
                WHERE f.id = ? AND f.company_id = ?
            """, (facility_id, company_id)).fetchall()

            if not fac_rows:
                return evaluate_broker_opportunity_raw(
                    has_callable_route=False,
                    has_ftl_fit=False,
                    lifecycle_stage="DISCOVERY",
                    suppression_status=supp_status
                )

            f_row = fac_rows[0]
            contact_rows = conn.execute("""
                SELECT id, role_category, phone_directness, phone_number, email_address
                FROM contacts
                WHERE facility_id = ?
            """, (facility_id,)).fetchall()

            has_callable = any(
                (c["phone_number"] and str(c["phone_number"]).strip()) or
                (c["email_address"] and str(c["email_address"]).strip())
                for c in contact_rows
            )

            best_role = None
            best_dir = None
            for c in contact_rows:
                if c["role_category"] == "FREIGHT_LOGISTICS":
                    best_role = "FREIGHT_LOGISTICS"
                    best_dir = c["phone_directness"]
                    break
                elif c["role_category"] == "COMMERCIAL_SALES" and not best_role:
                    best_role = "COMMERCIAL_SALES"
                    best_dir = c["phone_directness"]

            comm_rows = conn.execute("""
                SELECT fc.equipment_category
                FROM facility_commodities fc
                WHERE fc.facility_id = ?
            """, (facility_id,)).fetchall()
            has_ftl = any(c["equipment_category"] in ("FLATBED", "STEP_DECK", "DRY_VAN") for c in comm_rows)

            return evaluate_broker_opportunity_raw(
                private_fleet_present=f_row["private_fleet_present"],
                commercial_carrier_use=f_row["commercial_carrier_use"],
                broker_friendly_status=f_row["broker_friendly_status"],
                lifecycle_stage=f_row["stage"] or "DISCOVERY",
                has_callable_route=has_callable,
                has_ftl_fit=has_ftl,
                suppression_status=supp_status,
                direct_contact_role=best_role,
                direct_contact_directness=best_dir,
                is_lane_suppression_only=False,
            )

        # Company-level evaluation using unified evaluator
        supp_rows = conn.execute("""
            SELECT scope_type, company_id, facility_id, suppression_status
            FROM suppressions
            WHERE (scope_type = 'COMPANY' AND company_id = ?)
               OR (scope_type = 'FACILITY' AND facility_id IN (SELECT id FROM facilities WHERE company_id = ?))
        """, (company_id, company_id)).fetchall()

        dnc_company = any(
            s["scope_type"] == "COMPANY" and s["company_id"] == company_id and s["suppression_status"] == "DO_NOT_CONTACT"
            for s in supp_rows
        )
        dnc_fac_ids = set(
            s["facility_id"] for s in supp_rows
            if s["scope_type"] == "FACILITY" and s["suppression_status"] == "DO_NOT_CONTACT"
        )

        fac_rows = conn.execute("""
            SELECT f.id, f.private_fleet_present, f.fleet_relationship_type,
                   f.commercial_carrier_use, f.broker_friendly_status,
                   pl.stage
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.company_id = ?
            ORDER BY f.id
        """, (company_id,)).fetchall()

        if not fac_rows:
            return evaluate_broker_opportunity_raw(
                has_callable_route=False,
                has_ftl_fit=False,
                lifecycle_stage="DISCOVERY",
                suppression_status="DO_NOT_CONTACT" if dnc_company else None
            )

        fac_ids = set(f["id"] for f in fac_rows)
        is_dnc = dnc_company or (len(fac_ids) > 0 and fac_ids.issubset(dnc_fac_ids))

        contact_rows = conn.execute("""
            SELECT id, role_category, phone_directness, phone_number, email_address
            FROM contacts
            WHERE company_id = ? OR facility_id IN (SELECT id FROM facilities WHERE company_id = ?)
        """, (company_id, company_id)).fetchall()

        comm_rows = conn.execute("""
            SELECT fc.facility_id, fc.equipment_category
            FROM facility_commodities fc
            JOIN facilities f ON fc.facility_id = f.id
            WHERE f.company_id = ? AND fc.equipment_category IN ('FLATBED', 'STEP_DECK', 'DRY_VAN')
        """, (company_id,)).fetchall()
        ftl_fac_ids = set(r["facility_id"] for r in comm_rows)

        return evaluate_company_opportunity_from_context(
            company_id=company_id,
            facilities=[dict(f) for f in fac_rows],
            contacts=[dict(c) for c in contact_rows],
            ftl_facility_ids=ftl_fac_ids,
            is_dnc=is_dnc,
        )
    finally:
        if should_close:
            conn.close()
        else:
            conn.row_factory = old_row_factory


def get_opportunity_tier_company_ids(
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[str | Path] = None,
    universe_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[int]]:
    """
    Evaluates all operating companies and groups company IDs by opportunity tier.
    Authoritative single source of truth for universe metadata and directory filtering.
    """
    if universe_context and "tier_company_ids" in universe_context:
        return universe_context["tier_company_ids"]

    u_ctx = load_opportunity_universe_context(conn=conn, db_path=db_path)
    return u_ctx["tier_company_ids"]


