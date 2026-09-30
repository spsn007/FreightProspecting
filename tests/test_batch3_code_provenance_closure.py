"""
FreightProspecting V1 — Batch 3 Final Code + Provenance Closure Regression Suite
Mandatory 23-point test suite covering:
1. grouped assembler mixed-stage case
2. grouped assembler company DNC case
3. grouped assembler mixed DIRECT_ONLY siblings
4. grouped assembler carrier-positive sibling case
5. exact engine == grouped card tier (all 565 companies)
6. exact engine ID sets == directory filter ID sets (all 5 tiers)
7. five opportunity buckets mutually exclusive
8. five opportunity buckets exhaustive over all operating companies
9. tier filtering before pagination
10. tier + search
11. last-page pagination
12. metadata == engine
13. provenance 404 is not success
14. provenance DNS failure is not success
15. blocked source is not success
16. google.com never COMPANY_WEBSITE
17. closure JSON historical claim 2747 exact
18. closure JSON historical claim 2752 exact
19. closure JSON evidence ID/URL mapping exact
20. Rex QA directness narrative matches SQLite
21. Tier A identities generated from SQLite
22. lifecycle unchanged
23. operational tables zero
"""

import json
import sqlite3
from pathlib import Path
import pytest

from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.opportunity import (
    BROKER_OPPORTUNITY_RULE_VERSION,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    RESTRICTED,
    evaluate_broker_opportunity,
    evaluate_company_opportunity_from_context,
    load_opportunity_universe_context,
    get_opportunity_tier_company_ids,
)
from src.backend.db.queries import (
    get_company_grouped_prospects,
    get_universe_metadata,
)

ACTIVE_DB = Path("data/backups/prospects_backup_pre_tier_a_phase_a_freeze_20260929.db")
PRE_BATCH3_BASELINE = Path("data/backups/prospects_backup_pre_batch3_wave_A_20260928_212245.db")
CLOSURE_CORRECTION_FILE = Path("reports/batch_3_final_closure_correction.json")
PROVENANCE_VERIFICATION_FILE = Path("reports/batch_3_final_provenance_verification.json")
BATCH3_RESULT_FILE = Path("reports/broker_research_batch3_result.json")


# 1. Grouped assembler mixed-stage case (exercises actual grouped directory path)
def test_1_grouped_assembler_mixed_stage_case():
    disk_conn = create_connection(ACTIVE_DB)
    mem_conn = sqlite3.connect(":memory:")
    disk_conn.backup(mem_conn)
    disk_conn.close()
    mem_conn.row_factory = sqlite3.Row

    # Modify facilities for Company 219 (Steel Dynamics) in isolated memory to create an explicit mixed-stage scenario:
    # Facility 266 (Butler) -> stage DISCOVERY
    # Facility 267 (Columbia City) -> stage QUALIFIED
    mem_conn.execute("UPDATE prospect_lifecycle SET stage = 'DISCOVERY' WHERE facility_id = 266")
    mem_conn.execute("UPDATE prospect_lifecycle SET stage = 'QUALIFIED' WHERE facility_id = 267")
    mem_conn.commit()

    # 1. Call authoritative opportunity evaluator
    engine_res = evaluate_broker_opportunity(219, conn=mem_conn)

    # 2. Call actual grouped-company/card assembly path used by Master Directory
    grouped_cards = get_company_grouped_prospects(conn=mem_conn, search="Steel Dynamics")

    assert len(grouped_cards) == 1
    card = grouped_cards[0]

    # Assert exact parity between authoritative engine and grouped card display
    assert card["opportunity_tier"] == engine_res["opportunity_tier"]
    assert card["opportunity_tier"] == TIER_B_WORTH_CALLING
    mem_conn.close()


