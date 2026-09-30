import sqlite3

PRE_DB = "data/backups/prospects_backup_stage3e_pre_import_latest.db"
CURR_DB = "data/prospects.db"

def inspect_db(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    # Companies
    c.execute("SELECT id, operating_brand, legal_name, corporate_address, website_url FROM companies ORDER BY id")
    companies = {r["id"]: dict(r) for r in c.fetchall()}
    
    # Facilities
    c.execute("SELECT f.id, f.company_id, f.facility_name, f.city, f.state_prov, pl.stage FROM facilities f LEFT JOIN prospect_lifecycle pl ON f.id = pl.facility_id ORDER BY f.id")
    facilities = {r["id"]: dict(r) for r in c.fetchall()}
    
    # Stages
    c.execute("SELECT pl.stage, count(*) FROM facilities f JOIN prospect_lifecycle pl ON f.id = pl.facility_id GROUP BY pl.stage")
    fac_stages = dict(c.fetchall())
    
    c.execute("""
        SELECT pl.stage, count(DISTINCT f.company_id) 
        FROM facilities f 
        JOIN prospect_lifecycle pl ON f.id = pl.facility_id 
        GROUP BY pl.stage
    """)
    comp_stages = dict(c.fetchall())
    
    conn.close()
    return companies, facilities, fac_stages, comp_stages

pre_comp, pre_fac, pre_fac_stages, pre_comp_stages = inspect_db(PRE_DB)
curr_comp, curr_fac, curr_fac_stages, curr_comp_stages = inspect_db(CURR_DB)

print("=== PRE-STAGE-3E METRICS ===")
print("Total companies table:", len(pre_comp))
print("Operating companies with facilities:", len(set(f["company_id"] for f in pre_fac.values())))
print("Company stages:", pre_comp_stages)
print("Total facilities:", len(pre_fac))
print("Facility stages:", pre_fac_stages)

print("\n=== CURRENT METRICS ===")
print("Total companies table:", len(curr_comp))
print("Operating companies with facilities:", len(set(f["company_id"] for f in curr_fac.values())))
print("Company stages:", curr_comp_stages)
print("Total facilities:", len(curr_fac))
print("Facility stages:", curr_fac_stages)

# Delta
new_company_ids = sorted(set(curr_comp.keys()) - set(pre_comp.keys()))
new_facility_ids = sorted(set(curr_fac.keys()) - set(pre_fac.keys()))

print(f"\n=== DELTA ===")
print(f"New company IDs count: {len(new_company_ids)} (Range: {min(new_company_ids)} to {max(new_company_ids)})")
print(f"New facility IDs count: {len(new_facility_ids)} (Range: {min(new_facility_ids)} to {max(new_facility_ids)})")

# Check facilities mapped to new vs existing companies
new_facs = [curr_fac[fid] for fid in new_facility_ids]
facs_to_new_comps = [f for f in new_facs if f["company_id"] in new_company_ids]
facs_to_old_comps = [f for f in new_facs if f["company_id"] not in new_company_ids]

print(f"New facilities mapped to new companies: {len(facs_to_new_comps)}")
print(f"New facilities mapped to PRE-EXISTING companies: {len(facs_to_old_comps)}")
for f in facs_to_old_comps:
    parent = curr_comp[f["company_id"]]
    print(f"  -> Facility ID {f['id']} ({f['facility_name']}, {f['city']}, {f['state_prov']}) mapped to existing company {parent['id']}: {parent['operating_brand']}")

# Check company-to-facility mapping among new companies
comp_fac_counts = {}
for f in facs_to_new_comps:
    comp_fac_counts[f["company_id"]] = comp_fac_counts.get(f["company_id"], 0) + 1

multi_in_new = {cid: cnt for cid, cnt in comp_fac_counts.items() if cnt > 1}
print(f"\nNew companies with multiple new facilities: {len(multi_in_new)}")
for cid, cnt in multi_in_new.items():
    print(f"  Company {cid} ({curr_comp[cid]['operating_brand']}): {cnt} facilities")

# Check Facility 18 in both
print("\n=== FACILITY 18 CHECK ===")
if 18 in pre_fac:
    f18_pre = pre_fac[18]
    c18_pre = pre_comp[f18_pre["company_id"]]
    print(f"Pre-Stage-3E Facility 18: {f18_pre}")
    print(f"Pre-Stage-3E Parent Company: {c18_pre}")
if 18 in curr_fac:
    f18_curr = curr_fac[18]
    c18_curr = curr_comp[f18_curr["company_id"]]
    print(f"Current Facility 18: {f18_curr}")
    print(f"Current Parent Company: {c18_curr}")
