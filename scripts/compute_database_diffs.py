import sqlite3
from pathlib import Path

cur_db = Path("data/prospects.db")
pre_closure_db = Path("data/backups/prospects_backup_pre_batch3_final_closure_20260929_083324.db")
baseline_db = Path("data/backups/prospects_backup_pre_batch3_wave_A_20260928_212245.db")

conn_cur = sqlite3.connect(cur_db)
conn_cur.row_factory = sqlite3.Row
conn_pre = sqlite3.connect(pre_closure_db)
conn_pre.row_factory = sqlite3.Row
conn_base = sqlite3.connect(baseline_db)
conn_base.row_factory = sqlite3.Row

tables = [r[0] for r in conn_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]

print("=== 1. DIFF vs PRE-CLOSURE CANDIDATE (321200AB...) ===")
for t in sorted(tables):
    c_cnt = conn_cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    p_cnt = conn_pre.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    if c_cnt != p_cnt:
        print(f"Table {t}: pre={p_cnt} -> cur={c_cnt} (delta={c_cnt - p_cnt})")

claims_cur = {r["id"]: dict(r) for r in conn_cur.execute("SELECT * FROM claims").fetchall()}
claims_pre = {r["id"]: dict(r) for r in conn_pre.execute("SELECT * FROM claims").fetchall()}
added_claims = sorted(set(claims_cur.keys()) - set(claims_pre.keys()))
print(f"\nAdded claims count: {len(added_claims)}")
for cid in added_claims:
    c = claims_cur[cid]
    print(f"  Claim {cid}: field={c['claim_field']}, value={c['claimed_value']}, status={c['verification_status']}, accepted={c['is_current_accepted']}, fac_id={c['facility_id']}")

modified_claims = sorted([cid for cid in claims_pre if cid in claims_cur and claims_pre[cid] != claims_cur[cid]])
print(f"\nModified claims (superseded) count: {len(modified_claims)}")
for cid in modified_claims:
    pre = claims_pre[cid]
    cur = claims_cur[cid]
    diff_keys = [k for k in cur if cur[k] != pre[k]]
    print(f"  Claim {cid} ({cur['claim_field']}): {[(k, pre[k], '->', cur[k]) for k in diff_keys]}")

cts_cur = {r["id"]: dict(r) for r in conn_cur.execute("SELECT * FROM contacts").fetchall()}
cts_pre = {r["id"]: dict(r) for r in conn_pre.execute("SELECT * FROM contacts").fetchall()}
mod_cts = sorted([cid for cid in cts_pre if cts_pre[cid] != cts_cur[cid]])
print(f"\nModified contacts count: {len(mod_cts)}")
for cid in mod_cts:
    pre = cts_pre[cid]
    cur = cts_cur[cid]
    diff_keys = [k for k in cur if cur[k] != pre[k]]
    print(f"  Contact {cid} ({cur['person_name']}): {[(k, pre[k], '->', cur[k]) for k in diff_keys]}")

# Facilities diffs
fac_cur = {r["id"]: dict(r) for r in conn_cur.execute("SELECT * FROM facilities").fetchall()}
fac_pre = {r["id"]: dict(r) for r in conn_pre.execute("SELECT * FROM facilities").fetchall()}
mod_facs = sorted([fid for fid in fac_pre if fac_pre[fid] != fac_cur[fid]])
print(f"\nModified facilities count vs pre-closure candidate: {len(mod_facs)}")
for fid in mod_facs:
    pre = fac_pre[fid]
    cur = fac_cur[fid]
    diff_keys = [k for k in cur if cur[k] != pre[k]]
    print(f"  Facility {fid} ({cur['facility_name']}): {[(k, pre[k], '->', cur[k]) for k in diff_keys]}")

print("\n=== 2. DIFF vs FROZEN BATCH 2 BASELINE (05BAE4B9...) ===")
for t in sorted(tables):
    c_cnt = conn_cur.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    b_cnt = conn_base.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    if c_cnt != b_cnt:
        print(f"Table {t}: base={b_cnt} -> cur={c_cnt} (delta={c_cnt - b_cnt})")

fac_base = {r["id"]: dict(r) for r in conn_base.execute("SELECT * FROM facilities").fetchall()}
mod_facs_base = sorted([fid for fid in fac_base if fac_base[fid] != fac_cur[fid]])
print(f"\nModified facilities count vs Batch 2 baseline: {len(mod_facs_base)}")
for fid in mod_facs_base:
    pre = fac_base[fid]
    cur = fac_cur[fid]
    diff_keys = [k for k in cur if cur[k] != pre[k]]
    print(f"  Facility {fid} ({cur['facility_name']}): {[(k, pre[k], '->', cur[k]) for k in diff_keys]}")
