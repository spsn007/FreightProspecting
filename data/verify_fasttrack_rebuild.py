import tempfile
import sqlite3
from pathlib import Path
from src.backend.db.schema import init_db
from src.backend.db.seed import seed_database
from src.backend.db.import_batch1 import import_batch1
from src.backend.db.import_fasttrack import import_fasttrack_candidates

def verify_fasttrack_full_rebuild():
    tmp = Path(tempfile.gettempdir()) / "test_rebuild_fasttrack_full.db"
    if tmp.exists():
        tmp.unlink()

    print("1. Initializing clean schema...")
    init_db(tmp)

    print("2. Seeding 4 shortlisted seed families...")
    seed_database(tmp)

    print("3. Importing Batch 1 discovery facilities...")
    import_batch1(tmp)

    print("4. Importing Fast-Track Discovery Pool expansion...")
    stats = import_fasttrack_candidates(db_path=tmp, max_discovery_target=185, hard_stop_max=200)

    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row

    # Assertions
    stages = dict(conn.execute("SELECT stage, count(*) FROM prospect_lifecycle GROUP BY stage").fetchall())
    assert stages == {"SHORTLISTED": 4, "DISCOVERY": 185}, f"Stages mismatch: {stages}"

    total_facs = conn.execute("SELECT count(*) FROM facilities").fetchone()[0]
    assert total_facs == 189, f"Total facilities mismatch: {total_facs}"

    # Verified equipment
    v_rows = conn.execute("SELECT facility_id FROM facility_commodities WHERE equipment_usage_status = 'VERIFIED' ORDER BY facility_id").fetchall()
    assert [r[0] for r in v_rows] == [1, 2, 18]

    # FK & Integrity
    assert len(conn.execute("PRAGMA foreign_key_check").fetchall()) == 0
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    # Operational zero
    assert conn.execute("SELECT count(*) FROM load_opportunities").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM freight_demand_signals").fetchone()[0] == 0

    conn.close()
    tmp.unlink()
    print("FAST-TRACK FULL REBUILD REPRODUCIBILITY: 100% VERIFIED!")

if __name__ == "__main__":
    verify_fasttrack_full_rebuild()
