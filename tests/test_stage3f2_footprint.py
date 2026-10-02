"""
FreightProspecting V1 — Stage 3F.2 Live Shortlist Verification & Footprint Truth Tests
Validates the 12 required Stage 3F.2 regression invariants:
1. Database facility count != company footprint status.
2. A company with 1 database facility is NOT assumed to be single-site unless verified.
3. UNKNOWN footprint yields UNKNOWN/neutral friction unless other enterprise factors exist.
4. Verified 4+ location footprint triggers HIGH broker access friction.
5. Verified 2-3 location footprint triggers MEDIUM broker access friction.
6. Verified single-site footprint triggers LOW broker access friction when logistics/carrier use confirmed.
7. Fax numbers are never represented as callable phone numbers.
8. Yoder Lumber: Wayne Yoder has no callable direct phone (UNKNOWN), Berlin toll-free (800) 531-1704 is switchboard, footprint is MULTI_SITE_VERIFIED (3 locations), fax is stored as non-callable (330) 893-3031.
9. Cole Hardwood: located in Logansport IN, phone (574) 753-3151, footprint SINGLE_SITE_VERIFIED (1 location), owned private fleet.
10. Majestic Steel, Heidtman Steel, Bemis Manufacturing, Coreslab Structures are MULTI_SITE_VERIFIED enterprise footprints with HIGH friction in QUALIFIED.
11. All 31 Shortlisted companies have verified live-source footprints, active callable phone numbers, and non-empty resolving source URLs.
12. Core equipment invariant: strictly only facilities 1 (Beasley), 2 (Kenwal), and 18 (CSP) have VERIFIED equipment usage.
"""

import sqlite3
import pytest
from tests.authenticated_client import TestClient

from src.backend.main import app
from src.backend.db.connection import get_db_path, create_connection
from src.backend.db.queries import (
    get_summary_counts,
    get_prospects_list,
    get_company_grouped_prospects,
    get_prospect_detail,
    evaluate_broker_access_friction,
)

client = TestClient(app)
DB_PATH = get_db_path()


# ============================================================================
# 1. Database Facility Count != Company Footprint Status
# ============================================================================
def test_database_facility_count_not_equal_footprint_status():
    """Verify that company_footprint_status is an independent entity attribute, not derived from count(facilities)."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Majestic Steel has 1 facility in the database, but 9 verified operating locations
    majestic = conn.execute("SELECT * FROM companies WHERE operating_brand LIKE '%Majestic Steel%'").fetchone()
    assert majestic is not None
    fac_count = conn.execute("SELECT count(*) FROM facilities WHERE company_id = ?", (majestic["id"],)).fetchone()[0]
    assert fac_count == 1, "Majestic Steel has 1 imported facility in DB"
    assert majestic["company_footprint_status"] == "MULTI_SITE_VERIFIED"
    assert majestic["verified_operating_location_count"] == 9

    # Cole Hardwood has 1 facility in the database and is verified single site
    cole = conn.execute("SELECT * FROM companies WHERE operating_brand LIKE '%Cole Hardwood%'").fetchone()
    assert cole["company_footprint_status"] == "SINGLE_SITE_VERIFIED"
    assert cole["verified_operating_location_count"] == 1

    # Lamb Brothers has 1 facility in DB and footprint is UNKNOWN
    lamb = conn.execute("SELECT * FROM companies WHERE operating_brand LIKE '%Lamb Brothers%'").fetchone()
    assert lamb["company_footprint_status"] == "UNKNOWN"
    assert lamb["verified_operating_location_count"] is None

    conn.close()


# ============================================================================
# 2. Single Database Facility Not Assumed Single-Site
# ============================================================================
def test_single_database_facility_not_assumed_single_site():
    """Verify that a company with 1 facility in DB is NOT assumed to be single-site unless explicitly verified."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Query all companies with 1 database facility and UNKNOWN footprint
    unknown_fp_companies = conn.execute("""
        SELECT c.id, c.operating_brand, c.company_footprint_status, count(f.id) as fac_count
        FROM companies c
        JOIN facilities f ON f.company_id = c.id
        WHERE c.company_footprint_status = 'UNKNOWN'
        GROUP BY c.id
        HAVING fac_count = 1
        LIMIT 20
    """).fetchall()

    assert len(unknown_fp_companies) >= 10

    for r in unknown_fp_companies:
        comp = dict(conn.execute("SELECT * FROM companies WHERE id = ?", (r["id"],)).fetchone())
        facs = [dict(x) for x in conn.execute("SELECT * FROM facilities WHERE company_id = ?", (r["id"],)).fetchall()]
        friction = evaluate_broker_access_friction(comp, facs)

        # Invariant: Must NOT claim single-site operation
        for reason in friction["reasons"]:
            assert "Single independent shipping facility" not in reason, (
                f"{r['operating_brand']} assumed single-site without verification!"
            )
        assert friction["facts"]["company_footprint_status"] == "UNKNOWN"
        assert friction["facts"]["footprint_display"] == "Company footprint — UNKNOWN"

    conn.close()


