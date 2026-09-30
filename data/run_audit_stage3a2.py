import sqlite3
from pathlib import Path

def run_audit():
    conn = sqlite3.connect("data/prospects.db")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=" * 80)
    print("AUDIT QUERY 1: FACILITY COMMODITIES FOR 1, 2, 3, 4, 18")
    print("=" * 80)
    rows = cur.execute("""
        SELECT f.id, c.operating_brand, fc.commodity_category, fc.equipment_category,
               fc.equipment_usage_status, fc.trailer_specs_notes, fc.securement_tarp_notes
        FROM facility_commodities fc
        JOIN facilities f ON fc.facility_id = f.id
        JOIN companies c ON f.company_id = c.id
        WHERE f.id IN (1, 2, 3, 4, 18)
        ORDER BY f.id
    """).fetchall()
    for r in rows:
        print(f"Facility #{r['id']} ({r['operating_brand']}):")
        print(f"  Commodity: {r['commodity_category']}")
        print(f"  Equipment Category: {r['equipment_category']}")
        print(f"  Equipment Usage Status: {r['equipment_usage_status']}")
        print(f"  Trailer Specs Notes: {r['trailer_specs_notes']}")
        print(f"  Securement Tarp Notes: {r['securement_tarp_notes']}")
        print()

    print("=" * 80)
    print("AUDIT QUERY 2: FACILITY OPERATIONAL FIELDS FOR 1, 2, 3, 4, 18")
    print("=" * 80)
    f_rows = cur.execute("""
        SELECT f.id, c.operating_brand, f.private_fleet_present,
               f.fleet_relationship_type, f.commercial_carrier_use, f.broker_friendly_status
        FROM facilities f
        JOIN companies c ON f.company_id = c.id
        WHERE f.id IN (1, 2, 3, 4, 18)
        ORDER BY f.id
    """).fetchall()
    for r in f_rows:
        print(f"Facility #{r['id']} ({r['operating_brand']}):")
        print(f"  Private Fleet Present: {r['private_fleet_present']}")
        print(f"  Fleet Relationship Type: {r['fleet_relationship_type']}")
        print(f"  Commercial Carrier Use: {r['commercial_carrier_use']}")
        print(f"  Broker Friendly Status: {r['broker_friendly_status']}")
        print()

    print("=" * 80)
    print("AUDIT QUERY 3: NON-UNKNOWN OPERATIONAL CLAIMS & EVIDENCE FOR 1, 2, 3, 4, 18")
    print("=" * 80)
    claim_rows = cur.execute("""
        SELECT f.id as fac_id, c.operating_brand, cl.id as claim_id, cl.claim_field,
               cl.claimed_value, cl.verification_status, cl.is_current_accepted,
               es.id as src_id, es.source_type, es.source_title_publisher, es.source_url, es.notes as src_notes
        FROM facilities f
        JOIN companies c ON f.company_id = c.id
        JOIN claims cl ON cl.facility_id = f.id
        LEFT JOIN claim_evidence ce ON cl.id = ce.claim_id
        LEFT JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE f.id IN (1, 2, 3, 4, 18)
          AND cl.claim_field IN ('private_fleet_present', 'fleet_relationship_type', 'commercial_carrier_use', 'broker_friendly_status')
          AND cl.is_current_accepted = 1
        ORDER BY f.id, cl.id
    """).fetchall()
    for r in claim_rows:
        print(f"Facility #{r['fac_id']} ({r['operating_brand']}) -> Claim #{r['claim_id']}:")
        print(f"  Field: {r['claim_field']} = {r['claimed_value']} [{r['verification_status']}] (accepted={r['is_current_accepted']})")
        print(f"  Evidence #{r['src_id']}: {r['source_title_publisher']} ({r['source_type']}) - URL: {r['source_url']}")
        print(f"  Evidence Notes: {r['src_notes']}")
        print()

    print("=" * 80)
    print("AUDIT QUERY 4: COMMODITY EQUIPMENT CLAIMS & EVIDENCE FOR 1, 2, 3, 4, 18")
    print("=" * 80)
    comm_claim_rows = cur.execute("""
        SELECT f.id as fac_id, c.operating_brand, cl.id as claim_id, cl.claim_field,
               cl.claimed_value, cl.verification_status, cl.is_current_accepted,
               es.id as src_id, es.source_type, es.source_title_publisher, es.source_url, es.notes as src_notes
        FROM facility_commodities fc
        JOIN facilities f ON fc.facility_id = f.id
        JOIN companies c ON f.company_id = c.id
        JOIN claims cl ON cl.facility_commodity_id = fc.id
        LEFT JOIN claim_evidence ce ON cl.id = ce.claim_id
        LEFT JOIN evidence_sources es ON ce.evidence_source_id = es.id
        WHERE f.id IN (1, 2, 3, 4, 18)
          AND cl.claim_field = 'equipment_category'
          AND cl.is_current_accepted = 1
        ORDER BY f.id, cl.id
    """).fetchall()
    for r in comm_claim_rows:
        print(f"Facility #{r['fac_id']} ({r['operating_brand']}) -> Equipment Claim #{r['claim_id']}:")
        print(f"  Field: {r['claim_field']} = {r['claimed_value']} [{r['verification_status']}] (accepted={r['is_current_accepted']})")
        print(f"  Evidence #{r['src_id']}: {r['source_title_publisher']} ({r['source_type']}) - URL: {r['source_url']}")
        print(f"  Evidence Notes: {r['src_notes']}")
        print()

    print("=" * 80)
    print("AUDIT QUERY 5: LIFECYCLE COUNTS")
    print("=" * 80)
    counts = cur.execute("SELECT stage, count(*) as cnt FROM prospect_lifecycle GROUP BY stage ORDER BY stage").fetchall()
    for row in counts:
        print(f"  Stage {row['stage']}: {row['cnt']}")
    print(f"  Total Lifecycle: {sum(r['cnt'] for r in counts)}")
    print()

    print("=" * 80)
    print("AUDIT QUERY 6: OPERATIONAL DATA COUNTS (LOADS, SIGNALS, CAPACITY, MATCHES, OUTREACH)")
    print("=" * 80)
    print(f"  Freight Demand Signals: {cur.execute('SELECT count(*) FROM freight_demand_signals').fetchone()[0]}")
    print(f"  Load Opportunities: {cur.execute('SELECT count(*) FROM load_opportunities').fetchone()[0]}")
    print(f"  Carriers: {cur.execute('SELECT count(*) FROM carriers').fetchone()[0]}")
    print(f"  Capacity Postings: {cur.execute('SELECT count(*) FROM capacity_postings').fetchone()[0]}")
    print(f"  Load Capacity Matches: {cur.execute('SELECT count(*) FROM load_capacity_matches').fetchone()[0]}")
    print(f"  Outreach Logs: {cur.execute('SELECT count(*) FROM outreach_logs').fetchone()[0]}")
    print()

    print("=" * 80)
    print("AUDIT QUERY 7: INTEGRITY & FK CHECKS")
    print("=" * 80)
    print(f"  PRAGMA foreign_key_check: {cur.execute('PRAGMA foreign_key_check;').fetchall()}")
    print(f"  PRAGMA integrity_check: {cur.execute('PRAGMA integrity_check;').fetchall()}")
    print()

    conn.close()

if __name__ == "__main__":
    run_audit()
