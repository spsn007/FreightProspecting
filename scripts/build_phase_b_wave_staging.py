"""
FreightProspecting V1 — Phase B Wave Staging and Validated Change Plan Builder
Reads crawler raw results and database state, evaluates Qualification Gate and Tier A trigger,
and generates machine-auditable staging and change plan artifacts.
"""

import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend.db.queries import evaluate_qualification_readiness

DB_PATH = Path("data/prospects.db")
ROSTER_PATH = Path("reports/tier_a_acceleration_phase_b_roster.json")

# Boilerplate or false positive filter
FALSE_POSITIVE_PATTERNS = [
    r"fobackground",
    r"rgba\(",
    r"terms-and-conditions",
    r"terms-conditions",
    r"terms-of-sale",
    r"privacy-policy",
    r"terms of use",
]


def is_valid_operational_carrier_snippet(snippet: str, url: str) -> bool:
    """Validate that snippet is genuine operational carrier use, not boilerplate or false positive."""
    s_low = snippet.lower()
    u_low = url.lower()

    for fp in FALSE_POSITIVE_PATTERNS:
        if fp in s_low or fp in u_low:
            return False

    # Check for strong operational carrier phrases
    valid_indicators = [
        "shipped via common carrier",
        "ship via common carrier",
        "delivery via common carrier",
        "approved common carrier",
        "outside carriers for product distribution",
        "outside carrier network",
        "carrier onboarding",
        "carrier scheduling",
        "carrier requirements",
        "carrier packet",
        "motor carrier requirements",
        "commercial carrier",
    ]
    return any(ind in s_low for ind in valid_indicators)


def is_valid_operational_fleet_snippet(snippet: str, url: str) -> bool:
    """Validate that snippet is genuine operational fleet presence."""
    s_low = snippet.lower()
    for fp in FALSE_POSITIVE_PATTERNS:
        if fp in s_low:
            return False
    return any(ind in s_low for ind in ["our fleet of", "our own fleet", "operates a fleet of", "company drivers"])


def analyze_company_findings(crawled_data: dict, fac_city: str, fac_state: str) -> dict:
    """Analyze raw evidence snippets to distinguish facility-scope vs company-scope."""
    ev = crawled_data.get("evidence", {})
    carrier_snips = ev.get("carrier_snippets", [])
    broker_snips = ev.get("broker_snippets", [])
    fleet_snips = ev.get("fleet_snippets", [])

    city_lower = (fac_city or "").lower()
    state_lower = (fac_state or "").lower()

    # Filter valid snippets
    valid_carrier = [s for s in carrier_snips if is_valid_operational_carrier_snippet(s.get("snippet", ""), s.get("url", ""))]
    valid_fleet = [s for s in fleet_snips if is_valid_operational_fleet_snippet(s.get("snippet", ""), s.get("url", ""))]
    valid_broker = [s for s in broker_snips if not any(fp in s.get("snippet", "").lower() for fp in FALSE_POSITIVE_PATTERNS)]

    fac_carrier = []
    comp_carrier = []
    for s in valid_carrier:
        text = s.get("snippet", "")
        t_low = text.lower()
        if city_lower and city_lower in t_low or (state_lower and f", {state_lower}" in t_low):
            fac_carrier.append(s)
        else:
            comp_carrier.append(s)

    fac_fleet = []
    comp_fleet = []
    for s in valid_fleet:
        text = s.get("snippet", "")
        t_low = text.lower()
        if city_lower and city_lower in t_low or (state_lower and f", {state_lower}" in t_low):
            fac_fleet.append(s)
        else:
            comp_fleet.append(s)

    return {
        "facility_carrier": fac_carrier,
        "company_carrier": comp_carrier,
        "facility_broker": valid_broker,
        "company_broker": valid_broker,
        "facility_fleet": fac_fleet,
        "company_fleet": comp_fleet,
        "all_carrier": valid_carrier,
        "all_broker": valid_broker,
        "all_fleet": valid_fleet,
        "contacts": ev.get("contact_snippets", []),
        "emails": ev.get("emails", []),
        "phones": ev.get("phones", []),
    }


