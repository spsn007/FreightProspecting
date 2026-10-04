"""
Carrier & Capacity Network Schema Migration
Shipper IQ V1 — Additive Carrier Network Domain Extension
"""

import sqlite3
from typing import Optional
from pathlib import Path


CARRIER_DDL = """
-- Dedicated Carrier Assignments (Team Workflow)
CREATE TABLE IF NOT EXISTS carrier_assignments (
    carrier_id INTEGER PRIMARY KEY REFERENCES carriers(id) ON DELETE CASCADE,
    owner_id INTEGER NOT NULL REFERENCES team_users(id),
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_carrier_assignments_owner ON carrier_assignments(owner_id);

-- Dedicated Carrier Assignment History
CREATE TABLE IF NOT EXISTS carrier_assignment_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier_id INTEGER NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
    actor_id INTEGER NOT NULL REFERENCES team_users(id),
    from_user_id INTEGER REFERENCES team_users(id),
    to_user_id INTEGER REFERENCES team_users(id),
    action TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_carrier_assignment_history_carrier ON carrier_assignment_history(carrier_id, id);

-- Carrier Relationship & Engagement State
CREATE TABLE IF NOT EXISTS carrier_engagement_state (
    carrier_id INTEGER PRIMARY KEY REFERENCES carriers(id) ON DELETE CASCADE,
    current_relationship_status TEXT NOT NULL DEFAULT 'UNCONTACTED' CHECK(current_relationship_status IN (
        'UNCONTACTED', 'INTERESTED', 'CALL_BACK', 'NO_ANSWER', 'NOT_INTERESTED'
    )),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_contacted_at TEXT,
    next_callback_at TEXT,
    last_call_disposition TEXT,
    last_call_notes TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Dedicated Append-Only Carrier Outreach History
CREATE TABLE IF NOT EXISTS carrier_outreach_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier_id INTEGER NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
    author_user_id INTEGER REFERENCES team_users(id),
    contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    load_capacity_match_id INTEGER REFERENCES load_capacity_matches(id) ON DELETE SET NULL,
    load_opportunity_id INTEGER REFERENCES load_opportunities(id) ON DELETE SET NULL,
    capacity_posting_id INTEGER REFERENCES capacity_postings(id) ON DELETE SET NULL,
    facility_location TEXT,
    disposition TEXT NOT NULL CHECK(disposition IN (
        'INTERESTED', 'CALL_BACK', 'NO_ANSWER', 'NOT_INTERESTED',
        'LEFT_VOICEMAIL', 'WRONG_CONTACT', 'CONNECTED_DISPATCH', 'CONNECTED_OWNER'
    )),
    call_timestamp TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    callback_date TEXT,
    callback_time TEXT,
    quoted_rate NUMERIC,
    quoted_rate_currency TEXT DEFAULT 'USD' CHECK(quoted_rate_currency IS NULL OR quoted_rate_currency IN ('USD', 'CAD')),
    quoted_rate_basis TEXT DEFAULT 'FLAT',
    notes TEXT,
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_carrier_outreach_carrier ON carrier_outreach_logs(carrier_id, id);

-- Carrier Quote History (Preserves all quotes without overwriting truth)
CREATE TABLE IF NOT EXISTS carrier_quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carrier_id INTEGER NOT NULL REFERENCES carriers(id) ON DELETE CASCADE,
    load_opportunity_id INTEGER NOT NULL REFERENCES load_opportunities(id) ON DELETE CASCADE,
    capacity_posting_id INTEGER REFERENCES capacity_postings(id) ON DELETE SET NULL,
    load_capacity_match_id INTEGER REFERENCES load_capacity_matches(id) ON DELETE SET NULL,
    author_user_id INTEGER NOT NULL REFERENCES team_users(id),
    quoted_amount NUMERIC NOT NULL,
    rate_basis TEXT NOT NULL DEFAULT 'FLAT' CHECK(rate_basis IN ('FLAT', 'PER_MILE')),
    currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency IN ('USD', 'CAD')),
    quote_status TEXT NOT NULL DEFAULT 'OFFERED' CHECK(quote_status IN ('OFFERED', 'ACCEPTED', 'REJECTED', 'SUPERSEDED')),
    notes TEXT,
    quoted_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_carrier_quotes_carrier ON carrier_quotes(carrier_id);
CREATE INDEX IF NOT EXISTS idx_carrier_quotes_load ON carrier_quotes(load_opportunity_id);

-- Distinct Carrier Suppression (CARRIER, CONTACT, LANE)
CREATE TABLE IF NOT EXISTS carrier_suppressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_type TEXT NOT NULL CHECK(scope_type IN ('CARRIER', 'CONTACT', 'LANE')),
    carrier_id INTEGER REFERENCES carriers(id) ON DELETE CASCADE,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    origin_country TEXT CHECK(origin_country IS NULL OR origin_country IN ('US', 'CA')),
    origin_state_prov TEXT,
    dest_country TEXT CHECK(dest_country IS NULL OR dest_country IN ('US', 'CA')),
    dest_state_prov TEXT,
    suppression_status TEXT NOT NULL CHECK(suppression_status IN ('DO_NOT_CONTACT', 'DO_NOT_USE', 'RESTRICTED_LANE')),
    reason_notes TEXT NOT NULL,
    assigned_by TEXT NOT NULL DEFAULT 'USER',
    effective_date TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (
        (scope_type = 'CARRIER' AND carrier_id IS NOT NULL AND contact_id IS NULL) OR
        (scope_type = 'CONTACT' AND contact_id IS NOT NULL) OR
        (scope_type = 'LANE' AND origin_state_prov IS NOT NULL AND dest_state_prov IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_carrier_suppressions_carrier ON carrier_suppressions(carrier_id);
CREATE INDEX IF NOT EXISTS idx_carrier_suppressions_contact ON carrier_suppressions(contact_id);
"""