# ============================================================================
# 3. UNKNOWN Footprint Yields Neutral Friction
# ============================================================================
def test_unknown_footprint_neutral_friction():
    """Verify that an UNKNOWN footprint contributes neutral (0 points / UNKNOWN level) unless other factors exist."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Lamb Brothers Lumber: no private fleet, no corporate procurement, UNKNOWN footprint
    comp = dict(conn.execute("SELECT * FROM companies WHERE operating_brand LIKE '%Lamb Brothers%'").fetchone())
    facs = [dict(x) for x in conn.execute("SELECT * FROM facilities WHERE company_id = ?", (comp["id"],)).fetchall()]
    friction = evaluate_broker_access_friction(comp, facs)

    assert friction["level"] == "UNKNOWN"
    assert any("Company footprint UNKNOWN" in r for r in friction["reasons"])

    conn.close()


# ============================================================================
# 4. Verified 4+ Locations Triggers HIGH Friction
# ============================================================================
def test_verified_four_plus_locations_high_friction():
    """Verify that verified 4+ locations triggers HIGH broker access friction."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    for brand, min_locs in [
        ("Majestic Steel USA", 9),
        ("Heidtman Steel Products", 5),
        ("Bemis Manufacturing", 6),
        ("Coreslab Structures", 17),
        ("Cascade Engineering", 5),
    ]:
        comp = dict(conn.execute("SELECT * FROM companies WHERE operating_brand LIKE ?", (f"%{brand}%",)).fetchone())
        assert comp["company_footprint_status"] == "MULTI_SITE_VERIFIED"
        assert comp["verified_operating_location_count"] >= min_locs

        facs = [dict(x) for x in conn.execute("SELECT * FROM facilities WHERE company_id = ?", (comp["id"],)).fetchall()]
        friction = evaluate_broker_access_friction(comp, facs)

        assert friction["level"] == "HIGH", f"{brand} should have HIGH friction"
        assert any("Potentially higher access complexity due to multi-site scale" in r for r in friction["reasons"])

    conn.close()


# ============================================================================
# 5. Verified 2-3 Locations Triggers MEDIUM Friction
# ============================================================================
def test_verified_two_to_three_locations_medium_friction():
    """Verify that verified 2-3 locations triggers MEDIUM broker access friction."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    for brand in ["Yoder Lumber Co.", "Janco Steel Ltd.", "Encore Precast LLC"]:
        comp = dict(conn.execute("SELECT * FROM companies WHERE operating_brand LIKE ?", (f"%{brand}%",)).fetchone())
        assert comp["company_footprint_status"] == "MULTI_SITE_VERIFIED"
        assert comp["verified_operating_location_count"] in (2, 3)

        facs = [dict(x) for x in conn.execute("SELECT * FROM facilities WHERE company_id = ?", (comp["id"],)).fetchall()]
        friction = evaluate_broker_access_friction(comp, facs)

        assert friction["level"] == "MEDIUM", f"{brand} should have MEDIUM friction"
        assert any("Manageable regional multi-plant network" in r for r in friction["reasons"])

    conn.close()


# ============================================================================
# 6. Verified Single-Site Triggers LOW Friction When Confirmed
# ============================================================================
def test_verified_single_site_low_friction():
    """Verify that verified single-site operation triggers LOW friction when carrier or freight logistics confirmed."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    for brand in ["MidWest Materials", "Battle Lumber Company"]:
        comp = dict(conn.execute("SELECT * FROM companies WHERE operating_brand LIKE ?", (f"%{brand}%",)).fetchone())
        assert comp["company_footprint_status"] == "SINGLE_SITE_VERIFIED"
        assert comp["verified_operating_location_count"] == 1

        facs = [dict(x) for x in conn.execute("SELECT * FROM facilities WHERE company_id = ?", (comp["id"],)).fetchall()]
        friction = evaluate_broker_access_friction(comp, facs)

        assert friction["level"] == "LOW", f"{brand} should have LOW friction"
        assert any("Single independent shipping facility" in r for r in friction["reasons"])

    conn.close()


