import sqlite3

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

for fid in [1, 2, 3, 4, 18]:
    claims = cur.execute("""
        SELECT c.id, c.claim_field, c.claimed_value, c.verification_status, ce.evidence_source_id, s.source_title_publisher, s.source_url
        FROM claims c
        LEFT JOIN claim_evidence ce ON c.id = ce.claim_id
        LEFT JOIN evidence_sources s ON ce.evidence_source_id = s.id
        WHERE c.facility_id = ? AND c.claim_field = 'physical_address'
    """, (fid,)).fetchall()
    print(f"Facility {fid} physical_address claims:")
    for cl in claims:
        print(f"  Claim {cl['id']}: '{cl['claimed_value']}' | status={cl['verification_status']} | src={cl['evidence_source_id']} ({cl['source_title_publisher']} - {cl['source_url']})")
conn.close()