CARRIER_TRIGGERS = """
-- Append-only enforcement on carrier_outreach_logs
CREATE TRIGGER IF NOT EXISTS trg_carrier_outreach_logs_no_update
BEFORE UPDATE ON carrier_outreach_logs
BEGIN
    SELECT RAISE(ABORT, 'carrier_outreach_logs is append-only: UPDATE operations are strictly prohibited.');
END;

CREATE TRIGGER IF NOT EXISTS trg_carrier_outreach_logs_no_delete
BEFORE DELETE ON carrier_outreach_logs
BEGIN
    SELECT RAISE(ABORT, 'carrier_outreach_logs is append-only: DELETE operations are strictly prohibited.');
END;

CREATE TRIGGER IF NOT EXISTS trg_carrier_outreach_logs_no_replace
BEFORE INSERT ON carrier_outreach_logs
FOR EACH ROW
WHEN NEW.id IS NOT NULL AND EXISTS (SELECT 1 FROM carrier_outreach_logs WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'carrier_outreach_logs is append-only: replacing or reusing existing id is strictly forbidden');
END;
"""

# Additional indexes for high performance filtering and matching
PERFORMANCE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_carriers_usdot ON carriers(usdot_number);
CREATE INDEX IF NOT EXISTS idx_carriers_mc ON carriers(mc_number);
CREATE INDEX IF NOT EXISTS idx_carriers_country_state ON carriers(country, physical_state_prov);
CREATE INDEX IF NOT EXISTS idx_carriers_operating_status ON carriers(operating_status);
CREATE INDEX IF NOT EXISTS idx_capacity_carrier_status ON capacity_postings(carrier_id, capacity_status);
CREATE INDEX IF NOT EXISTS idx_capacity_dates ON capacity_postings(available_date_start, available_date_end);
CREATE INDEX IF NOT EXISTS idx_capacity_equip ON capacity_postings(equipment_type);
CREATE INDEX IF NOT EXISTS idx_capacity_location ON capacity_postings(available_country, available_state_prov, available_city);
CREATE INDEX IF NOT EXISTS idx_load_opps_status ON load_opportunities(load_status);
CREATE INDEX IF NOT EXISTS idx_load_opps_lane ON load_opportunities(origin_state_prov, dest_state_prov);
"""


from pathlib import Path
from typing import Union, Dict, Any
from contextlib import closing


def apply_carrier_schema_migration(conn_or_path: Union[sqlite3.Connection, str, Path]) -> Dict[str, Any]:
    """
    Applies additive migrations for the Carrier & Capacity module.
    Preserves all existing tables, rows, claims, outreach, and configurations.
    Idempotent.
    """
    if isinstance(conn_or_path, (str, Path)):
        with closing(sqlite3.connect(conn_or_path)) as conn:
            apply_carrier_schema_migration(conn)
        return {"status": "SUCCESS"}

    conn = conn_or_path
    cur = conn.cursor()

    # 1. Additive columns to existing carriers table
    carrier_cols = {row[1] for row in cur.execute("PRAGMA table_info(carriers);").fetchall()}
    columns_to_add_carriers = [
        ("postal_code", "TEXT"),
        ("business_address", "TEXT"),
        ("business_phone", "TEXT"),
        ("business_email", "TEXT"),
        ("website", "TEXT"),
        ("driver_count", "INTEGER"),
        ("cargo_categories", "TEXT"),
        ("authority_status", "TEXT DEFAULT 'UNKNOWN'"),
        ("authority_verified_at", "TEXT"),
        ("authority_source", "TEXT"),
        ("source_type", "TEXT DEFAULT 'USER_ENTERED'"),
        ("source_name", "TEXT"),
        ("source_url", "TEXT"),
        ("external_record_id", "TEXT"),
        ("observed_at", "TEXT"),
        ("updated_at", "TEXT"),
    ]
    for col_name, col_type in columns_to_add_carriers:
        if col_name not in carrier_cols:
            cur.execute(f"ALTER TABLE carriers ADD COLUMN {col_name} {col_type};")

    # 2. Additive columns to existing capacity_postings table
    capacity_cols = {row[1] for row in cur.execute("PRAGMA table_info(capacity_postings);").fetchall()}
    columns_to_add_capacity = [
        ("available_truck_count", "INTEGER DEFAULT 1"),
        ("origin_latitude", "REAL"),
        ("origin_longitude", "REAL"),
        ("destination_city", "TEXT"),
        ("destination_state_prov", "TEXT"),
        ("destination_country", "TEXT"),
        ("dest_latitude", "REAL"),
        ("dest_longitude", "REAL"),
        ("desired_rate", "NUMERIC"),
        ("desired_rate_per_mile", "NUMERIC"),
        ("rate_currency", "TEXT DEFAULT 'USD'"),
        ("rate_basis", "TEXT DEFAULT 'FLAT'"),
        ("post_type", "TEXT DEFAULT 'ONE_TIME'"),
        ("source_type", "TEXT DEFAULT 'USER_ENTERED'"),
        ("source_name", "TEXT"),
        ("source_url", "TEXT"),
        ("external_record_id", "TEXT"),
        ("source_published_at", "TEXT"),
        ("claim_confidence", "TEXT DEFAULT 'VERIFIED'"),
        ("system_stale_after", "TEXT"),
        ("notes", "TEXT"),
    ]
    for col_name, col_type in columns_to_add_capacity:
        if col_name not in capacity_cols:
            cur.execute(f"ALTER TABLE capacity_postings ADD COLUMN {col_name} {col_type};")

    # 3. Additive columns to existing carrier_lane_activity table
    lane_cols = {row[1] for row in cur.execute("PRAGMA table_info(carrier_lane_activity);").fetchall()}
    columns_to_add_lane = [
        ("preference_level", "TEXT DEFAULT 'PREFERRED'"),
        ("origin_city", "TEXT"),
        ("dest_city", "TEXT"),
        ("available_days", "TEXT"),
        ("source_type", "TEXT DEFAULT 'USER_ENTERED'"),
    ]
    for col_name, col_type in columns_to_add_lane:
        if col_name not in lane_cols:
            cur.execute(f"ALTER TABLE carrier_lane_activity ADD COLUMN {col_name} {col_type};")

    # 4. Additive columns to existing load_capacity_matches table
    match_cols = {row[1] for row in cur.execute("PRAGMA table_info(load_capacity_matches);").fetchall()}
    columns_to_add_match = [
        ("match_score", "REAL"),
        ("carrier_id", "INTEGER REFERENCES carriers(id) ON DELETE CASCADE"),
        ("last_quoted_rate", "NUMERIC"),
        ("quote_currency", "TEXT DEFAULT 'USD'"),
        ("workflow_status", "TEXT DEFAULT 'CANDIDATE'"),
        ("notes", "TEXT"),
        ("booked_at", "TEXT"),
        ("booked_by_user_id", "INTEGER REFERENCES team_users(id)"),
    ]
    for col_name, col_type in columns_to_add_match:
        if col_name not in match_cols:
            cur.execute(f"ALTER TABLE load_capacity_matches ADD COLUMN {col_name} {col_type};")

    # 5. Create new dedicated carrier tables
    cur.executescript(CARRIER_DDL)

    # 6. Create performance indexes
    cur.executescript(PERFORMANCE_INDEXES)

    # 7. Create triggers
    cur.executescript(CARRIER_TRIGGERS)

    conn.commit()


from threading import Lock
from datetime import datetime, timezone
_carrier_schema_lock = Lock()
_carrier_initialized = set()


def initialize(db_path=None) -> None:
    """Thread-safe additive migration initializer with production backup protection."""
    from src.backend.db.connection import create_connection, get_db_path, DEFAULT_DB_PATH
    from contextlib import closing
    path = get_db_path(db_path).resolve()
    with _carrier_schema_lock:
        if path in _carrier_initialized:
            return
        with closing(create_connection(path)) as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='carrier_outreach_logs'").fetchone()
            if not exists and path == DEFAULT_DB_PATH.resolve():
                backup = path.parent / "backups" / ("prospects_pre_carrier_capacity_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ".db")
                backup.parent.mkdir(exist_ok=True)
                with closing(sqlite3.connect(backup)) as dest:
                    conn.backup(dest)
            apply_carrier_schema_migration(conn)
        _carrier_initialized.add(path)

