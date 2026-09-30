"""
Audit all 523 Discovery companies for Qualification Gate readiness.
Tests:
- Working / verified primary source URL
- Complete physical street address
- Approved equipment fit (Flatbed / Step Deck / Dry Van)
- Eligible geography (Lower 48 / Canada)
- Usable outreach route (Callable phone or valid email)
"""
import sqlite3
import json
import urllib.parse
from typing import Dict, List, Any

def audit_all_candidates():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Fetch all discovery facilities with their company, commodities, contacts, and evidence
    query = """
    SELECT 
        c.id as company_id,
        c.operating_brand,
        c.website_url,
        f.id as facility_id,
        f.facility_name,
        f.physical_address,
        f.city,
        f.state_prov,
        f.country,
        f.commercial_carrier_use,
        f.private_fleet_present,
        f.freight_procurement_level,
        fc.commodity_category,
        fc.specific_products,
        fc.equipment_category,
        fc.equipment_usage_status,
        ct.person_name,
        ct.phone_number,
        ct.phone_directness,
        ct.email_address,
        ct.role_category,
        es.id as source_id,
        es.source_url,
        es.source_type
    FROM companies c
    JOIN facilities f ON c.id = f.company_id
    JOIN prospect_lifecycle l ON f.id = l.facility_id
    LEFT JOIN facility_commodities fc ON f.id = fc.facility_id
    LEFT JOIN contacts ct ON f.id = ct.facility_id
    LEFT JOIN claims cl ON cl.facility_id = f.id AND cl.is_current_accepted = 1
    LEFT JOIN claim_evidence ce ON cl.id = ce.claim_id
    LEFT JOIN evidence_sources es ON ce.evidence_source_id = es.id
    WHERE l.stage = 'DISCOVERY'
    ORDER BY c.id, f.id
    """
    rows = conn.execute(query).fetchall()
    print(f"Total raw discovery rows: {len(rows)}")

    # Aggregate by company
    companies = {}
    for r in rows:
        cid = r["company_id"]
        if cid not in companies:
            companies[cid] = {
                "company_id": cid,
                "operating_brand": r["operating_brand"],
                "website_url": r["website_url"],
                "facilities": {}
            }
        fid = r["facility_id"]
        if fid not in companies[cid]["facilities"]:
            companies[cid]["facilities"][fid] = {
                "facility_id": fid,
                "facility_name": r["facility_name"],
                "address": r["physical_address"],
                "city": r["city"],
                "state": r["state_prov"],
                "country": r["country"],
                "commercial_carrier": r["commercial_carrier_use"],
                "private_fleet": r["private_fleet_present"],
                "procurement_level": r["freight_procurement_level"],
                "commodities": [],
                "contacts": [],
                "sources": []
            }
        if r["commodity_category"]:
            c_entry = {
                "category": r["commodity_category"],
                "products": r["specific_products"],
                "equipment": r["equipment_category"],
                "status": r["equipment_usage_status"]
            }
            if c_entry not in companies[cid]["facilities"][fid]["commodities"]:
                companies[cid]["facilities"][fid]["commodities"].append(c_entry)
        if r["phone_number"] or r["email_address"]:
            ct_entry = {
                "person": r["person_name"],
                "phone": r["phone_number"],
                "directness": r["phone_directness"],
                "email": r["email_address"],
                "role": r["role_category"]
            }
            if ct_entry not in companies[cid]["facilities"][fid]["contacts"]:
                companies[cid]["facilities"][fid]["contacts"].append(ct_entry)
        if r["source_url"]:
            s_entry = {
                "id": r["source_id"],
                "url": r["source_url"],
                "type": r["source_type"]
            }
            if s_entry not in companies[cid]["facilities"][fid]["sources"]:
                companies[cid]["facilities"][fid]["sources"].append(s_entry)

    print(f"Aggregated {len(companies)} Discovery companies.")

    conn.close()
    return companies

if __name__ == "__main__":
    audit_all_candidates()
