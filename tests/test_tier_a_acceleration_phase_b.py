"""
FreightProspecting V1 — Tier A Acceleration Campaign Phase B Validation Test Suite
Validates:
1. Candidate DB SHA-256 integrity.
2. Exact distribution parity across Authoritative Engine, Universe Metadata, and Directory.
3. 5 validated Tier A promotions (Bush Concrete, Swanson Group, Peerless Steel, Pike Lumber, Bull Moose Tube).
4. 3 validated Tier C movements (Rutland Lumber, G&G Steel, Permatile Concrete).
5. 398 lifecycle transitions (DISCOVERY -> QUALIFIED) and 47 companies maintained in DISCOVERY / Tier D.
6. Zero polymorphic FKs and zero foreign key violations.
7. Zero records in all 5 canonical operational tables.
8. Exact-1 check constraint and single current accepted claim invariant on claims table.
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
    load_opportunity_universe_context,
)
from src.backend.db.queries import (
    get_company_grouped_prospects,
    get_universe_metadata,
)

ACTIVE_DB = Path("data/prospects.db")
CANDIDATE_SHA256 = "6BD5B8360FA713630477D715C5794906F44CB8814DFAB8EDF47D676C672767D9"


def test_1_database_hash_and_integrity():
    """Verify candidate database SHA-256 matches expected freeze hash and passes integrity checks."""
    assert ACTIVE_DB.exists(), "Active database does not exist"
    actual_hash = hashlib.sha256(ACTIVE_DB.read_bytes()).hexdigest().upper()
    assert actual_hash == CANDIDATE_SHA256, f"Expected {CANDIDATE_SHA256}, got {actual_hash}"

    conn = create_connection(ACTIVE_DB)
    try:
        integrity = conn.execute("PRAGMA integrity_check;").fetchone()[0]
        assert integrity == "ok", f"Integrity check failed: {integrity}"
        fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
        assert len(fk_violations) == 0, f"Foreign key violations found: {fk_violations}"
    finally:
        conn.close()


def test_2_exact_three_surface_distribution_parity():
    """Verify 100% exact parity across Authoritative Opportunity Engine, Universe Metadata, and Grouped Directory."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        # 1. Authoritative Opportunity Engine
        ctx = load_opportunity_universe_context(conn)
        engine_tiers = ctx["tier_company_ids"]
        engine_counts = {k: len(v) for k, v in engine_tiers.items()}

        assert engine_counts[TIER_A_PRIORITY] == 19
        assert engine_counts[TIER_B_WORTH_CALLING] == 489
        assert engine_counts[TIER_C_SECONDARY] == 10
        assert engine_counts[TIER_D_RESEARCH_NEEDED] == 47
        assert engine_counts[RESTRICTED] == 0
        assert sum(engine_counts.values()) == 565

        # 2. Universe Metadata
        meta = get_universe_metadata(conn)
        meta_counts = meta["opportunity_counts"]

        assert meta_counts["ALL"] == 565
        assert meta_counts[TIER_A_PRIORITY] == 19
        assert meta_counts[TIER_B_WORTH_CALLING] == 489
        assert meta_counts[TIER_C_SECONDARY] == 10
        assert meta_counts[TIER_D_RESEARCH_NEEDED] == 47
        assert meta_counts[RESTRICTED] == 0

        # 3. Grouped Directory
        for tier_key, expected_count in [
            (TIER_A_PRIORITY, 19),
            (TIER_B_WORTH_CALLING, 489),
            (TIER_C_SECONDARY, 10),
            (TIER_D_RESEARCH_NEEDED, 47),
            (RESTRICTED, 0),
        ]:
            res = get_company_grouped_prospects(page=1, page_size=600, tier=tier_key, conn=conn)
            assert res["total_count"] == expected_count, f"Directory mismatch for {tier_key}: expected {expected_count}, got {res['total_count']}"
            assert len(res["items"]) == expected_count
    finally:
        conn.close()


def test_3_validated_tier_a_promotions():
    """Verify the 5 Phase B Tier A promotions evaluate authoritatively to TIER_A_PRIORITY with verified claims."""
    promotions = [
        (128, "Bush Concrete Products", 157, "commercial_carrier_use", "VERIFIED"),
        (331, "Swanson Group", 418, "commercial_carrier_use", "VERIFIED"),
        (395, "Peerless Steel", 482, "commercial_carrier_use", "VERIFIED"),
        (187, "Pike Lumber Company", 221, "commercial_carrier_use", "VERIFIED"),
        (396, "Bull Moose Tube Co.", 483, "commercial_carrier_use", "VERIFIED"),
    ]

    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        for cid, brand, fid, claim_field, expected_val in promotions:
            eval_res = evaluate_broker_opportunity(cid, conn=conn)
            assert eval_res["opportunity_tier"] == TIER_A_PRIORITY, f"{brand} (CID {cid}) did not evaluate to TIER_A_PRIORITY: {eval_res['opportunity_tier']}"

            # Check facility column
            fac = conn.execute(f"SELECT {claim_field} FROM facilities WHERE id = ?", (fid,)).fetchone()
            assert fac[claim_field] == expected_val, f"{brand} facility {fid} {claim_field} != {expected_val}"

            # Check accepted claim exists
            claim = conn.execute("""
                SELECT claimed_value, verification_status, is_current_accepted
                FROM claims
                WHERE facility_id = ? AND claim_field = ? AND is_current_accepted = 1
            """, (fid, claim_field)).fetchone()
            assert claim is not None, f"No current accepted claim for {brand} (FID {fid}, field {claim_field})"
            assert claim["claimed_value"] == expected_val
            assert claim["verification_status"] == "VERIFIED"
    finally:
        conn.close()


