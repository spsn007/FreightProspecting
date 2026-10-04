"""Small shared-team layer: persistent sessions, ownership and preserved attribution."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException

from src.backend.db.connection import create_connection, get_db_path, DEFAULT_DB_PATH

_schema_lock = Lock()
_initialized = set()
COOKIE = "fp_session"
SESSION_SECONDS = 12 * 60 * 60

DDL = """
CREATE TABLE IF NOT EXISTS team_users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL COLLATE NOCASE UNIQUE,
 password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('BROKER','ADMIN')),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS team_sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES team_users(id), expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS team_login_attempts (
 attempt_key TEXT NOT NULL, attempted_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_team_attempts ON team_login_attempts(attempt_key, attempted_at);
CREATE TABLE IF NOT EXISTS company_assignments (
 company_id INTEGER PRIMARY KEY REFERENCES companies(id),
 owner_id INTEGER NOT NULL REFERENCES team_users(id), updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_company_owner ON company_assignments(owner_id);
CREATE TABLE IF NOT EXISTS assignment_history (
 id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id),
 actor_id INTEGER NOT NULL REFERENCES team_users(id), from_user_id INTEGER REFERENCES team_users(id),
 to_user_id INTEGER REFERENCES team_users(id), action TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outreach_authors (
 outreach_log_id INTEGER PRIMARY KEY REFERENCES outreach_logs(id) ON DELETE CASCADE, user_id INTEGER NOT NULL REFERENCES team_users(id)
);
CREATE TABLE IF NOT EXISTS team_notifications (
 id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL REFERENCES team_users(id),
 actor_id INTEGER NOT NULL REFERENCES team_users(id), company_id INTEGER REFERENCES companies(id),
 kind TEXT NOT NULL CHECK(kind IN ('TRANSFER','ANNOUNCEMENT')),
 title TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON team_notifications(recipient_id,id);
CREATE TABLE IF NOT EXISTS team_company_alerts (
 id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL REFERENCES team_users(id),
 actor_id INTEGER NOT NULL REFERENCES team_users(id), company_id INTEGER NOT NULL REFERENCES companies(id),
 kind TEXT NOT NULL CHECK(kind IN ('REASSIGNED','RESCHEDULED')),
 target_id INTEGER REFERENCES team_users(id), previous_due_at TEXT, due_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_company_alerts_recipient ON team_company_alerts(recipient_id,id);
CREATE TABLE IF NOT EXISTS team_notification_reads (
 user_id INTEGER NOT NULL REFERENCES team_users(id), notification_key TEXT NOT NULL,
 read_at TEXT NOT NULL, PRIMARY KEY(user_id,notification_key)
);
CREATE INDEX IF NOT EXISTS idx_assignment_history_company ON assignment_history(company_id,id);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def password_hash(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + ":" + digest.hex()


def password_matches(password, stored):
    salt, digest = stored.split(":")
    actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return hmac.compare_digest(actual.hex(), digest)


def initialize(db_path=None):
    """Add only team tables; take a consistent production backup before first migration."""
    path = get_db_path(db_path).resolve()
    with _schema_lock:
        if path in _initialized:
            return
        with closing(create_connection(path)) as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE name='team_users'").fetchone()
            notifications_exist = conn.execute("SELECT 1 FROM sqlite_master WHERE name='team_notifications'").fetchone()
            alerts_exist = conn.execute("SELECT 1 FROM sqlite_master WHERE name='team_company_alerts'").fetchone()
            if (not exists or not notifications_exist or not alerts_exist) and path == DEFAULT_DB_PATH.resolve():
                backup = path.parent / "backups" / (("prospects_pre_notifications_" if exists else "prospects_pre_team_") + datetime.now().strftime("%Y%m%d_%H%M%S") + ".db")
                backup.parent.mkdir(exist_ok=True)
                with closing(sqlite3.connect(backup)) as dest:
                    conn.backup(dest)
            conn.executescript(DDL)
            with conn:
                if not conn.execute("SELECT 1 FROM team_users LIMIT 1").fetchone():
                    initial = os.getenv("FP_INITIAL_PASSWORD", "12345")
                    for name, role in (("Selena", "BROKER"), ("Kevin", "BROKER"), ("Admin", "ADMIN")):
                        conn.execute("INSERT INTO team_users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                                     (name, password_hash(initial), role, now()))
        _initialized.add(path)


def authenticate(username, password, client_ip):
    key = hashlib.sha256((client_ip + ":" + username.strip().casefold()).encode()).hexdigest()
    current = int(time.time())
    with closing(create_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM team_login_attempts WHERE attempted_at < ?", (current - 900,))
        if conn.execute("SELECT count(*) FROM team_login_attempts WHERE attempt_key=?", (key,)).fetchone()[0] >= 5:
            raise HTTPException(429, "Too many attempts. Please try again in 15 minutes.")
        row = conn.execute("SELECT * FROM team_users WHERE username=?", (username.strip(),)).fetchone()
        valid = password_matches(password, row["password_hash"] if row else _dummy_hash)
        if not row or not row["active"] or not valid:
            conn.execute("INSERT INTO team_login_attempts VALUES(?,?)", (key, current))
            conn.commit()
            raise HTTPException(401, "Incorrect username or password.")
        conn.execute("DELETE FROM team_login_attempts WHERE attempt_key=?", (key,))
        conn.execute("DELETE FROM team_sessions WHERE expires_at <= ?", (current,))
        token = secrets.token_urlsafe(32)
        conn.execute("INSERT INTO team_sessions VALUES(?,?,?)", (token_digest(token), row["id"], current + SESSION_SECONDS))
        return token


_dummy_hash = password_hash(secrets.token_hex(16))


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session_user(token):
    if not token or len(token) > 128:
        return None
    with closing(create_connection()) as conn:
        row = conn.execute("""SELECT u.id,u.username,u.role FROM team_sessions s JOIN team_users u ON u.id=s.user_id
                              WHERE s.token_hash=? AND s.expires_at>? AND u.active=1""",
                           (token_digest(token), int(time.time()))).fetchone()
        return dict(row) if row else None


def require_admin(user):
    if user["role"] != "ADMIN":
        raise HTTPException(403, "Only Admin can manage accounts and reassign companies.")


def users(active_only=False):
    with closing(create_connection()) as conn:
        sql = "SELECT id,username,role,active FROM team_users" + (" WHERE active=1" if active_only else "")
        return [dict(row) for row in conn.execute(sql + " ORDER BY username")]


def validate_username(username):
    username = username.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,49}", username):
        raise HTTPException(400, "Use a name of 1–50 letters, numbers, spaces, dots, underscores or hyphens.")
    return username


def create_user(username, password):
    username = validate_username(username)
    if not 5 <= len(password) <= 128:
        raise HTTPException(400, "Password must contain 5–128 characters.")
    with closing(create_connection()) as conn, conn:
        try:
            conn.execute("INSERT INTO team_users(username,password_hash,role,created_at) VALUES(?,?,'BROKER',?)",
                         (username, password_hash(password), now()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "That profile name already exists, including disabled profiles.")


def update_user(actor, user_id, action, password=None, target_id=None, username=None):
    require_admin(actor)
    with closing(create_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM team_users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Profile not found.")
        if row["role"] == "ADMIN" and action in ("disable", "enable"):
            raise HTTPException(400, "The Admin account cannot be disabled.")
        if action == "rename":
            name = validate_username(username or "")
            try:
                conn.execute("UPDATE team_users SET username=? WHERE id=?", (name, user_id))
            except sqlite3.IntegrityError:
                raise HTTPException(409, "That profile name already exists, including disabled profiles.")
        elif action == "password":
            if not password or not 5 <= len(password) <= 128:
                raise HTTPException(400, "Password must contain 5–128 characters.")
            conn.execute("UPDATE team_users SET password_hash=? WHERE id=?", (password_hash(password), user_id))
        elif action == "disable":
            if target_id == user_id:
                raise HTTPException(400, "Choose another broker for the handoff.")
            if target_id:
                check_target(conn, target_id)
            for assignment in conn.execute("SELECT company_id FROM company_assignments WHERE owner_id=?", (user_id,)).fetchall():
                set_owner(conn, assignment["company_id"], actor["id"], user_id, target_id, "ACCOUNT_DISABLED", "Profile disabled by Admin")
            conn.execute("UPDATE team_users SET active=0 WHERE id=?", (user_id,))
        elif action == "enable":
            conn.execute("UPDATE team_users SET active=1 WHERE id=?", (user_id,))
        else:
            raise HTTPException(400, "Unknown profile action.")
        if action != "rename":
            conn.execute("DELETE FROM team_sessions WHERE user_id=?", (user_id,))


def check_target(conn, user_id):
    if not conn.execute("SELECT 1 FROM team_users WHERE id=? AND active=1 AND role='BROKER'", (user_id,)).fetchone():
        raise HTTPException(400, "Choose an active broker.")


def assert_owner(conn, company_id, user_id):
    if not conn.execute("SELECT 1 FROM company_assignments WHERE company_id=? AND owner_id=?", (company_id, user_id)).fetchone():
        raise HTTPException(409, "Start Working on this company first. It may already belong to another broker.")
    if not conn.execute("SELECT 1 FROM team_users WHERE id=? AND active=1", (user_id,)).fetchone():
        raise HTTPException(401, "Your profile is no longer active.")


def set_owner(conn, company_id, actor_id, previous_id, target_id, action, note):
    if target_id:
        conn.execute("INSERT INTO company_assignments VALUES(?,?,?) ON CONFLICT(company_id) DO UPDATE SET owner_id=excluded.owner_id,updated_at=excluded.updated_at",
                     (company_id, target_id, now()))
    else:
        conn.execute("DELETE FROM company_assignments WHERE company_id=?", (company_id,))
    conn.execute("INSERT INTO assignment_history(company_id,actor_id,from_user_id,to_user_id,action,note,created_at) VALUES(?,?,?,?,?,?,?)",
                 (company_id, actor_id, previous_id, target_id, action, note, now()))
    if action in {"TRANSFER", "ACCOUNT_DISABLED"} and target_id and target_id != previous_id and target_id != actor_id:
        conn.execute("""INSERT INTO team_notifications(recipient_id,actor_id,company_id,kind,title,message,created_at)
                        VALUES(?,?,?,'TRANSFER','Company transferred to you',?,?)""",
                     (target_id, actor_id, company_id, note, now()))

    if previous_id and target_id != previous_id and actor_id != previous_id:
        conn.execute("""INSERT INTO team_company_alerts(recipient_id,actor_id,company_id,kind,target_id,created_at)
                        VALUES(?,?,?,'REASSIGNED',?,?)""", (previous_id, actor_id, company_id, target_id, now()))


def assign(user, company_id, action, target_id=None, note=""):
    with closing(create_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT 1 FROM team_users WHERE id=? AND active=1", (user["id"],)).fetchone():
            raise HTTPException(401, "Your profile is no longer active.")
        if not conn.execute("SELECT 1 FROM companies WHERE id=?", (company_id,)).fetchone():
            raise HTTPException(404, "Company not found.")
        old = conn.execute("SELECT owner_id FROM company_assignments WHERE company_id=?", (company_id,)).fetchone()
        old_id = old[0] if old else None
        if action == "claim":
            if old_id == user["id"]:
                return
            if old_id:
                raise HTTPException(409, "Another broker is already working on this company.")
            target_id = user["id"]
        else:
            if user["role"] != "ADMIN":
                assert_owner(conn, company_id, user["id"])
            if action == "release":
                target_id = None
            else:
                check_target(conn, target_id)
        set_owner(conn, company_id, user["id"], old_id, target_id, action.upper(), note)


def snapshot():
    with closing(create_connection()) as conn:
        rows = conn.execute("""SELECT c.id company_id,a.owner_id,u.username owner_name,a.updated_at assigned_at,
                  COALESCE(p.current_outreach_status,'UNCONTACTED') outreach_status,p.next_follow_up_at,
                  p.last_contacted_at,p.last_feedback_notes,COALESCE(p.attempt_count,0) attempt_count,
                  EXISTS(SELECT 1 FROM suppressions s WHERE s.scope_type='COMPANY'
                         AND s.company_id=c.id AND s.suppression_status!='NORMAL_PROSPECT') is_suppressed,
                  (SELECT note FROM assignment_history h WHERE h.company_id=c.id ORDER BY h.id DESC LIMIT 1) handoff_note,
                  COALESCE(author.username,'Existing history — broker not recorded') last_broker_name
                  FROM companies c LEFT JOIN company_assignments a ON a.company_id=c.id
                  LEFT JOIN team_users u ON u.id=a.owner_id
                  LEFT JOIN prospect_engagement_state p ON p.company_id=c.id
                  LEFT JOIN outreach_authors oa ON oa.outreach_log_id=(SELECT MAX(id) FROM outreach_logs WHERE company_id=c.id)
                  LEFT JOIN team_users author ON author.id=oa.user_id""")
        return {row["company_id"]: dict(row) for row in rows}


def add_authors(history):
    with closing(create_connection()) as conn:
        authors = {r[0]: r[1] for r in conn.execute("SELECT a.outreach_log_id,u.username FROM outreach_authors a JOIN team_users u ON u.id=a.user_id")}
    for row in history:
        row["broker_name"] = authors.get(row["id"], "Existing history — broker not recorded")
    return history


def allowed_company_ids(user, view, state):
    if view == "all":
        return None
    return [cid for cid, entry in state.items() if
            (entry["owner_id"] == user["id"] if view == "mine" else
             not entry["owner_id"] and entry["outreach_status"] != "NOT_INTERESTED" and not entry["is_suppressed"])]


def assignment_history(company_id):
    with closing(create_connection()) as conn:
        return [dict(r) for r in conn.execute("""SELECT h.*,actor.username actor_name,old.username from_name,new.username to_name
                 FROM assignment_history h JOIN team_users actor ON actor.id=h.actor_id
                 LEFT JOIN team_users old ON old.id=h.from_user_id LEFT JOIN team_users new ON new.id=h.to_user_id
                 WHERE h.company_id=? ORDER BY h.id DESC""", (company_id,))]


def notifications(user, tz="UTC"):
    """Personal transfers/announcements plus reminders from current ownership and due dates."""
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(400, "Choose a valid timezone.")
    today = datetime.now(timezone.utc).astimezone(zone).date()
    with closing(create_connection()) as conn:
        reads = {r[0]: r[1] for r in conn.execute(
            "SELECT notification_key,read_at FROM team_notification_reads WHERE user_id=?", (user["id"],))}
        items = []
        rows = conn.execute("""SELECT n.*,u.username actor_name,COALESCE(c.operating_brand,c.legal_name) company_name,
                (SELECT MIN(f.id) FROM facilities f WHERE f.company_id=n.company_id) facility_id
                FROM team_notifications n JOIN team_users u ON u.id=n.actor_id
                LEFT JOIN companies c ON c.id=n.company_id WHERE n.recipient_id=?""", (user["id"],))
        for row in rows:
            r = dict(row)
            key = "message:" + str(r["id"])
            message = r["message"]
            if r["kind"] == "TRANSFER":
                message = r["actor_name"] + " transferred " + r["company_name"] + " to you." + (" Handoff: " + message if message else "")
            items.append({"key": key, "kind": r["kind"], "title": r["title"], "message": message,
                          "created_at": r["created_at"], "due_at": None, "actor_name": r["actor_name"],
                          "company_name": r["company_name"], "url": "/prospects/" + str(r["facility_id"]) if r["facility_id"] else None,
                          "read_at": reads.get(key)})
        rows = conn.execute("""SELECT n.*,u.username actor_name,t.username target_name,
                COALESCE(c.operating_brand,c.legal_name) company_name,
                (SELECT MIN(f.id) FROM facilities f WHERE f.company_id=n.company_id) facility_id
                FROM team_company_alerts n JOIN team_users u ON u.id=n.actor_id
                JOIN companies c ON c.id=n.company_id LEFT JOIN team_users t ON t.id=n.target_id
                WHERE n.recipient_id=?""", (user["id"],))
        for row in rows:
            r = dict(row)
            key = "alert:" + str(r["id"])
            if r["kind"] == "REASSIGNED":
                title = "Company reassigned away from you"
                message = r["actor_name"] + " reassigned " + r["company_name"] + (" to " + r["target_name"] if r["target_name"] else " to the available team pool") + "."
            else:
                title = "Admin rescheduled a follow-up"
                message = r["actor_name"] + " changed the follow-up for " + r["company_name"].rstrip(".") + "."
            items.append({"key":key, "kind":r["kind"], "title":title, "message":message,
                          "created_at":r["created_at"], "due_at":r["due_at"], "previous_due_at":r["previous_due_at"],
                          "actor_name":r["actor_name"], "company_name":r["company_name"],
                          "url":"/prospects/" + str(r["facility_id"]) if r["facility_id"] else None, "read_at":reads.get(key)})
        unanswered = conn.execute("""SELECT a.company_id,COALESCE(c.operating_brand,c.legal_name) company_name,
                (SELECT MIN(f.id) FROM facilities f WHERE f.company_id=a.company_id) facility_id
                FROM company_assignments a JOIN companies c ON c.id=a.company_id
                JOIN prospect_engagement_state p ON p.company_id=a.company_id
                WHERE a.owner_id=? AND p.current_outreach_status='NO_ANSWER'""", (user["id"],))
        for company in unanswered:
            streak = conn.execute("""SELECT COUNT(*) count,MIN(id) first_id,MAX(contacted_at) latest_at FROM outreach_logs
                    WHERE company_id=? AND outreach_channel='PHONE' AND id>COALESCE(
                    (SELECT MAX(id) FROM outreach_logs WHERE company_id=? AND outreach_channel='PHONE'
                     AND COALESCE(disposition,outcome)!='NO_ANSWER'),0)""", (company["company_id"], company["company_id"])).fetchone()
            if streak["count"] < 3:
                continue
            key = f"unanswered:{company['company_id']}:{streak['first_id']}"
            items.append({"key":key, "kind":"NO_ANSWER_STREAK", "title":str(streak["count"]) + " unanswered calls in a row",
                          "message":company["company_name"].rstrip(".") + " has not answered. Try a different time or review the contact details.",
                          "created_at":streak["latest_at"], "due_at":None, "actor_name":None, "company_name":company["company_name"],
                          "url":"/prospects/" + str(company["facility_id"]) if company["facility_id"] else None, "read_at":reads.get(key)})
        rows = conn.execute("""SELECT a.company_id,p.next_follow_up_at,COALESCE(c.operating_brand,c.legal_name) company_name,
                (SELECT MIN(f.id) FROM facilities f WHERE f.company_id=a.company_id) facility_id
                FROM company_assignments a JOIN companies c ON c.id=a.company_id
                JOIN prospect_engagement_state p ON p.company_id=a.company_id
                WHERE a.owner_id=? AND p.next_follow_up_at IS NOT NULL""", (user["id"],))
        for row in rows:
            try:
                due = datetime.fromisoformat(row["next_follow_up_at"].replace("Z", "+00:00"))
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            due_day = due.astimezone(zone).date()
            phase = "OVERDUE" if due_day < today else "TODAY" if due_day == today else "UPCOMING"
            key = f"followup:{row['company_id']}:{row['next_follow_up_at']}:{phase}"
            items.append({"key": key, "kind": phase, "title": {"OVERDUE":"Overdue follow-up", "TODAY":"Follow-up today", "UPCOMING":"Upcoming follow-up"}[phase],
                          "message": "Follow up with " + row["company_name"].rstrip(".") + ".", "created_at": row["next_follow_up_at"],
                          "due_at": row["next_follow_up_at"], "actor_name": None, "company_name": row["company_name"],
                          "url": "/prospects/" + str(row["facility_id"]) if row["facility_id"] else None, "read_at": reads.get(key)})
    priority = {"TODAY":0, "OVERDUE":1, "TRANSFER":2, "ANNOUNCEMENT":2, "UPCOMING":3, "REASSIGNED":2, "RESCHEDULED":2, "NO_ANSWER_STREAK":2}
    def sort_key(item):
        recorded = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        return (bool(item["read_at"]), priority[item["kind"]], recorded.timestamp() * (1 if item["kind"] in {"TODAY","OVERDUE","UPCOMING"} else -1))
    items.sort(key=sort_key)
    return {"items": items, "unread_count": sum(not i["read_at"] for i in items)}


def read_notifications(user, keys=None, tz="UTC"):
    accessible = {i["key"] for i in notifications(user, tz)["items"]}
    selected = accessible if keys is None else accessible.intersection(keys)
    with closing(create_connection()) as conn, conn:
        conn.executemany("INSERT OR IGNORE INTO team_notification_reads VALUES(?,?,?)",
                         [(user["id"], key, now()) for key in selected])


def announce(user, title, message):
    require_admin(user)
    with closing(create_connection()) as conn, conn:
        recipients = conn.execute("SELECT id FROM team_users WHERE active=1 AND role='BROKER'").fetchall()
        conn.executemany("""INSERT INTO team_notifications(recipient_id,actor_id,kind,title,message,created_at)
                            VALUES(?,?,'ANNOUNCEMENT',?,?,?)""",
                         [(r[0], user["id"], title, message, now()) for r in recipients])
    return len(recipients)


def reschedule_follow_up(user, company_id, follow_up_at):
    require_admin(user)
    from src.backend.db.validators import normalize_to_utc_iso
    try:
        due = datetime.fromisoformat(follow_up_at.replace("Z", "+00:00"))
        if due.tzinfo is None or due <= datetime.now(timezone.utc):
            raise ValueError()
        normalized = normalize_to_utc_iso(follow_up_at)
    except ValueError:
        raise HTTPException(400, "Choose a future follow-up date and time with a timezone.")
    with closing(create_connection()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("""SELECT a.owner_id,p.next_follow_up_at FROM company_assignments a
                              JOIN prospect_engagement_state p ON p.company_id=a.company_id WHERE a.company_id=?""", (company_id,)).fetchone()
        if not row or not row["next_follow_up_at"]:
            raise HTTPException(409, "This company needs an assigned broker and an existing follow-up to reschedule.")
        if row["next_follow_up_at"] == normalized:
            return
        conn.execute("UPDATE prospect_engagement_state SET next_follow_up_at=?,updated_at=? WHERE company_id=?", (normalized, now(), company_id))
        conn.execute("""INSERT INTO team_company_alerts(recipient_id,actor_id,company_id,kind,previous_due_at,due_at,created_at)
                        VALUES(?,?,?,'RESCHEDULED',?,?,?)""", (row["owner_id"], user["id"], company_id, row["next_follow_up_at"], normalized, now()))