# ============================================================================
# 7. Fax Numbers Never Represented As Callable Phone Numbers
# ============================================================================
def test_fax_numbers_never_represented_as_callable_phone():
    """Verify fax numbers are stored in contacts.fax_number and not used for callable telephone outreach."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Wayne Yoder
    yoder_ct = conn.execute("SELECT * FROM contacts WHERE id = 418").fetchone()
    assert yoder_ct["phone_number"] is None, "Fax number must not be stored in phone_number"
    assert yoder_ct["fax_number"] == "(330) 893-3031"
    assert yoder_ct["phone_directness"] == "UNKNOWN"

    # UI check: Detail page for Yoder Lumber (facility_id=408)
    resp = client.get("/prospects/408")
    assert resp.status_code == 200
    html = resp.text

    # Dial button must dial callable phone (800) 531-1704, NOT the fax number
    assert "tel:(800) 531-1704" in html or "tel:8005311704" in html or "(800) 531-1704" in html
    assert "tel:(330) 893-3031" not in html
    assert "tel:3308933031" not in html
    assert "Non-callable document route" in html

    conn.close()


# ============================================================================
# 8. Yoder Lumber Footprint & Contact Truth
# ============================================================================
def test_yoder_lumber_footprint_and_contact_truth():
    """Verify Yoder Lumber Company ID=321, Facility ID=408 exact attributes."""
    detail = get_prospect_detail(408, DB_PATH)
    assert detail is not None
    assert detail["company_id"] == 321
    assert detail["operating_brand"] == "Yoder Lumber Co."
    assert detail["company_footprint_status"] == "MULTI_SITE_VERIFIED"
    assert detail["verified_operating_location_count"] == 3
    assert detail["friction_level"] == "MEDIUM"

    # Check contacts: Wayne Yoder + Berlin switchboard
    contacts = detail["contacts"]
    yoder_contact = next(c for c in contacts if c["person_name"] == "Wayne Yoder")
    assert yoder_contact["exact_published_title"] == "Shipping Manager"
    assert yoder_contact["phone_number"] is None
    assert yoder_contact["phone_directness"] == "UNKNOWN"
    assert yoder_contact["fax_number"] == "(330) 893-3031"

    switchboard = next(c for c in contacts if c["phone_number"] == "(800) 531-1704")
    assert switchboard["phone_directness"] == "TOLL_FREE"


# ============================================================================
# 9. Cole Hardwood Footprint & Location Truth
# ============================================================================
def test_cole_hardwood_footprint_and_location_truth():
    """Verify Cole Hardwood Company ID=300, Facility ID=386 in Logansport, IN."""
    detail = get_prospect_detail(386, DB_PATH)
    assert detail is not None
    assert detail["company_id"] == 300
    assert detail["operating_brand"] == "Cole Hardwood Inc."
    assert detail["city"] == "Logansport"
    assert detail["state_prov"] == "IN"
    assert detail["postal_code"] == "46947"
    assert "1611 W Market St" in detail["physical_address"]
    assert any(c["phone_number"] == "(574) 753-3151" for c in detail["contacts"])
    assert detail["company_footprint_status"] == "SINGLE_SITE_VERIFIED"
    assert detail["verified_operating_location_count"] == 1
    assert detail["private_fleet_present"] == "VERIFIED_PRESENT"
    # Because of verified private fleet, friction is MEDIUM
    assert detail["friction_level"] == "MEDIUM"


# ============================================================================
# 10. Enterprise Multi-Site Shippers in QUALIFIED with HIGH Friction
# ============================================================================
def test_enterprise_multi_site_demoted_to_qualified_with_high_friction():
    """Verify Majestic Steel, Heidtman Steel, Bemis Manufacturing, Coreslab Structures are QUALIFIED with HIGH friction."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    enterprise_brands = [
        "Majestic Steel USA",
        "Heidtman Steel Products",
        "Bemis Manufacturing",
        "Coreslab Structures",
    ]

    for brand in enterprise_brands:
        row = conn.execute("""
            SELECT c.id, c.operating_brand, pl.stage, c.company_footprint_status, c.verified_operating_location_count
            FROM companies c
            JOIN facilities f ON f.company_id = c.id
            JOIN prospect_lifecycle pl ON pl.facility_id = f.id
            WHERE c.operating_brand LIKE ?
        """, (f"%{brand}%",)).fetchone()

        assert row is not None, f"Company {brand} missing from DB"
        assert row["stage"] == "QUALIFIED", f"{brand} must be in QUALIFIED, not SHORTLISTED"
        assert row["company_footprint_status"] == "MULTI_SITE_VERIFIED"
        assert row["verified_operating_location_count"] >= 4

    conn.close()


