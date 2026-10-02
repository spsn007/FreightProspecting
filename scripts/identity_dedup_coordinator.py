import json
import re
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any, List, Tuple

import sys
sys.path.insert(0, '.')
from scripts.build_identity_index import normalize_text, extract_domain, normalize_phone, normalize_address

KNOWN_CORPORATE_FAMILIES = {
    "beasley": ["beasleyforestproducts", "beasleygroup", "thompsonhardwoods", "sunnysidelumber"],
    "boisecascade": ["boisecascade", "coastalforestresources", "coastalplywood"],
    "weyerhaeuser": ["weyerhaeuser"],
    "westfraser": ["westfraser", "norbord"],
    "canfor": ["canfor"],
    "georgiapacific": ["georgiapacific", "gp"],
    "interfor": ["interfor"],
    "sierrapacific": ["sierrapacificindustries"],
    "resolute": ["resolutefp", "resoluteforestproducts"],
    "nucor": ["nucor", "harrisrebar", "vulcraft", "davidjjoseph"],
    "steeldynamics": ["steeldynamics", "omnisource", "newcor"],
    "ussteel": ["unitedstatessteel", "ussteel", "bigriversteel"],
    "clivancor": ["clevelandcliffs", "clevelandcliffssteel"],
    "reliance": ["reliancesteelandaluminum", "reliance", "onealsteel"],
    "oldcastle": ["oldcastle", "crh", "oldcastleinfrastructure", "oldcastlebuildingenvelope", "amerimix"],
    "rinker": ["rinkermaterials", "cemex", "quikrete"],
    "berryglobal": ["berryglobal", "berryplastics"],
    "amcor": ["amcor", "bemis"],
    "greif": ["greif", "greifpackaging"],
    "ip": ["internationalpaper"],
    "packagingcorp": ["packagingcorporationofamerica", "pca", "boiseinc"],
    "sonoco": ["sonoco", "sonocoproducts"],
    "graphicpackaging": ["graphicpackaging", "graphicpackaginginternational"],
    "smurfitkappa": ["smurfitkappa", "westrock", "smurfitwestrock"],
}

