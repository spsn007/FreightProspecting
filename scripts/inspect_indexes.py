import sqlite3

conn = sqlite3.connect("data/prospects.db")
cur = conn.cursor()
indexes = cur.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE type='index' ORDER BY tbl_name, name").fetchall()
print(f"Total indexes: {len(indexes)}")
for idx in indexes:
    print(f"{idx[2]:<30} | {idx[1]:<35} | {idx[3] or 'AUTO'}")
conn.close()
