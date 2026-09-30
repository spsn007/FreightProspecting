import sqlite3, hashlib
from pathlib import Path

db_path = Path("data/prospects.db")
conn = sqlite3.connect(db_path)

# 1. Revert facility 3 (DECAST) fleet claims to preserve Stage 2/3A seed baseline
conn.execute("UPDATE facilities SET private_fleet_present = 'UNKNOWN', fleet_relationship_type = 'UNKNOWN' WHERE id = 3")
conn.execute("UPDATE claims SET is_current_accepted = 0 WHERE id IN (2736, 2737)")
conn.execute("UPDATE claims SET is_current_accepted = 1 WHERE id = 11")

# 2. Revert facility 65 (Bristol Sawmill) private_fleet_present to UNKNOWN per 'affiliated carrier != private fleet' invariant
conn.execute("UPDATE facilities SET private_fleet_present = 'UNKNOWN' WHERE id = 65")
conn.execute("UPDATE claims SET is_current_accepted = 0 WHERE id = 2738")
conn.execute("UPDATE claims SET is_current_accepted = 1 WHERE id = 334")

conn.commit()
conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
conn.close()

with open(db_path, "rb") as f:
    h = hashlib.sha256(f.read()).hexdigest().upper()
print("New Candidate Hash:", h)
