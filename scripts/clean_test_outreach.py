"""
Reset any test outreach logs from earlier browser testing so production DB is 100% clean with 0 fake calls.
"""

import sqlite3

def clean():
    con = sqlite3.connect("data/prospects.db")
    con.execute("DELETE FROM outreach_logs;")
    con.execute("""
        UPDATE prospect_engagement_state 
        SET current_outreach_status = 'UNCONTACTED',
            attempt_count = 0,
            last_contacted_at = NULL,
            next_follow_up_at = NULL,
            last_facility_id = NULL,
            last_feedback_notes = NULL,
            status_source_outreach_log_id = NULL,
            is_viewed = 0,
            first_viewed_at = NULL,
            last_viewed_at = NULL;
    """)
    con.commit()
    print("Outreach logs remaining:", con.execute("SELECT count(*) FROM outreach_logs").fetchone()[0])
    print("All companies in UNCONTACTED:", con.execute("SELECT count(*) FROM prospect_engagement_state WHERE current_outreach_status != 'UNCONTACTED'").fetchone()[0])
    con.close()

if __name__ == "__main__":
    clean()
