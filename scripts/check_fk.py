import sqlite3
con = sqlite3.connect('data/prospects.db')
cur = con.cursor()
tables = cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
for name, sql in tables:
    if sql and 'outreach_logs' in sql and name != 'outreach_logs':
        print(f'{name} references outreach_logs')
con.close()
