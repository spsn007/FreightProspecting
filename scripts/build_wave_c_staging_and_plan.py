"""
Build Phase A Wave C Research Staging and Validated Change Plan.
Generates:
1. reports/tier_a_phase_a_wave_C_staging.json
2. reports/tier_a_phase_a_wave_C_change_plan.json
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("data/prospects.db")
CRAWLER_RAW_PATH = Path("reports/tier_a_phase_a_wave_C_crawler_raw.json")
ROSTER_PATH = Path("reports/tier_a_acceleration_phase_a_roster.json")

def main():
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)
    wave_c_roster = [r for r in roster if r["wave"] == "C"]

    with open(CRAWLER_RAW_PATH, "r", encoding="utf-8") as f:
        crawler_data = json.load(f)
    crawler_by_cid = {c["company_id"]: c for c in crawler_data}

    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    staging_records = []
    change_proposals = []

    for item in wave_c_roster:
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
            "wave": "C",
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

        if cid == 91:
            # Worthington Steel -> TIER A PROMOTION
            stg["evaluation_decision"] = "PROMOTE_TO_TIER_A"
            stg["findings"] = {
                "carrier_evidence": "Official Carrier Information page explicitly invites and onboards outside carriers: 'We appreciate your interest in hauling freight for Worthington Steel. We work with carriers big and small, from large fleet companies to single owner operators, who can provide excellent service at fair market rates.'",
                "broker_evidence": "Official Carrier Information Form explicitly onboards freight brokers: 'Company Type: -- Select One -- Asset-based Broker Both'.",
                "equipment_evidence": "Carrier form specifically requests Dry Van and Flatbed trailer capacity for hauling steel.",
                "sources": [
                    {
                        "source_url": "https://www.worthingtonsteel.com/company/working-with-us/carrier-information",
                        "source_title": "Carrier Information - Working With Us - Worthington Steel",
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
                "source_url": "https://www.worthingtonsteel.com/company/working-with-us/carrier-information",
                "source_title": "Carrier Information - Working With Us - Worthington Steel",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Official website explicitly onboards outside commercial carriers big and small across dry van and flatbed modes.",
            }
            p2 = {
                "company_id": cid,
                "operating_brand": brand,
                "facility_id": fid,
                "field": "broker_friendly_status",
                "subject_type": "facility",
                "action": "ACCEPT",
                "old_value": fac["broker_friendly_status"] or "UNKNOWN",
                "proposed_value": "VERIFIED_ACCEPTS",
                "verification_status": "VERIFIED",
                "source_url": "https://www.worthingtonsteel.com/company/working-with-us/carrier-information",
                "source_title": "Carrier Information - Working With Us - Worthington Steel",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Official carrier onboarding form explicitly provides 'Broker' option under Company Type.",
            }
            stg["proposed_changes"].extend([p1, p2])
            change_proposals.extend([p1, p2])

        elif cid == 102:
            # FerrouSouth -> TIER C MOVEMENT
            stg["evaluation_decision"] = "MOVE_TO_TIER_C"
            stg["findings"] = {
                "fleet_evidence": "Official logistics page explicitly states: 'With easy access to major highways our own trucks give you yet another shipping option.'",
                "carrier_evidence": "Outside commercial carrier use unmentioned; preserved UNKNOWN.",
                "broker_evidence": "Broker acceptance unmentioned; preserved UNKNOWN.",
                "sources": [
                    {
                        "source_url": "https://ferrousouth.com/logistics/",
                        "source_title": "Logistics - FerrouSouth",
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
                "field": "private_fleet_present",
                "subject_type": "facility",
                "action": "ACCEPT",
                "old_value": fac["private_fleet_present"] or "UNKNOWN",
                "proposed_value": "VERIFIED_PRESENT",
                "verification_status": "VERIFIED",
                "source_url": "https://ferrousouth.com/logistics/",
                "source_title": "Logistics - FerrouSouth",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Official website explicitly documents 'our own trucks give you yet another shipping option.'",
            }
            p2 = {
                "company_id": cid,
                "operating_brand": brand,
                "facility_id": fid,
                "field": "fleet_relationship_type",
                "subject_type": "facility",
                "action": "ACCEPT",
                "old_value": fac["fleet_relationship_type"] or "UNKNOWN",
                "proposed_value": "IN_HOUSE_OWNED",
                "verification_status": "VERIFIED",
                "source_url": "https://ferrousouth.com/logistics/",
                "source_title": "Logistics - FerrouSouth",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Explicit statement of company-owned trucking fleet ('our own trucks').",
            }
            stg["proposed_changes"].extend([p1, p2])
            change_proposals.extend([p1, p2])

        elif cid == 104:
            # Target Steel -> TIER C MOVEMENT
            stg["evaluation_decision"] = "MOVE_TO_TIER_C"
            stg["findings"] = {
                "fleet_evidence": "Official headquarters page explicitly confirms: 'Coils are transferred from the adjacent Flat Rock Distribution Center building to ours using our own trucks, maximizing efficiency.' and 'Transportation : Company-owned trucks ensure reliable delivery, with truck appointments required (contact traffic@targetsteel.net ).'",
                "carrier_evidence": "Outside commercial carrier contracts unmentioned; preserved UNKNOWN.",
                "broker_evidence": "Broker acceptance unmentioned; preserved UNKNOWN.",
                "contact_evidence": "Official traffic desk email: traffic@targetsteel.net.",
                "sources": [
                    {
                        "source_url": "https://www.targetsteel.net/locations/target-steel-inc-hq-flat-rock-mi",
                        "source_title": "Target Steel Inc. HQ - Flat Rock, MI",
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
                "field": "private_fleet_present",
                "subject_type": "facility",
                "action": "ACCEPT",
                "old_value": fac["private_fleet_present"] or "UNKNOWN",
                "proposed_value": "VERIFIED_PRESENT",
                "verification_status": "VERIFIED",
                "source_url": "https://www.targetsteel.net/locations/target-steel-inc-hq-flat-rock-mi",
                "source_title": "Target Steel Inc. HQ - Flat Rock, MI",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Official corporate site explicitly documents 'our own trucks' and 'Company-owned trucks ensure reliable delivery'.",
            }
            p2 = {
                "company_id": cid,
                "operating_brand": brand,
                "facility_id": fid,
                "field": "fleet_relationship_type",
                "subject_type": "facility",
                "action": "ACCEPT",
                "old_value": fac["fleet_relationship_type"] or "UNKNOWN",
                "proposed_value": "IN_HOUSE_OWNED",
                "verification_status": "VERIFIED",
                "source_url": "https://www.targetsteel.net/locations/target-steel-inc-hq-flat-rock-mi",
                "source_title": "Target Steel Inc. HQ - Flat Rock, MI",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Explicit company-owned fleet statement.",
            }
            p3 = {
                "company_id": cid,
                "operating_brand": brand,
                "facility_id": fid,
                "field": "contact",
                "subject_type": "contact",
                "action": "ACCEPT",
                "old_value": "NONE",
                "proposed_value": "Traffic Department | traffic@targetsteel.net [GENERAL_DESK] | (734) 789-9700 [GENERAL_SWITCHBOARD]",
                "verification_status": "VERIFIED",
                "source_url": "https://www.targetsteel.net/locations/target-steel-inc-hq-flat-rock-mi",
                "source_title": "Target Steel Inc. HQ - Flat Rock, MI",
                "source_type": "COMPANY_WEBSITE",
                "contact_payload": {
                    "facility_id": fid,
                    "contact_identity": "DEPARTMENT",
                    "person_name": None,
                    "department": "Traffic & Logistics",
                    "exact_published_title": "Traffic Department (Truck Appointments)",
                    "phone_number": "(734) 789-9700",
                    "phone_extension": None,
                    "phone_directness": "GENERAL_SWITCHBOARD",
                    "email_address": "traffic@targetsteel.net",
                    "email_directness": "DEPARTMENT",
                    "role_category": "FREIGHT_LOGISTICS",
                    "outbound_shipping_procurement_relevance": "VERIFIED",
                    "broker_procurement_relevance": "UNKNOWN",
                    "is_primary_contact": 1,
                },
                "rationale": "Directly published logistics/truck appointment contact email on official facility page.",
            }
            stg["proposed_changes"].extend([p1, p2, p3])
            change_proposals.extend([p1, p2, p3])

        else:
            stg["findings"] = {
                "summary": f"Public website inspected across {len(prov_recs)} attempted URLs. Insufficient primary evidence to verify outside commercial carrier contracts or broker acceptance. Maintained UNKNOWN per zero-hallucination standards.",
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
    staging_path = Path("reports/tier_a_phase_a_wave_C_staging.json")
    with open(staging_path, "w", encoding="utf-8") as f:
        json.dump(staging_records, f, indent=2)
    print(f"[WAVE C] Saved {len(staging_records)} staging records to {staging_path}")

    # Build and save change plan
    plan_data = {
        "campaign": "TIER_A_ACCELERATION",
        "phase": "PHASE_A",
        "wave": "C",
        "created_at_utc": now_utc,
        "companies_researched_count": len(staging_records),
        "total_change_proposals_count": len(change_proposals),
        "accepted_changes": [p for p in change_proposals if p["action"] == "ACCEPT"],
        "downgraded_changes": [p for p in change_proposals if p["action"] == "DOWNGRADE_TO_INFERRED"],
        "rejected_changes": [p for p in change_proposals if p["action"] == "REJECT"],
        "tier_movement_forecast": [
            {
                "company_id": 91,
                "operating_brand": "Worthington Steel",
                "facility_id": 111,
                "current_tier": "TIER_B_WORTH_CALLING",
                "projected_tier": "TIER_A_PRIORITY",
                "trigger": "commercial_carrier_use = VERIFIED and broker_friendly_status = VERIFIED_ACCEPTS",
            },
            {
                "company_id": 102,
                "operating_brand": "FerrouSouth",
                "facility_id": 131,
                "current_tier": "TIER_B_WORTH_CALLING",
                "projected_tier": "TIER_C_SECONDARY",
                "trigger": "private_fleet_present = VERIFIED_PRESENT, commercial_carrier_use = UNKNOWN",
            },
            {
                "company_id": 104,
                "operating_brand": "Target Steel",
                "facility_id": 133,
                "current_tier": "TIER_B_WORTH_CALLING",
                "projected_tier": "TIER_C_SECONDARY",
                "trigger": "private_fleet_present = VERIFIED_PRESENT, commercial_carrier_use = UNKNOWN",
            }
        ]
    }

    plan_path = Path("reports/tier_a_phase_a_wave_C_change_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)
    print(f"[WAVE C] Saved change plan ({len(change_proposals)} proposals) to {plan_path}")

if __name__ == "__main__":
    main()
