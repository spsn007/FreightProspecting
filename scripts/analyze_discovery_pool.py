"""
Analyze all 523 Discovery companies to evaluate qualification readiness across sectors.
"""
import sqlite3
import json
from pathlib import Path

def analyze_discovery_pool():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    query = """
    SELECT 
        c.id as company_id,
        c.operating_brand,
        c.legal_name,
        c.website_url,
        f.id as facility_id,
        f.facility_name,
        f.physical_address,
        f.city,
        f.state_prov,
        f.country,
        f.commercial_carrier_use,
        f.private_fleet_present,
        fc.commodity_category,
        fc.specific_products,
        fc.equipment_category,
        fc.equipment_usage_status,
        ct.phone_number,
        ct.phone_directness,
        ct.email_address,
        ct.role_category,
        ct.person_name,
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
    """
    rows = conn.execute(query).fetchall()
    print(f"Total rows fetched: {len(rows)}")

    # Group by company
    companies = {}
    for r in rows:
        cid = r["company_id"]
        if cid not in companies:
            companies[cid] = {
                "company_id": cid,
                "operating_brand": r["operating_brand"],
                "website_url": r["website_url"],
                "facilities": {},
                "commodities": set(),
                "equipments": set(),
                "sources": set()
            }
        fid = r["facility_id"]
        if fid not in companies[cid]["facilities"]:
            companies[cid]["facilities"][fid] = {
                "facility_id": fid,
                "name": r["facility_name"],
                "city": r["city"],
                "state": r["state_prov"],
                "country": r["country"],
                "address": r["physical_address"],
                "commercial_carrier": r["commercial_carrier_use"],
                "private_fleet": r["private_fleet_present"],
                "contacts": [],
                "commodities": []
            }
        if r["commodity_category"]:
            companies[cid]["commodities"].add(r["commodity_category"])
            companies[cid]["facilities"][fid]["commodities"].append({
                "category": r["commodity_category"],
                "products": r["specific_products"],
                "equipment": r["equipment_category"],
                "status": r["equipment_usage_status"]
            })
        if r["equipment_category"]:
            companies[cid]["equipments"].add(r["equipment_category"])
        if r["phone_number"] or r["email_address"]:
            companies[cid]["facilities"][fid]["contacts"].append({
                "phone": r["phone_number"],
                "directness": r["phone_directness"],
                "email": r["email_address"],
                "role": r["role_category"],
                "person": r["person_name"]
            })
        if r["source_url"]:
            companies[cid]["sources"].add(r["source_url"])

    print(f"Total distinct Discovery companies: {len(companies)}")
    
    # Analyze by sector
    sectors = {}
    for c in companies.values():
        comms = tuple(sorted(list(c["commodities"])))
        sectors[comms] = sectors.get(comms, 0) + 1
    print("\nSector breakdown (commodity categories):")
    for sec, count in sorted(sectors.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {sec}: {count}")

    conn.close()

if __name__ == "__main__":
    analyze_discovery_pool()
