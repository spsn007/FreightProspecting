"""
Generates the Phase 0 finding matrix from the audit files and current codebase.
"""
import json

with open("D:/FreightProspecting-Audit/professional_audit_findings.json", "r", encoding="utf-8") as f:
    audit_data = json.load(f)

# Remediation A status mapping
statuses = {
    "AUD-001": ("FIXED IN A", "Test DB session isolation in tests/conftest.py + SQLite authorizer write guard in connection.py. Production DB hash byte-identical across pytest."),
    "AUD-002": ("FIXED IN A", "Server-side evaluate_outreach_suppression across all 5 scopes; SuppressionBlockedError raises HTTP 403 with 0 DB writes."),
    "AUD-003": ("FIXED IN A", "evaluate_qualification_readiness strictly checks accepted claims backed by documented evidence_sources for address, equipment, contact."),
    "AUD-004": ("FIXED IN A", "evaluate_broker_access_friction no longer marks switchboards Low; switchboards evaluate to Medium. Only single-site with verified carrier/logistics desk is Low."),
    "AUD-005": ("FIXED IN A", "UNKNOWN footprint remains neutral (0 points) and never defaults to single-site or Low friction. Friction counts: 12 High, 89 Medium, 6 Low, 420 Unknown."),
    "AUD-006": ("FIXED IN A", "All 8 canonical call dispositions supported in SQLite schema CHECK constraint, Pydantic validator, and UI modal."),
    "AUD-007": ("FIXED IN A", "Sibling facility contamination fixed: facility-level outreach queries outreach_logs WHERE facility_id = ?."),
    "AUD-008": ("FIXED IN A", "Facility 18 shipping desk updated to (419) 269-9706, shipping@coilsteelprocessing.com, DEPARTMENT_LINE, FREIGHT_LOGISTICS."),
    "AUD-009": ("FIXED IN A", "Purged BAGGED_MULCH_SOIL from facilities 5 & 460; StructureCraft facility 613 reclassified to ROOF_TRUSSES_WALL_PANELS (Mass Timber) primary."),
    "AUD-010": ("FIXED IN A", "evidence_sources CHECK constraint updated for INDUSTRY_DIRECTORY and TRADE_ASSOCIATION; is_primary_source set to 0 for directories."),
    "AUD-011": ("UNRESOLVED", "Deferred to Remediation B. Loading /prospects executes ~5,500 SQL queries."),
    "AUD-012": ("UNRESOLVED", "CRM accepts malformed timestamps in contacted_at / follow_up_at."),
    "AUD-013": ("UNRESOLVED", "Mutating endpoints (/api/outreach, /api/viewed) lack origin / CSRF check."),
    "AUD-014": ("UNRESOLVED", "Load schema permits impossible rates and arbitrary margin calculations."),
    "AUD-015": ("UNRESOLVED", "Source observation dates hide missing publication context."),
    "AUD-016": ("PARTIALLY FIXED", "Readiness evaluator checks evidence now, but Discovery copy still says 'review pending' despite 5/5 check pass; need distinct UI copy reflecting actual readiness vs triage state."),
    "AUD-017": ("UNRESOLVED", "375px mobile view overflows horizontally."),
    "AUD-018": ("UNRESOLVED", "Hardcoded text colors fail contrast in dark mode."),
    "AUD-019": ("UNRESOLVED", "Call modal lacks dialog role, focus trap, and ARIA relationships."),
    "AUD-020": ("UNRESOLVED", "GET /prospects/{id} mutates is_viewed state silently."),
    "AUD-021": ("UNRESOLVED", "Missing database creates empty 4KB file and crashes 500."),
    "AUD-022": ("UNRESOLVED", "URL schemes not validated before rendering as links."),
    "AUD-023": ("UNRESOLVED", "Timestamp storage violates canonical UTC ISO-8601 format."),
    "AUD-024": ("UNRESOLVED", "CSP evidence URL reachability and link status."),
    "AUD-025": ("UNRESOLVED", "Outreach history append-only enforcement at database level."),
    "AUD-026": ("UNRESOLVED", "Legal entity name displays literal 'None' instead of clean fallback.")
}

print(f"{'ID':<9} | {'Sev':<8} | {'Status after A':<16} | {'Title'}")
print("-" * 100)
for item in audit_data["findings"]:
    fid = item["id"]
    sev = item["severity"]
    title = item["title"]
    status, evidence = statuses.get(fid, ("UNKNOWN", ""))
    print(f"{fid:<9} | {sev:<8} | {status:<16} | {title}")