def test_4_validated_tier_c_secondary_movements():
    """Verify the 3 Phase B Tier C movements evaluate to TIER_C_SECONDARY with verified private fleet claims."""
    movements = [
        (316, "Rutland Lumber Co.", 403, "private_fleet_present", "VERIFIED_PRESENT"),
        (412, "G&G Steel Inc.", 499, "private_fleet_present", "VERIFIED_PRESENT"),
        (497, "Permatile Concrete Products", 584, "private_fleet_present", "VERIFIED_PRESENT"),
    ]

    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        for cid, brand, fid, claim_field, expected_val in movements:
            eval_res = evaluate_broker_opportunity(cid, conn=conn)
            assert eval_res["opportunity_tier"] == TIER_C_SECONDARY, f"{brand} (CID {cid}) did not evaluate to TIER_C_SECONDARY: {eval_res['opportunity_tier']}"

            # Check facility column
            fac = conn.execute(f"SELECT {claim_field}, commercial_carrier_use FROM facilities WHERE id = ?", (fid,)).fetchone()
            assert fac[claim_field] == expected_val, f"{brand} facility {fid} {claim_field} != {expected_val}"
            assert fac["commercial_carrier_use"] != "VERIFIED", f"{brand} must not have outside carrier verified"

            # Check accepted claim exists
            claim = conn.execute("""
                SELECT claimed_value, verification_status, is_current_accepted
                FROM claims
                WHERE facility_id = ? AND claim_field = ? AND is_current_accepted = 1
            """, (fid, claim_field)).fetchone()
            assert claim is not None, f"No current accepted claim for {brand} (FID {fid}, field {claim_field})"
            assert claim["claimed_value"] == expected_val
            assert claim["verification_status"] == "VERIFIED"
    finally:
        conn.close()


def test_5_lifecycle_stages_and_discovery_pool():
    """Verify lifecycle counts: 522 QUALIFIED, 102 DISCOVERY, 29 SHORTLISTED = 653 facilities."""
    conn = create_connection(ACTIVE_DB)
    try:
        counts = dict(conn.execute("SELECT stage, count(*) FROM prospect_lifecycle GROUP BY stage").fetchall())
        assert counts.get("QUALIFIED") == 522
        assert counts.get("DISCOVERY") == 102
        assert counts.get("SHORTLISTED") == 29
        assert sum(counts.values()) == 653

        # Exactly 47 operating companies remain in DISCOVERY / Tier D
        ctx = load_opportunity_universe_context(conn)
        tier_d_cids = ctx["tier_company_ids"][TIER_D_RESEARCH_NEEDED]
        assert len(tier_d_cids) == 47

        # Cascade Engineering (CID 40) and Challenger Pallet (CID 540) remain in Tier D
        assert 40 in tier_d_cids
        assert 540 in tier_d_cids
    finally:
        conn.close()


def test_6_zero_operational_data_pollution():
    """Verify zero outreach records, placeholder signals, loads, postings, or matches."""
    conn = create_connection(ACTIVE_DB)
    try:
        for tbl in ["outreach_logs", "load_opportunities", "freight_demand_signals", "capacity_postings", "load_capacity_matches"]:
            cnt = conn.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
            assert cnt == 0, f"Pollution in table {tbl}: found {cnt} rows"
    finally:
        conn.close()


def test_7_claims_relational_integrity_and_single_accepted():
    """Verify exact-1 check constraint and partial unique index on current accepted claims."""
    conn = create_connection(ACTIVE_DB)
    conn.row_factory = sqlite3.Row
    try:
        # 1. Exact-1 subject constraint check on all claims
        claims = conn.execute("""
            SELECT id,
                   (CASE WHEN company_id IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN company_relationship_id IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN facility_id IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN facility_commodity_id IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN contact_id IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN freight_demand_signal_id IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN load_opportunity_id IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN carrier_id IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN carrier_lane_activity_id IS NOT NULL THEN 1 ELSE 0 END +
                    CASE WHEN capacity_posting_id IS NOT NULL THEN 1 ELSE 0 END) AS subject_count
            FROM claims
        """).fetchall()
        for c in claims:
            assert c["subject_count"] == 1, f"Claim {c['id']} violates exact-1 subject constraint (count={c['subject_count']})"

        # 2. Single current accepted claim per subject + claim_field
        dupes = conn.execute("""
            SELECT facility_id, claim_field, count(*) as c
            FROM claims
            WHERE is_current_accepted = 1 AND facility_id IS NOT NULL
            GROUP BY facility_id, claim_field
            HAVING c > 1
        """).fetchall()
        assert len(dupes) == 0, f"Duplicate current accepted facility claims found: {dupes}"

        comp_dupes = conn.execute("""
            SELECT company_id, claim_field, count(*) as c
            FROM claims
            WHERE is_current_accepted = 1 AND company_id IS NOT NULL
            GROUP BY company_id, claim_field
            HAVING c > 1
        """).fetchall()
        assert len(comp_dupes) == 0, f"Duplicate current accepted company claims found: {comp_dupes}"
    finally:
        conn.close()
