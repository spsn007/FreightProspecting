"""
Comprehensive Qualification and Shortlist selector based on verified factual evidence.
"""
import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Any

def build_review_universe():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Query all companies and facilities
    query = """
    SELECT 
        c.id as comp_id,
        c.operating_brand,
        c.legal_name,
        c.website_url,
        f.id as fac_id,
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
        ct.id as contact_id,
        ct.person_name,
        ct.exact_published_title,
        ct.department,
        ct.phone_number,
        ct.phone_directness,
        ct.email_address,
        ct.role_category,
        es.id as source_id,
        es.source_url
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

    companies = {}
    for r in rows:
        cid = r["comp_id"]
        if cid not in companies:
            companies[cid] = {
                "comp_id": cid,
                "brand": r["operating_brand"],
                "legal_name": r["legal_name"],
                "website": r["website_url"],
                "facilities": {},
                "commodities": set(),
                "equipments": set(),
                "contacts": [],
                "sources": set()
            }
        fid = r["fac_id"]
        if fid not in companies[cid]["facilities"]:
            companies[cid]["facilities"][fid] = {
                "fac_id": fid,
                "name": r["facility_name"],
                "address": r["physical_address"],
                "city": r["city"],
                "state": r["state_prov"],
                "country": r["country"],
                "commercial_carrier": r["commercial_carrier_use"],
                "private_fleet": r["private_fleet_present"],
                "procurement": r["freight_procurement_level"],
                "commodities": [],
                "contacts": [],
                "sources": []
            }
        if r["commodity_category"]:
            companies[cid]["commodities"].add(r["commodity_category"])
            companies[cid]["facilities"][fid]["commodities"].append(r["commodity_category"])
        if r["equipment_category"]:
            companies[cid]["equipments"].add(r["equipment_category"])
        if r["phone_number"] or r["email_address"]:
            c_info = {
                "person": r["person_name"],
                "title": r["exact_published_title"],
                "dept": r["department"],
                "phone": r["phone_number"],
                "directness": r["phone_directness"],
                "email": r["email_address"],
                "role": r["role_category"]
            }
            if c_info not in companies[cid]["facilities"][fid]["contacts"]:
                companies[cid]["facilities"][fid]["contacts"].append(c_info)
                companies[cid]["contacts"].append(c_info)
        if r["source_url"]:
            companies[cid]["sources"].add(r["source_url"])

    conn.close()
    return companies

if __name__ == "__main__":
    comps = build_review_universe()
    print(f"Loaded {len(comps)} companies.")
