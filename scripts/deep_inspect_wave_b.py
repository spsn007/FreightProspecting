import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backend.db.queries import evaluate_qualification_readiness

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

comp = conn.execute("SELECT * FROM companies WHERE id = 187").fetchone()
print("Company 187:", dict(comp))

facs = conn.execute("SELECT * FROM facilities WHERE company_id = 187").fetchall()
print(f"Facilities count: {len(facs)}")
for f in facs:
    print("  Facility:", dict(f))
    q = evaluate_qualification_readiness(f['id'], conn=conn)
    print(f"  Qualification: is_ready={q['is_ready']} checks={q['checks']}")