# 2. Grouped assembler company DNC case (exercises actual grouped directory path)
def test_2_grouped_assembler_company_dnc_case():
    disk_conn = create_connection(ACTIVE_DB)
    mem_conn = sqlite3.connect(":memory:")
    disk_conn.backup(mem_conn)
    disk_conn.close()
    mem_conn.row_factory = sqlite3.Row

    # Apply company-level DNC suppression to Company 23 (Imperial Metal Services, normally Tier A Priority)
    mem_conn.execute("""
        INSERT INTO suppressions (scope_type, company_id, suppression_status, reason_notes)
        VALUES ('COMPANY', 23, 'DO_NOT_CONTACT', 'In-memory test company DNC')
    """)
    mem_conn.commit()

    # 1. Call authoritative engine path
    engine_res = evaluate_broker_opportunity(23, conn=mem_conn)

    # 2. Call actual grouped-company/card assembly path used by Master Directory
    grouped_cards = get_company_grouped_prospects(conn=mem_conn, search="Imperial Metal Services")

    assert len(grouped_cards) == 1
    card = grouped_cards[0]

    # Assert both engine and grouped card evaluate to RESTRICTED
    assert engine_res["opportunity_tier"] == RESTRICTED
    assert card["opportunity_tier"] == RESTRICTED
    assert "RESTRICTED_DO_NOT_CONTACT" in engine_res["reason_codes"]

    # Also verify directory tier filter for RESTRICTED contains Company 23
    restricted_dir = get_company_grouped_prospects(conn=mem_conn, tier=RESTRICTED)
    restricted_cids = {c["company_id"] for c in restricted_dir}
    assert 23 in restricted_cids
    mem_conn.close()


# 3. Grouped assembler mixed DIRECT_ONLY siblings (Steel Dynamics Company 219)
def test_3_grouped_assembler_mixed_direct_only_siblings():
    conn = create_connection(ACTIVE_DB)
    res_engine = evaluate_broker_opportunity(219, conn=conn)
    groups = get_company_grouped_prospects(db_path=ACTIVE_DB, search="Steel Dynamics")
    assert len(groups) == 1
    sd_group = groups[0]

    assert res_engine["opportunity_tier"] == TIER_B_WORTH_CALLING
    assert sd_group["opportunity_tier"] == TIER_B_WORTH_CALLING
    assert sd_group["qualifying_facility_id"] == 267  # Columbia City facility
    conn.close()


# 4. Grouped assembler carrier-positive sibling case (Imperial Metal Services Company 23)
def test_4_grouped_assembler_carrier_positive_sibling_case():
    conn = create_connection(ACTIVE_DB)
    res_engine = evaluate_broker_opportunity(23, conn=conn)
    groups = get_company_grouped_prospects(db_path=ACTIVE_DB, search="Imperial Metal Services")
    assert len(groups) == 1
    ims_group = groups[0]

    assert res_engine["opportunity_tier"] == TIER_A_PRIORITY
    assert ims_group["opportunity_tier"] == TIER_A_PRIORITY
    conn.close()


# 5. Exact engine == grouped card tier across all 565 companies
def test_5_exact_engine_equals_grouped_card_tier():
    conn = create_connection(ACTIVE_DB)
    context = load_opportunity_universe_context(conn)
    all_groups = get_company_grouped_prospects(db_path=ACTIVE_DB)
    assert len(all_groups) == 565

    mismatches = []
    for g in all_groups:
        cid = g["company_id"]
        opp = evaluate_broker_opportunity(cid, conn=conn, universe_context=context)
        if g["opportunity_tier"] != opp["opportunity_tier"]:
            mismatches.append((cid, g["operating_brand"], g["opportunity_tier"], opp["opportunity_tier"]))

    assert len(mismatches) == 0, f"Mismatches found: {mismatches}"
    conn.close()


