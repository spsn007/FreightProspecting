"""
Build Phase A Wave A Research Staging and Validated Change Plan.
Generates:
1. reports/tier_a_phase_a_wave_A_staging.json
2. reports/tier_a_phase_a_wave_A_change_plan.json
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("data/prospects.db")
CRAWLER_RAW_PATH = Path("reports/tier_a_phase_a_wave_A_crawler_raw.json")
ROSTER_PATH = Path("reports/tier_a_acceleration_phase_a_roster.json")

def main():
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)
    wave_a_roster = [r for r in roster if r["wave"] == "A"]

    with open(CRAWLER_RAW_PATH, "r", encoding="utf-8") as f:
        crawler_data = json.load(f)
    crawler_by_cid = {c["company_id"]: c for c in crawler_data}

    conn = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    staging_records = []
    change_proposals = []

    for item in wave_a_roster:
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

        # Build staging item
        stg = {
            "campaign": "TIER_A_ACCELERATION",
            "phase": "PHASE_A",
            "wave": "A",
            "campaign_position": pos,
            "company_id": cid,
            "operating_brand": brand,
            "research_focus_facility_id": fid,
            "research_focus_facility_name": fac["facility_name"],
            "current_state": {
                "opportunity_tier": cur_tier,
                "lifecycle_stage": fac["stage"] or "QUALIFIED",
                "private_fleet_present": fac["private_fleet_present"] or "UNKNOWN",
                "fleet_relationship_type": fac["fleet_relationship_type"] or "UNKNOWN",
                "commercial_carrier_use": fac["commercial_carrier_use"] or "UNKNOWN",
                "broker_friendly_status": fac["broker_friendly_status"] or "UNKNOWN",
                "existing_contacts_count": len(contacts),
            },
            "crawler_provenance_summary": {
                "total_attempts": len(prov_recs),
                "successful_200": len([p for p in prov_recs if p.get("result") == "SUCCESS_FETCHED"]),
                "inaccessible_or_blocked": len([p for p in prov_recs if p.get("result") in ("HTTP_403", "AUTOMATION_BLOCKED", "OFFICIAL_SOURCE_INACCESSIBLE", "DNS_FAILURE")]),
            },
            "findings": {},
            "evaluation_decision": "MAINTAIN_CURRENT_TIER",
            "proposed_changes": [],
        }

        if cid == 105:
            # Precision Strip -> TIER A PROMOTION
            stg["evaluation_decision"] = "PROMOTE_TO_TIER_A"
            stg["findings"] = {
                "carrier_evidence": "Official website explicitly documents common carrier shipping: 'Shipment of material by approved common carrier can also be arranged by our Traffic Coordinator.' and 'We can arrange for shipment of your material on either a Precision Strip Transport truck or by common carrier, to or from virtually anywhere in the U.S., at a cost competitive price.'",
                "broker_evidence": "Official website explicitly offers and coordinates 3PL and brokerage services: 'In addition, Precision Strip Transport provides third party logistic (3PL) services to handle all your transportation needs. By outsourcing your logistic function to Precision Strip Transportation Services, you preserve valuable time that can be used to operate your business.'",
                "fleet_evidence": "Fleet of over 200 trucks operated (already VERIFIED_PRESENT in DB).",
                "contact_evidence": "Jamey Eilerman listed on official Transportation Services page as Main Contact (jamey_eilerman@precision-strip.com).",
                "sources": [
                    {
                        "source_url": "https://www.precision-strip.com/capabilities/transportation-services/",
                        "source_title": "Precision Strip - Transportation Services",
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
                "source_url": "https://www.precision-strip.com/capabilities/transportation-services/",
                "source_title": "Precision Strip - Transportation Services",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Official Transportation Services page explicitly documents shipment of material by approved common carrier arranged by Traffic Coordinator.",
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
                "source_url": "https://www.precision-strip.com/capabilities/transportation-services/",
                "source_title": "Precision Strip - Transportation Services",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Official corporate site explicitly documents provision and utilization of 3PL logistics services and approved common carriers.",
            }
            p3 = {
                "company_id": cid,
                "operating_brand": brand,
                "facility_id": fid,
                "field": "contact",
                "subject_type": "contact",
                "action": "ACCEPT",
                "old_value": "NONE",
                "proposed_value": "Jamey Eilerman | Main Contact - Transportation Services | jamey_eilerman@precision-strip.com [DIRECT_PERSON] | 419-628-2343 [GENERAL_SWITCHBOARD]",
                "verification_status": "VERIFIED",
                "source_url": "https://www.precision-strip.com/capabilities/transportation-services/",
                "source_title": "Precision Strip - Transportation Services",
                "source_type": "COMPANY_WEBSITE",
                "contact_payload": {
                    "facility_id": fid,
                    "contact_identity": "NAMED_PERSON",
                    "person_name": "Jamey Eilerman",
                    "department": "Transportation & Logistics",
                    "exact_published_title": "Main Contact - Transportation Services",
                    "phone_number": "419-628-2343",
                    "phone_extension": None,
                    "phone_directness": "GENERAL_SWITCHBOARD",
                    "email_address": "jamey_eilerman@precision-strip.com",
                    "email_directness": "DIRECT_PERSON",
                    "role_category": "FREIGHT_LOGISTICS",
                    "outbound_shipping_procurement_relevance": "VERIFIED",
                    "broker_procurement_relevance": "VERIFIED",
                    "is_primary_contact": 1,
                },
                "rationale": "Directly published logistics / transportation main contact on official corporate capabilities page.",
            }
            stg["proposed_changes"].extend([p1, p2, p3])
            change_proposals.extend([p1, p2, p3])

        elif cid == 24:
            # AmeriSteel -> TIER C MOVEMENT
            stg["evaluation_decision"] = "MOVE_TO_TIER_C"
            stg["findings"] = {
                "fleet_evidence": "Official website explicitly documents owned delivery truck: 'In-House Delivery Our own 2022 Kenworth truck with 40,000lb capacity ensures reliable delivery... delivery across Metro Detroit.' and '2023 Purchased new 40,000 lb capacity delivery truck'.",
                "carrier_evidence": "Outside commercial carrier use unmentioned; preserved UNKNOWN.",
                "broker_evidence": "Broker acceptance unmentioned; preserved UNKNOWN.",
                "sources": [
                    {
                        "source_url": "https://www.ameristeel.com/about",
                        "source_title": "About AmeriSteel | Family-Owned Steel Service Center",
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
                "source_url": "https://www.ameristeel.com/about",
                "source_title": "About AmeriSteel | Family-Owned Steel Service Center",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Official website confirms in-house 2022 Kenworth delivery truck with 40,000lb capacity.",
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
                "source_url": "https://www.ameristeel.com/about",
                "source_title": "About AmeriSteel | Family-Owned Steel Service Center",
                "source_type": "COMPANY_WEBSITE",
                "rationale": "Company explicitly states 'Our own 2022 Kenworth truck', proving in-house owned asset.",
            }
            stg["proposed_changes"].extend([p1, p2])
            change_proposals.extend([p1, p2])

        else:
            # Conservative UNKNOWN preservation
            stg["findings"] = {
                "summary": f"Public website inspected across {len(prov_recs)} attempted URLs. Insufficient primary evidence to verify commercial carrier contracts or broker acceptance. Maintained UNKNOWN per zero-hallucination rules.",
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
    staging_path = Path("reports/tier_a_phase_a_wave_A_staging.json")
    with open(staging_path, "w", encoding="utf-8") as f:
        json.dump(staging_records, f, indent=2)
    print(f"Saved {len(staging_records)} staging records to {staging_path}")

    # Build and save validated change plan
    plan_data = {
        "campaign": "TIER_A_ACCELERATION",
        "phase": "PHASE_A",
        "wave": "A",
        "created_at_utc": now_utc,
        "companies_researched_count": len(staging_records),
        "total_change_proposals_count": len(change_proposals),
        "accepted_changes": [p for p in change_proposals if p["action"] == "ACCEPT"],
        "downgraded_changes": [p for p in change_proposals if p["action"] == "DOWNGRADE_TO_INFERRED"],
        "rejected_changes": [p for p in change_proposals if p["action"] == "REJECT"],
        "tier_movement_forecast": [
            {
                "company_id": 105,
                "operating_brand": "Precision Strip",
                "facility_id": 134,
                "current_tier": "TIER_C_SECONDARY",
                "projected_tier": "TIER_A_PRIORITY",
                "trigger": "commercial_carrier_use = VERIFIED and broker_friendly_status = VERIFIED_ACCEPTS",
            },
            {
                "company_id": 24,
                "operating_brand": "AmeriSteel",
                "facility_id": 23,
                "current_tier": "TIER_B_WORTH_CALLING",
                "projected_tier": "TIER_C_SECONDARY",
                "trigger": "private_fleet_present = VERIFIED_PRESENT, commercial_carrier_use = UNKNOWN",
            }
        ]
    }

    plan_path = Path("reports/tier_a_phase_a_wave_A_change_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, indent=2)
    print(f"Saved change plan ({len(change_proposals)} proposals) to {plan_path}")

if __name__ == "__main__":
    main()