def classify_duplicate(candidate: Dict[str, Any], existing_index: Dict[str, Any]) -> Tuple[bool, str, str]:
    """
    Returns (is_duplicate, duplicate_type, reason_detail).
    If is_duplicate is False, duplicate_type is '' and reason_detail is 'ACCEPTED_UNIQUE'.
    """
    brand = candidate.get("brand") or candidate.get("operating_brand") or ""
    legal = candidate.get("legal_name") or candidate.get("legal") or ""
    url = candidate.get("website_url") or candidate.get("url") or candidate.get("source_url") or ""
    address = candidate.get("address") or candidate.get("physical_address") or ""
    city = candidate.get("city") or ""
    state = candidate.get("state") or candidate.get("state_prov") or ""
    phone = candidate.get("phone") or candidate.get("phone_number") or ""

    b_norm = normalize_text(brand)
    l_norm = normalize_text(legal)
    d_norm = extract_domain(url)
    a_norm = normalize_address(address)
    p_norm = normalize_phone(phone)
    cs_norm = f"{normalize_text(city)}|{normalize_text(state)}"

    lookup = existing_index["lookup"]
    companies = existing_index["companies"]

    # 1. Check EXACT physical address match
    if a_norm and a_norm in lookup["addresses_norm"]:
        matched_cids = lookup["addresses_norm"][a_norm]
        matched_c = companies[str(matched_cids[0])] if str(matched_cids[0]) in companies else companies[matched_cids[0]]
        return True, "SAME_ADDRESS_SAME_ENTITY", f"Address matches existing company '{matched_c['operating_brand']}' (ID: {matched_c['company_id']})"

    # 2. Check EXACT domain match
    if d_norm and d_norm in lookup["domains"]:
        matched_cids = lookup["domains"][d_norm]
        matched_c = companies[str(matched_cids[0])] if str(matched_cids[0]) in companies else companies[matched_cids[0]]
        # If domain matches and address differs -> EXISTING_COMPANY_NEW_FACILITY
        if a_norm and a_norm not in matched_c["facility_addresses_norm"]:
            return True, "EXISTING_COMPANY_NEW_FACILITY", f"Domain '{d_norm}' matches existing company '{matched_c['operating_brand']}' at new location ({city}, {state})"
        else:
            return True, "SAME_DOMAIN_SAME_ENTITY", f"Domain '{d_norm}' matches existing company '{matched_c['operating_brand']}' (ID: {matched_c['company_id']})"

    # 3. Check EXACT brand match
    if b_norm and b_norm in lookup["brands_norm"]:
        matched_cids = lookup["brands_norm"][b_norm]
        matched_c = companies[str(matched_cids[0])] if str(matched_cids[0]) in companies else companies[matched_cids[0]]
        if cs_norm in matched_c["cities_states"] or a_norm in matched_c["facility_addresses_norm"]:
            return True, "EXACT_EXISTING_COMPANY", f"Brand '{brand}' matches existing company in same city/state (ID: {matched_c['company_id']})"
        else:
            return True, "EXISTING_COMPANY_NEW_FACILITY", f"Brand '{brand}' matches existing company '{matched_c['operating_brand']}' at new location ({city}, {state})"

    # 4. Check Legal Name match
    if l_norm and l_norm in lookup["legals_norm"]:
        matched_cids = lookup["legals_norm"][l_norm]
        matched_c = companies[str(matched_cids[0])] if str(matched_cids[0]) in companies else companies[matched_cids[0]]
        return True, "EXACT_EXISTING_COMPANY", f"Legal name '{legal}' matches existing company '{matched_c['operating_brand']}' (ID: {matched_c['company_id']})"

    # 5. Check Brand Suffix / Alias match (e.g. stripping inc, llc, corp, co)
    clean_b = re.sub(r"(inc|llc|corp|corporation|co|company|ltd|limited)$", "", b_norm)
    if clean_b and len(clean_b) > 4:
        for ex_b, cids in lookup["brands_norm"].items():
            clean_ex = re.sub(r"(inc|llc|corp|corporation|co|company|ltd|limited)$", "", ex_b)
            if clean_b == clean_ex:
                matched_c = companies[str(cids[0])] if str(cids[0]) in companies else companies[cids[0]]
                return True, "OPERATING_BRAND_ALIAS", f"Brand alias '{brand}' matches existing company '{matched_c['operating_brand']}' (ID: {matched_c['company_id']})"

    # 6. Check Parent / Corporate Family Match
    for fam_name, members in KNOWN_CORPORATE_FAMILIES.items():
        if any(m in b_norm for m in members):
            # check if any member is in existing DB
            for ex_b, cids in lookup["brands_norm"].items():
                if any(m in ex_b for m in members):
                    matched_c = companies[str(cids[0])] if str(cids[0]) in companies else companies[cids[0]]
                    # If brand matches the existing parent name
                    if fam_name in b_norm and fam_name in ex_b:
                        return True, "PARENT_SUBSIDIARY_MATCH", f"Belongs to known existing corporate group '{fam_name}' (matches ID {matched_c['company_id']})"

    # 7. Check Phone Match
    if p_norm and len(p_norm) >= 10 and p_norm in lookup["phones_norm"]:
        matched_cids = lookup["phones_norm"][p_norm]
        matched_c = companies[str(matched_cids[0])] if str(matched_cids[0]) in companies else companies[matched_cids[0]]
        return True, "AMBIGUOUS_IDENTITY_REVIEW", f"Phone number {phone} matches existing company '{matched_c['operating_brand']}' (ID: {matched_c['company_id']})"

    return False, "", "ACCEPTED_UNIQUE"


