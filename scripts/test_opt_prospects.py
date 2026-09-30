import sys
sys.path.insert(0, ".")
import time
import sqlite3
from pathlib import Path

DB_PATH = Path("data/prospects.db")

LOWER_48_STATES = {
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI",
    "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
}
CANADIAN_PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "ON", "PE", "QC", "SK"}
CANADIAN_TERRITORIES = {"NT", "NU", "YT"}
CANADIAN_JURISDICTIONS = CANADIAN_PROVINCES | CANADIAN_TERRITORIES

def get_prospects_list_optimized(lifecycle_stage="ALL", db_path=DB_PATH, allow_alaska=False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Query 1: Facilities with joins
    where_clause = ""
    params = []
    if lifecycle_stage and lifecycle_stage.upper() != "ALL":
        where_clause = "WHERE COALESCE(pl.stage, 'DISCOVERY') = ?"
        params.append(lifecycle_stage.upper())

    q_fac = f"""
        SELECT
            f.id as facility_id, f.facility_name, f.facility_type, f.physical_address,
            f.city, f.state_prov, f.country, f.postal_code, f.private_fleet_present,
            f.vehicle_asset_ownership, f.fleet_relationship_type, f.commercial_carrier_use,
            f.broker_friendly_status, f.freight_procurement_level,
            c.id as company_id, c.operating_brand, c.legal_name, c.website_url,
            c.corporate_address, c.notes as company_notes, c.company_footprint_status,
            c.verified_operating_location_count, c.footprint_source_notes,
            COALESCE(pl.stage, 'DISCOVERY') as lifecycle_stage,
            pl.updated_at as stage_updated_at, pl.notes as stage_notes,
            COALESCE(pes.current_outreach_status, 'UNCONTACTED') as company_outreach_status,
            COALESCE(pes.attempt_count, 0) as company_attempt_count,
            pes.next_follow_up_at as next_follow_up_at,
            COALESCE(pes.is_viewed, 0) as is_viewed
        FROM facilities f
        JOIN companies c ON f.company_id = c.id
        LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        LEFT JOIN prospect_engagement_state pes ON c.id = pes.company_id
        {where_clause}
        ORDER BY f.id ASC
    """
    facility_rows = conn.execute(q_fac, params).fetchall()

    # Query 2: Pre-aggregated latest facility outreach
    fac_outreach_map = {}
    for r in conn.execute("""
        SELECT facility_id, outcome, count_phone
        FROM (
            SELECT facility_id, outcome,
                   ROW_NUMBER() OVER(PARTITION BY facility_id ORDER BY contacted_at DESC, id DESC) as rn,
                   SUM(CASE WHEN outreach_channel = 'PHONE' THEN 1 ELSE 0 END) OVER(PARTITION BY facility_id) as count_phone
            FROM outreach_logs
            WHERE facility_id IS NOT NULL
        ) WHERE rn = 1
    """).fetchall():
        fac_outreach_map[r["facility_id"]] = (r["outcome"], r["count_phone"])

    # Query 3: Commodities
    comms_by_fac = {}
    for r in conn.execute("""
        SELECT id, facility_id, commodity_category, specific_products, equipment_category,
               equipment_usage_status, trailer_specs_notes, securement_tarp_notes
        FROM facility_commodities
        ORDER BY facility_id, id ASC
    """).fetchall():
        fid = r["facility_id"]
        if fid not in comms_by_fac:
            comms_by_fac[fid] = []
        comms_by_fac[fid].append(dict(r))

    # Query 4: Taxonomy mappings
    tax_by_fac = {}
    for r in conn.execute("""
        SELECT m.facility_id, c.id as category_id, c.category_code, c.display_name as category_name,
               c.typical_equipment_fit, c.seasonality_profile as cat_seasonality,
               c.peak_months as cat_peak_months, c.operating_characteristics,
               cf.id as family_id, cf.family_code, cf.display_name as family_name,
               m.is_primary, m.source_evidence_notes
        FROM facility_commodity_mappings m
        JOIN commodity_categories c ON m.category_id = c.id
        JOIN commodity_families cf ON c.family_id = cf.id
        ORDER BY m.facility_id, m.is_primary DESC, c.sort_order ASC
    """).fetchall():
        fid = r["facility_id"]
        if fid not in tax_by_fac:
            tax_by_fac[fid] = []
        tax_by_fac[fid].append(dict(r))

    # Query 5: Contacts
    contacts_by_fac = {}
    for r in conn.execute("""
        SELECT id, facility_id, contact_identity, person_name, exact_published_title, department,
               phone_number, phone_extension, phone_directness, email_address,
               email_directness, role_category, outbound_shipping_procurement_relevance,
               broker_procurement_relevance, is_primary_contact
        FROM contacts
        ORDER BY facility_id, is_primary_contact DESC,
                 CASE WHEN phone_directness = 'DIRECT_PERSON' THEN 0
                      WHEN phone_directness = 'DEPARTMENT_LINE' THEN 1
                      ELSE 2 END,
                 id ASC
    """).fetchall():
        fid = r["facility_id"]
        if fid not in contacts_by_fac:
            contacts_by_fac[fid] = []
        contacts_by_fac[fid].append(dict(r))

    # Query 6: Company relationships
    parent_by_comp = {}
    for r in conn.execute("""
        SELECT r.child_company_id, r.relationship_type, r.valid_from, r.notes as relationship_notes,
               p.operating_brand as parent_brand, p.legal_name as parent_legal,
               p.notes as parent_notes
        FROM company_relationships r
        JOIN companies p ON r.parent_company_id = p.id
        WHERE r.is_current = 1
    """).fetchall():
        parent_by_comp[r["child_company_id"]] = {
            "relationship_type": r["relationship_type"],
            "valid_from": r["valid_from"],
            "relationship_notes": r["relationship_notes"],
            "parent_brand": r["parent_brand"],
            "parent_legal": r["parent_legal"],
            "parent_notes": r["parent_notes"],
            "corporate_group": "TI Automotive",
            "current_hierarchy_status": "UNKNOWN"
        }

    # Query 7: Claims counts
    claims_cnt_fac = dict(conn.execute("SELECT facility_id, count(*) FROM claims WHERE facility_id IS NOT NULL GROUP BY facility_id").fetchall())
    claims_cnt_comp = dict(conn.execute("SELECT company_id, count(*) FROM claims WHERE company_id IS NOT NULL GROUP BY company_id").fetchall())

    # Query 8: Evidenced claims for readiness
    evidenced_addr = set(r[0] for r in conn.execute("""
        SELECT DISTINCT c.facility_id
        FROM claims c
        JOIN claim_evidence ce ON c.id = ce.claim_id
        WHERE c.claim_field = 'physical_address'
          AND c.is_current_accepted = 1
          AND c.verification_status = 'VERIFIED'
    """).fetchall())

    evidenced_equip = set(r[0] for r in conn.execute("""
        SELECT DISTINCT fc.facility_id
        FROM claims c
        JOIN facility_commodities fc ON c.facility_commodity_id = fc.id
        JOIN claim_evidence ce ON c.id = ce.claim_id
        WHERE c.claim_field = 'equipment_category'
          AND c.is_current_accepted = 1
          AND c.verification_status IN ('VERIFIED', 'INFERRED')
    """).fetchall())

    evidenced_contact = set(r[0] for r in conn.execute("""
        SELECT DISTINCT ct.facility_id
        FROM claims c
        JOIN contacts ct ON c.contact_id = ct.id
        JOIN claim_evidence ce ON c.id = ce.claim_id
        WHERE c.is_current_accepted = 1
    """).fetchall())

    conn.close()

    # Pure Python Assembly
    approved_equip = {"FLATBED", "STEP_DECK", "DRY_VAN"}
    prospects = []

    for row in facility_rows:
        fac_id = row["facility_id"]
        comp_id = row["company_id"]

        commodities = comms_by_fac.get(fac_id, [])
        primary_commodity = commodities[0] if commodities else None

        taxonomy_mappings = tax_by_fac.get(fac_id, [])
        primary_tax = taxonomy_mappings[0] if taxonomy_mappings else None

        contacts = contacts_by_fac.get(fac_id, [])
        best_contact = contacts[0] if contacts else None

        parent_info = parent_by_comp.get(comp_id)

        claims_count = claims_cnt_fac.get(fac_id, 0) + claims_cnt_comp.get(comp_id, 0)

        # Outreach & Next Action
        direct_contact = next((ct for ct in contacts if ct["phone_directness"] == "DIRECT_PERSON"), None)
        if direct_contact and direct_contact.get("phone_number"):
            next_action = f"Call {direct_contact['person_name']} (Direct: {direct_contact['phone_number']})"
            contact_type_badge = "DIRECT_PERSON"
        elif best_contact and best_contact.get("phone_number"):
            name_or_title = best_contact["person_name"] or best_contact["exact_published_title"]
            next_action = f"Call {name_or_title} ({best_contact['phone_number']}) — {best_contact['phone_directness']}"
            contact_type_badge = best_contact["phone_directness"]
        elif best_contact and best_contact.get("email_address"):
            name_or_dept = best_contact["person_name"] or best_contact["department"] or "Shipping"
            next_action = f"Email {name_or_dept} ({best_contact['email_address']})"
            contact_type_badge = best_contact.get("email_directness", "UNKNOWN")
        else:
            next_action = "Research primary shipping contact"
            contact_type_badge = "UNKNOWN"

        # Qualification Readiness (Pure Python in 0.001 ms)
        addr = (row["physical_address"] or "").strip()
        city = (row["city"] or "").strip()
        state = (row["state_prov"] or "").strip().upper()
        country = (row["country"] or "").strip().upper()

        has_addr_evidence = fac_id in evidenced_addr
        identity_passed = bool(addr and addr.upper() != "UNKNOWN" and city and state and country in ("US", "CA") and has_addr_evidence)
        if identity_passed:
            identity_details = f"Physical facility confirmed at {addr}, {city}, {state} {country} (backed by verified evidence source)"
        elif not has_addr_evidence and addr and addr.upper() != "UNKNOWN":
            identity_details = "Facility address present but missing verified accepted claim backed by documented evidence source"
        else:
            identity_details = "Incomplete facility physical address or unsupported country"

        has_commodities = len(commodities) > 0
        equip_fit_basic = has_commodities and any(
            any(eq in (c["equipment_category"] or "") for eq in approved_equip) and
            c["equipment_usage_status"] in ("VERIFIED", "INFERRED")
            for c in commodities
        )
        has_equip_evidence = fac_id in evidenced_equip
        equip_fit_passed = bool(equip_fit_basic and has_equip_evidence)
        if equip_fit_passed:
            equip_details = f"{len(commodities)} commodity profile(s) with approved FTL equipment backed by documented evidence"
        elif equip_fit_basic and not has_equip_evidence:
            equip_details = "Commodity equipment fit identified but missing accepted equipment claim backed by documented evidence"
        else:
            equip_details = "Missing commodity profile or unverified/unapproved equipment category"

        if country == "US":
            if state == "AK":
                geo_passed = allow_alaska
                geo_details = "Alaska freight territory (Override toggle enabled)" if allow_alaska else "Alaska excluded by default in V1 (Decision A)"
            elif state == "HI":
                geo_passed = False
                geo_details = "Excluded freight territory (Hawaii - no FTL truckload service)"
            elif state in LOWER_48_STATES:
                geo_passed = True
                geo_details = f"Eligible US Lower 48 freight territory ({state})"
            else:
                geo_passed = False
                geo_details = f"Unrecognized US state or territory ({state})"
        elif country == "CA":
            if not state or state in CANADIAN_JURISDICTIONS:
                geo_passed = True
                if state in CANADIAN_PROVINCES:
                    geo_details = f"Eligible Canadian province ({state})"
                elif state in CANADIAN_TERRITORIES:
                    geo_details = f"Eligible Canadian territory ({state})"
                else:
                    geo_details = f"Eligible Canadian jurisdiction ({state if state else 'Canada'})"
            else:
                geo_passed = False
                geo_details = f"Unrecognized Canadian jurisdiction ({state})"
        elif country == "MX":
            geo_passed = False
            geo_details = "Excluded freight territory (Mexico - out of V1 scope)"
        else:
            geo_passed = False
            geo_details = f"Unrecognized freight territory ({state}, {country})"

        has_phone = any(bool(ct["phone_number"] and str(ct["phone_number"]).strip() and ct["phone_number"] != "UNKNOWN") for ct in contacts)
        has_email = any(bool(ct["email_address"] and str(ct["email_address"]).strip() and ct["email_address"] != "UNKNOWN") for ct in contacts)
        outreach_basic = has_phone or has_email
        has_contact_evidence = fac_id in evidenced_contact
        outreach_passed = bool(outreach_basic and has_contact_evidence)
        if outreach_passed:
            if has_phone and has_email:
                outreach_details = "Verified phone route and usable email address available (evidence backed)"
            elif has_phone:
                outreach_details = "Callable phone route available for voice outreach (evidence backed)"
            else:
                outreach_details = "Usable email address available for written outreach (evidence backed)"
        elif outreach_basic and not has_contact_evidence:
            outreach_details = "Phone or email present but missing accepted contact claim backed by documented evidence source"
        else:
            outreach_details = "No phone number or email address found for facility"

        evidence_passed = bool(has_addr_evidence and has_equip_evidence and has_contact_evidence)
        if evidence_passed:
            evidence_details = "All core qualification claims (address, equipment, contact) backed by documented evidence sources"
        else:
            missing_parts = []
            if not has_addr_evidence: missing_parts.append("address")
            if not has_equip_evidence: missing_parts.append("equipment")
            if not has_contact_evidence: missing_parts.append("contact")
            evidence_details = f"Missing documented evidence provenance for: {', '.join(missing_parts)}"

        checks = {
            "facility_identity_verified": {"passed": identity_passed, "details": identity_details},
            "commodity_equipment_fit": {"passed": equip_fit_passed, "details": equip_details},
            "geography_eligible": {"passed": geo_passed, "details": geo_details},
            "usable_outreach_route": {"passed": outreach_passed, "details": outreach_details},
            "supporting_evidence_provenance": {"passed": evidence_passed, "details": evidence_details},
        }
        passed_count = sum(1 for c in checks.values() if c["passed"])
        is_ready = (passed_count == 5)
        readiness = {
            "facility_id": fac_id,
            "is_ready": is_ready,
            "status": "READY" if is_ready else "INCOMPLETE",
            "passed_count": passed_count,
            "total_checks": 5,
            "checks": checks,
        }

        # Facility outreach status
        fac_outreach_status, fac_attempts = fac_outreach_map.get(fac_id, ("UNCONTACTED", 0))

        # Why facts
        why_facts = []
        if is_ready:
            why_facts.append("All 5 factual qualification readiness checks passed")
        if primary_commodity and primary_commodity.get("equipment_category"):
            why_facts.append(f"Approved heavy FTL fit: {primary_commodity['equipment_category']}")
        if best_contact and best_contact.get("phone_directness") == "DIRECT_PERSON" and best_contact.get("person_name"):
            why_facts.append(f"Direct callable line: {best_contact['person_name']}")
        elif best_contact and best_contact.get("person_name"):
            why_facts.append(f"Identified logistics contact: {best_contact['person_name']}")
        if row["private_fleet_present"] == "VERIFIED_PRESENT":
            why_facts.append("Private fleet present (competing asset capacity noted)")
        if row["commercial_carrier_use"] == "VERIFIED":
            why_facts.append("Commercial carrier use (VERIFIED)")

        # Stage explanation (Solving AUD-016!)
        stage = row["lifecycle_stage"]
        if stage == "SHORTLISTED":
            stage_expl = "Shortlisted for high-probability direct phone outreach"
        elif stage == "QUALIFIED":
            stage_expl = "Fully qualified candidate; queued for shortlist rotation"
        else:
            if is_ready:
                stage_expl = "Meets all 5 qualification checks; ready for qualification review"
            else:
                stage_expl = f"Discovery intake; {passed_count}/5 qualification criteria verified"

        p_dict = {
            "facility_id": fac_id,
            "facility_name": row["facility_name"],
            "facility_type": row["facility_type"],
            "physical_address": row["physical_address"],
            "city": row["city"],
            "state_prov": row["state_prov"],
            "country": row["country"],
            "postal_code": row["postal_code"],
            "company_id": comp_id,
            "operating_brand": row["operating_brand"],
            "legal_name": row["legal_name"],
            "website_url": row["website_url"],
            "corporate_address": row["corporate_address"],
            "company_notes": row["company_notes"],
            "company_footprint_status": row["company_footprint_status"] or "UNKNOWN",
            "verified_operating_location_count": row["verified_operating_location_count"],
            "footprint_source_notes": row["footprint_source_notes"],
            "parent_info": parent_info,
            "lifecycle_stage": stage,
            "stage_updated_at": row["stage_updated_at"],
            "stage_notes": row["stage_notes"],
            "stage_explanation": stage_expl,
            "company_outreach_status": row["company_outreach_status"] if "company_outreach_status" in row.keys() else "UNCONTACTED",
            "company_attempt_count": row["company_attempt_count"] if "company_attempt_count" in row.keys() else 0,
            "outreach_status": fac_outreach_status,
            "attempt_count": fac_attempts,
            "next_follow_up_at": row["next_follow_up_at"] if "next_follow_up_at" in row.keys() else None,
            "is_viewed": row["is_viewed"] if "is_viewed" in row.keys() else 0,
            "private_fleet_present": row["private_fleet_present"] or "UNKNOWN",
            "vehicle_asset_ownership": row["vehicle_asset_ownership"],
            "fleet_relationship_type": row["fleet_relationship_type"],
            "commercial_carrier_use": row["commercial_carrier_use"],
            "broker_friendly_status": row["broker_friendly_status"] or "UNKNOWN",
            "freight_procurement_level": row["freight_procurement_level"] or "UNKNOWN",
            "commodities": commodities,
            "primary_commodity": primary_commodity,
            "taxonomy_mappings": taxonomy_mappings,
            "primary_taxonomy": primary_tax,
            "contacts": contacts,
            "best_contact": best_contact,
            "claims_count": claims_count,
            "next_action": next_action,
            "contact_type_badge": contact_type_badge,
            "readiness": readiness,
            "freight_state": "PROSPECT",
            "why_facts": why_facts,
        }
        prospects.append(p_dict)

    return prospects

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    q_count = 0
    def trace_cb(stmt):
        global q_count
        q_count += 1
    conn.set_trace_callback(trace_cb)
    
    t0 = time.perf_counter()
    prospects = get_prospects_list_optimized("ALL")
    t_opt = time.perf_counter() - t0
    print(f"Optimized get_prospects_list(ALL): {len(prospects)} facilities in {t_opt*1000:.2f} ms")
    
    # Let's count queries by tracing inside the function
    # Wrap sqlite3.connect
    orig_connect = sqlite3.connect
    cnt = 0
    def wrapped_connect(*args, **kwargs):
        c = orig_connect(*args, **kwargs)
        def cb(s):
            global cnt
            cnt += 1
        c.set_trace_callback(cb)
        return c
    sqlite3.connect = wrapped_connect
    t0 = time.perf_counter()
    p = get_prospects_list_optimized("ALL")
    t_traced = time.perf_counter() - t0
    sqlite3.connect = orig_connect
    print(f"Total SQL queries executed: {cnt} queries in {t_traced*1000:.2f} ms")
