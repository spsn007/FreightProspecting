"""
FreightProspecting V1 — Safe Database Backup Engine
Creates atomic, online backups of prospects.db using SQLite native backup API.
"""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Optional

from src.backend.db.connection import create_connection, get_db_path


def create_backup(
    db_path: Optional[str | Path] = None,
    backup_dir: Optional[str | Path] = None
) -> Path:
    """
    Create a safe, point-in-time backup of the specified database.
    Does not lock out readers/writers; safe for WAL mode.
    Returns the Path to the created backup file.
    """
    src_path = get_db_path(db_path)
    if str(src_path) == ":memory:":
        raise ValueError("Cannot perform file backup of in-memory database.")

    if not src_path.exists():
        raise FileNotFoundError(f"Source database not found at {src_path}")

    target_dir = Path(backup_dir) if backup_dir else src_path.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"prospects_backup_{timestamp}.db"
    dest_path = target_dir / backup_filename

    src_conn = create_connection(src_path)
    dest_conn = sqlite3.connect(str(dest_path))

    try:
        # Perform SQLite native online backup
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()

    return dest_path
