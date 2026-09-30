import sys, os
sys.path.insert(0, os.path.abspath('.'))
import sqlite3
import shutil
from collections import Counter
from src.backend.db.connection import get_db_path
from src.backend.db.queries import get_company_grouped_prospects, get_summary_counts

TEST_DB = "data/test_friction_sim.db"
shutil.copy2("data/prospects.db", TEST_DB)

conn = sqlite3.connect(TEST_DB)
c = conn.cursor()

# 1. Update Yoder
c.execute("""
    UPDATE facilities 
    SET facility_name = 'Berlin Sawmill & Millwork Facility',
        physical_address = '4515 Township Road 367',
        city = 'Millersburg', state_prov = 'OH', postal_code = '44654',
        private_fleet_present = 'VERIFIED_PRESENT',
        vehicle_asset_ownership = 'VERIFIED_OWNED',
        fleet_relationship_type = 'IN_HOUSE_OWNED'
    WHERE id = 408
""")
c.execute("""
    UPDATE contacts
    SET person_name = 'Wayne Yoder',
        exact_published_title = 'Shipping Manager',
        department = 'Shipping',
        phone_number = '(330) 893-3031',
        phone_directness = 'DIRECT_PERSON',
        email_address = 'info@yoderlumber.com',
        email_directness = 'GENERAL',
        role_category = 'FREIGHT_LOGISTICS',
        contact_identity = 'NAMED_PERSON'
    WHERE id = 418
""")

# 2. Update Cole Hardwood
c.execute("""
    UPDATE facilities
    SET private_fleet_present = 'VERIFIED_PRESENT',
        vehicle_asset_ownership = 'VERIFIED_OWNED',
        fleet_relationship_type = 'IN_HOUSE_OWNED'
    WHERE id = 386
""")
c.execute("""
    UPDATE contacts
    SET person_name = NULL,
        exact_published_title = NULL,
        department = 'Commercial Sales',
        phone_number = '(574) 342-8050',
        phone_directness = 'GENERAL_SWITCHBOARD',
        email_address = 'sales@colehardwood.com',
        email_directness = 'DEPARTMENT',
        role_category = 'COMMERCIAL_SALES',
        contact_identity = 'DEPARTMENT'
    WHERE id = 396
""")

# 3. Update Somerset flooring
c.execute("""
    UPDATE contacts
    SET person_name = NULL,
        exact_published_title = NULL,
        department = 'Shipping Department',
        phone_directness = 'GENERAL_SWITCHBOARD',
        email_directness = 'DEPARTMENT',
        role_category = 'FREIGHT_LOGISTICS',
        contact_identity = 'DEPARTMENT'
    WHERE id = 400
""")

# 4. Update all other Stage 3E contacts
c.execute("SELECT id, email_address FROM contacts WHERE id >= 383 AND id NOT IN (418, 396, 400)")
rows = c.fetchall()
for cid, email in rows:
    em = (email or "").lower()
    if any(em.startswith(p) for p in ["sales@", "ventes@", "sales.", "salespa@", "salesfs@", "torontosales@"]):
        c.execute("""
            UPDATE contacts
            SET person_name = NULL,
                exact_published_title = NULL,
                department = 'Commercial Sales',
                phone_directness = 'GENERAL_SWITCHBOARD',
                email_directness = 'DEPARTMENT',
                role_category = 'COMMERCIAL_SALES',
                contact_identity = 'DEPARTMENT'
            WHERE id = ?
        """, (cid,))
    else:
        email_dir = 'GENERAL' if email else 'UNKNOWN'
        c.execute("""
            UPDATE contacts
            SET person_name = NULL,
                exact_published_title = NULL,
                department = NULL,
                phone_directness = 'GENERAL_SWITCHBOARD',
                email_directness = ?,
                role_category = 'GENERAL_FACILITY',
                contact_identity = 'GENERAL_FACILITY'
            WHERE id = ?
        """, (email_dir, cid))

# 5. Fix source 449
c.execute("""
    UPDATE evidence_sources
    SET source_title_publisher = 'R.J. Hoffman & Sons Lumber, Inc. Official Website',
        source_url = 'http://www.rjhoffmansonslumber.com/contact-us.html',
        notes = 'Central Pennsylvania hardwood and softwood lumber producer in Mt Pleasant Mills, PA.'
    WHERE id = 449
""")

# 6. Deduplicate Boise Cascade / Coastal Forest Resources (Facility 228 into Boise Cascade)
# First record corporate acquisition
c.execute("""
    INSERT INTO company_relationships (parent_company_id, child_company_id, relationship_type, is_current, verification_status, notes)
    VALUES (61, 193, 'ACQUISITION', 1, 'VERIFIED', 'Boise Cascade acquired Coastal Plywood Company including Havana FL mill in July 2022 ($512M)')
""")
# Consolidate facility 228: delete facility 228 and its dependent rows
c.execute("DELETE FROM claim_evidence WHERE claim_id IN (SELECT id FROM claims WHERE facility_id = 228)")
c.execute("DELETE FROM claims WHERE facility_id = 228")
c.execute("DELETE FROM contacts WHERE facility_id = 228")
c.execute("DELETE FROM facility_commodities WHERE facility_id = 228")
c.execute("DELETE FROM prospect_lifecycle WHERE facility_id = 228")
c.execute("DELETE FROM discovery_intake_audit WHERE target_facility_id = 228")
c.execute("DELETE FROM facilities WHERE id = 228")
c.execute("DELETE FROM prospect_engagement_state WHERE company_id = 193")
c.execute("UPDATE companies SET notes = 'Acquired by Boise Cascade in July 2022 (holding/inactive)' WHERE id = 193")

conn.commit()
conn.close()

# Now inspect with get_company_grouped_prospects
groups = get_company_grouped_prospects(lifecycle_stage="ALL", db_path=TEST_DB)
frictions = Counter(g["friction_level"] for g in groups)
print("\n=== RECALCULATED BROKER ACCESS FRICTION ===")
print("Friction distribution:", frictions)
print(f"Total groups: {len(groups)}")

# Summary counts
counts = get_summary_counts(TEST_DB)
print("\n=== RECALCULATED SUMMARY COUNTS ===")
for k in ["total_companies_count", "all_companies_count", "discovery_companies_count", "shortlisted_companies_count", "all_prospects_count", "discovery_count", "shortlisted_count", "single_facility_companies_count", "multi_facility_companies_count"]:
    print(f"  {k}: {counts[k]}")

# Clean up test DB
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
