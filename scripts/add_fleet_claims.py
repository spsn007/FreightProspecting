import sqlite3

conn = sqlite3.connect("data/prospects.db")
c = conn.cursor()

c.execute("SELECT id FROM evidence_sources WHERE source_url='https://www.yoderlumber.com/about-us/'")
yoder_src = c.fetchone()[0]

c.execute("SELECT id FROM evidence_sources WHERE source_url='https://colehardwood.com/'")
cole_src = c.fetchone()[0]

c.execute("""
    INSERT INTO claims (facility_id, claim_field, claimed_value, verification_status, is_current_accepted, claim_notes) 
    VALUES (408, 'fleet_relationship_type', 'IN_HOUSE_OWNED', 'VERIFIED', 1, 'Audited fleet relationship structure: IN_HOUSE_OWNED.')
""")
y_claim = c.lastrowid
c.execute("INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship) VALUES (?, ?, 'SUPPORTS')", (y_claim, yoder_src))

c.execute("""
    INSERT INTO claims (facility_id, claim_field, claimed_value, verification_status, is_current_accepted, claim_notes) 
    VALUES (386, 'fleet_relationship_type', 'IN_HOUSE_OWNED', 'VERIFIED', 1, 'Audited fleet relationship structure: IN_HOUSE_OWNED.')
""")
col_claim = c.lastrowid
c.execute("INSERT INTO claim_evidence (claim_id, evidence_source_id, relationship) VALUES (?, ?, 'SUPPORTS')", (col_claim, cole_src))

conn.commit()
conn.close()
print("Added fleet_relationship_type claims and evidence links successfully!")