# 6. Exact engine ID sets == directory filter ID sets
def test_6_exact_engine_id_sets_equal_directory_filter_id_sets():
    conn = create_connection(ACTIVE_DB)
    tier_map = get_opportunity_tier_company_ids(conn=conn)
    tiers = [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]
    for t in tiers:
        engine_ids = set(tier_map[t])
        dir_groups = get_company_grouped_prospects(tier=t, db_path=ACTIVE_DB)
        dir_ids = {g["company_id"] for g in dir_groups}
        assert engine_ids == dir_ids, f"Discrepancy in tier {t}: engine={len(engine_ids)}, dir={len(dir_ids)}"
    conn.close()


# 7. Five opportunity buckets mutually exclusive
def test_7_five_opportunity_buckets_mutually_exclusive():
    conn = create_connection(ACTIVE_DB)
    tier_map = get_opportunity_tier_company_ids(conn=conn)
    tiers = [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]

    for i in range(len(tiers)):
        for j in range(i + 1, len(tiers)):
            t1, t2 = tiers[i], tiers[j]
            overlap = set(tier_map[t1]) & set(tier_map[t2])
            assert len(overlap) == 0, f"Overlap between {t1} and {t2}: {overlap}"
    conn.close()


# 8. Five opportunity buckets exhaustive over all operating companies
def test_8_five_opportunity_buckets_exhaustive_over_operating_companies():
    conn = create_connection(ACTIVE_DB)
    tier_map = get_opportunity_tier_company_ids(conn=conn)
    tiers = [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]
    all_tier_ids = set()
    for t in tiers:
        all_tier_ids |= set(tier_map[t])

    operating_companies = conn.execute("SELECT COUNT(DISTINCT company_id) FROM facilities").fetchone()[0]
    assert len(all_tier_ids) == operating_companies == 565
    conn.close()


# 9. Tier filtering before pagination
def test_9_tier_filtering_before_pagination():
    res = get_company_grouped_prospects(
        tier=TIER_B_WORTH_CALLING, page=1, page_size=10, db_path=ACTIVE_DB
    )
    items = res["items"]
    assert len(items) == 10
    assert res["total_count"] == 102
    assert all(p["opportunity_tier"] == TIER_B_WORTH_CALLING for p in items)


# 10. Tier + search combination
def test_10_tier_plus_search():
    res = get_company_grouped_prospects(
        tier=TIER_A_PRIORITY, search="Imperial", db_path=ACTIVE_DB
    )
    assert len(res) == 1
    assert res[0]["company_id"] == 23
    assert res[0]["opportunity_tier"] == TIER_A_PRIORITY


# 11. Last-page pagination
def test_11_last_page_pagination():
    res = get_company_grouped_prospects(
        tier=TIER_A_PRIORITY, page=2, page_size=10, db_path=ACTIVE_DB
    )
    items = res["items"]
    assert len(items) == 3
    assert res["total_count"] == 13
    assert res["page"] == 2
    assert res["total_pages"] == 2


# 12. Metadata == engine
def test_12_metadata_equals_engine():
    conn = create_connection(ACTIVE_DB)
    meta = get_universe_metadata(conn)
    counts = meta["opportunity_counts"]

    assert counts[TIER_A_PRIORITY] == 13
    assert counts[TIER_B_WORTH_CALLING] == 102
    assert counts[TIER_C_SECONDARY] == 5
    assert counts[TIER_D_RESEARCH_NEEDED] == 445
    assert counts[RESTRICTED] == 0
    assert counts["ALL"] == 565
    conn.close()


