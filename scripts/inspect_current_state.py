import sqlite3
import sys
sys.path.insert(0, ".")

def inspect():
    conn = sqlite3.connect('data/prospects.db')
    cur = conn.cursor()

    total_companies = cur.execute('SELECT count(*) FROM companies').fetchone()[0]
    holding_parents = cur.execute('SELECT count(*) FROM companies WHERE id NOT IN (SELECT DISTINCT company_id FROM facilities)').fetchone()[0]
    operating_companies = cur.execute('SELECT count(DISTINCT company_id) FROM facilities').fetchone()[0]
    facility_stages = cur.execute('SELECT stage, count(*) FROM prospect_lifecycle GROUP BY stage').fetchall()

    company_stages = cur.execute('''
        SELECT stage, count(DISTINCT f.company_id)
        FROM prospect_lifecycle pl
        JOIN facilities f ON pl.facility_id = f.id
        GROUP BY stage
    ''').fetchall()

    total_facilities = cur.execute('SELECT count(*) FROM facilities').fetchone()[0]
    outreach_logs = cur.execute('SELECT count(*) FROM outreach_logs').fetchone()[0]
    
    tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    supp_count = cur.execute('SELECT count(*) FROM customer_suppressions').fetchone()[0] if 'customer_suppressions' in tables else 0

    print("=== LIVE CURRENT DATABASE STATUS ===")
    print(f"Total companies in 'companies' table: {total_companies}")
    print(f"Active operating company groups (with facilities): {operating_companies}")
    print(f"Holding parent companies (without facilities): {holding_parents}")
    print(f"Total physical facilities: {total_facilities}")
    print(f"Facility stages: {facility_stages}")
    print(f"Company stages (DISTINCT company_id): {company_stages}")
    print(f"Outreach logs: {outreach_logs}")
    print(f"Customer suppressions: {supp_count}")

    # Check query layer summary
    from src.backend.db.queries import get_summary_counts
    counts = get_summary_counts()
    print("\n=== QUERY LAYER get_summary_counts() ===")
    for k, v in counts.items():
        print(f"  {k}: {v}")

if __name__ == '__main__':
    inspect()
