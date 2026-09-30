import sys, os
sys.path.insert(0, os.path.abspath('.'))
import sqlite3
from collections import Counter
from src.backend.db.connection import get_db_path
from src.backend.db.queries import get_company_grouped_prospects, get_summary_counts

DB_PATH = get_db_path()

# Simulate the corrections in memory on a copy of data
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# 1. Check Yoder Lumber and Cole Hardwood
print("Simulating contact and fleet adjustments...")

# 2. Check how many contacts will become COMMERCIAL_SALES vs GENERAL_FACILITY vs FREIGHT_LOGISTICS
c = conn.cursor()
c.execute("SELECT id, email_address FROM contacts WHERE id >= 383")
st3e_contacts = c.fetchall()

sales_cnt = 0
gen_cnt = 0
freight_cnt = 0

for cid, email in st3e_contacts:
    em = (email or "").lower()
    if cid == 418: # Yoder
        freight_cnt += 1
    elif cid == 400: # Somerset shipping@
        freight_cnt += 1
    elif any(em.startswith(p) for p in ["sales@", "ventes@", "sales.", "salespa@", "salesfs@", "torontosales@"]):
        sales_cnt += 1
    else:
        gen_cnt += 1

print(f"Stage 3E contacts classification:")
print(f"  FREIGHT_LOGISTICS: {freight_cnt} (Wayne Yoder + Somerset shipping@)")
print(f"  COMMERCIAL_SALES: {sales_cnt}")
print(f"  GENERAL_FACILITY: {gen_cnt}")
print(f"  Total: {freight_cnt + sales_cnt + gen_cnt}")

conn.close()
