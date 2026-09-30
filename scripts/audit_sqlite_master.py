import sqlite3

conn = sqlite3.connect("data/prospects.db")
c = conn.cursor()

c.execute("SELECT type, name, sql FROM sqlite_master WHERE sql LIKE '%_old%' OR name LIKE '%_old%' OR name LIKE '%_new%'")
rows = c.fetchall()
print(f"Stale table/SQL rows found: {len(rows)}")
for r in rows:
    print(r)

c.execute("SELECT name, sql FROM sqlite_master WHERE name='evidence_sources'")
print("evidence_sources definition:")
print(c.fetchone()[1])

# Run FK check
c.execute("PRAGMA foreign_key_check")
fk_errors = c.fetchall()
print("FK errors:", len(fk_errors))

# Run integrity check
c.execute("PRAGMA integrity_check")
print("Integrity check:", c.fetchone()[0])

conn.close()
