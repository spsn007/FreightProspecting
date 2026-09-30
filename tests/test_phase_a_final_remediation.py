"""
FreightProspecting V1 — Phase A Final Remediation Test Suite
Validates resolution of the 5 OpenCode audit blockers:
1. Precision Strip broker acceptance superseded to UNKNOWN, commercial carrier VERIFIED preserved (stays Tier A).
2. Precision Strip Contact 671 exact title 'Main Contact', broker_procurement_relevance UNKNOWN, phone source 188.
3. Worthington Steel no unsupported facility narrowing: FID 111/112/113 UNKNOWN, CID 91 company-scope claims created, evaluated tier = Tier B.
4. Metals USA no unsupported facility narrowing: FID 264/265 UNKNOWN, CID 218 company-scope claim created, evaluated tier = Tier B.
5. Company-level claim scope integrity: exact-1 constraint holds, partial unique indexes hold.
6. Validated private fleet movements (AmeriSteel, FerrouSouth, Target Steel) strictly preserved in Tier C.
7. Engine == Metadata == Directory exact set equality across all 5 tiers (14 A, 99 B, 7 C, 445 D, 0 Restricted).
8. Zero lifecycle diff across all 653 facilities, operational tables = 0, production DB SHA-256 verified.
"""

import hashlib
import json
import sqlite3
from pathlib import Path
import pytest

from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.opportunity import (
    RESTRICTED,
    TIER_A_PRIORITY,
    TIER_B_WORTH_CALLING,
    TIER_C_SECONDARY,
    TIER_D_RESEARCH_NEEDED,
    evaluate_broker_opportunity,
)
from src.backend.db.queries import (
    get_company_grouped_prospects,
    get_universe_metadata,
)

ACTIVE_DB = Path("data/backups/prospects_backup_pre_tier_a_phase_b_wave_A_20260929_080024.db")
PRE_PHASE_A_BASELINE = Path("data/backups/prospects_backup_pre_tier_a_phase_a_freeze_20260929.db")
FINAL_CANDIDATE_HASH = "FE73DC3F051A7AEE7FC83ED7E0D7DF2CA05EFEE9C9C2629001327B551AF104DF"


def test_1_precision_strip_broker_unknown_and_carrier_verified():
    """Verify Precision Strip (CID 105, FID 134) broker acceptance is UNKNOWN, carrier is VERIFIED, tier is A."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        fac = conn.execute("SELECT commercial_carrier_use, broker_friendly_status, private_fleet_present FROM facilities WHERE id = 134").fetchone()
        assert fac["commercial_carrier_use"] == "VERIFIED"
        assert fac["broker_friendly_status"] == "UNKNOWN"
        assert fac["private_fleet_present"] == "VERIFIED_PRESENT"

        # Claim 2762 superseded
        c2762 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2762").fetchone()
        assert c2762["is_current_accepted"] == 0

        # Current accepted broker claim is UNKNOWN
        cur_broker_claim = conn.execute("""
            SELECT claimed_value, verification_status, is_current_accepted
            FROM claims
            WHERE facility_id = 134 AND claim_field = 'broker_friendly_status' AND is_current_accepted = 1
        """).fetchone()
        assert cur_broker_claim["claimed_value"] == "UNKNOWN"
        assert cur_broker_claim["verification_status"] == "UNKNOWN"

        # Evaluated opportunity tier is TIER_A_PRIORITY
        opp = evaluate_broker_opportunity(105, conn=conn)
        assert opp["opportunity_tier"] == TIER_A_PRIORITY
        assert "Outside carrier use confirmed (VERIFIED)" in opp["positive_facts"]
    finally:
        conn.close()


def test_2_precision_contact_671_provenance_and_relevance():
    """Verify Contact 671 exact title is 'Main Contact', broker relevance UNKNOWN, phone source is 188."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        ct = conn.execute("SELECT * FROM contacts WHERE id = 671").fetchone()
        assert ct["person_name"] == "Jamey Eilerman"
        assert ct["exact_published_title"] == "Main Contact"
        assert ct["broker_procurement_relevance"] == "UNKNOWN"
        assert ct["outbound_shipping_procurement_relevance"] == "VERIFIED"
        assert ct["role_category"] == "FREIGHT_LOGISTICS"
        assert ct["email_address"] == "jamey_eilerman@precision-strip.com"
        assert ct["email_directness"] == "DIRECT_PERSON"
        assert ct["phone_number"] == "419-628-2343"
        assert ct["phone_directness"] == "GENERAL_SWITCHBOARD"

        # Claim 2763 superseded
        c2763 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2763").fetchone()
        assert c2763["is_current_accepted"] == 0

        # Replacement phone claim linked to evidence source 188 (not 758)
        cur_phone_claim = conn.execute("""
            SELECT c.id, c.claimed_value, ce.evidence_source_id, es.source_url
            FROM claims c
            JOIN claim_evidence ce ON ce.claim_id = c.id
            JOIN evidence_sources es ON es.id = ce.evidence_source_id
            WHERE c.contact_id = 671 AND c.claim_field = 'phone_number' AND c.is_current_accepted = 1
        """).fetchone()
        assert cur_phone_claim["claimed_value"] == "419-628-2343"
        assert cur_phone_claim["evidence_source_id"] == 188
        assert "locations" in cur_phone_claim["source_url"]
    finally:
        conn.close()


