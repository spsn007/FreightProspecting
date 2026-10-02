import sqlite3, json, hashlib
from pathlib import Path
import sys
sys.path.insert(0, '.')
from src.backend.db.connection import create_connection
from src.backend.db.opportunity import load_opportunity_universe_context
from src.backend.db.queries import get_company_grouped_prospects

db_path = 'data/prospects.db'
conn = create_connection(db_path)
conn.row_factory = sqlite3.Row

# 1. Hashes & Backups
pre_sha = '6BD5B8360FA713630477D715C5794906F44CB8814DFAB8EDF47D676C672767D9'
final_sha = hashlib.sha256(Path(db_path).read_bytes()).hexdigest().upper()
backup_path = 'D:\\FreightProspecting\\backup\\expansion\\pre_1000_expansion_20261002_071700.db'

# 2. PRAGMAs & Integrity
integ = [tuple(r) for r in conn.execute('PRAGMA integrity_check;').fetchall()]
fks = [tuple(r) for r in conn.execute('PRAGMA foreign_key_check;').fetchall()]

# 3. Claims & Relational Integrity
orphans_claims = conn.execute('''
    SELECT count(*) FROM claims c
    WHERE (c.company_id IS NOT NULL AND c.company_id NOT IN (SELECT id FROM companies))
       OR (c.facility_id IS NOT NULL AND c.facility_id NOT IN (SELECT id FROM facilities))
       OR (c.contact_id IS NOT NULL AND c.contact_id NOT IN (SELECT id FROM contacts))
       OR (c.facility_commodity_id IS NOT NULL AND c.facility_commodity_id NOT IN (SELECT id FROM facility_commodities))
''').fetchone()[0]

orphans_ce = conn.execute('''
    SELECT count(*) FROM claim_evidence ce
    WHERE ce.claim_id NOT IN (SELECT id FROM claims)
       OR ce.evidence_source_id NOT IN (SELECT id FROM evidence_sources)
''').fetchone()[0]

dup_curr_claims = len(conn.execute('''
    SELECT facility_id, claim_field, count(*) FROM claims
    WHERE is_current_accepted = 1 AND facility_id IS NOT NULL
    GROUP BY facility_id, claim_field HAVING count(*) > 1
''').fetchall())

dup_comp_identities = len(conn.execute('''
    SELECT lower(operating_brand), count(*) FROM companies
    GROUP BY lower(operating_brand) HAVING count(*) > 1
''').fetchall())

# 4. Parity
ctx = load_opportunity_universe_context(conn)
engine_tiers = {k: len(v) for k, v in ctx['tier_company_ids'].items()}
engine_total = sum(engine_tiers.values())

groups = get_company_grouped_prospects(lifecycle_stage='ALL', db_path=db_path)
grouped_tiers = {}
for g in groups:
    t = g.get('opportunity_tier')
    grouped_tiers[t] = grouped_tiers.get(t, 0) + 1
grouped_total = len(groups)

parity = 'PASS' if (engine_tiers == grouped_tiers and engine_total == grouped_total) else 'FAIL'

# 5. Quality metrics on newly added universe (id > 567)
new_companies = conn.execute('SELECT * FROM companies WHERE id > 567').fetchall()
new_company_ids = [c['id'] for c in new_companies]

with_website = sum(1 for c in new_companies if c['website_url'])
without_website = len(new_companies) - with_website

new_contacts = conn.execute('SELECT * FROM contacts WHERE facility_id IN (SELECT id FROM facilities WHERE company_id > 567)').fetchall()
named_contacts = sum(1 for c in new_contacts if c['contact_identity'] == 'NAMED_INDIVIDUAL')
dept_contacts = sum(1 for c in new_contacts if c['contact_identity'] == 'DEPARTMENT_CHANNEL')
general_contacts = sum(1 for c in new_contacts if c['contact_identity'] == 'ORGANIZATIONAL_ROLE')

new_facs = conn.execute('SELECT * FROM facilities WHERE company_id > 567').fetchall()
carrier_verified = sum(1 for f in new_facs if f['commercial_carrier_use'] == 'VERIFIED_USES_OUTSIDE')
broker_verified = sum(1 for f in new_facs if f['broker_friendly_status'] == 'VERIFIED_ACCEPTS')
fleet_verified = sum(1 for f in new_facs if f['private_fleet_present'] == 'VERIFIED_PRESENT')

new_comm = conn.execute('SELECT * FROM facility_commodities WHERE facility_id IN (SELECT id FROM facilities WHERE company_id > 567)').fetchall()
eq_verified = sum(1 for fc in new_comm if fc['equipment_usage_status'] == 'VERIFIED')
eq_inferred = sum(1 for fc in new_comm if fc['equipment_usage_status'] == 'INFERRED')

unknown_fields = sum(1 for f in new_facs if f['commercial_carrier_use'] == 'UNKNOWN') + sum(1 for f in new_facs if f['broker_friendly_status'] == 'UNKNOWN') + sum(1 for f in new_facs if f['private_fleet_present'] == 'UNKNOWN')

print(f"PRE_SHA: {pre_sha}")
print(f"BACKUP_PATH: {backup_path}")
print(f"FINAL_SHA: {final_sha}")
print(f"INTEGRITY: {'ok' if integ == [('ok',)] else integ}")
print(f"FK: {len(fks)}")
print(f"ORPHAN_CLAIMS: {orphans_claims}")
print(f"ORPHAN_CE: {orphans_ce}")
print(f"DUP_CURRENT_CLAIMS: {dup_curr_claims}")
print(f"DUP_COMP_IDENTITIES: {dup_comp_identities}")
print(f"PARITY: {parity} (Engine: {engine_total}, Grouped: {grouped_total})")
print(f"ENGINE_TIERS: {engine_tiers}")
print(f"GROUPED_TIERS: {grouped_tiers}")
print(f"WITH_WEBSITE: {with_website}")
print(f"WITHOUT_WEBSITE: {without_website}")
print(f"NAMED_CONTACTS: {named_contacts}")
print(f"DEPT_CONTACTS: {dept_contacts}")
print(f"GENERAL_CONTACTS: {general_contacts}")
print(f"CARRIER_VERIFIED: {carrier_verified}")
print(f"BROKER_VERIFIED: {broker_verified}")
print(f"FLEET_VERIFIED: {fleet_verified}")
print(f"EQ_VERIFIED: {eq_verified}")
print(f"EQ_INFERRED: {eq_inferred}")
print(f"UNKNOWN_FIELDS: {unknown_fields}")
conn.close()
