import sqlite3
import json

con = sqlite3.connect("data/prospects.db")
con.row_factory = sqlite3.Row
cur = con.cursor()

items = cur.execute("SELECT type, name, sql FROM sqlite_master WHERE tbl_name='claim_evidence'").fetchall()
for t in items:
    print(f"=== {t['type']} {t['name']} ===")
    print(t["sql"])
    print()

con.close()
