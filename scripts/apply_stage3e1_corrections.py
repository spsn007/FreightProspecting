"""
Stage 3E.1 Execution Script:
Applies truth-based corrections and deduplication to data/prospects.db:
1. Yoder Lumber: Berlin location truth, Wayne Yoder (Shipping Manager, direct line), verified private fleet.
2. Cole Hardwood: Remove generic freight contact, classify sales@ as COMMERCIAL_SALES, verified private fleet.
3. Somerset Flooring: Keep shipping@ as FREIGHT_LOGISTICS Shipping Department.
4. All Stage 3E Contacts: Classify into Category A (published person), Category B (published freight dept),
   Category C (Commercial Sales for sales/ventes emails), and Category D -> General Facility for general emails.
5. Fix Source 449: Align with R.J. Hoffman & Sons.
6. Deduplicate Boise Cascade / Coastal Forest Resources: Record acquisition relationship, remove duplicate Facility 228.
7. Audit database foreign keys and integrity.
"""

import sqlite3
import datetime
from pathlib import Path

DB_PATH = "data/prospects.db"

def apply_corrections():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    c = conn.cursor()
    
    print("Beginning Stage 3E.1 corrections transaction...")
    c.execute("BEGIN TRANSACTION;")
    
    # ---------------------------------------------------------
    # 1. Yoder Lumber Co. (Company 321, Facility 408, Contact 418)
    # ---------------------------------------------------------
    print("1. Correcting Yoder Lumber...")
    c.execute("""
        UPDATE facilities 
        SET facility_name = 'Berlin Sawmill & Millwork Facility',
            physical_address = '4515 Township Road 367',
            city = 'Millersburg', 
            state_prov = 'OH', 
            postal_code = '44654',
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
    # Update phone directness claim for contact 418
    c.execute("""
        UPDATE claims
        SET claimed_value = 'DIRECT_PERSON'
        WHERE contact_id = 418 AND claim_field = 'phone_directness'
    """)
    # Insert source for Yoder Lumber fleet
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    c.execute("""
        INSERT INTO evidence_sources (source_type, source_title_publisher, source_url, is_primary_source, observed_at, notes)
        VALUES ('COMPANY_WEBSITE', 'Yoder Lumber Company Official Website - About Us & Delivery', 'https://www.yoderlumber.com/about-us/', 1, ?, 'Documents company growth, dedicated truck fleet and delivery operations.')
    """, (now_iso,))
    yoder_src_id = c.lastrowid
    # Update claim for private fleet present
    c.execute("""
        UPDATE claims 
        SET claimed_value = 'VERIFIED_PRESENT', 
            verification_status = 'VERIFIED', 
            claim_notes = 'Company documents dedicated truck fleet and build-ready delivery.'
        WHERE id = 1706
    """)
    yoder_claim_id = 1706
    c.execute("""
        INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship)
        VALUES (?, ?, 'SUPPORTS')
    """, (yoder_claim_id, yoder_src_id))

    # ---------------------------------------------------------
    # 2. Cole Hardwood Inc. (Company 300, Facility 386, Contact 396)
    # ---------------------------------------------------------
    print("2. Correcting Cole Hardwood...")
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
    # Insert source for Cole Hardwood fleet
    c.execute("""
        INSERT INTO evidence_sources (source_type, source_title_publisher, source_url, is_primary_source, observed_at, notes)
        VALUES ('COMPANY_WEBSITE', 'Cole Hardwood Official Website', 'https://colehardwood.com/', 1, ?, 'The company maintains its own truck fleet to serve customers globally.')
    """, (now_iso,))
    cole_src_id = c.lastrowid
    # Update claim for private fleet present
    c.execute("""
        UPDATE claims 
        SET claimed_value = 'VERIFIED_PRESENT', 
            verification_status = 'VERIFIED', 
            claim_notes = 'Maintains company-owned truck fleet for domestic and export deliveries.'
        WHERE id = 1618
    """)
    cole_claim_id = 1618
    c.execute("""
        INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship)
        VALUES (?, ?, 'SUPPORTS')
    """, (cole_claim_id, cole_src_id))

    # ---------------------------------------------------------
    # 3. Somerset Hardwood Flooring (Facility 390, Contact 400)
    # ---------------------------------------------------------
    print("3. Correcting Somerset Flooring...")
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

    # ---------------------------------------------------------
    # 4. Stage 3E Contacts Truth Audit (IDs >= 383, excluding 418, 396, 400)
    # ---------------------------------------------------------
    print("4. Auditing and correcting remaining 241 Stage 3E contacts...")
    c.execute("SELECT id, email_address FROM contacts WHERE id >= 383 AND id NOT IN (418, 396, 400)")
    contacts_to_audit = c.fetchall()
    
    sales_updated = 0
    general_updated = 0
    
    sales_prefixes = ["sales@", "ventes@", "sales.", "salespa@", "salesfs@", "torontosales@"]
    for cid, email in contacts_to_audit:
        em = (email or "").lower()
        if any(em.startswith(p) for p in sales_prefixes):
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
            sales_updated += 1
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
            general_updated += 1

    print(f"   -> Updated {sales_updated} contacts to COMMERCIAL_SALES")
    print(f"   -> Updated {general_updated} contacts to GENERAL_FACILITY")

    # ---------------------------------------------------------
    # 5. Fix Source 449 (R.J. Hoffman & Sons)
    # ---------------------------------------------------------
    print("5. Correcting Evidence Source 449...")
    c.execute("""
        UPDATE evidence_sources
        SET source_title_publisher = 'R.J. Hoffman & Sons Lumber, Inc. Official Website',
            source_url = 'http://www.rjhoffmansonslumber.com/contact-us.html',
            notes = 'Central Pennsylvania hardwood and softwood lumber producer in Mt Pleasant Mills, PA.'
        WHERE id = 449
    """)

    # ---------------------------------------------------------
    # 6. Deduplicate Boise Cascade / Coastal Forest Resources
    # ---------------------------------------------------------
    print("6. Resolving Boise Cascade / Coastal Forest Resources duplicate...")
    # Record corporate acquisition in company_relationships
    c.execute("""
        INSERT INTO company_relationships (parent_company_id, child_company_id, relationship_type, is_current, verification_status, notes)
        VALUES (61, 193, 'ACQUISITION', 1, 'VERIFIED', 'Boise Cascade acquired Coastal Plywood Company including Havana FL mill in July 2022 ($512M)')
    """)
    # Delete duplicate Facility 228 and its dependent rows
    c.execute("DELETE FROM claim_evidence WHERE claim_id IN (SELECT id FROM claims WHERE facility_id = 228)")
    c.execute("DELETE FROM claims WHERE facility_id = 228")
    c.execute("DELETE FROM contacts WHERE facility_id = 228")
    c.execute("DELETE FROM facility_commodities WHERE facility_id = 228")
    c.execute("DELETE FROM prospect_lifecycle WHERE facility_id = 228")
    c.execute("DELETE FROM discovery_intake_audit WHERE target_facility_id = 228")
    c.execute("DELETE FROM facilities WHERE id = 228")
    c.execute("DELETE FROM prospect_engagement_state WHERE company_id = 193")
    c.execute("UPDATE companies SET notes = 'Acquired by Boise Cascade in July 2022 (holding/inactive subsidiary)' WHERE id = 193")

    conn.commit()
    print("Stage 3E.1 corrections committed successfully!")

    # Verification checks
    fk_errors = list(conn.execute("PRAGMA foreign_key_check;"))
    assert len(fk_errors) == 0, f"FK errors encountered: {fk_errors}"
    integ = conn.execute("PRAGMA integrity_check;").fetchone()[0]
    assert integ == "ok", f"Integrity check failed: {integ}"
    print("PRAGMA foreign_key_check: 0 errors")
    print("PRAGMA integrity_check: ok")
    
    conn.close()

if __name__ == "__main__":
    apply_corrections()
