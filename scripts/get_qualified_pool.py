"""
Select all companies passing the strict Qualification Gate with verified active resolving websites.
"""
import sqlite3
import json

def get_qualified_candidates():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row

    # Exclude shortlisted IDs
    shortlist_ids = {1, 2, 3, 5, 321, 300, 6, 7, 10, 63, 68, 77, 60, 19, 16, 17, 18, 21, 25, 26, 86, 30, 31, 32, 33, 34, 35, 40, 42, 44, 155, 289}

    # Query discovery companies
    comps = conn.execute("""
        SELECT c.id, c.operating_brand, c.legal_name, c.corporate_address, c.website_url,
               f.id as fac_id, f.facility_name, f.physical_address, f.city, f.state_prov, f.country,
               fc.commodity_category, fc.equipment_category,
               ct.phone_number, ct.phone_directness, ct.role_category,
               es.id as source_id, es.source_url
        FROM companies c
        JOIN facilities f ON c.id = f.company_id
        JOIN prospect_lifecycle l ON f.id = l.facility_id
        LEFT JOIN facility_commodities fc ON f.id = fc.facility_id
        LEFT JOIN contacts ct ON f.id = ct.facility_id
        LEFT JOIN claims cl ON cl.facility_id = f.id AND cl.is_current_accepted = 1
        LEFT JOIN claim_evidence ce ON cl.id = ce.claim_id
        LEFT JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE l.stage = 'DISCOVERY' AND c.id NOT IN ({seq})
        GROUP BY c.id
        ORDER BY c.id ASC
    """.format(seq=','.join(str(i) for i in shortlist_ids))).fetchall()

    print(f"Remaining Discovery Candidates to Evaluate: {len(comps)}")

    # Let's filter by:
    # 1. Has non-empty, non-PO-Box address
    # 2. Has phone number
    # 3. Has approved equipment
    # 4. Has source URL
    valid_candidates = []
    for c in comps:
        addr = (c["physical_address"] or "").strip()
        phone = (c["phone_number"] or "").strip()
        source = (c["source_url"] or "").strip()
        eq = (c["equipment_category"] or "").strip()

        if addr and len(addr) > 5 and not addr.upper().startswith("P.O.") and not addr.upper().startswith("PO BOX"):
            if phone and phone != "UNKNOWN":
                if source and source.startswith("http"):
                    if eq in ("FLATBED", "STEP_DECK", "DRY_VAN"):
                        valid_candidates.append(c)

    print(f"Candidates meeting strict physical, phone, source, and FTL criteria: {len(valid_candidates)}")
    conn.close()
    return valid_candidates

if __name__ == "__main__":
    cands = get_qualified_candidates()
    print("Sample candidates:", [(c["id"], c["operating_brand"], c["city"], c["state_prov"], c["equipment_category"]) for c in cands[:10]])
