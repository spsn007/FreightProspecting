import tempfile
import sqlite3
from pathlib import Path
from src.backend.db.schema import init_db
from src.backend.db.seed import seed_database
from src.backend.db.import_batch1 import import_batch1
from src.backend.db.queries import evaluate_qualification_readiness

def verify_fresh_rebuild():
    tmp = Path(tempfile.gettempdir()) / "test_rebuild_complete_check.db"
    if tmp.exists():
        tmp.unlink()

    init_db(tmp)
    seed_database(tmp)
    import_batch1(tmp)

    conn = sqlite3.connect(tmp)
    conn.row_factory = sqlite3.Row

    # 1. Lifecycle counts: SHORTLISTED=4, DISCOVERY=39, QUALIFIED=0, ARCHIVED=0
    stages = dict(conn.execute("SELECT stage, count(*) FROM prospect_lifecycle GROUP BY stage").fetchall())
    assert stages == {"SHORTLISTED": 4, "DISCOVERY": 39}, f"Stages mismatch: {stages}"

    # 2. Equipment verified: exactly [1, 2, 18]
    v_rows = conn.execute(
        "SELECT facility_id FROM facility_commodities WHERE equipment_usage_status = 'VERIFIED' ORDER BY facility_id"
    ).fetchall()
    assert [r[0] for r in v_rows] == [1, 2, 18], f"Verified equipment mismatch: {[r[0] for r in v_rows]}"

    # 3. Equipment inferred: exactly 40
    inf_count = conn.execute(
        "SELECT count(*) FROM facility_commodities WHERE equipment_usage_status = 'INFERRED'"
    ).fetchone()[0]
    assert inf_count == 40, f"Inferred count mismatch: {inf_count}"

    # 4. Kenwal & Beasley commercial_carrier_use: UNKNOWN
    for fid in [1, 2, 3, 4]:
        row = conn.execute("SELECT commercial_carrier_use FROM facilities WHERE id = ?", (fid,)).fetchone()
        assert row["commercial_carrier_use"] == "UNKNOWN", f"Facility {fid} commercial_carrier_use != UNKNOWN"

    # 5. Zero spurious claims for commercial_carrier_use on seeds
    spurious = conn.execute(
        "SELECT count(*) FROM claims WHERE facility_id IN (1, 2, 3, 4) AND claim_field = 'commercial_carrier_use'"
    ).fetchone()[0]
    assert spurious == 0, f"Spurious claims found: {spurious}"

    # 6. Trailer specs & tarps on seeds: NULL
    for fid in [1, 2, 3, 4]:
        row = conn.execute(
            "SELECT trailer_specs_notes, securement_tarp_notes FROM facility_commodities WHERE facility_id = ?", (fid,)
        ).fetchone()
        assert row["trailer_specs_notes"] is None, f"Facility {fid} trailer_specs_notes != NULL"
        assert row["securement_tarp_notes"] is None, f"Facility {fid} securement_tarp_notes != NULL"

    # CSP trailer specs & tarps
    csp = conn.execute(
        "SELECT trailer_specs_notes, securement_tarp_notes FROM facility_commodities WHERE facility_id = 18"
    ).fetchone()
    assert "overhead crane" in csp["trailer_specs_notes"].lower()
    assert csp["securement_tarp_notes"] is None

    # 7. Total non-null specs & tarps across entire DB
    assert conn.execute("SELECT count(*) FROM facility_commodities WHERE trailer_specs_notes IS NOT NULL").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM facility_commodities WHERE securement_tarp_notes IS NOT NULL").fetchone()[0] == 0

    # 8. Stage 3A.3 Address Reconciliations
    # Beasley
    b_fac = conn.execute("SELECT physical_address, city, state_prov, postal_code FROM facilities WHERE id = 1").fetchone()
    assert b_fac["physical_address"] == "770 Uvalda Hwy"
    assert b_fac["city"] == "Hazlehurst"
    assert b_fac["state_prov"] == "GA"
    assert b_fac["postal_code"] == "31539"
    b_claim = conn.execute("SELECT claimed_value, verification_status, is_current_accepted FROM claims WHERE facility_id = 1 AND claim_field = 'physical_address'").fetchone()
    assert b_claim is not None
    assert b_claim["claimed_value"] == "770 Uvalda Hwy, Hazlehurst, GA 31539, US"
    assert b_claim["verification_status"] == "VERIFIED"
    assert b_claim["is_current_accepted"] == 1

    # CSP
    csp_fac = conn.execute("SELECT physical_address, city, state_prov, postal_code FROM facilities WHERE id = 18").fetchone()
    assert csp_fac["physical_address"] == "1604 Prosperity Road"
    assert csp_fac["city"] == "Toledo"
    assert csp_fac["state_prov"] == "OH"
    assert csp_fac["postal_code"] == "43612"
    csp_claim = conn.execute("SELECT claimed_value, verification_status, is_current_accepted FROM claims WHERE facility_id = 18 AND claim_field = 'physical_address'").fetchone()
    assert csp_claim is not None
    assert csp_claim["claimed_value"] == "1604 Prosperity Road, Toledo, OH 43612, US"
    assert csp_claim["verification_status"] == "VERIFIED"
    assert csp_claim["is_current_accepted"] == 1

    # Total claims in fresh rebuild
    assert conn.execute("SELECT count(*) FROM claims").fetchone()[0] == 241

    # 9. Readiness on all 43
    for fid in range(1, 44):
        res = evaluate_qualification_readiness(fid, conn)
        assert len(res["checks"]) == 5

    # 10. FK & Integrity
    assert len(conn.execute("PRAGMA foreign_key_check;").fetchall()) == 0
    assert conn.execute("PRAGMA integrity_check;").fetchone()[0] == "ok"

    conn.close()
    tmp.unlink()
    print("FRESH REBUILD REPRODUCIBILITY: 100% VERIFIED!")

if __name__ == "__main__":
    verify_fresh_rebuild()
