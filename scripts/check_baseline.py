import sys
from pathlib import Path
import hashlib

sys.path.insert(0, str(Path(".").resolve()))
from src.backend.db.queries import get_summary_counts, create_connection

db_path = Path("data/prospects.db")
h = hashlib.sha256(db_path.read_bytes()).hexdigest().upper()
print(f"DB Path: {db_path}")
print(f"DB Size: {db_path.stat().st_size} bytes")
print(f"DB SHA-256: {h}")

counts = get_summary_counts(db_path)
for k, v in sorted(counts.items()):
    print(f"  {k}: {v}")

conn = create_connection(db_path)
cur = conn.cursor()

# Operational counts
ops = {t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ['outreach_logs', 'load_opportunities', 'capacity_postings', 'freight_demand_signals', 'load_capacity_matches']}
print(f"\nOperational counts: {ops}")

# Check verified equipment
verified_eq = cur.execute("""
    SELECT fc.facility_id, f.facility_name, fc.commodity_category, fc.equipment_category, fc.equipment_usage_status
    FROM facility_commodities fc
    JOIN facilities f ON fc.facility_id = f.id
    WHERE fc.equipment_usage_status = 'VERIFIED'
""").fetchall()
print(f"\nVerified facility equipment ({len(verified_eq)}): {verified_eq}")
conn.close()
