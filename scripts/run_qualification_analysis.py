"""
Evaluate candidate pool for Qualification and Shortlisting based on live verified evidence.
"""
import concurrent.futures
import json
import sqlite3
import urllib.parse
from typing import Dict, List, Set, Any

def run_qualification_analysis():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Get working URLs from our checks
    # Load all sources
    sources = conn.execute("SELECT id, source_url, source_type FROM evidence_sources").fetchall()
    
    # Query all discovery facilities
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
                "contacts": [],
                "commodities": []
            }
        if r["commodity_category"]:
            companies[cid]["commodities"].add(r["commodity_category"])
            companies[cid]["facilities"][fid]["commodities"].append(r["commodity_category"])
        if r["equipment_category"]:
            companies[cid]["equipments"].add(r["equipment_category"])
        if r["phone_number"] or r["email_address"]:
            c_info = {
                "person": r["person_name"],
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

    print(f"Total Discovery Companies: {len(companies)}")

    # Sector tagging
    for cid, c in companies.items():
        comm_text = " ".join(c["commodities"]).lower()
        if any(w in comm_text for w in ["wood", "lumber", "forest", "timber", "plywood", "sawmill"]):
            c["sector"] = "TRACK_A_WOOD"
        elif any(w in comm_text for w in ["steel", "metal", "tube", "pipe", "aluminum", "iron", "coil"]):
            c["sector"] = "TRACK_B_STEEL"
        elif any(w in comm_text for w in ["concrete", "precast", "building", "brick", "stone", "masonry", "roofing"]):
            c["sector"] = "TRACK_C_PRECAST_BUILDING"
        elif any(w in comm_text for w in ["plastic", "mold", "tooling", "machining", "fabricat", "industrial"]):
            c["sector"] = "TRACK_D_PLASTICS_TOOLING_INDUSTRIAL"
        else:
            c["sector"] = "TRACK_E_CROSS_SECTOR"

        # Check contact quality
        c["has_direct_phone"] = any(ct["directness"] in ("DIRECT_PERSON", "DEPARTMENT_LINE") for ct in c["contacts"])
        c["has_freight_role"] = any(ct["role"] in ("FREIGHT_LOGISTICS", "OPERATIONS") for ct in c["contacts"])
        c["has_phone"] = any(bool(ct["phone"] and ct["phone"] != "UNKNOWN") for ct in c["contacts"])
        c["has_email"] = any(bool(ct["email"] and ct["email"] != "UNKNOWN") for ct in c["contacts"])
        c["fac_count"] = len(c["facilities"])
        
        # Check carrier / fleet facts
        c["has_commercial_carrier"] = any(f["commercial_carrier"] == "VERIFIED" for f in c["facilities"].values())
        c["has_private_fleet"] = any(f["private_fleet"] == "VERIFIED_PRESENT" for f in c["facilities"].values())

    conn.close()
    return companies

if __name__ == "__main__":
    comps = run_qualification_analysis()
    sectors = {}
    for c in comps.values():
        sectors[c["sector"]] = sectors.get(c["sector"], 0) + 1
    print("Discovery pool sectors:", sectors)

    # Let's see how many companies have a callable phone
    with_phone = [c for c in comps.values() if c["has_phone"]]
    print(f"Companies with callable phone: {len(with_phone)}")

    # Let's see how many companies have direct logistics or operations or commercial carrier
    high_priority = [c for c in comps.values() if c["has_freight_role"] or c["has_direct_phone"] or c["has_commercial_carrier"]]
    print(f"Companies with freight/ops role or direct phone or carrier: {len(high_priority)}")
    for hp in high_priority[:15]:
        print(f"  ID {hp['comp_id']}: {hp['brand']} ({hp['sector']}) - Facs: {hp['fac_count']} - Phone: {hp['has_phone']} - FreightRole: {hp['has_freight_role']} - Carrier: {hp['has_commercial_carrier']} - Fleet: {hp['has_private_fleet']}")
