"""
FreightProspecting V1 — Batch 3 Independent Artifact & Lifecycle Validation Script
Does NOT reuse artifact generator assumptions.
Validates:
1. Frozen Batch 3 roster vs JSON vs CSV vs Audit Ledger
2. Lifecycle stages against live SQLite prospect_lifecycle table for all 100 facilities
3. Opportunity tiers against live SQLite/opportunity engine for all 100 companies
4. Company IDs and focus facility IDs alignment
5. Database SHA-256 integrity
"""

import json
import csv
import sqlite3
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend.db.opportunity import evaluate_broker_opportunity

DB_PATH = Path("data/prospects.db")
ROSTER_PATH = Path("reports/batch_3_frozen_selection.json")
RESULT_JSON_PATH = Path("reports/broker_research_batch3_result.json")
RESULT_CSV_PATH = Path("reports/broker_research_batch3_result.csv")
AUDIT_LEDGER_PATH = Path("reports/broker_research_batch3_audit_ledger.json")

EXPECTED_HASH = "95D7FE5C53676AD286CF460F0B9A76D676A4678683D04193634804F4D42FB321"

def compute_sha256(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest().upper()

def run_validation():
    print("=" * 60)
    print("INDEPENDENT BATCH 3 ARTIFACT & LIFECYCLE VALIDATION")
    print("=" * 60)

    # 1. DB Hash check
    current_hash = compute_sha256(DB_PATH)
    assert current_hash == EXPECTED_HASH, f"Database hash mismatch! {current_hash} != {EXPECTED_HASH}"
    print(f"[OK] Database SHA-256 matches: {current_hash}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 2. PRAGMAs
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    fk_violations = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    assert integrity == "ok", f"Integrity check failed: {integrity}"
    assert fk_violations == 0, f"FK violations: {fk_violations}"
    print("[OK] PRAGMA integrity_check: ok | foreign_key_check: 0")

    # 3. Load artifacts
    with open(ROSTER_PATH, "r", encoding="utf-8") as f:
        roster = json.load(f)
    assert len(roster) == 100, f"Expected 100 companies in roster, got {len(roster)}"

    with open(RESULT_JSON_PATH, "r", encoding="utf-8") as f:
        res_json = json.load(f)
    res_companies = res_json.get("researched_companies", [])
    assert len(res_companies) == 100, f"Expected 100 companies in JSON, got {len(res_companies)}"

    with open(RESULT_CSV_PATH, "r", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))
    assert len(csv_rows) == 100, f"Expected 100 rows in CSV, got {len(csv_rows)}"

    with open(AUDIT_LEDGER_PATH, "r", encoding="utf-8") as f:
        ledger = json.load(f)
    ledger_entries = ledger.get("entries", [])
    assert len(ledger_entries) == 100, f"Expected 100 entries in audit ledger, got {len(ledger_entries)}"

    print("[OK] All 4 artifact files loaded with exactly 100 entries.")

    # Build index maps
    roster_map = {item["company_id"]: item for item in roster}
    json_map = {item["company_id"]: item for item in res_companies}
    csv_map = {int(item["company_id"]): item for item in csv_rows}
    ledger_map = {item["company_id"]: item for item in ledger_entries}

    cid_mismatches = 0
    fid_mismatches = 0
    lifecycle_json_mismatches = 0
    lifecycle_csv_mismatches = 0
    lifecycle_ledger_mismatches = 0
    tier_json_mismatches = 0
    tier_csv_mismatches = 0

    for item in roster:
        cid = item["company_id"]
        exp_fid = item["research_focus_facility_id"]

        # Check existence
        if cid not in json_map or cid not in csv_map or cid not in ledger_map:
            cid_mismatches += 1
            continue

        j_item = json_map[cid]
        c_item = csv_map[cid]
        l_item = ledger_map[cid]

        # Facility ID check
        if j_item.get("facility_id") != exp_fid or int(c_item.get("facility_id", 0)) != exp_fid or l_item.get("facility_id") != exp_fid:
            fid_mismatches += 1

        # Query live SQLite prospect_lifecycle
        pl_row = conn.execute("SELECT stage FROM prospect_lifecycle WHERE facility_id = ?", (exp_fid,)).fetchone()
        db_stage = pl_row["stage"] if pl_row else None

        if j_item.get("lifecycle_stage") != db_stage:
            lifecycle_json_mismatches += 1
            print(f"[FAIL] JSON lifecycle CID {cid} (FID {exp_fid}): JSON='{j_item.get('lifecycle_stage')}' != DB='{db_stage}'")

        if c_item.get("lifecycle_stage") != db_stage:
            lifecycle_csv_mismatches += 1
            print(f"[FAIL] CSV lifecycle CID {cid} (FID {exp_fid}): CSV='{c_item.get('lifecycle_stage')}' != DB='{db_stage}'")

        if l_item.get("lifecycle_stage") != db_stage:
            lifecycle_ledger_mismatches += 1
            print(f"[FAIL] Ledger lifecycle CID {cid} (FID {exp_fid}): Ledger='{l_item.get('lifecycle_stage')}' != DB='{db_stage}'")

        # Opportunity tier check
        eng_opp = evaluate_broker_opportunity(cid, conn=conn)
        db_tier = eng_opp["opportunity_tier"]

        if j_item.get("final_tier") != db_tier:
            tier_json_mismatches += 1
        if c_item.get("final_tier") != db_tier:
            tier_csv_mismatches += 1

    conn.close()

    print("\n--- VALIDATION RESULTS ---")
    print(f"Company ID mismatches:            {cid_mismatches} (required: 0)")
    print(f"Facility ID mismatches:           {fid_mismatches} (required: 0)")
    print(f"Lifecycle mismatches (JSON):      {lifecycle_json_mismatches} (required: 0)")
    print(f"Lifecycle mismatches (CSV):       {lifecycle_csv_mismatches} (required: 0)")
    print(f"Lifecycle mismatches (Ledger):    {lifecycle_ledger_mismatches} (required: 0)")
    print(f"Opportunity Tier mismatches JSON: {tier_json_mismatches} (required: 0)")
    print(f"Opportunity Tier mismatches CSV:  {tier_csv_mismatches} (required: 0)")

    success = (
        cid_mismatches == 0 and
        fid_mismatches == 0 and
        lifecycle_json_mismatches == 0 and
        lifecycle_csv_mismatches == 0 and
        lifecycle_ledger_mismatches == 0 and
        tier_json_mismatches == 0 and
        tier_csv_mismatches == 0
    )

    if success:
        print("\n[PASS] ALL INDEPENDENT VALIDATION CHECKS PASSED WITH 0 MISMATCHES!")
        return 0
    else:
        print("\n[FAIL] VALIDATION FAILED!")
        return 1

if __name__ == "__main__":
    sys.exit(run_validation())
