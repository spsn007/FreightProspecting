import sqlite3

def run():
    conn = sqlite3.connect('data/prospects.db')
    c = conn.cursor()

    def sample_group(name, cat_code_filter, limit=10):
        print(f"\n=== SAMPLE: {name} (10 facilities) ===")
        query = f"""
            SELECT f.id, comp.id, comp.operating_brand, f.facility_name, fc.commodity_category, fc.specific_products, cat.category_code, cat.display_name
            FROM facility_commodity_mappings m
            JOIN facilities f ON m.facility_id = f.id
            JOIN companies comp ON f.company_id = comp.id
            JOIN facility_commodities fc ON fc.facility_id = f.id
            JOIN commodity_categories cat ON m.category_id = cat.id
            WHERE m.is_primary = 1 AND {cat_code_filter}
            ORDER BY f.id ASC
            LIMIT ?
        """
        rows = c.execute(query, (limit,)).fetchall()
        for r in rows:
            prod = (r[5][:40] + "...") if r[5] and len(r[5]) > 40 else r[5]
            print(f"FacID={r[0]}, CompID={r[1]} | {r[2]} ({r[3]}) | Legacy: {r[4]} | Prod: {prod} | Primary: {r[6]}")

    sample_group("WOOD / FOREST PRODUCTS", "cat.category_code = 'LUMBER_FOREST_PRODUCTS'")
    sample_group("STEEL / METALS", "cat.category_code = 'STEEL_METALS'")
    sample_group("CONCRETE / PRECAST", "cat.category_code = 'CONCRETE_PRECAST_PRODUCTS'")
    sample_group("PLASTICS / TOOLING", "cat.category_code = 'PLASTICS_TOOLING_PRODUCTS'")
    sample_group("INDUSTRIAL / BUILDING", "cat.category_code IN ('BUILDING_MATERIALS_GENERAL', 'INDUSTRIAL_MFG_EQUIPMENT')")

if __name__ == '__main__':
    run()
