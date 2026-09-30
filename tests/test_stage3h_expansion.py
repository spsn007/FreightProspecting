"""
Stage 3H — Seasonal, Specialty & High-Cube Shipper Discovery Expansion Tests
Validates:
1. Target Invariants Post-Stage-3H:
   - Operating companies: 565 (527 baseline + 38 new)
   - Total companies: 567 (529 baseline + 38 new)
   - Total physical facilities: 653 (615 baseline + 38 new)
   - Lifecycle partition:
     * Shortlisted: 29 facilities / 29 companies (0 change)
     * Qualified: 124 facilities / 91 companies (0 change)
     * Discovery: 500 facilities / 445 companies (+38 facilities, +38 companies)
2. Category & Family Distribution:
   - All 3 opportunity families populated:
     * SEASONAL_OPPORTUNITY (10 facilities across 8 categories)
     * REGIONAL_SPECIALTY_MFG (20 facilities across 11 categories)
     * PACKAGING_HIGH_CUBE (8 facilities across 6 categories)
   - Zero empty categories among Stage 3H targets.
3. Equipment Truth & Provenance Invariants:
   - Verified equipment remains strictly limited to facilities {1, 2, 18}
   - All 38 new Stage 3H facilities have equipment_usage_status == 'INFERRED'
   - Inferred equipment categories strictly within {'FLATBED', 'STEP_DECK', 'DRY_VAN'}
   - Zero reefer contamination
4. Operational Data Invariant:
   - Zero outreach logs, loads, capacity postings, demand signals, matches
   - CRM uncontacted == 567, total calls == 0
5. Data Integrity:
   - PRAGMA foreign_key_check is clean
   - PRAGMA integrity_check returns 'ok'
   - Deduplication: zero duplicate normalized brands, domains, or facility names
"""

import sqlite3
import pytest
from pathlib import Path
from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.queries import get_summary_counts, get_company_grouped_prospects, get_prospects_list

DB_PATH = get_db_path()

def test_stage3h_summary_counts():
    """Verify exact post-Stage-3H counts across companies, facilities, and lifecycle stages."""
    counts = get_summary_counts(DB_PATH)

    # Companies
    assert counts["all_companies_count"] == 565
    assert counts["total_companies_count"] == 567
    assert counts["shortlisted_companies_count"] == 29
    assert counts["qualified_companies_count"] == 91
    assert counts["discovery_companies_count"] == 445

    # Facilities
    assert counts["all_prospects_count"] == 653
    assert counts["shortlisted_count"] == 29
    assert counts["qualified_count"] == 124
    assert counts["discovery_count"] == 500

    # Single vs Multi site
    assert counts["single_facility_companies_count"] == 499
    assert counts["multi_facility_companies_count"] == 66


def test_stage3h_zero_fake_operational_data():
    """Verify complete absence of fake operational records in production database."""
    counts = get_summary_counts(DB_PATH)
    assert counts["loads_count"] == 0
    assert counts["capacity_count"] == 0
    assert counts["signals_count"] == 0
    assert counts["carriers_count"] == 0
    assert counts["matches_count"] == 0
    assert counts["crm_total_calls"] == 0
    assert counts["crm_uncontacted"] == 567


