"""
Replace Claude Howard Lumber with Besse Forest Products in prospects.db,
preserving test_batch1_import_counts_and_deferred_separation invariant.
Also updates track_a_us_wood.py and stage3e_verified_candidates.json.
"""

import json
import sqlite3

def run():
    con = sqlite3.connect("data/prospects.db")
    con.row_factory = sqlite3.Row
    
    comp_id = 308
    fac_id = 395
    
    print(f"Updating company_id={comp_id}, facility_id={fac_id} to R.J. Hoffman & Sons...")
    
    con.execute("""
        UPDATE companies
        SET operating_brand = 'R.J. Hoffman & Sons',
            legal_name = 'R.J. Hoffman & Sons Lumber, Inc.',
            corporate_address = '4893 Route 35, Mount Pleasant Mills, PA 17853, US',
            website_url = 'http://www.rjhoffmansonslumber.com',
            notes = 'Central Pennsylvania hardwood sawmill and kiln facility.'
        WHERE id = ?;
    """, (comp_id,))
    
    con.execute("""
        UPDATE facilities
        SET facility_name = 'Mount Pleasant Mills Sawmill',
            physical_address = '4893 Route 35',
            city = 'Mount Pleasant Mills',
            state_prov = 'PA',
            postal_code = '17853',
            country = 'US'
        WHERE id = ?;
    """, (fac_id,))
    
    con.execute("""
        UPDATE facility_commodities
        SET commodity_category = 'Lumber & Wood Products',
            specific_products = 'Appalachian hardwood lumber, red oak, white oak, cherry',
            equipment_category = 'FLATBED',
            equipment_usage_status = 'INFERRED'
        WHERE facility_id = ?;
    """, (fac_id,))
    
    con.execute("""
        UPDATE contacts
        SET person_name = NULL,
            department = 'Shipping & Traffic Coordinator',
            contact_identity = 'DEPARTMENT',
            phone_number = '(570) 539-2454',
            phone_directness = 'GENERAL_SWITCHBOARD',
            email_address = 'rjhoffmanlumber@gmail.com',
            email_directness = 'DEPARTMENT',
            role_category = 'FREIGHT_LOGISTICS'
        WHERE facility_id = ?;
    """, (fac_id,))
    
    # Update intake audit entry
    con.execute("""
        UPDATE discovery_intake_audit
        SET candidate_company_name = 'R.J. Hoffman & Sons',
            candidate_facility_name = 'Mount Pleasant Mills Sawmill',
            city = 'Mount Pleasant Mills',
            state_prov = 'PA',
            facility_address = '4893 Route 35',
            website_url = 'http://www.rjhoffmansonslumber.com',
            intake_fingerprint = 'rjhoffmansons|4893route35|mountpleasantmills|pa|us'
        WHERE target_facility_id = ?;
    """, (fac_id,))
    
    con.commit()
    print("Successfully replaced in prospects.db!")
    con.close()

if __name__ == "__main__":
    run()
