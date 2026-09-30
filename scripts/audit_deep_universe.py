import sqlite3
from collections import Counter
from pathlib import Path

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

# Check companies, facilities, commodities, contacts, lifecycle
companies = conn.execute("""
    SELECT c.id, c.operating_brand, c.company_footprint_status,
           count(DISTINCT f.id) as fac_count,
           min(pl.stage) as min_stage,
           max(pl.stage) as max_stage
    FROM companies c
    JOIN facilities f ON c.id = f.company_id
    LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
    GROUP BY c.id
    ORDER BY c.id
""").fetchall()

stage_counter = Counter()
for c in companies:
    # If all facilities same stage, or mixed
    stages = conn.execute("""
        SELECT DISTINCT pl.stage 
        FROM facilities f
        LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id
        WHERE f.company_id = ?
    """, (c["id"],)).fetchall()
    st_set = {s[0] for s in stages if s[0]}
    stage_str = "/".join(sorted(st_set)) if st_set else "NO_LIFECYCLE"
    stage_counter[stage_str] += 1

print("Company Lifecycle Distribution (565 operating companies):")
for k, v in stage_counter.items():
    print(f"  {k}: {v}")

# Check facilities without commodities
no_comm_facs = conn.execute("""
    SELECT f.id, f.facility_name, c.operating_brand
    FROM facilities f
    JOIN companies c ON f.company_id = c.id
    LEFT JOIN facility_commodities fc ON f.id = fc.facility_id
    WHERE fc.id IS NULL
""").fetchall()
print(f"\nFacilities without commodities: {len(no_comm_facs)}")

# Check companies without contacts
no_contact_comps = conn.execute("""
    SELECT c.id, c.operating_brand
    FROM companies c
    WHERE c.id NOT IN (
        SELECT DISTINCT company_id FROM contacts WHERE company_id IS NOT NULL
        UNION
        SELECT DISTINCT f.company_id FROM contacts ct JOIN facilities f ON ct.facility_id = f.id
    )
""").fetchall()
print(f"Companies without any contact: {len(no_contact_comps)}")

# Check contacts details: direct phone vs general switchboard
contacts = conn.execute("""
    SELECT role_category, phone_directness, count(*) 
    FROM contacts
    GROUP BY role_category, phone_directness
""").fetchall()
print("\nContacts by role_category and phone_directness:")
for ct in contacts:
    print(f"  Role: {ct[0]}, Directness: {ct[1]} -> Count: {ct[2]}")

# Check claims on commercial carrier use and private fleet
claims = conn.execute("""
    SELECT claim_field, claim_value, verification_status, count(*)
    FROM claims
    WHERE claim_field IN ('private_fleet_present', 'commercial_carrier_use', 'broker_friendly_status', 'fleet_relationship_type')
    GROUP BY claim_field, claim_value, verification_status
""").fetchall()
print("\nClaims on fleet/carrier/broker:")
for cl in claims:
    print(f"  Field: {cl[0]}, Value: {cl[1]}, Status: {cl[2]} -> Count: {cl[3]}")

conn.close()
