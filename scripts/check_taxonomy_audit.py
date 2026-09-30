import sqlite3

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

# 1. StructureCraft
print("--- StructureCraft Search ---")
sc_rows = cur.execute("""
    SELECT c.id, c.operating_brand, f.id, f.facility_name, fc.id, fc.commodity_category, fc.specific_products, fc.equipment_category
    FROM companies c
    JOIN facilities f ON c.id = f.company_id
    LEFT JOIN facility_commodities fc ON f.id = fc.facility_id
    WHERE c.operating_brand LIKE '%StructureCraft%' OR f.facility_name LIKE '%StructureCraft%'
""").fetchall()
for r in sc_rows:
    print("  StructureCraft:", r)
    tm_rows = cur.execute("""
        SELECT fcm.id, fcm.is_primary, cc.category_code, cc.display_name, cc.typical_equipment_fit, cf.display_name, fcm.source_evidence_notes
        FROM facility_commodity_mappings fcm
        JOIN commodity_categories cc ON fcm.category_id = cc.id
        JOIN commodity_families cf ON cc.family_id = cf.id
        WHERE fcm.facility_id = ?
    """, (r[2],)).fetchall()
    for tm in tm_rows:
        print("    Mapping:", tm)

# 2. Check all facilities mapped to BAGGED_MULCH_SOIL or related mulch categories
print("\n--- Mulch / Soil Mappings ---")
mulch_rows = cur.execute("""
    SELECT f.id, c.operating_brand, f.facility_name, fc.specific_products, fc.commodity_category, cc.category_code, fcm.is_primary, fcm.source_evidence_notes
    FROM facility_commodity_mappings fcm
    JOIN commodity_categories cc ON fcm.category_id = cc.id
    JOIN facilities f ON fcm.facility_id = f.id
    JOIN companies c ON f.company_id = c.id
    LEFT JOIN facility_commodities fc ON f.id = fc.facility_id
    WHERE cc.category_code LIKE '%MULCH%' OR fc.specific_products LIKE '%mulch%' OR fc.commodity_category LIKE '%mulch%'
""").fetchall()
for r in mulch_rows:
    print("  Mulch row:", r)

# 3. Check all categories in commodity_categories
print("\n--- All 32 Categories ---")
cats = cur.execute("SELECT id, category_code, display_name, family_id, is_active FROM commodity_categories").fetchall()
for c in cats:
    print("  Cat:", c)

conn.close()