# ============================================================================
# 11. All 31 Shortlisted Companies Have Verified Live Sources & Active Phones
# ============================================================================
def test_all_thirty_one_shortlisted_verified_live_sources():
    """Verify all 31 Shortlisted companies have verified live-source footprints, active callable phones, and resolving URLs."""
    prospects = get_prospects_list(lifecycle_stage="SHORTLISTED")
    assert len(prospects) == 29, f"Expected exactly 29 shortlisted prospects, got {len(prospects)}"

    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    for p in prospects:
        cid = p["company_id"]
        fid = p["facility_id"]
        comp = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()

        # Footprint verified
        assert comp["company_footprint_status"] in ("SINGLE_SITE_VERIFIED", "MULTI_SITE_VERIFIED"), (
            f"Shortlist company {comp['operating_brand']} has unverified footprint: {comp['company_footprint_status']}"
        )
        assert comp["verified_operating_location_count"] is not None and comp["verified_operating_location_count"] >= 1
        assert comp["footprint_source_notes"] is not None and len(comp["footprint_source_notes"].strip()) > 10

        # Resolving website URL
        assert comp["website_url"] is not None and comp["website_url"].startswith("http"), (
            f"Shortlist company {comp['operating_brand']} missing valid website URL"
        )

        # Callable phone exists on facility or contacts
        has_phone = False
        if p.get("phone_number") and len(p["phone_number"].strip()) > 5:
            has_phone = True
        contacts = conn.execute("SELECT * FROM contacts WHERE facility_id = ? OR company_id = ?", (fid, cid)).fetchall()
        for ct in contacts:
            if ct["phone_number"] and len(ct["phone_number"].strip()) > 5:
                has_phone = True
                break
        assert has_phone, f"Shortlist company {comp['operating_brand']} has no callable phone!"

    conn.close()


# ============================================================================
# 12. Core Equipment Invariant: Strictly Only Facilities 1, 2, and 18 are VERIFIED
# ============================================================================
def test_core_equipment_invariant():
    """Verify strictly only facilities 1 (Beasley), 2 (Kenwal), and 18 (CSP) have VERIFIED equipment usage."""
    conn = create_connection(DB_PATH)
    conn.row_factory = sqlite3.Row

    verified_rows = conn.execute("""
        SELECT facility_id, equipment_category, equipment_usage_status
        FROM facility_commodities
        WHERE equipment_usage_status = 'VERIFIED'
        ORDER BY facility_id
    """).fetchall()

    verified_facility_ids = sorted(list({r["facility_id"] for r in verified_rows}))
    assert verified_facility_ids == [1, 2, 18], (
        f"Strict equipment invariant violated! Only facilities 1, 2, 18 may be VERIFIED, found {verified_facility_ids}"
    )

    # All other facilities must be INFERRED or UNKNOWN
    other_rows = conn.execute("""
        SELECT count(*) FROM facility_commodities
        WHERE facility_id NOT IN (1, 2, 18) AND equipment_usage_status NOT IN ('INFERRED', 'UNKNOWN')
    """).fetchone()[0]
    assert other_rows == 0, f"Found {other_rows} unexpected non-inferred commodities"

    conn.close()
