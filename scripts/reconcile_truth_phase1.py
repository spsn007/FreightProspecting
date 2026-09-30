import sqlite3
from pathlib import Path

DB_PATH = Path("data/prospects.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 80)
print("1A. FACILITY 460 IDENTITY CHECK")
print("=" * 80)

f460 = cur.execute("""
    SELECT f.id as facility_id, f.company_id, c.operating_brand, f.facility_name, f.city, f.state_prov,
           f.physical_address
    FROM facilities f
    JOIN companies c ON f.company_id = c.id
    WHERE f.id = 460
""").fetchone()

if f460:
    print(f"Facility ID: {f460['facility_id']}")
    print(f"Company ID: {f460['company_id']}")
    print(f"Operating Brand: {f460['operating_brand']}")
    print(f"Facility Name: {f460['facility_name']}")
    print(f"City: {f460['city']}")
    print(f"State/Province: {f460['state_prov']}")
    print(f"Physical Address: {f460['physical_address']}")

    maps = cur.execute("""
        SELECT m.is_primary, c.category_code, c.display_name as cat_name, fam.display_name as fam_name
        FROM facility_commodity_mappings m
        JOIN commodity_categories c ON m.category_id = c.id
        JOIN commodity_families fam ON c.family_id = fam.id
        WHERE m.facility_id = 460
        ORDER BY m.is_primary DESC
    """).fetchall()
    print("Taxonomy mappings for Facility 460:")
    for m in maps:
        role = "PRIMARY" if m['is_primary'] == 1 else "SECONDARY"
        print(f"  [{role}] {m['category_code']} - {m['cat_name']} ({m['fam_name']})")
else:
    print("Facility 460 NOT FOUND")

# Check Appalachian Wood Products
awp = cur.execute("""
    SELECT f.id as facility_id, f.company_id, c.operating_brand, f.facility_name, f.city, f.state_prov
    FROM facilities f
    JOIN companies c ON f.company_id = c.id
    WHERE c.operating_brand LIKE '%Appalachian%' OR f.facility_name LIKE '%Appalachian%'
""").fetchall()
print("\nAppalachian search results in DB:")
for r in awp:
    print(f"  Facility {r['facility_id']}, Company {r['company_id']}: {r['operating_brand']} - {r['facility_name']} ({r['city']}, {r['state_prov']})")

print("\n" + "=" * 80)
print("1B. CSP EQUIPMENT HISTORY CHECK")
print("=" * 80)

# Facility 18 in current DB
f18 = cur.execute("SELECT * FROM facilities WHERE id = 18").fetchone()
c18 = cur.execute("SELECT * FROM companies WHERE id = ?", (f18["company_id"],)).fetchone()
print(f"Facility 18: {f18['facility_name']}, Company: {c18['operating_brand']}")

# Facility commodities for Facility 18
comms18 = cur.execute("SELECT * FROM facility_commodities WHERE facility_id = 18").fetchall()
print(f"facility_commodities count for Fac 18: {len(comms18)}")
for fc in comms18:
    print(f"  ID: {fc['id']}, Cat: {fc['commodity_category']}, Equip: {fc['equipment_category']}, Status: {fc['equipment_usage_status']}")

# Claims for Facility 18
claims18 = cur.execute("""
    SELECT c.id, c.claim_field, c.claimed_value, c.verification_status, c.is_current_accepted
    FROM claims c
    WHERE c.facility_id = 18 OR c.facility_commodity_id IN (SELECT id FROM facility_commodities WHERE facility_id = 18)
    ORDER BY c.claim_field, c.id
""").fetchall()
print(f"Claims for Facility 18 / its commodities: {len(claims18)}")
for cl in claims18:
    print(f"  Claim {cl['id']}: field='{cl['claim_field']}', val='{cl['claimed_value']}', status='{cl['verification_status']}', accepted={cl['is_current_accepted']}")

# Check pre-remediation backup for Facility 18
BACKUP_PATH = Path("data/backups/prospects_backup_audit_remediation_a_20260927_211600.db")
if BACKUP_PATH.exists():
    b_conn = sqlite3.connect(BACKUP_PATH)
    b_conn.row_factory = sqlite3.Row
    b_cur = b_conn.cursor()
    b_comms18 = b_cur.execute("SELECT * FROM facility_commodities WHERE facility_id = 18").fetchall()
    print(f"\nPre-Remediation A Backup facility_commodities for Fac 18: {len(b_comms18)}")
    for fc in b_comms18:
        print(f"  Equip: {fc['equipment_category']}, Status: {fc['equipment_usage_status']}")
    b_claims = b_cur.execute("""
        SELECT c.id, c.claim_field, c.claimed_value, c.verification_status, c.is_current_accepted
        FROM claims c
        WHERE c.facility_id = 18 OR c.facility_commodity_id IN (SELECT id FROM facility_commodities WHERE facility_id = 18)
        ORDER BY c.claim_field, c.id
    """).fetchall()
    print(f"Pre-Remediation A Backup Claims for Fac 18: {len(b_claims)}")
    for cl in b_claims:
        print(f"  Claim {cl['id']}: field='{cl['claim_field']}', val='{cl['claimed_value']}', status='{cl['verification_status']}', accepted={cl['is_current_accepted']}")
    b_conn.close()

conn.close()
