"""
Detailed evaluation script for Stage 3F Qualification and Shortlisting.
Runs factual readiness gate checks and broker priority heuristics across all 523 Discovery companies.
"""
import sqlite3
import json
import urllib.parse
from typing import Dict, List, Any

LOWER_48_STATES = {
    "AL", "AR", "AZ", "CA", "CO", "CT", "DE", "FL", "GA", "IA", "ID", "IL", "IN", "KS", "KY",
    "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM",
    "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA",
    "WI", "WV", "WY", "DC"
}

CANADIAN_PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}

def evaluate_candidates():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Fetch all discovery companies and facilities
    companies_rows = conn.execute("""
        SELECT c.id, c.operating_brand, c.legal_name, c.corporate_address, c.website_url, c.notes
        FROM companies c
        JOIN facilities f ON c.id = f.company_id
        JOIN prospect_lifecycle l ON f.id = l.facility_id
        WHERE l.stage = 'DISCOVERY'
        GROUP BY c.id
        ORDER BY c.operating_brand
    """).fetchall()

    print(f"Total Discovery Companies to Review: {len(companies_rows)}")

    # For each company, evaluate facilities, commodities, contacts, claims, sources
    results = []
    for c in companies_rows:
        cid = c["id"]
        brand = c["operating_brand"]

        # Fetch facilities
        fac_rows = conn.execute("""
            SELECT f.id, f.facility_name, f.physical_address, f.city, f.state_prov, f.country,
                   f.commercial_carrier_use, f.private_fleet_present, f.freight_procurement_level
            FROM facilities f
            JOIN prospect_lifecycle l ON f.id = l.facility_id
            WHERE f.company_id = ? AND l.stage = 'DISCOVERY'
        """, (cid,)).fetchall()

        comp_eval = {
            "company_id": cid,
            "brand": brand,
            "legal_name": c["legal_name"],
            "website_url": c["website_url"],
            "facilities": [],
            "qualifies": False,
            "qualification_reasons": [],
            "failed_reasons": [],
            "shortlist_candidate": False,
            "shortlist_score": 0,
            "shortlist_reasons": [],
            "sector": "OTHER"
        }

        # Check company-wide sector from commodities
        comms = conn.execute("""
            SELECT fc.commodity_category, fc.specific_products, fc.equipment_category, fc.equipment_usage_status
            FROM facility_commodities fc
            JOIN facilities f ON fc.facility_id = f.id
            WHERE f.company_id = ?
        """, (cid,)).fetchall()

        comm_cats = [cm["commodity_category"] or "" for cm in comms]
        comm_text = " ".join(comm_cats).lower()
        if any(w in comm_text for w in ["wood", "lumber", "forest", "timber", "plywood"]):
            comp_eval["sector"] = "TRACK_A_WOOD"
        elif any(w in comm_text for w in ["steel", "metal", "tube", "pipe", "aluminum", "iron", "coil"]):
            comp_eval["sector"] = "TRACK_B_STEEL"
        elif any(w in comm_text for w in ["concrete", "precast", "building", "brick", "stone", "masonry", "roofing"]):
            comp_eval["sector"] = "TRACK_C_PRECAST_BUILDING"
        elif any(w in comm_text for w in ["plastic", "mold", "tooling", "machining", "fabricat", "industrial"]):
            comp_eval["sector"] = "TRACK_D_PLASTICS_TOOLING_INDUSTRIAL"
        else:
            comp_eval["sector"] = "TRACK_E_CROSS_SECTOR"

        # Check if country is Canada
        if any(f["country"] == "CA" for f in fac_rows):
            comp_eval["is_canada"] = True
        else:
            comp_eval["is_canada"] = False

        # Evaluate each facility
        all_facs_pass = True
        for f in fac_rows:
            fid = f["id"]
            addr = (f["physical_address"] or "").strip()
            city = (f["city"] or "").strip()
            state = (f["state_prov"] or "").strip().upper()
            country = (f["country"] or "").strip().upper()

            # Gate 1: Operating facility verified
            # Street address must be real, non-empty, non-PO-Box
            addr_valid = bool(addr and len(addr) > 5 and not addr.upper().startswith("P.O.") and not addr.upper().startswith("PO BOX"))
            city_valid = bool(city and len(city) >= 2)
            gate_facility = addr_valid and city_valid

            # Gate 2: Commodity / Equipment fit
            f_comms = [cm for cm in comms]
            has_approved_eq = any(
                any(eq in (cm["equipment_category"] or "") for eq in ["FLATBED", "STEP_DECK", "DRY_VAN"])
                for cm in f_comms
            )
            gate_commodity = has_approved_eq and len(f_comms) > 0

            # Gate 3: Geography
            if country == "US":
                gate_geo = (state in LOWER_48_STATES)
            elif country == "CA":
                gate_geo = (state in CANADIAN_PROVINCES or len(state) == 2)
            else:
                gate_geo = False

            # Gate 4: Outreach route
            cts = conn.execute("SELECT * FROM contacts WHERE facility_id = ?", (fid,)).fetchall()
            has_phone = any(ct["phone_number"] and ct["phone_number"].strip() and ct["phone_number"] != "UNKNOWN" for ct in cts)
            has_email = any(ct["email_address"] and ct["email_address"].strip() and ct["email_address"] != "UNKNOWN" for ct in cts)
            gate_outreach = (has_phone or has_email)

            # Gate 5: Evidence
            cur_ev = conn.execute("""
                SELECT COUNT(DISTINCT es.id)
                FROM claims c
                JOIN claim_evidence ce ON c.id = ce.claim_id
                JOIN evidence_sources es ON ce.evidence_source_id = es.id
                WHERE c.is_current_accepted = 1
                  AND (c.facility_id = ? OR c.company_id = ?)
            """, (fid, cid)).fetchone()[0]
            gate_evidence = (cur_ev > 0)

            f_pass = gate_facility and gate_commodity and gate_geo and gate_outreach and gate_evidence
            if not f_pass:
                all_facs_pass = False

            comp_eval["facilities"].append({
                "facility_id": fid,
                "name": f["facility_name"],
                "city": city,
                "state": state,
                "country": country,
                "pass": f_pass,
                "gate_facility": gate_facility,
                "gate_commodity": gate_commodity,
                "gate_geo": gate_geo,
                "gate_outreach": gate_outreach,
                "gate_evidence": gate_evidence,
                "has_phone": has_phone,
                "has_email": has_email,
                "contacts": [dict(ct) for ct in cts],
                "commodities": [dict(cm) for cm in f_comms],
                "sources_count": cur_ev
            })

        comp_eval["qualifies"] = all_facs_pass
        results.append(comp_eval)

    conn.close()
    return results

if __name__ == "__main__":
    res = evaluate_candidates()
    qual = [r for r in res if r["qualifies"]]
    print(f"\nCompanies passing baseline technical gates: {len(qual)} of {len(res)}")
    by_sector = {}
    for r in qual:
        by_sector[r["sector"]] = by_sector.get(r["sector"], 0) + 1
    print("Qualified by Sector:", by_sector)
