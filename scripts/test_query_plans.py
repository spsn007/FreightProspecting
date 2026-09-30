import sqlite3

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()

cur.execute("CREATE INDEX IF NOT EXISTS idx_claims_facility_id ON claims(facility_id);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_claims_company_id ON claims(company_id);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_claim_evidence_claim_id ON claim_evidence(claim_id);")
cur.execute("CREATE INDEX IF NOT EXISTS idx_claim_evidence_source_id ON claim_evidence(evidence_source_id);")
conn.commit()

def explain(name, sql, params=()):
    print(f"\n--- {name} ---")
    print(f"SQL: {sql.strip()}")
    plans = cur.execute(f"EXPLAIN QUERY PLAN {sql}", params).fetchall()
    for p in plans:
        print(f"  id={p[0]}, parent={p[1]}, detail={p[3]}")

# 1. Claims lookup by facility_id / company_id
explain(
    "Claims count by facility or company",
    "SELECT count(*) FROM claims WHERE facility_id = ? OR company_id = ?",
    (18, 14)
)

# 2. Join claims and claim_evidence
explain(
    "Claims join claim_evidence on facility_id",
    """
    SELECT c.id FROM claims c
    JOIN claim_evidence ce ON c.id = ce.claim_id
    WHERE c.facility_id = ? AND c.claim_field = 'physical_address'
    """,
    (18,)
)

# 3. Join facility_commodity_mappings
explain(
    "Facility commodity mappings by facility_id",
    """
    SELECT m.is_primary, c.category_code
    FROM facility_commodity_mappings m
    JOIN commodity_categories c ON m.category_id = c.id
    WHERE m.facility_id = ?
    """,
    (18,)
)

conn.close()