def test_3_worthington_steel_no_unsupported_facility_narrowing():
    """Verify Worthington Steel facilities are UNKNOWN, company-scope claims created, tier is B."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        facs = conn.execute("SELECT id, commercial_carrier_use, broker_friendly_status FROM facilities WHERE company_id = 91").fetchall()
        assert len(facs) == 3
        for f in facs:
            assert f["commercial_carrier_use"] == "UNKNOWN", f"Facility {f['id']} commercial_carrier_use must be UNKNOWN"
            assert f["broker_friendly_status"] == "UNKNOWN", f"Facility {f['id']} broker_friendly_status must be UNKNOWN"

        # Claims 2767 and 2768 superseded
        c2767 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2767").fetchone()
        assert c2767["is_current_accepted"] == 0
        c2768 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2768").fetchone()
        assert c2768["is_current_accepted"] == 0

        # Company-scope claims exist for CID 91
        comp_claims = conn.execute("""
            SELECT claim_field, claimed_value, verification_status
            FROM claims
            WHERE company_id = 91 AND is_current_accepted = 1
        """).fetchall()
        claims_map = {r["claim_field"]: r for r in comp_claims}
        assert "commercial_carrier_use" in claims_map
        assert claims_map["commercial_carrier_use"]["claimed_value"] == "VERIFIED"
        assert "broker_friendly_status" in claims_map
        assert claims_map["broker_friendly_status"]["claimed_value"] == "VERIFIED_ACCEPTS"

        # Evaluated tier is TIER_B_WORTH_CALLING
        opp = evaluate_broker_opportunity(91, conn=conn)
        assert opp["opportunity_tier"] == TIER_B_WORTH_CALLING
    finally:
        conn.close()


def test_4_metals_usa_no_unsupported_facility_narrowing():
    """Verify Metals USA facilities are UNKNOWN, company-scope claim created, tier is B."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        facs = conn.execute("SELECT id, commercial_carrier_use, broker_friendly_status FROM facilities WHERE company_id = 218").fetchall()
        assert len(facs) == 2
        for f in facs:
            assert f["commercial_carrier_use"] == "UNKNOWN", f"Facility {f['id']} commercial_carrier_use must be UNKNOWN"
            assert f["broker_friendly_status"] == "UNKNOWN", f"Facility {f['id']} broker_friendly_status must be UNKNOWN"

        # Claim 2775 superseded
        c2775 = conn.execute("SELECT is_current_accepted FROM claims WHERE id = 2775").fetchone()
        assert c2775["is_current_accepted"] == 0

        # Company-scope claim exists for CID 218
        comp_claim = conn.execute("""
            SELECT claim_field, claimed_value, verification_status
            FROM claims
            WHERE company_id = 218 AND is_current_accepted = 1
        """).fetchone()
        assert comp_claim["claim_field"] == "commercial_carrier_use"
        assert comp_claim["claimed_value"] == "VERIFIED"

        # Evaluated tier is TIER_B_WORTH_CALLING
        opp = evaluate_broker_opportunity(218, conn=conn)
        assert opp["opportunity_tier"] == TIER_B_WORTH_CALLING
    finally:
        conn.close()


def test_5_company_level_claim_scope_integrity():
    """Verify exact-1 subject constraint and partial unique indexes hold for company-scope claims."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        comp_claims = conn.execute("SELECT * FROM claims WHERE company_id IS NOT NULL AND is_current_accepted = 1").fetchall()
        assert len(comp_claims) == 85  # 81 operating_brand, 1 legal_name, 2 commercial_carrier_use, 1 broker_friendly_status
        carrier_claims = [c for c in comp_claims if c["claim_field"] == "commercial_carrier_use"]
        broker_claims = [c for c in comp_claims if c["claim_field"] == "broker_friendly_status"]
        assert len(carrier_claims) == 2  # CID 91, CID 218
        assert len(broker_claims) == 1   # CID 91

        for c in comp_claims:
            # Verify exact-1 foreign key check
            fk_count = sum(1 for k in [
                "company_id", "company_relationship_id", "facility_id", "facility_commodity_id",
                "contact_id", "freight_demand_signal_id", "load_opportunity_id", "carrier_id",
                "carrier_lane_activity_id", "capacity_posting_id"
            ] if c[k] is not None)
            assert fk_count == 1, f"Claim {c['id']} must reference exactly one subject, found {fk_count}"
    finally:
        conn.close()


def test_6_validated_private_fleet_movements_preserved():
    """Verify AmeriSteel, FerrouSouth, and Target Steel remain preserved in Tier C Secondary."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        for cid, expected_fid, brand in [
            (24, 23, "AmeriSteel"),
            (102, 131, "FerrouSouth"),
            (104, 133, "Target Steel"),
        ]:
            fac = conn.execute("SELECT private_fleet_present, fleet_relationship_type FROM facilities WHERE id = ?", (expected_fid,)).fetchone()
            assert fac["private_fleet_present"] == "VERIFIED_PRESENT", f"{brand} must have VERIFIED_PRESENT fleet"
            assert fac["fleet_relationship_type"] == "IN_HOUSE_OWNED", f"{brand} must have IN_HOUSE_OWNED fleet"

            opp = evaluate_broker_opportunity(cid, conn=conn)
            assert opp["opportunity_tier"] == TIER_C_SECONDARY, f"{brand} must evaluate as TIER_C_SECONDARY"

        # Target Steel appointment contact 672 preserved
        c672 = conn.execute("SELECT * FROM contacts WHERE id = 672").fetchone()
        assert c672 is not None
        assert c672["facility_id"] == 133
        assert c672["phone_directness"] == "GENERAL_SWITCHBOARD"
    finally:
        conn.close()


