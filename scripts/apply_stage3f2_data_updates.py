"""
Stage 3F.2 Data Updates:
1. Reconcile Yoder Lumber (phone, fax, footprint, contacts)
2. Reconcile Cole Hardwood (address, facility name, phone, footprint)
3. Update footprints for all 31 Shortlisted companies
4. Update footprints for demoted companies (Majestic, Heidtman, Bemis, SyBridge, Rex, Coreslab, Cascade)
5. Demote 7 companies from Shortlist to Qualified
6. Promote 6 companies from Qualified to Shortlist
7. Add live resolving source for Custom Cut Timber Products
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path("data/prospects.db")

def apply_updates():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    print("--- 1. Reconciling Yoder Lumber (CID 321, FID 408) ---")
    # Wayne Yoder (Contact 418): direct phone is UNKNOWN, 330-893-3031 is FAX
    c.execute("""
        UPDATE contacts 
        SET phone_number = NULL,
            phone_directness = 'UNKNOWN',
            fax_number = '(330) 893-3031'
        WHERE id = 418
    """)
    
    # Check if facility switchboard / toll-free contact exists for FID 408
    c.execute("SELECT id FROM contacts WHERE facility_id = 408 AND id != 418")
    extra_cts = c.fetchall()
    if not extra_cts:
        c.execute("""
            INSERT INTO contacts (
                company_id, facility_id, contact_identity, person_name,
                exact_published_title, department, phone_number, fax_number,
                phone_directness, email_address, email_directness,
                role_category, outbound_shipping_procurement_relevance,
                broker_procurement_relevance, is_primary_contact
            ) VALUES (
                NULL, 408, 'GENERAL_FACILITY', NULL,
                'Berlin Facility Main & Toll-Free Desk', 'Shipping & Sales',
                '(800) 531-1704', '(330) 893-3031',
                'TOLL_FREE', 'info@yoderlumber.com', 'GENERAL',
                'FREIGHT_LOGISTICS', 'VERIFIED', 'UNKNOWN', 0
            )
        """)
        print("Inserted Berlin facility toll-free contact.")
    
    # Update Yoder Lumber company footprint
    c.execute("""
        UPDATE companies
        SET company_footprint_status = 'MULTI_SITE_VERIFIED',
            verified_operating_location_count = 3,
            footprint_source_notes = 'Official site verifies 3 operating locations in Ohio: Berlin Sawmill (Millersburg, OH), Millersburg/Buckhorn processing facility, and Rolling Ridge Woods.'
        WHERE id = 321
    """)
    
    # Update Yoder Lumber claim 1708 (phone_directness was incorrectly DIRECT_PERSON)
    c.execute("""
        UPDATE claims
        SET claimed_value = 'UNKNOWN',
            verification_status = 'UNKNOWN',
            claim_notes = 'Wayne Yoder personal direct phone is UNKNOWN; (330) 893-3031 is official facility FAX. Facility reachable via toll-free (800) 531-1704.',
            updated_at = ?
        WHERE id = 1708
    """, (now_iso,))

    print("--- 2. Reconciling Cole Hardwood (CID 300, FID 386) ---")
    # Correct facility address and name
    c.execute("""
        UPDATE facilities
        SET facility_name = 'Logansport Hardwood Facility & Concentration Yard',
            physical_address = '1611 W Market St',
            city = 'Logansport',
            state_prov = 'IN',
            postal_code = '46947',
            updated_at = ?
        WHERE id = 386
    """, (now_iso,))

    # Correct Cole Hardwood contact phone
    c.execute("""
        UPDATE contacts
        SET phone_number = '(574) 753-3151',
            phone_directness = 'GENERAL_SWITCHBOARD',
            exact_published_title = 'Sales & Shipping Switchboard'
        WHERE facility_id = 386
    """)

    # Update Cole Hardwood footprint
    c.execute("""
        UPDATE companies
        SET company_footprint_status = 'SINGLE_SITE_VERIFIED',
            verified_operating_location_count = 1,
            footprint_source_notes = 'Official site confirms major single-site hardwood inventory and concentration facility at 1611 W Market St, Logansport, IN with company-owned truck fleet.'
        WHERE id = 300
    """)

    # Update Cole Hardwood physical address claim
    c.execute("""
        UPDATE claims
        SET claimed_value = '1611 W Market St, Logansport, IN 46947, US',
            claim_notes = 'Official corporate site verifies Logansport concentration yard & distribution center.',
            updated_at = ?
        WHERE facility_id = 386 AND claim_field = 'physical_address'
    """, (now_iso,))

    print("--- 3. Demoting 7 Companies from Shortlist to Qualified ---")
    demotions = [
        (25, 24, "Majestic Steel USA", 9, "Nationwide network of 9 service centers across US."),
        (26, 25, "Heidtman Steel Products, Inc.", 5, "Network of 5+ wholly owned processing plants and JVs."),
        (42, 41, "Bemis Manufacturing Company", 6, "Multiple manufacturing plants in Sheboygan Falls complex plus Lenoir NC and Russellville AR."),
        (44, 43, "SyBridge Technologies", 14, "Private equity tooling conglomerate with 14+ acquired tooling centers across North America."),
        (60, 65, "Rex Lumber", 4, "4 large Southern Yellow Pine sawmills: Bristol FL, Graceville FL, Brookhaven MS, Troy AL."),
        (32, 31, "Coreslab Structures (ONT) Inc.", 17, "Network of 17 precast concrete production facilities across North America."),
        (40, 39, "Cascade Engineering", 5, "5 operating facilities across Grand Rapids MI campus, North Carolina, Texas, and international operations.")
    ]

    for cid, fid, brand, loc_cnt, notes in demotions:
        c.execute("""
            UPDATE companies
            SET company_footprint_status = 'MULTI_SITE_VERIFIED',
                verified_operating_location_count = ?,
                footprint_source_notes = ?
            WHERE id = ?
        """, (loc_cnt, notes, cid))

        c.execute("""
            UPDATE prospect_lifecycle
            SET stage = 'QUALIFIED',
                qualification_notes = ?,
                updated_at = ?
            WHERE facility_id = ?
        """, (f"Reclassified to Qualified in Stage 3F.2: Verified multi-site enterprise scale ({loc_cnt} locations) with High broker access friction.", now_iso, fid))
        print(f"Demoted CID {cid} ({brand}) -> QUALIFIED ({loc_cnt} locations)")

    print("--- 4. Promoting 6 Companies from Qualified to Shortlist ---")
    promotions = [
        (13, 12, "Jordan Forest Products, LLC", "SINGLE_SITE_VERIFIED", 1, "Single-site pine sawmill in Barnesville, GA (752 Grove St) with Mill/Sales Manager Larry Spillers."),
        (22, 21, "Janco Steel Ltd.", "MULTI_SITE_VERIFIED", 2, "Two operating locations in Ontario: Stoney Creek campus (Arvin Ave) and Wallenstein manufacturing plant."),
        (15, 14, "The Universal Steel Company", "SINGLE_SITE_VERIFIED", 1, "Single 200,000 sq ft flat-rolled steel service center at 6600 Grant Ave, Cleveland, OH."),
        (114, 143, "Anchor Concrete Products", "SINGLE_SITE_VERIFIED", 1, "Single manufacturing plant in Kingston, ON (1645 Sydenham Rd) producing precast infrastructure since 1969."),
        (122, 151, "Encore Precast LLC", "MULTI_SITE_VERIFIED", 3, "3 locations: Seven Mile OH manufacturing plant, Dayton OH plant, and London KY yard."),
        (9, 8, "Shearouse Lumber Company", "SINGLE_SITE_VERIFIED", 1, "Single family-owned sawmill, planer mill, and treating plant in Pooler, GA (833 W Hwy 80) since 1926.")
    ]

    for cid, fid, brand, fp_status, loc_cnt, notes in promotions:
        c.execute("""
            UPDATE companies
            SET company_footprint_status = ?,
                verified_operating_location_count = ?,
                footprint_source_notes = ?
            WHERE id = ?
        """, (fp_status, loc_cnt, notes, cid))

        c.execute("""
            UPDATE prospect_lifecycle
            SET stage = 'SHORTLISTED',
                shortlisted_at = CURRENT_TIMESTAMP,
                qualification_notes = ?,
                updated_at = ?
            WHERE facility_id = ?
        """, (f"Promoted to Shortlist in Stage 3F.2: Verified {fp_status.replace('_', ' ').lower()} footprint ({loc_cnt} loc), Low/Medium broker friction, primary source, active phone.", now_iso, fid))
        print(f"Promoted CID {cid} ({brand}) -> SHORTLISTED ({fp_status}, {loc_cnt} loc)")

    print("--- 5. Setting Verified Footprints for Remaining Core Shortlist ---")
    remaining_shortlist = [
        (1, "MULTI_SITE_VERIFIED", 6, "Beasley Forest Products / Beasley Group operates ~6 hardwood sawmills in GA/SC."),
        (2, "MULTI_SITE_VERIFIED", 3, "Kenwal Steel operates 3 service centers: Dearborn MI, Burns Harbor IN, Lebanon TN."),
        (3, "SINGLE_SITE_VERIFIED", 1, "DECAST Ltd. operates a single massive precast manufacturing complex in Utopia, ON."),
        (5, "MULTI_SITE_VERIFIED", 3, "WMG Technologies operates tooling plants and design centers across Windsor, ON campus."),
        (6, "SINGLE_SITE_VERIFIED", 1, "Battle Lumber operates a single massive sawmill complex in Wadley, GA."),
        (7, "SINGLE_SITE_VERIFIED", 1, "Custom Cut Timber Products operates a single hardwood sawmill in Forsyth, GA."),
        (10, "SINGLE_SITE_VERIFIED", 1, "Leslie Forest Products operates a single remanufacturing mill in Delta, BC."),
        (16, "SINGLE_SITE_VERIFIED", 1, "Miami Valley Steel Service operates a single 320,000 sq ft facility in Piqua, OH."),
        (17, "SINGLE_SITE_VERIFIED", 1, "MidWest Materials operates a single steel service center in Perry, OH."),
        (18, "MULTI_SITE_VERIFIED", 2, "Liberty Steel Products operates processing centers in Hubbard and North Jackson, OH."),
        (19, "SINGLE_SITE_VERIFIED", 1, "Coil Steel Processing operates a single stretcher leveling plant in Toledo, OH."),
        (21, "MULTI_SITE_VERIFIED", 2, "Taylor Steel operates 2 major campuses: Stoney Creek ON and Lordstown OH."),
        (30, "MULTI_SITE_VERIFIED", 2, "High Concrete Group operates 2 precast plants: Denver PA and Springboro OH."),
        (31, "SINGLE_SITE_VERIFIED", 1, "Concast Pipe operates a single precast pipe plant in Puslinch, ON."),
        (33, "MULTI_SITE_VERIFIED", 2, "Norwalk Concrete Industries operates 2 plants in Norwalk, OH: Commerce Dr and Woodlawn Ave."),
        (34, "MULTI_SITE_VERIFIED", 2, "E.C. Babbert operates 2 precast plants in OH: Canal Winchester and Lancaster."),
        (35, "SINGLE_SITE_VERIFIED", 1, "Precon Precast Limited operates a single manufacturing plant in Woodstock, ON."),
        (63, "MULTI_SITE_VERIFIED", 3, "Scotch Plywood operates 3 facilities: Fulton AL plywood mill, Beatrice AL veneer mill, Waynesboro MS veneer mill."),
        (68, "SINGLE_SITE_VERIFIED", 1, "Troy Lumber Company operates a single sawmill complex in Troy, NC."),
        (77, "SINGLE_SITE_VERIFIED", 1, "Vanderwell Contractors operates a single sawmill and pellet plant complex in Slave Lake, AB."),
        (86, "SINGLE_SITE_VERIFIED", 1, "Scott Steel operates a single processing facility in Piqua, OH."),
        (155, "MULTI_SITE_VERIFIED", 2, "AarKel Tool and Die operates 2 locations: Wallaceburg ON mold facility and Windsor design center."),
        (289, "SINGLE_SITE_VERIFIED", 1, "Kepley-Frank Hardwood operates a single hardwood sawmill in Lexington, NC.")
    ]

    for cid, fp_status, loc_cnt, notes in remaining_shortlist:
        c.execute("""
            UPDATE companies
            SET company_footprint_status = ?,
                verified_operating_location_count = ?,
                footprint_source_notes = ?
            WHERE id = ?
        """, (fp_status, loc_cnt, notes, cid))

    # Also for Custom Cut Timber Products (CID 7), attach resolving source
    c.execute("""
        UPDATE companies
        SET website_url = 'https://gatrees.org/forest-management-conservation/wood-using-industries/'
        WHERE id = 7 AND website_url IS NULL
    """)

    conn.commit()

    # Verify counts
    c.execute("SELECT stage, count(*) FROM prospect_lifecycle GROUP BY stage")
    print("\nLifecycle facility counts:", c.fetchall())

    c.execute("""
        SELECT 
            pl.stage, 
            count(DISTINCT f.company_id) 
        FROM facilities f 
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id 
        GROUP BY pl.stage
    """)
    print("Lifecycle distinct company counts:", c.fetchall())

    # Check footprint distribution on Shortlist
    c.execute("""
        SELECT 
            c.company_footprint_status, 
            count(DISTINCT c.id)
        FROM facilities f
        JOIN companies c ON f.company_id = c.id
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE pl.stage = 'SHORTLISTED'
        GROUP BY c.company_footprint_status
    """)
    print("Shortlist footprint status distribution:", c.fetchall())

    conn.close()
    print("Database updates completed successfully.")

if __name__ == "__main__":
    apply_updates()