# 13. Provenance 404 is not success
def test_13_provenance_404_is_not_success():
    assert PROVENANCE_VERIFICATION_FILE.exists()
    with open(PROVENANCE_VERIFICATION_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    assert len(records) == 34
    allowed_results = {
        "SUCCESS_FETCHED", "HTTP_404", "HTTP_403", "HTTP_OTHER_ERROR",
        "DNS_FAILURE", "TLS_FAILURE", "TIMEOUT", "AUTOMATION_BLOCKED",
        "OFFICIAL_SOURCE_INACCESSIBLE", "INSUFFICIENT_PUBLIC_EVIDENCE"
    }

    for r in records:
        assert r["result"] in allowed_results
        assert "attempted_url" in r and r["attempted_url"]
        assert "requested_at_utc" in r and r["requested_at_utc"]
        if r.get("http_status") == 404:
            assert r["result"] == "HTTP_404"
            assert r["result"] != "SUCCESS_FETCHED"


# 14. Provenance DNS failure is not success
def test_14_provenance_dns_failure_is_not_success():
    with open(PROVENANCE_VERIFICATION_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    dns_failures = [r for r in records if r["dns_status"] == "FAILED"]
    assert len(dns_failures) >= 2  # CID 107 and 447
    for r in dns_failures:
        assert r["result"] == "DNS_FAILURE"
        assert r["result"] != "SUCCESS_FETCHED"


# 15. Blocked source is not success
def test_15_blocked_source_is_not_success():
    with open(PROVENANCE_VERIFICATION_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    blocked = [r for r in records if r["access_status"] == "BLOCKED" or r["http_status"] == 403]
    assert len(blocked) >= 18
    for r in blocked:
        assert r["result"] in ["HTTP_403", "AUTOMATION_BLOCKED"]
        assert r["result"] != "SUCCESS_FETCHED"


# 16. google.com never COMPANY_WEBSITE
def test_16_google_com_never_company_website():
    conn = create_connection(ACTIVE_DB)
    bad_sources = conn.execute("""
        SELECT COUNT(*) FROM evidence_sources 
        WHERE source_url LIKE '%google.com%' AND source_type = 'COMPANY_WEBSITE'
    """).fetchone()[0]
    assert bad_sources == 0

    bad_companies = conn.execute("""
        SELECT COUNT(*) FROM companies WHERE website_url LIKE '%google.com%'
    """).fetchone()[0]
    assert bad_companies == 0
    conn.close()


# 17. Closure JSON historical claim 2747 exact
def test_17_closure_json_historical_claim_2747_exact():
    with open(CLOSURE_CORRECTION_FILE, "r", encoding="utf-8") as f:
        closure_data = json.load(f)

    details = closure_data["evidence_scope_details"]
    c2747 = next((d for d in details if d["superseded_claim_id"] == 2747), None)
    assert c2747 is not None
    assert c2747["old_value"] == "IN_HOUSE_OWNED"

    conn = create_connection(ACTIVE_DB)
    db_c2747 = conn.execute("SELECT claimed_value FROM claims WHERE id = 2747").fetchone()
    assert db_c2747[0] == "IN_HOUSE_OWNED"
    conn.close()


# 18. Closure JSON historical claim 2752 exact
def test_18_closure_json_historical_claim_2752_exact():
    with open(CLOSURE_CORRECTION_FILE, "r", encoding="utf-8") as f:
        closure_data = json.load(f)

    details = closure_data["evidence_scope_details"]
    c2752 = next((d for d in details if d["superseded_claim_id"] == 2752), None)
    assert c2752 is not None
    assert c2752["old_value"] == "IN_HOUSE_OWNED"

    conn = create_connection(ACTIVE_DB)
    db_c2752 = conn.execute("SELECT claimed_value FROM claims WHERE id = 2752").fetchone()
    assert db_c2752[0] == "IN_HOUSE_OWNED"
    conn.close()


# 19. Closure JSON evidence ID/URL mapping exact
def test_19_closure_json_evidence_id_url_mapping_exact():
    with open(CLOSURE_CORRECTION_FILE, "r", encoding="utf-8") as f:
        closure_data = json.load(f)

    expected = {
        749: "https://tolko.com/company/logistics/",
        752: "https://www.precision-strip.com/shipping-receiving",
        753: "https://www.onealsteel.com/terms-and-conditions/",
        755: "https://peerlesssteel.com"
    }

    conn = create_connection(ACTIVE_DB)
    for src_id, exp_url in expected.items():
        row = conn.execute("SELECT source_url FROM evidence_sources WHERE id = ?", (src_id,)).fetchone()
        assert row is not None
        assert row[0] == exp_url

    for item in closure_data["evidence_scope_details"]:
        sid = item["evidence_source_id"]
        assert item["source_url"] == expected[sid]
    conn.close()


# 20. Rex QA directness narrative matches SQLite
def test_20_rex_qa_directness_narrative_matches_sqlite():
    conn = create_connection(ACTIVE_DB)
    ct = conn.execute("""
        SELECT person_name, phone_directness, phone_number, role_category 
        FROM contacts WHERE id = 666
    """).fetchone()

    assert ct["person_name"] == "Chris Brown"
    assert ct["phone_directness"] == "DIRECT_PERSON"
    assert ct["role_category"] == "OPERATIONS"

    with open(CLOSURE_CORRECTION_FILE, "r", encoding="utf-8") as f:
        closure_data = json.load(f)
    c666 = next(c for c in closure_data["contact_truth_details"] if c["contact_id"] == 666)
    assert c666["phone_directness"] == "DIRECT_PERSON"
    conn.close()


# 21. Tier A identities generated from SQLite
def test_21_tier_a_identities_generated_from_sqlite():
    assert BATCH3_RESULT_FILE.exists()
    with open(BATCH3_RESULT_FILE, "r", encoding="utf-8") as f:
        res_data = json.load(f)

    conn = create_connection(ACTIVE_DB)
    for item in res_data["tier_a_list"]:
        cid = item["company_id"]
        c_row = conn.execute("SELECT operating_brand FROM companies WHERE id = ?", (cid,)).fetchone()
        assert c_row is not None
        assert item["operating_brand"] == c_row["operating_brand"]

    # Explicit brand verification
    c16 = conn.execute("SELECT operating_brand FROM companies WHERE id = 16").fetchone()[0]
    assert c16 == "Miami Valley Steel Service, Inc."
    c19 = conn.execute("SELECT operating_brand FROM companies WHERE id = 19").fetchone()[0]
    assert c19 == "Coil Steel Processing (CSP)"
    conn.close()


# 22. Lifecycle unchanged
def test_22_lifecycle_unchanged():
    conn = create_connection(ACTIVE_DB)
    bak_conn = create_connection(PRE_BATCH3_BASELINE)
    conn.row_factory = sqlite3.Row
    bak_conn.row_factory = sqlite3.Row

    prod_lc = {r["facility_id"]: dict(r) for r in conn.execute("SELECT * FROM prospect_lifecycle").fetchall()}
    bak_lc = {r["facility_id"]: dict(r) for r in bak_conn.execute("SELECT * FROM prospect_lifecycle").fetchall()}

    assert len(prod_lc) == len(bak_lc) == 653
    diffs = [
        fid for fid, bl in bak_lc.items()
        if any(bl[k] != prod_lc[fid][k] for k in bl)
    ]
    assert len(diffs) == 0, f"Lifecycle stage drift detected: {diffs}"

    # Also verify that all 100 researched companies in the machine result artifact match SQLite exactly (0 mismatches)
    with open(BATCH3_RESULT_FILE, "r", encoding="utf-8") as f:
        res_data = json.load(f)
    for c in res_data["researched_companies"]:
        fid = c["facility_id"]
        row = conn.execute("SELECT stage FROM prospect_lifecycle WHERE facility_id = ?", (fid,)).fetchone()
        assert row is not None
        assert c["lifecycle_stage"] == row[0], f"CID {c['company_id']} FID {fid} stage mismatch: {c['lifecycle_stage']} != {row[0]}"

    conn.close()
    bak_conn.close()


# 23. Operational tables zero
def test_23_operational_tables_zero():
    conn = create_connection(ACTIVE_DB)
    tables = [
        "outreach_logs",
        "load_opportunities",
        "freight_demand_signals",
        "capacity_postings",
        "load_capacity_matches"
    ]
    for tbl in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        assert count == 0, f"Table {tbl} has {count} rows; expected 0."
    conn.close()