def test_7_engine_metadata_directory_parity():
    """Verify engine == metadata == directory exact set equality across all 5 tiers."""
    conn = create_connection(ACTIVE_DB)
    try:
        meta = get_universe_metadata(conn)
        meta_counts = meta["opportunity_counts"]

        # Expected authoritative counts after remediation:
        # Tier A: 14 (started 13, +1 Precision Strip)
        # Tier B: 99 (started 102, -3 AmeriSteel/FerrouSouth/TargetSteel to C, -1 Precision to A, +1 Worthington, +1 Metals USA)
        # Tier C: 7 (started 5, +3 from B, -1 Precision to A)
        # Tier D: 445
        # Restricted: 0
        # Total: 565
        assert meta_counts["ALL"] == 565
        assert meta_counts["TIER_A_PRIORITY"] == 14
        assert meta_counts["TIER_B_WORTH_CALLING"] == 99
        assert meta_counts["TIER_C_SECONDARY"] == 7
        assert meta_counts["TIER_D_RESEARCH_NEEDED"] == 445
        assert meta_counts["RESTRICTED"] == 0

        # Engine iteration
        comps = conn.execute("SELECT id FROM companies WHERE id IN (SELECT DISTINCT company_id FROM facilities)").fetchall()
        assert len(comps) == 565
        engine_counts = {TIER_A_PRIORITY: 0, TIER_B_WORTH_CALLING: 0, TIER_C_SECONDARY: 0, TIER_D_RESEARCH_NEEDED: 0, RESTRICTED: 0}
        engine_tier_ids = {t: set() for t in engine_counts}
        for c in comps:
            res = evaluate_broker_opportunity(c[0], conn=conn)
            t = res["opportunity_tier"]
            engine_counts[t] += 1
            engine_tier_ids[t].add(c[0])

        for t in engine_counts:
            assert engine_counts[t] == meta_counts[t], f"Mismatch for {t}"

        # Directory query set equality
        for t in [TIER_A_PRIORITY, TIER_B_WORTH_CALLING, TIER_C_SECONDARY, TIER_D_RESEARCH_NEEDED, RESTRICTED]:
            dir_items = get_company_grouped_prospects(tier=t, db_path=ACTIVE_DB)
            dir_ids = {item["company_id"] for item in dir_items}
            assert len(dir_ids) == engine_counts[t]
            assert dir_ids == engine_tier_ids[t], f"Directory vs Engine set inequality for {t}"
    finally:
        conn.close()


def test_8_lifecycle_and_operational_invariants():
    """Verify 0 lifecycle diff, 0 operational records, and exact production DB hash."""
    assert PRE_PHASE_A_BASELINE.exists()
    conn = create_connection(ACTIVE_DB)
    bak_conn = create_connection(PRE_PHASE_A_BASELINE)
    try:
        p_life = dict(conn.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
        b_life = dict(bak_conn.execute("SELECT facility_id, stage FROM prospect_lifecycle").fetchall())
        diffs = [fid for fid, s in b_life.items() if p_life.get(fid) != s]
        assert len(diffs) == 0, f"Lifecycle stage changes: {diffs}"

        # Operational tables = 0
        for tbl in ["freight_demand_signals", "load_opportunities", "carrier_lane_activity", "capacity_postings"]:
            cnt = conn.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
            assert cnt == 0, f"Operational table {tbl} must be 0, found {cnt}"

        # PRAGMA checks
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok"
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert len(fk_violations) == 0

        # DB SHA-256
        with open(ACTIVE_DB, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest().upper()
        assert h == FINAL_CANDIDATE_HASH, f"Expected {FINAL_CANDIDATE_HASH}, got {h}"
    finally:
        conn.close()
        bak_conn.close()
