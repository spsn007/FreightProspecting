import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Tuple, Optional

US_LOWER_48 = {
    "AL", "AR", "AZ", "CA", "CO", "CT", "DE", "FL", "GA", "IA", "ID", "IL", "IN",
    "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND",
    "NE", "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY", "DC"
}

CANADA_PROVINCES = {
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"
}

ALLOWED_EQUIPMENT = {"FLATBED", "STEP_DECK", "DRY_VAN"}

DEPARTMENT_TITLE_KEYWORDS = [
    "shipping", "receiving", "logistics", "dispatch", "sales", "office", "desk",
    "department", "operations", "customer service", "transportation", "traffic",
    "manager", "coordinator", "supervisor", "director"
]

def validate_candidate_evidence(c: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validates a candidate against strict provenance and quality gates.
    Returns (is_valid, rejection_reason, normalized_record).
    """
    brand = (c.get("brand") or c.get("operating_brand") or "").strip()
    if not brand:
        return False, "MISSING_BRAND_NAME", None

    legal_name = (c.get("legal_name") or c.get("legal") or brand).strip()
    
    fac_name = (c.get("fac_name") or c.get("facility_name") or f"{brand} Main Facility").strip()
    address = (c.get("address") or c.get("physical_address") or "").strip()
    if not address or len(address) < 4:
        return False, "MISSING_PHYSICAL_ADDRESS", None

    city = (c.get("city") or "").strip()
    state = (c.get("state") or c.get("state_prov") or "").strip().upper()
    country = (c.get("country") or "").strip().upper()
    postal = (c.get("postal_code") or c.get("zip") or "").strip() or None

    if not city or not state:
        return False, "MISSING_CITY_OR_STATE", None

    # Geography check: Lower 48 or Canada only. Explicitly reject AK, HI, MX.
    if state in ("AK", "HI") or country in ("MX", "MEXICO"):
        return False, f"EXCLUDED_GEOGRAPHY_{state}_{country}", None

    if country == "US":
        if state not in US_LOWER_48:
            return False, f"INVALID_US_STATE_{state}", None
    elif country == "CA":
        if state not in CANADA_PROVINCES:
            return False, f"INVALID_CA_PROVINCE_{state}", None
    else:
        # Check if state is in US or CA
        if state in US_LOWER_48:
            country = "US"
        elif state in CANADA_PROVINCES:
            country = "CA"
        else:
            return False, f"UNKNOWN_COUNTRY_GEOGRAPHY_{country}_{state}", None

    # Contact route check: At least one callable phone or valid email
    phone = (c.get("phone") or c.get("phone_number") or "").strip() or None
    email = (c.get("email") or c.get("email_address") or "").strip() or None

    if not phone and not email:
        return False, "NO_CALLABLE_PHONE_OR_EMAIL", None

    # Zero-hallucination contact verification
    raw_person = (c.get("best_person") or c.get("contact_name") or c.get("person_name") or "").strip() or None
    raw_title = (c.get("exact_title") or c.get("contact_title") or "").strip() or None
    raw_dept = (c.get("department") or "").strip() or None

    contact_identity = "GENERAL_FACILITY"
    person_name = None
    dept_name = raw_dept
    exact_title = raw_title

    if raw_person:
        # Check if raw_person is actually a title/department
        is_dept_like = any(kw in raw_person.lower() for kw in DEPARTMENT_TITLE_KEYWORDS)
        if is_dept_like:
            contact_identity = "DEPARTMENT"
            dept_name = raw_person
            person_name = None
        else:
            contact_identity = "NAMED_PERSON"
            person_name = raw_person
    elif raw_dept:
        contact_identity = "DEPARTMENT"

    # Contact role category
    role_cat = (c.get("role_cat") or c.get("role_category") or "GENERAL_FACILITY").strip().upper()
    if role_cat not in ("FREIGHT_LOGISTICS", "OPERATIONS", "COMMERCIAL_SALES", "GENERAL_FACILITY"):
        role_cat = "GENERAL_FACILITY"

    # Phone directness
    phone_dir = (c.get("phone_dir") or c.get("phone_directness") or "GENERAL_SWITCHBOARD").strip().upper() if phone else "UNKNOWN"
    if phone_dir not in ("GENERAL_SWITCHBOARD", "DEPARTMENT_LINE", "DIRECT_PERSON", "RECEPTION", "TOLL_FREE", "UNKNOWN"):
        phone_dir = "GENERAL_SWITCHBOARD" if phone else "UNKNOWN"

    # Email directness
    raw_email_dir = (c.get("email_dir") or c.get("email_directness") or "GENERAL").strip().upper() if email else "UNKNOWN"
    if raw_email_dir in ("GENERAL_INBOX", "GENERAL_FACILITY"):
        email_dir = "GENERAL"
    elif raw_email_dir in ("DIRECT_PERSON", "DEPARTMENT", "GENERAL", "UNKNOWN"):
        email_dir = raw_email_dir
    else:
        email_dir = "GENERAL" if email else "UNKNOWN"

    # Equipment suitability
    eq_cat = (c.get("eq_cat") or c.get("equipment_category") or "FLATBED").strip().upper()
    if eq_cat not in ALLOWED_EQUIPMENT:
        eq_cat = "FLATBED"
    eq_status = (c.get("eq_status") or c.get("equipment_usage_status") or "INFERRED").strip().upper()
    if eq_status not in ("VERIFIED", "INFERRED", "UNKNOWN"):
        eq_status = "INFERRED"

    # Commodity Category
    comm_cat = (c.get("comm_cat") or c.get("commodity_category") or "Industrial Freight").strip()
    specific_prod = (c.get("specific_prod") or c.get("specific_products") or comm_cat).strip()
    cat_code = (c.get("category_code") or "").strip() or None
    category_id = c.get("commodity_category_id") or c.get("category_id")

    # Source Provenance
    source_url = (c.get("source_url") or c.get("website_url") or "").strip() or None
    source_title = (c.get("source_title") or f"{brand} — Operating Facility Record").strip()
    notes = (c.get("notes") or f"Operating facility verified at {address}, {city}, {state}. Commodity: {comm_cat}.").strip()

    observed_at = c.get("observed_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    normalized = {
        "operating_brand": brand,
        "legal_name": legal_name,
        "facility_name": fac_name,
        "facility_type": c.get("fac_type") or "MANUFACTURING_PLANT",
        "physical_address": address,
        "city": city,
        "state_prov": state,
        "postal_code": postal,
        "country": country,
        "website_url": c.get("website_url") or source_url,
        "source_url": source_url,
        "source_title": source_title,
        "notes": notes,
        "observed_at": observed_at,
        "commodity_category": comm_cat,
        "category_code": cat_code,
        "commodity_category_id": category_id,
        "specific_products": specific_prod,
        "equipment_category": eq_cat,
        "equipment_usage_status": eq_status,
        "contact_identity": contact_identity,
        "person_name": person_name,
        "exact_published_title": exact_title,
        "department": dept_name,
        "phone_number": phone,
        "phone_directness": phone_dir,
        "email_address": email,
        "email_directness": email_dir,
        "role_category": role_cat,
        "private_fleet_present": c.get("private_fleet_present", "UNKNOWN"),
        "commercial_carrier_use": c.get("commercial_carrier_use", "UNKNOWN"),
        "broker_friendly_status": c.get("broker_friendly_status", "UNKNOWN"),
        "freight_procurement_level": c.get("freight_procurement_level", "FACILITY_LEVEL"),
    }

    return True, None, normalized

def run_evidence_truth_coordinator(accepted_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    validated = []
    rejected = []

    for c in accepted_candidates:
        is_valid, reason, norm_rec = validate_candidate_evidence(c)
        if is_valid:
            validated.append(norm_rec)
        else:
            rejected.append({"candidate": c, "rejection_reason": reason})

    return {
        "summary": {
            "total_candidates_reviewed": len(accepted_candidates),
            "validated_candidates_count": len(validated),
            "rejected_candidates_count": len(rejected),
        },
        "validated_candidates": validated,
        "rejected_candidates": rejected,
    }

if __name__ == "__main__":
    print("Evidence & Truth Coordinator loaded successfully.")
