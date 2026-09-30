"""
FreightProspecting V1 — Database CLI Bootstrap Script
Initializes SQLite schema and optionally seeds the audited 4 proof-of-schema records.
Usage:
    python scripts/init_db.py [--seed] [--db-path PATH]
"""

import argparse
from pathlib import Path
import sys

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.backend.db.connection import get_db_path
from src.backend.db.schema import init_db
from src.backend.db.seed import seed_database


def main():
    parser = argparse.ArgumentParser(description="Initialize FreightProspecting SQLite Database")
    parser.add_argument("--db-path", type=str, default=None, help="Custom path to SQLite database")
    parser.add_argument("--seed", action="store_true", help="Ingest audited Stage 2 seed data")
    args = parser.parse_args()

    target_path = get_db_path(args.db_path)
    print(f"Initializing database at: {target_path}")

    init_db(target_path)
    print("Schema initialization complete (17 tables, partial unique indexes, default settings).")

    if args.seed:
        print("Ingesting audited seed records (Beasley, Kenwal, DECAST, WMG)...")
        seed_database(target_path)
        print("Seeding complete.")


if __name__ == "__main__":
    main()