def run_identity_dedup_coordinator(raw_candidates: List[Dict[str, Any]], existing_index_path: str = "reports/expansion_1000_identity_dedup.json") -> Dict[str, Any]:
    with open(existing_index_path, "r", encoding="utf-8") as f:
        existing_index = json.load(f)

    rejected_duplicates = []
    accepted_candidates = []
    seen_in_batch_brands = {}
    seen_in_batch_domains = {}
    seen_in_batch_addresses = {}

    type_counts = {
        "EXACT_EXISTING_COMPANY": 0,
        "EXISTING_COMPANY_NEW_FACILITY": 0,
        "PARENT_SUBSIDIARY_MATCH": 0,
        "OPERATING_BRAND_ALIAS": 0,
        "SAME_DOMAIN_SAME_ENTITY": 0,
        "SAME_ADDRESS_SAME_ENTITY": 0,
        "AMBIGUOUS_IDENTITY_REVIEW": 0,
        "DUPLICATE_IN_BATCH": 0,
    }

    for c in raw_candidates:
        brand = c.get("brand") or c.get("operating_brand") or ""
        url = c.get("website_url") or c.get("url") or c.get("source_url") or ""
        address = c.get("address") or c.get("physical_address") or ""
        city = c.get("city") or ""
        state = c.get("state") or c.get("state_prov") or ""

        b_norm = normalize_text(brand)
        d_norm = extract_domain(url)
        a_norm = normalize_address(address)

        # 1. Check against existing database index
        is_dup, dup_type, reason = classify_duplicate(c, existing_index)
        if is_dup:
            type_counts[dup_type] = type_counts.get(dup_type, 0) + 1
            rejected_duplicates.append({
                "candidate": c,
                "rejection_type": dup_type,
                "reason": reason,
            })
            continue

        # 2. Check in-batch duplicates across discovered candidates
        clean_b = re.sub(r"(inc|llc|corp|corporation|co|company|ltd|limited)$", "", b_norm)
        if clean_b in seen_in_batch_brands:
            prev = seen_in_batch_brands[clean_b]
            type_counts["DUPLICATE_IN_BATCH"] += 1
            rejected_duplicates.append({
                "candidate": c,
                "rejection_type": "DUPLICATE_IN_BATCH",
                "reason": f"Duplicate brand in batch matches earlier candidate '{prev['brand']}'",
            })
            continue

        if d_norm and d_norm in seen_in_batch_domains:
            prev = seen_in_batch_domains[d_norm]
            type_counts["DUPLICATE_IN_BATCH"] += 1
            rejected_duplicates.append({
                "candidate": c,
                "rejection_type": "DUPLICATE_IN_BATCH",
                "reason": f"Duplicate domain '{d_norm}' in batch matches earlier candidate '{prev['brand']}'",
            })
            continue

        if a_norm and a_norm in seen_in_batch_addresses:
            prev = seen_in_batch_addresses[a_norm]
            type_counts["DUPLICATE_IN_BATCH"] += 1
            rejected_duplicates.append({
                "candidate": c,
                "rejection_type": "DUPLICATE_IN_BATCH",
                "reason": f"Duplicate physical address in batch matches earlier candidate '{prev['brand']}'",
            })
            continue

        # Register in batch tracker
        c_summary = {"brand": brand, "url": url, "address": address, "city": city, "state": state}
        if clean_b:
            seen_in_batch_brands[clean_b] = c_summary
        if d_norm:
            seen_in_batch_domains[d_norm] = c_summary
        if a_norm:
            seen_in_batch_addresses[a_norm] = c_summary

        accepted_candidates.append(c)

    result = {
        "summary": {
            "raw_candidates_evaluated": len(raw_candidates),
            "rejected_duplicates_total": len(rejected_duplicates),
            "accepted_unique_candidates": len(accepted_candidates),
            "duplicate_breakdown": type_counts,
        },
        "accepted_candidates": accepted_candidates,
        "rejected_duplicates": rejected_duplicates,
    }

    return result

if __name__ == "__main__":
    print("Identity & Dedup Coordinator loaded successfully.")
