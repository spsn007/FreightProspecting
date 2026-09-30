"""
Build Phase A Wave E Research Staging and Validated Change Plan.
Generates:
1. reports/tier_a_phase_a_wave_E_staging.json
2. reports/tier_a_phase_a_wave_E_change_plan.json
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("data/prospects.db")
CRAWLER_RAW_PATH = Path("reports/tier_a_phase_a_wave_E_crawler_raw.json")
ROSTER_PATH = Path("reports/tier_a_acceleration_phase_a_roster.json")

def main():
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)
    wave_e_roster = [r for r in roster if r["wave"] == "E"]

    with open(CRAWLER_RAW_PATH, "r", encoding="utf-8") as f:
        crawler_data = json.load(f)
    crawler_by_cid = {c["company_id"]: c for c in crawler_data}

    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    staging_records = []
    change_proposals = []

    for item in wave_e_roster:
        cid = item["company_id"]
        pos = item["campaign_position"]
        brand = item["operating_brand"]
        fid = item["candidate_focus_facility_ids"][0]
        cur_tier = item["current_tier"]

        fac = conn.execute("""
            SELECT f.id, f.facility_name, f.city, f.state_prov,
                   f.private_fleet_present, f.fleet_relationship_type,
                   f.commercial_carrier_use, f.broker_friendly_status, pl.stage
            FROM facilities f
            LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
            WHERE f.id = ?
        """, (fid,)).fetchone()

        contacts = conn.execute("""
            SELECT id, person_name, exact_published_title, phone_number, phone_directness,
                   email_address, email_directness, role_category
            FROM contacts WHERE company_id = ? OR facility_id = ?
        """, (cid, fid)).fetchall()

        crawled = crawler_by_cid.get(cid, {})
        prov_recs = crawled.get("provenance_records", [])

        stg = {
            "campaign": "TIER_A_ACCELERATION",
            "phase": "PHASE_A",
            "wave": "E",
            "campaign_position": pos,
            "company_id": cid,
            "operating_brand": brand,
            "research_focus_facility_id": fid,
            "research_focus_facility_name": fac["facility_name"] if fac else "",
            "current_state": {
                "opportunity_tier": cur_tier,
                "lifecycle_stage": (fac["stage"] if fac else "QUALIFIED") or "QUALIFIED",
                "private_fleet_present": (fac["private_fleet_present"] if fac else "UNKNOWN") or "UNKNOWN",
                "fleet_relationship_type": (fac["fleet_relationship_type"] if fac else "UNKNOWN") or "UNKNOWN",
                "commercial_carrier_use": (fac["commercial_carrier_use"] if fac else "UNKNOWN") or "UNKNOWN",
                "broker_friendly_status": (fac["broker_friendly_status"] if fac else "UNKNOWN") or "UNKNOWN",
                "existing_contacts_count": len(contacts),
            },
            "crawler_provenance_summary": {
                "total_attempts": len(prov_recs),
                "successful_200": len([p for p in prov_recs if p.get("result") == "SUCCESS_FETCHED"]),
                "inaccessible_or_blocked": len([p for p in prov_recs if p.get("result") in ("HTTP_403", "AUTOMATION_BLOCKED", "OFFICIAL_SOURCE_INACCESSIBLE", "DNS_FAILURE", "TLS_FAILURE")]),
            },
            "findings": {},
            "evaluation_decision": "MAINTAIN_CURRENT_TIER",
            "proposed_changes": [],
        }

        if cid == 218:
            # Metals USA -> TIER A PROMOTION
            stg["evaluation_decision"] = "PROMOTE_TO_TIER_A"
            stg["findings"] = {
                "carrier_evidence": "Official capabilities page explicitly documents commercial carrier freight: 'Metals USA works in conjunction with some of the nation’s largest freight carriers to deliver their material quickly and on-time. A team of common carriers also help transport the material longer distances to accommodate customers in any geographical location.'",
                "broker_evidence": "Broker acceptance unmentioned; preserved UNKNOWN.",
                "fleet_evidence": "Private fleet presence unmentioned; preserved UNKNOWN.",
                "sources": [
                    {
                        "source_url": "https://www.metalsusa.com/metal-shipping-services/",
                        "source_title": "Metal Shipping Services | Metals USA",
                        "source_type": "COMPANY_WEBSITE",
                        "http_status": 200,
                        "is_primary": True,
                    }
                ]
            }

            p1 = {
                "company_id": cid,
                "operating_brand": brand,
                "facility_id": fid,
                "field": "commercial_carrier_use",
                "subject_type": "facility",
                "action": "ACCEPT",
                "old_value": fac["commercial_carrier_use"] or "UNKNOWN",
                "proposed_value": "VERIFIED",
                "verification_status": "VERIFIED",
                "source_url": "https://www.metalsusa.com/metal-shipping-services/",
                "source_title": "Metal Shipping Services | Metals USA",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Official website explicitly documents partnership with freight carriers and common carriers for customer shipments.",
            }
            stg["proposed_changes"].append(p1)
            change_proposals.append(p1)

        else:
            stg["findings"] = {
                "summary": f"Public website inspected across {len(prov_recs)} attempted URLs. Insufficient primary evidence to verify outside commercial carrier contracts or broker acceptance beyond current status. Maintained UNKNOWN per zero-hallucination standards.",
                "sources": [
                    {
                        "source_url": p["final_url"],
                        "source_title": p.get("page_title") or brand,
                        "source_type": "COMPANY_WEBSITE",
                        "http_status": p.get("http_status"),
                    }
                    for p in prov_recs if p.get("result") == "SUCCESS_FETCHED"
                ][:3]
            }

        staging_records.append(stg)

    conn.close()

    # Save staging
    staging_path = Path("reports/tier_a_phase_a_wave_E_staging.json")
    with open(staging_path, "w", encoding="utf-8") as f:
        json.dump(staging_records, f, indent=2)
    print(f"[WAVE E] Saved {len(staging_records)} staging records to {staging_path}")

    # Build and save change plan
    plan_data = {
        "campaign": "TIER_A_ACCELERATION",
        "phase": "PHASE_A",
        "wave": "E",
        "created_at_utc": now_utc,
        "companies_researched_count": len(staging_records),
        "total_change_proposals_count": len(change_proposals),
        "accepted_changes": [p for p in change_proposals if p["action"] == "ACCEPT"],
        "downgraded_changes": [p for p in change_proposals if p["action"] == "DOWNGRADE_TO_INFERRED"],
        "rejected_changes": [p for p in change_proposals if p["action"] == "REJECT"],
        "tier_movement_forecast": [
            {
                "company_id": 218,
                "operating_brand": "Metals USA",
                "facility_id": 264,
                "current_tier": "TIER_B_WORTH_CALLING",
                "projected_tier": "TIER_A_PRIORITY",
                "trigger": "commercial_carrier_use = VERIFIED",
            }
        ]
    }

    plan_path = Path("reports/tier_a_phase_a_wave_E_change_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)
    print(f"[WAVE E] Saved change plan ({len(change_proposals)} proposals) to {plan_path}")

if __name__ == "__main__":
    main()
