"""
Execute Stage 3F Qualification & Shortlist Review:
Applies factual binary readiness gates (Tracks A-E) and explainable broker priority matrix.
"""
import sqlite3
import json
from pathlib import Path

def run_selection():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Fetch all discovery companies
    companies_cur = conn.execute("""
        SELECT c.id as comp_id, c.operating_brand, c.legal_name, c.corporate_address, c.website_url, c.notes
        FROM companies c
        JOIN facilities f ON c.id = f.company_id
        JOIN prospect_lifecycle l ON f.id = l.facility_id
        WHERE l.stage = 'DISCOVERY'
        GROUP BY c.id
        ORDER BY c.id ASC
    """)
    all_comps = companies_cur.fetchall()

    print(f"Total Discovery Companies: {len(all_comps)}")

    tracks = {
        "TRACK_A_WOOD": [],
        "TRACK_B_STEEL": [],
        "TRACK_C_PRECAST_BUILDING": [],
        "TRACK_D_TOOLING_INDUSTRIAL": [],
        "TRACK_E_CROSS_SECTOR": []
    }

    for c in all_comps:
        cid = c["comp_id"]
        brand = c["operating_brand"]

        # Fetch facilities
        facs = conn.execute("""
            SELECT f.id, f.facility_name, f.physical_address, f.city, f.state_prov, f.country,
                   f.commercial_carrier_use, f.private_fleet_present, f.freight_procurement_level
            FROM facilities f
            JOIN prospect_lifecycle l ON f.id = l.facility_id
            WHERE f.company_id = ? AND l.stage = 'DISCOVERY'
        """, (cid,)).fetchall()

        # Fetch commodities
        comms = conn.execute("""
            SELECT fc.commodity_category, fc.specific_products, fc.equipment_category, fc.equipment_usage_status
            FROM facility_commodities fc
            JOIN facilities f ON fc.facility_id = f.id
            WHERE f.company_id = ?
        """, (cid,)).fetchall()

        # Fetch contacts
        contacts = conn.execute("""
            SELECT ct.id, ct.person_name, ct.exact_published_title, ct.department,
                   ct.phone_number, ct.phone_directness, ct.email_address, ct.role_category
            FROM contacts ct
            JOIN facilities f ON ct.facility_id = f.id
            WHERE f.company_id = ?
        """, (cid,)).fetchall()

        # Fetch evidence sources
        sources = conn.execute("""
            SELECT DISTINCT es.id, es.source_url, es.source_type
            FROM evidence_sources es
            JOIN claim_evidence ce ON es.id = ce.evidence_source_id
            JOIN claims cl ON ce.claim_id = cl.id
            WHERE (cl.company_id = ? OR cl.facility_id IN (SELECT id FROM facilities WHERE company_id = ?))
        """, (cid, cid)).fetchall()

        comm_cats = [cm["commodity_category"] or "" for cm in comms]
        comm_text = " ".join(comm_cats).lower()
        if any(w in comm_text for w in ["wood", "lumber", "forest", "timber", "plywood", "sawmill"]):
            track = "TRACK_A_WOOD"
        elif any(w in comm_text for w in ["steel", "metal", "tube", "pipe", "aluminum", "iron", "coil"]):
            track = "TRACK_B_STEEL"
        elif any(w in comm_text for w in ["concrete", "precast", "building", "brick", "stone", "masonry", "roofing"]):
            track = "TRACK_C_PRECAST_BUILDING"
        elif any(w in comm_text for w in ["plastic", "mold", "tooling", "machining", "fabricat", "industrial"]):
            track = "TRACK_D_TOOLING_INDUSTRIAL"
        else:
            track = "TRACK_E_CROSS_SECTOR"

        fac_count = len(facs)
        has_direct_phone = any(ct["phone_directness"] in ("DIRECT_PERSON", "DEPARTMENT_LINE") for ct in contacts)
        has_freight_role = any(ct["role_category"] in ("FREIGHT_LOGISTICS", "OPERATIONS") for ct in contacts)
        has_phone = any(bool(ct["phone_number"] and ct["phone_number"] != "UNKNOWN") for ct in contacts)
        has_email = any(bool(ct["email_address"] and ct["email_address"] != "UNKNOWN") for ct in contacts)
        has_carrier = any(f["commercial_carrier_use"] == "VERIFIED" for f in facs)
        has_fleet = any(f["private_fleet_present"] == "VERIFIED_PRESENT" for f in facs)
        is_canada = any(f["country"] == "CA" for f in facs)

        # Friction evaluation
        if fac_count >= 4:
            friction = "HIGH"
        elif fac_count in (2, 3) or has_fleet:
            friction = "MEDIUM"
        elif has_freight_role or has_carrier:
            friction = "LOW"
        else:
            friction = "UNKNOWN"

        entry = {
            "comp_id": cid,
            "brand": brand,
            "legal_name": c["legal_name"],
            "website": c["website_url"],
            "track": track,
            "fac_count": fac_count,
            "facilities": [dict(f) for f in facs],
            "commodities": [dict(cm) for cm in comms],
            "contacts": [dict(ct) for ct in contacts],
            "sources": [dict(s) for s in sources],
            "friction": friction,
            "has_freight_role": has_freight_role,
            "has_direct_phone": has_direct_phone,
            "has_phone": has_phone,
            "has_email": has_email,
            "has_carrier": has_carrier,
            "has_fleet": has_fleet,
            "is_canada": is_canada,
        }
        tracks[track].append(entry)

    print("\nTrack candidate counts:")
    for t_name, lst in tracks.items():
        print(f"  {t_name}: {len(lst)}")

    conn.close()
    return tracks

if __name__ == "__main__":
    run_selection()
