"""
Fix foreign key reference in evidence_sources table from outreach_logs_old to outreach_logs.
"""

import sqlite3

def fix_fk():
    con = sqlite3.connect("data/prospects.db")
    con.execute("PRAGMA foreign_keys = OFF;")
    
    con.execute("BEGIN TRANSACTION;")
    
    con.execute("""
    CREATE TABLE evidence_sources_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_type TEXT NOT NULL CHECK(source_type IN ('COMPANY_WEBSITE', 'GOVERNMENT_REGISTRY', 'JOB_POSTING', 'INDUSTRY_DIRECTORY', 'PHONE_OUTREACH', 'EMAIL_CORRESPONDENCE')),
        source_title_publisher TEXT NOT NULL,
        source_url TEXT,
        is_primary_source BOOLEAN,
        source_published_at DATETIME,
        event_at DATETIME,
        observed_at DATETIME NOT NULL,
        outreach_log_id INTEGER REFERENCES outreach_logs(id) ON DELETE SET NULL,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    con.execute("INSERT INTO evidence_sources_new SELECT * FROM evidence_sources;")
    con.execute("DROP TABLE evidence_sources;")
    con.execute("ALTER TABLE evidence_sources_new RENAME TO evidence_sources;")
    
    con.commit()
    
    con.execute("PRAGMA foreign_keys = ON;")
    fk_errs = list(con.execute("PRAGMA foreign_key_check;"))
    assert len(fk_errs) == 0, f"FK errors: {fk_errs}"
    integ = con.execute("PRAGMA integrity_check;").fetchone()[0]
    assert integ == "ok", f"Integrity error: {integ}"
    print("Fixed evidence_sources FK successfully! Foreign key check and integrity check both OK.")
    con.close()

if __name__ == "__main__":
    fix_fk()
