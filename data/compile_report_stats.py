import sqlite3
import json

conn = sqlite3.connect('data/prospects.db')
conn.row_factory = sqlite3.Row

# Lifecycle counts
lifecycle = dict(conn.execute('SELECT stage, count(*) FROM prospect_lifecycle GROUP BY stage').fetchall())
total_facs = conn.execute('SELECT count(*) FROM facilities').fetchone()[0]

# Countries
countries = dict(conn.execute('SELECT country, count(*) FROM facilities GROUP BY country').fetchall())

# Equipment
eq_usage = dict(conn.execute('SELECT equipment_usage_status, count(*) FROM facility_commodities GROUP BY equipment_usage_status').fetchall())
eq_cats = dict(conn.execute('SELECT equipment_category, count(*) FROM facility_commodities GROUP BY equipment_category').fetchall())

# Contacts
total_contacts = conn.execute('SELECT count(*) FROM contacts').fetchone()[0]
with_phone = conn.execute('SELECT count(*) FROM contacts WHERE phone_number IS NOT NULL').fetchone()[0]
with_email = conn.execute('SELECT count(*) FROM contacts WHERE email_address IS NOT NULL').fetchone()[0]
with_both = conn.execute('SELECT count(*) FROM contacts WHERE phone_number IS NOT NULL AND email_address IS NOT NULL').fetchone()[0]
named_persons = conn.execute("SELECT count(*) FROM contacts WHERE contact_identity = 'NAMED_PERSON'").fetchone()[0]
freight_logistics = conn.execute("SELECT count(*) FROM contacts WHERE role_category = 'FREIGHT_LOGISTICS'").fetchone()[0]
fl_sample = [r['operating_brand'] for r in conn.execute("SELECT DISTINCT c.operating_brand FROM contacts ct JOIN facilities f ON ct.facility_id = f.id JOIN companies c ON f.company_id = c.id WHERE ct.role_category = 'FREIGHT_LOGISTICS' LIMIT 20").fetchall()]

# Sources
sources = dict(conn.execute('SELECT source_type, count(*) FROM evidence_sources GROUP BY source_type').fetchall())

# Audit
audit = dict(conn.execute('SELECT intake_status, count(*) FROM discovery_intake_audit GROUP BY intake_status').fetchall())

# Operational zeros
zeros = {
    'loads': conn.execute('SELECT count(*) FROM load_opportunities').fetchone()[0],
    'signals': conn.execute('SELECT count(*) FROM freight_demand_signals').fetchone()[0],
    'capacity': conn.execute('SELECT count(*) FROM capacity_postings').fetchone()[0],
    'matches': conn.execute('SELECT count(*) FROM load_capacity_matches').fetchone()[0],
    'outreach_logs': conn.execute('SELECT count(*) FROM outreach_logs').fetchone()[0]
}

report_data = {
    'total_facilities': total_facs,
    'lifecycle': lifecycle,
    'countries': countries,
    'equipment_usage': eq_usage,
    'equipment_categories': eq_cats,
    'contacts': {
        'total': total_contacts,
        'with_phone': with_phone,
        'with_email': with_email,
        'with_both': with_both,
        'named_persons': named_persons,
        'freight_logistics_role': freight_logistics,
        'freight_logistics_sample': fl_sample
    },
    'sources': sources,
    'audit': audit,
    'operational_zeros': zeros
}

print(json.dumps(report_data, indent=2))
conn.close()