def main():
    wave_letter = sys.argv[1].upper() if len(sys.argv) > 1 else "A"
    crawler_raw_path = Path(f"reports/tier_a_phase_b_wave_{wave_letter}_crawler_raw.json")
    if not crawler_raw_path.exists():
        print(f"Error: {crawler_raw_path} not found. Run crawler first.")
        sys.exit(1)

    with open(ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)
    wave_roster = [r for r in roster if r["wave"] == wave_letter]

    with open(crawler_raw_path, "r", encoding="utf-8") as f:
        crawler_data = json.load(f)
    crawled_by_cid = {c["company_id"]: c for c in crawler_data}

    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    staging_list = []
    change_plan_items = []

    for item in wave_roster:
        cid = item["company_id"]
        pos = item["campaign_position"]
        brand = item["operating_brand"]
        fid = item["focus_facility_id"]
        cur_tier = item["current_tier"]
        cur_lifecycle = item["current_lifecycle"]

        fac = conn.execute("""
            SELECT f.id, f.facility_name, f.city, f.state_prov, f.country,
                   f.commercial_carrier_use, f.broker_friendly_status, f.private_fleet_present,
                   pl.stage as lifecycle_stage
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.id = ?
        """, (fid,)).fetchone()

        crawled = crawled_by_cid.get(cid, {})
        prov_recs = crawled.get("provenance_records", [])
        successful_fetches = [p for p in prov_recs if p.get("result") == "SUCCESS_FETCHED"]
        blocked_fetches = [p for p in prov_recs if p.get("result") in ("HTTP_403", "AUTOMATION_BLOCKED", "OFFICIAL_SOURCE_INACCESSIBLE", "DNS_FAILURE")]

        findings = analyze_company_findings(crawled, fac["city"], fac["state_prov"])

        # Evaluate Qualification Gate
        gate_res = evaluate_qualification_readiness(fid, conn=conn)
        is_ready = gate_res["is_ready"]
        checks = gate_res["checks"]

        cur_carrier = fac["commercial_carrier_use"] or "UNKNOWN"
        cur_broker = fac["broker_friendly_status"] or "UNKNOWN"
        cur_fleet = fac["private_fleet_present"] or "UNKNOWN"

        prop_carrier = cur_carrier
        prop_broker = cur_broker
        prop_fleet = cur_fleet
        proposed_claims = []

        carrier_source_url = None
        carrier_source_title = None
        carrier_rationale = None
        carrier_scope = "FACILITY"

        # Check crawler findings for commercial carrier
        if cur_carrier != "VERIFIED":
            if findings["facility_carrier"]:
                best = findings["facility_carrier"][0]
                prop_carrier = "VERIFIED"
                carrier_source_url = best["url"]
                carrier_rationale = best["snippet"]
                carrier_scope = "FACILITY"
            elif findings["company_carrier"]:
                fac_count = conn.execute("SELECT count(*) as c FROM facilities WHERE company_id = ?", (cid,)).fetchone()["c"]
                best = findings["company_carrier"][0]
                if fac_count == 1:
                    prop_carrier = "VERIFIED"
                    carrier_source_url = best["url"]
                    carrier_rationale = best["snippet"]
                    carrier_scope = "FACILITY"
                else:
                    prop_carrier = "UNKNOWN"
                    carrier_scope = "COMPANY"
                    carrier_source_url = best["url"]
                    carrier_rationale = best["snippet"]

        if carrier_source_url and prop_carrier == "VERIFIED":
            proposed_claims.append({
                "field": "commercial_carrier_use",
                "claimed_value": "VERIFIED",
                "verification_status": "VERIFIED",
                "scope": carrier_scope,
                "facility_id": fid if carrier_scope == "FACILITY" else None,
                "company_id": cid if carrier_scope == "COMPANY" else None,
                "source_url": carrier_source_url,
                "rationale": carrier_rationale,
            })

        # Check fleet findings
        fleet_source_url = None
        fleet_rationale = None
        if cur_fleet == "UNKNOWN" and findings["all_fleet"]:
            best_f = findings["all_fleet"][0]
            prop_fleet = "VERIFIED_PRESENT"
            fleet_source_url = best_f["url"]
            fleet_rationale = best_f["snippet"]
            proposed_claims.append({
                "field": "private_fleet_present",
                "claimed_value": "VERIFIED_PRESENT",
                "verification_status": "VERIFIED",
                "scope": "FACILITY",
                "facility_id": fid,
                "source_url": fleet_source_url,
                "rationale": fleet_rationale,
            })

        # Determine qualification proposal
        if is_ready:
            qual_proposal = "QUALIFY"
            if prop_carrier == "VERIFIED" or cur_carrier == "VERIFIED":
                expected_effect = "TIER_A_PROMOTION"
            elif prop_fleet == "VERIFIED_PRESENT" or cur_fleet == "VERIFIED_PRESENT":
                expected_effect = "TIER_C_MOVEMENT"
            else:
                expected_effect = "TIER_B_QUALIFIED"
        else:
            qual_proposal = "KEEP_DISCOVERY"
            expected_effect = "MAINTAIN_TIER_D"

        staging_record = {
            "campaign_position": pos,
            "company_id": cid,
            "operating_brand": brand,
            "focus_facility_id": fid,
            "facility_city": fac["city"],
            "facility_state": fac["state_prov"],
            "pre_lifecycle": cur_lifecycle,
            "pre_tier": cur_tier,
            "qualification_gate": {k: v["passed"] for k, v in checks.items()},
            "qualification_gate_details": {k: v["details"] for k, v in checks.items()},
            "qualification_proposal": qual_proposal,
            "commercial_carrier_before": cur_carrier,
            "commercial_carrier_proposed": prop_carrier,
            "broker_before": cur_broker,
            "broker_proposed": prop_broker,
            "private_fleet_before": cur_fleet,
            "private_fleet_proposed": prop_fleet,
            "company_scope_findings": [s["snippet"] for s in findings["company_carrier"][:3]],
            "facility_scope_findings": [s["snippet"] for s in findings["facility_carrier"][:3]],
            "sources_attempted": len(prov_recs),
            "sources_fetched": len(successful_fetches),
            "sources_blocked": len(blocked_fetches),
            "proposed_claims": proposed_claims,
            "proposed_contacts": [],
            "expected_engine_effect": expected_effect,
        }
        staging_list.append(staging_record)

        if qual_proposal == "QUALIFY" or proposed_claims:
            change_plan_items.append({
                "campaign_position": pos,
                "company_id": cid,
                "operating_brand": brand,
                "focus_facility_id": fid,
                "lifecycle_action": qual_proposal,
                "proposed_claims": proposed_claims,
                "expected_engine_effect": expected_effect,
                "validation_status": "ACCEPT",
            })

    out_staging = Path(f"reports/tier_a_phase_b_wave_{wave_letter}_staging.json")
    with open(out_staging, "w", encoding="utf-8") as f:
        json.dump(staging_list, f, indent=2)

    out_plan = Path(f"reports/tier_a_phase_b_wave_{wave_letter}_change_plan.json")
    with open(out_plan, "w", encoding="utf-8") as f:
        json.dump(change_plan_items, f, indent=2)

    print(f"[STAGING DONE] Wrote {len(staging_list)} staging records to {out_staging}")
    print(f"[PLAN DONE] Wrote {len(change_plan_items)} validated plan items to {out_plan}")


if __name__ == "__main__":
    main()
