"""
FreightProspecting V1 — Database Connection Management
Enforces SQLite foreign key constraints, WAL journal mode, and row factory.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Generator, Optional

# Default database location on D: drive
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DB_PATH = WORKSPACE_ROOT / "data" / "prospects.db"


def get_db_path(custom_path: Optional[str | Path] = None) -> Path:
    """Resolve database path, falling back to environment variable or default."""
    if custom_path:
        return Path(custom_path)
    env_path = os.getenv("FREIGHT_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def _read_only_authorizer(action_code, param1, param2, db_name, trigger_name):
    """Authorizer callback to block any mutation against protected database."""
    write_actions = {
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER,
    }
    if action_code in write_actions:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def is_test_environment() -> bool:
    """Detect if running inside pytest or test mode."""
    return "PYTEST_CURRENT_TEST" in os.environ or os.getenv("FP_TEST_MODE") == "1"


def create_connection(
    db_path: Optional[str | Path] = None,
    create_if_missing: bool = False
) -> sqlite3.Connection:
    """
    Create a new sqlite3 connection with strict PRAGMAs:
    - PRAGMA foreign_keys = ON (enforced on EVERY operational connection)
    - PRAGMA journal_mode = WAL (enabled for file-based databases)
    - sqlite3.Row row factory for named column access
    - Hard write-guard: Production database (DEFAULT_DB_PATH) is strictly read-only during tests.
    - Missing DB Guard (AUD-021): Raises FileNotFoundError if DB file is missing,
      refusing to create empty database files implicitly unless create_if_missing=True.
    """
    resolved_path = get_db_path(db_path)

    # Missing database guard: never implicitly create an empty SQLite file
    if str(resolved_path) != ":memory:":
        if not resolved_path.exists() and not create_if_missing:
            raise FileNotFoundError(
                f"Database file not found at '{resolved_path}'. "
                f"Run database initialization before starting the application."
            )

    is_prod_target = False
    if str(resolved_path) != ":memory:":
        try:
            is_prod_target = resolved_path.resolve() == DEFAULT_DB_PATH.resolve()
        except Exception:
            is_prod_target = str(resolved_path).endswith("prospects.db")

    is_test = is_test_environment()

    # Hard guard: If running under test and targeting production DB, open mode=ro with write authorizer
    if is_test and is_prod_target:
        uri_path = f"file:{resolved_path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri_path, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.set_authorizer(_read_only_authorizer)
        return conn

    # Ensure parent directory exists for file-based DBs
    if str(resolved_path) != ":memory:":
        resolved_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(resolved_path))
    conn.row_factory = sqlite3.Row

    # Always enforce foreign keys on every connection
    conn.execute("PRAGMA foreign_keys = ON;")

    # Enable WAL mode for file-based databases (ignored by :memory:)
    if str(resolved_path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")

    return conn


@contextmanager
def get_db_connection(
    db_path: Optional[str | Path] = None,
    create_if_missing: bool = False
) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections.
    Automatically commits on success and rolls back on exception.
    """
    conn = create_connection(db_path, create_if_missing=create_if_missing)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def check_database_health(db_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """
    Check if the database exists and has required operational schema.
    Returns diagnostic dict: {'healthy': bool, 'path': str, 'exists': bool, 'tables': list, 'error': Optional[str]}
    Does NOT create empty files if the database is missing.
    """
    resolved_path = get_db_path(db_path)
    if str(resolved_path) == ":memory:":
        return {"healthy": True, "path": ":memory:", "exists": True, "tables": [], "error": None}

    if not resolved_path.exists():
        return {
            "healthy": False,
            "path": str(resolved_path),
            "exists": False,
            "tables": [],
            "error": f"Database file not found at '{resolved_path}'. Run database initialization before starting the application."
        }

    try:
        uri = f"file:{resolved_path.resolve().as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        conn.close()
        required = {"companies", "facilities", "claims"}
        missing = required - set(tables)
        if missing:
            return {
                "healthy": False,
                "path": str(resolved_path),
                "exists": True,
                "tables": tables,
                "error": f"Database schema uninitialized; missing required tables: {sorted(missing)}"
            }
        return {
            "healthy": True,
            "path": str(resolved_path),
            "exists": True,
            "tables": tables,
            "error": None
        }
    except Exception as e:
        return {
            "healthy": False,
            "path": str(resolved_path),
            "exists": True,
            "tables": [],
            "error": f"Failed to read database: {str(e)}"
        }