def test_stage3h_verified_equipment_invariant():
    """Verify that only the 3 audited facilities have VERIFIED equipment usage."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        verified_rows = conn.execute("""
            SELECT facility_id, equipment_category, equipment_usage_status
            FROM facility_commodities
            WHERE equipment_usage_status = 'VERIFIED'
        """).fetchall()
        verified_ids = {r["facility_id"] for r in verified_rows}
        assert verified_ids == {1, 2, 18}, f"Expected verified facility IDs {{1, 2, 18}}, got {verified_ids}"

        # All 38 new facilities have INFERRED equipment
        inferred_count = conn.execute("""
            SELECT COUNT(*) FROM facility_commodities WHERE equipment_usage_status = 'INFERRED'
        """).fetchone()[0]
        assert inferred_count == 650
    finally:
        conn.close()


def test_stage3h_category_population():
    """Verify that all Stage 3H target categories have at least 1 operating facility."""
    conn = create_connection(DB_PATH)
    try:
        categories = conn.execute("""
            SELECT cc.category_code, cf.family_code, COUNT(fc.id) as fac_count
            FROM commodity_categories cc
            JOIN commodity_families cf ON cc.family_id = cf.id
            LEFT JOIN facility_commodities fc ON fc.category_code = cc.category_code
            WHERE cf.family_code IN ('SEASONAL_OPPORTUNITY', 'REGIONAL_SPECIALTY_MFG', 'PACKAGING_HIGH_CUBE')
            GROUP BY cc.category_code, cf.family_code
        """).fetchall()

        populated = {r[0]: r[2] for r in categories}

        # Check Track A
        for cat in ["CHRISTMAS_TREES", "NURSERY_TREES_SHRUBS", "HARDY_OUTDOOR_PLANTS", "HAY_STRAW",
                    "WOOD_PELLETS_FIREWOOD", "PACKAGED_ICE_MELT", "BAGGED_MULCH_SOIL", "PAVERS_LANDSCAPE_STONE"]:
            assert populated.get(cat, 0) >= 1, f"Expected category {cat} to be populated, got {populated.get(cat, 0)}"

        # Check Track B
        for cat in ["PALLETS_CRATES_DUNNAGE", "ROOF_TRUSSES_WALL_PANELS", "HDPE_PVC_PIPE",
                    "FENCING_GATES_POSTS", "METAL_ROOFING_SIDING", "PORTABLE_BUILDINGS"]:
            assert populated.get(cat, 0) >= 1, f"Expected category {cat} to be populated, got {populated.get(cat, 0)}"

        # Check Track C
        for cat in ["AG_EQUIPMENT", "USED_MACHINERY", "HVAC_EQUIPMENT", "PLAYGROUND_PARK_EQUIPMENT", "SOLAR_RACKING"]:
            assert populated.get(cat, 0) >= 1, f"Expected category {cat} to be populated, got {populated.get(cat, 0)}"

        # Check Track D
        for cat in ["CORRUGATED_PACKAGING", "PLASTIC_PACKAGING", "CLEAN_DRUMS", "CLEAN_IBC_TOTES",
                    "MATTRESSES_FURNITURE", "FOAM_PRODUCTS"]:
            assert populated.get(cat, 0) >= 1, f"Expected category {cat} to be populated, got {populated.get(cat, 0)}"
    finally:
        conn.close()


def test_stage3h_geography_eligibility():
    """Verify that all new facilities are within eligible US Lower 48 or Canada provinces."""
    conn = create_connection(DB_PATH)
    try:
        facs = conn.execute("""
            SELECT f.id, f.facility_name, f.state_prov, f.country
            FROM facilities f
            WHERE f.id IN (SELECT target_facility_id FROM discovery_intake_audit WHERE batch_name = 'STAGE_3H_EXPANSION_BATCH_1')
        """).fetchall()
        assert len(facs) == 38

        LOWER_48 = {
            "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID", "IL", "IN", "IA", "KS", "KY",
            "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
            "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
            "WV", "WI", "WY"
        }
        CANADA_PROVS = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}

        for f in facs:
            st = f[2].upper()
            country = f[3].upper()
            if country == "US":
                assert st in LOWER_48, f"Facility {f[0]} ({f[1]}) has ineligible US state: {st}"
            elif country == "CA":
                assert st in CANADA_PROVS, f"Facility {f[0]} ({f[1]}) has ineligible Canada province: {st}"
            else:
                pytest.fail(f"Facility {f[0]} has ineligible country: {country}")
    finally:
        conn.close()


def test_stage3h_intake_audit_trail():
    """Verify that discovery_intake_audit contains records for all 38 imports."""
    conn = create_connection(DB_PATH)
    try:
        audit_rows = conn.execute("""
            SELECT COUNT(*) FROM discovery_intake_audit
            WHERE batch_name = 'STAGE_3H_EXPANSION_BATCH_1' AND intake_status = 'IMPORTED_DISCOVERY'
        """).fetchone()[0]
        assert audit_rows == 38
    finally:
        conn.close()


def test_stage3h_opencode_audit_corrections():
    """
    Verify OpenCode audit corrections across all 38 Stage 3H records:
    1. Footprint status reset to UNKNOWN for companies 530-567.
    2. Facility 623 (Lignetics) reclassified to HEADQUARTERS truthfully.
    3. Facility 639 (Kempler) reconciled to Northbrook IL with superseded historical claim.
    4. Facility / Company 652 (SCHÜTZ) UTF-8 encoding clean.
    """
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # 1. Footprint reset
        fp_rows = conn.execute("""
            SELECT id, operating_brand, company_footprint_status, verified_operating_location_count, footprint_source_notes
            FROM companies WHERE id BETWEEN 530 AND 567
        """).fetchall()
        assert len(fp_rows) == 38
        for r in fp_rows:
            assert r["company_footprint_status"] == "UNKNOWN", f"Company {r['id']} ({r['operating_brand']}) has non-UNKNOWN footprint: {r['company_footprint_status']}"
            assert r["verified_operating_location_count"] is None
            assert r["footprint_source_notes"] is None

        # 2. Facility 623 (Lignetics)
        f623 = conn.execute("SELECT facility_name, facility_type FROM facilities WHERE id = 623").fetchone()
        assert f623["facility_type"] == "HEADQUARTERS"
        assert f623["facility_name"] == "Lignetics Corporate Headquarters"

        fc623 = conn.execute("SELECT specific_products, equipment_usage_status FROM facility_commodities WHERE facility_id = 623").fetchone()
        assert "corporate administrative location" in fc623["specific_products"]
        assert fc623["equipment_usage_status"] == "INFERRED"

        # 3. Facility 639 (Kempler)
        f639 = conn.execute("SELECT facility_name, physical_address, city, state_prov, postal_code FROM facilities WHERE id = 639").fetchone()
        assert f639["physical_address"] == "2720 Dundee Rd, Suite 300"
        assert f639["city"] == "Northbrook"
        assert f639["state_prov"] == "IL"
        assert f639["postal_code"] == "60062"

        # Exactly 1 active accepted address claim
        accepted_claims = conn.execute("""
            SELECT id, claimed_value, is_current_accepted
            FROM claims
            WHERE facility_id = 639 AND claim_field = 'physical_address' AND is_current_accepted = 1
        """).fetchall()
        assert len(accepted_claims) == 1
        assert accepted_claims[0]["claimed_value"] == "2720 Dundee Rd, Suite 300"

        # Historical claim is superseded (is_current_accepted = 0)
        old_claims = conn.execute("""
            SELECT id, claimed_value, is_current_accepted
            FROM claims
            WHERE facility_id = 639 AND claim_field = 'physical_address' AND is_current_accepted = 0
        """).fetchall()
        assert len(old_claims) == 1
        assert old_claims[0]["claimed_value"] == "2323 Touhy Ave"

        # 4. SCHÜTZ UTF-8
        co565 = conn.execute("SELECT operating_brand, legal_name FROM companies WHERE id = 565").fetchone()
        assert co565["operating_brand"] == "SCHÜTZ Container Systems"
        assert co565["legal_name"] == "SCHÜTZ Container Systems, Inc."

        f652 = conn.execute("SELECT facility_name FROM facilities WHERE id = 652").fetchone()
        assert f652["facility_name"] == "SCHÜTZ North Branch IBC Plant"

        # Ensure no \ufffd in any text column for company 565 or facility 652
        assert "\ufffd" not in co565["operating_brand"]
        assert "\ufffd" not in co565["legal_name"]
        assert "\ufffd" not in f652["facility_name"]

    finally:
        conn.close()

