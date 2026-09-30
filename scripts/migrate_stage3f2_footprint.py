"""
Stage 3F.2 Migration: Add company footprint columns to companies table.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("data/prospects.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check existing columns
    c.execute("PRAGMA table_info(companies)")
    cols = [r[1] for r in c.fetchall()]
    
    if "company_footprint_status" not in cols:
        print("Adding company_footprint_status...")
        c.execute("ALTER TABLE companies ADD COLUMN company_footprint_status TEXT DEFAULT 'UNKNOWN'")
        
    if "verified_operating_location_count" not in cols:
        print("Adding verified_operating_location_count...")
        c.execute("ALTER TABLE companies ADD COLUMN verified_operating_location_count INTEGER DEFAULT NULL")
        
    if "footprint_source_notes" not in cols:
        print("Adding footprint_source_notes...")
        c.execute("ALTER TABLE companies ADD COLUMN footprint_source_notes TEXT DEFAULT NULL")

    conn.commit()
    
    # Verify columns
    c.execute("PRAGMA table_info(companies)")
    print("Companies columns:", [r[1] for r in c.fetchall()])
    conn.close()

if __name__ == "__main__":
    migrate()
