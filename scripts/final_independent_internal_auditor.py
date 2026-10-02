import sqlite3
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Set

import sys
sys.path.insert(0, '.')
from src.backend.db.opportunity import load_opportunity_universe_context
from scripts.build_identity_index import normalize_text, extract_domain, normalize_address, normalize_phone

FORBIDDEN_PERSON_NAMES = [
    "shipping", "receiving", "logistics", "dispatch", "sales", "office", "desk",
    "department", "operations", "customer service", "transportation", "traffic",
    "manager", "coordinator", "supervisor", "director"
]

def run_independent_audit(db_path: str = "data/prospects.db", initial_company_max_id: int = 567) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    findings = []
    
    # 1. Structural DB Integrity
    integ = conn.execute("PRAGMA integrity_check;").fetchall()
    if len(integ) != 1 or integ[0][0] != "ok":
        findings.append({"severity": "CRITICAL", "type": "INTEGRITY_CHECK_FAILED", "detail": str([tuple(r) for r in integ])})

    fks = conn.execute("PRAGMA foreign_key_check;").fetchall()
    if len(fks) > 0:
        findings.append({"severity": "CRITICAL", "type": "FK_CHECK_FAILED", "detail": str(fks)})

    # 2. Scope Newly Added Universe
    new_companies = conn.execute("SELECT * FROM companies WHERE id > ?", (initial_company_max_id,)).fetchall()
    new_company_ids = set(c["id"] for c in new_companies)

    new_facs = conn.execute("SELECT * FROM facilities WHERE company_id IN ({})".format(
        ",".join(str(i) for i in new_company_ids) if new_company_ids else "0"
    )).fetchall()
    new_fac_ids = set(f["id"] for f in new_facs)

    new_contacts = conn.execute("SELECT * FROM contacts WHERE company_id IN ({}) OR facility_id IN ({})".format(
        ",".join(str(i) for i in new_company_ids) if new_company_ids else "0",
        ",".join(str(i) for i in new_fac_ids) if new_fac_ids else "0"
    )).fetchall()

    new_claims = conn.execute("""
        SELECT * FROM claims
        WHERE company_id IN ({})
           OR facility_id IN ({})
           OR contact_id IN ({})
           OR facility_commodity_id IN (SELECT id FROM facility_commodities WHERE facility_id IN ({}))
    """.format(
        ",".join(str(i) for i in new_company_ids) if new_company_ids else "0",
        ",".join(str(i) for i in new_fac_ids) if new_fac_ids else "0",
        ",".join(str(c["id"]) for c in new_contacts) if new_contacts else "0",
        ",".join(str(i) for i in new_fac_ids) if new_fac_ids else "0"
    )).fetchall()

    # 3. Duplicate Companies across newly added
    seen_brands = {}
    seen_domains = {}
    seen_addresses = {}
    
    dup_companies_found = 0
    for c in new_companies:
        b_norm = normalize_text(c["operating_brand"])
        clean_b = re.sub(r"(inc|llc|corp|corporation|co|company|ltd|limited)$", "", b_norm)
        d_norm = extract_domain(c["website_url"])

        if clean_b in seen_brands:
            findings.append({
                "severity": "ERROR",
                "type": "DUPLICATE_COMPANY_BRAND",
                "company_id": c["id"],
                "detail": f"Duplicate brand '{c['operating_brand']}' matches earlier new company ID {seen_brands[clean_b]}",
            })
            dup_companies_found += 1
        else:
            seen_brands[clean_b] = c["id"]

        if d_norm and d_norm in seen_domains:
            findings.append({
                "severity": "ERROR",
                "type": "DUPLICATE_COMPANY_DOMAIN",
                "company_id": c["id"],
                "detail": f"Duplicate domain '{d_norm}' matches earlier new company ID {seen_domains[d_norm]}",
            })
            dup_companies_found += 1
        elif d_norm:
            seen_domains[d_norm] = c["id"]

    # 4. Check Facility Addresses
    for f in new_facs:
        a_norm = normalize_address(f["physical_address"])
        cs_norm = f"{normalize_text(f['city'])}|{normalize_text(f['state_prov'])}"
        if a_norm in seen_addresses:
            findings.append({
                "severity": "ERROR",
                "type": "DUPLICATE_FACILITY_ADDRESS",
                "facility_id": f["id"],
                "detail": f"Duplicate address matches facility ID {seen_addresses[a_norm]}",
            })
        else:
            seen_addresses[a_norm] = f["id"]

        # Geography check
        state = (f["state_prov"] or "").upper()
        country = (f["country"] or "").upper()
        if state in ("AK", "HI") or country in ("MX", "MEXICO"):
            findings.append({
                "severity": "ERROR",
                "type": "EXCLUDED_GEOGRAPHY",
                "facility_id": f["id"],
                "detail": f"Facility in excluded territory {state}, {country}",
            })

    # 5. Contact Checks: Fake person names
    fake_person_names = 0
    for ct in new_contacts:
        pname = ct["person_name"]
        if pname:
            p_lower = pname.lower()
            if any(kw == p_lower or f" {kw}" in p_lower or f"{kw} " in p_lower for kw in FORBIDDEN_PERSON_NAMES):
                findings.append({
                    "severity": "ERROR",
                    "type": "FAKE_PERSON_NAME",
                    "contact_id": ct["id"],
                    "detail": f"Person name '{pname}' appears to be a title or department name",
                })
                fake_person_names += 1

    # 6. Duplicate Current Claims Invariant
    dup_curr_claims = conn.execute("""
        SELECT facility_id, claim_field, count(*) FROM claims
        WHERE is_current_accepted = 1 AND facility_id IN ({})
        GROUP BY facility_id, claim_field HAVING count(*) > 1
    """.format(",".join(str(i) for i in new_fac_ids) if new_fac_ids else "0")).fetchall()
    if len(dup_curr_claims) > 0:
        findings.append({
            "severity": "CRITICAL",
            "type": "DUPLICATE_CURRENT_ACCEPTED_CLAIMS",
            "detail": f"Found {len(dup_curr_claims)} duplicate current accepted claims",
        })

    # 7. Orphan Records
    orphan_claims = conn.execute("""
        SELECT count(*) FROM claims c
        WHERE (c.company_id IS NOT NULL AND c.company_id NOT IN (SELECT id FROM companies))
           OR (c.facility_id IS NOT NULL AND c.facility_id NOT IN (SELECT id FROM facilities))
           OR (c.contact_id IS NOT NULL AND c.contact_id NOT IN (SELECT id FROM contacts))
           OR (c.facility_commodity_id IS NOT NULL AND c.facility_commodity_id NOT IN (SELECT id FROM facility_commodities))
    """).fetchone()[0]
    if orphan_claims > 0:
        findings.append({"severity": "CRITICAL", "type": "ORPHAN_CLAIMS", "count": orphan_claims})

    orphan_claim_ev = conn.execute("""
        SELECT count(*) FROM claim_evidence ce
        WHERE (ce.claim_id NOT IN (SELECT id FROM claims))
           OR (ce.evidence_source_id NOT IN (SELECT id FROM evidence_sources))
    """).fetchone()[0]
    if orphan_claim_ev > 0:
        findings.append({"severity": "CRITICAL", "type": "ORPHAN_CLAIM_EVIDENCE", "count": orphan_claim_ev})

    # 8. Opportunity Engine Recomputation
    ctx = load_opportunity_universe_context(conn=conn)
    tier_counts = {k: len(v) for k, v in ctx["tier_company_ids"].items()}
    total_operating = sum(tier_counts.values())

    # Deep review breakdown
    new_tier_a = [cid for cid in ctx["tier_company_ids"]["TIER_A_PRIORITY"] if cid in new_company_ids]
    new_tier_c = [cid for cid in ctx["tier_company_ids"]["TIER_C_SECONDARY"] if cid in new_company_ids]
    new_restricted = [cid for cid in ctx["tier_company_ids"]["RESTRICTED"] if cid in new_company_ids]

    # Audit Status
    has_critical_or_error = any(f["severity"] in ("CRITICAL", "ERROR") for f in findings)
    audit_status = "FAIL" if has_critical_or_error else "PASS"

    audit_report = {
        "audit_status": audit_status,
        "newly_added_universe": {
            "companies_added": len(new_companies),
            "facilities_added": len(new_facs),
            "contacts_added": len(new_contacts),
            "claims_added": len(new_claims),
        },
        "total_operating_universe": total_operating,
        "tier_distribution": tier_counts,
        "deep_review_targets": {
            "new_tier_a_count": len(new_tier_a),
            "new_tier_c_count": len(new_tier_c),
            "new_restricted_count": len(new_restricted),
            "new_tier_a_ids": new_tier_a,
            "new_tier_c_ids": new_tier_c,
            "new_restricted_ids": new_restricted,
        },
        "findings_count": len(findings),
        "findings": findings,
    }

    conn.close()
    return audit_report

if __name__ == "__main__":
    report = run_independent_audit()
    print("Independent Audit Report:")
    print(json.dumps(report, indent=2))
