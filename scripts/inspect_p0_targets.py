import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3
from src.backend.db.queries import evaluate_qualification_readiness

conn = sqlite3.connect("data/prospects.db")
conn.row_factory = sqlite3.Row

for cid, fid in [(40, 39), (540, 627), (331, 418), (395, 482)]:
    res = evaluate_qualification_readiness(fid, conn=conn)
    print(f"CID {cid} FID {fid}: is_ready={res['is_ready']} failed_checks={res.get('failed_checks')} missing_evidence={res.get('missing_evidence')}")
    comms = conn.execute("SELECT * FROM facility_commodities WHERE facility_id = ?", (fid,)).fetchall()
    print("  comms:", [dict(c) for c in comms])
    cts = conn.execute("SELECT * FROM contacts WHERE facility_id = ? OR company_id = ?", (fid, cid)).fetchall()
    print("  contacts:", [dict(c) for c in cts])
