"""
Inspect and rank candidates for Shortlisting and Qualification using explainable broker criteria.
"""
import sqlite3
import json

def rank_candidates():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Fetch all discovery companies with their facilities, commodities, contacts, claims
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

    # Categorize into sectors and evaluate broker priority
    evaluated = []
    for cid, c in companies.items():
        comm_text = " ".join(c["commodities"]).lower()
        if any(w in comm_text for w in ["wood", "lumber", "forest", "timber", "plywood", "sawmill"]):
            sector = "WOOD"
        elif any(w in comm_text for w in ["steel", "metal", "tube", "pipe", "aluminum", "iron", "coil"]):
            sector = "STEEL"
        elif any(w in comm_text for w in ["concrete", "precast", "building", "brick", "stone", "masonry", "roofing"]):
            sector = "PRECAST_BUILDING"
        elif any(w in comm_text for w in ["plastic", "mold", "tooling", "machining", "fabricat", "industrial"]):
            sector = "TOOLING_INDUSTRIAL"
        else:
            sector = "CROSS_SECTOR"

        fac_count = len(c["facilities"])
        has_direct_phone = any(ct["directness"] in ("DIRECT_PERSON", "DEPARTMENT_LINE") for ct in c["contacts"])
        has_freight_role = any(ct["role"] in ("FREIGHT_LOGISTICS", "OPERATIONS") for ct in c["contacts"])
        has_carrier = any(f["commercial_carrier"] == "VERIFIED" for f in c["facilities"].values())
        has_fleet = any(f["private_fleet"] == "VERIFIED_PRESENT" for f in c["facilities"].values())
        is_canada = any(f["country"] == "CA" for f in c["facilities"].values())

        # Friction
        if fac_count >= 4:
            friction = "HIGH"
        elif fac_count in (2, 3) or has_fleet:
            friction = "MEDIUM"
        elif has_freight_role or has_carrier:
            friction = "LOW"
        else:
            friction = "UNKNOWN"

        # Explainable factors
        positive_factors = []
        negative_factors = []

        if has_freight_role:
            positive_factors.append("Verified freight/logistics contact")
        if has_direct_phone:
            positive_factors.append("Direct phone/department line verified")
        if has_carrier:
            positive_factors.append("Verified commercial carrier use")
        if fac_count == 1:
            positive_factors.append("Single-plant regional manufacturer")
        elif fac_count in (2, 3):
            positive_factors.append(f"Manageable regional multi-plant network ({fac_count} facilities)")
        else:
            negative_factors.append(f"Large enterprise scale ({fac_count} facilities)")

        if friction == "LOW":
            positive_factors.append("Low Access Friction")
        elif friction == "MEDIUM":
            positive_factors.append("Medium Access Friction")
        elif friction == "HIGH":
            negative_factors.append("High Access Friction (enterprise scale)")

        if has_fleet:
            negative_factors.append("Private fleet present (competing asset capacity)")

        if any("FLATBED" in eq for eq in c["equipments"]):
            positive_factors.append("Strong FTL Flatbed fit")
        elif any("STEP_DECK" in eq for eq in c["equipments"]):
            positive_factors.append("Strong FTL Step Deck fit")
        elif any("DRY_VAN" in eq for eq in c["equipments"]):
            positive_factors.append("FTL Dry Van fit")

        evaluated.append({
            "comp_id": cid,
            "brand": c["brand"],
            "legal_name": c["legal_name"],
            "website": c["website"],
            "sector": sector,
            "fac_count": fac_count,
            "facilities": list(c["facilities"].values()),
            "is_canada": is_canada,
            "friction": friction,
            "has_freight_role": has_freight_role,
            "has_direct_phone": has_direct_phone,
            "has_carrier": has_carrier,
            "has_fleet": has_fleet,
            "positive_factors": positive_factors,
            "negative_factors": negative_factors,
            "pos_score": len(positive_factors),
            "neg_score": len(negative_factors),
        })

    conn.close()
    return evaluated

if __name__ == "__main__":
    cands = rank_candidates()
    # Sort by pos_score descending, neg_score ascending
    cands.sort(key=lambda x: (x["has_freight_role"], x["has_carrier"], x["pos_score"] - x["neg_score"]), reverse=True)

    print(f"Total Evaluated Candidates: {len(cands)}")
    print("\n--- TOP CANDIDATES WITH FREIGHT ROLE OR COMMERCIAL CARRIER ---")
    for c in cands[:35]:
        print(f"ID {c['comp_id']:<3} | {c['brand']:<35} | {c['sector']:<18} | Facs: {c['fac_count']} | Fric: {c['friction']:<6} | Pos: {c['pos_score']} | Carrier: {c['has_carrier']} | Role: {c['has_freight_role']}")
