#!/usr/bin/env python3
"""
scripts/github_backup_status.py

Read-only disaster recovery status inspection utility for FreightProspecting.
Reports Git branch, uncommitted changes, active DB SHA-256, latest backup
snapshot SHA-256, snapshot sync status, and latest Git commit SHA.

Strictly read-only: does NOT mutate database, does NOT push, does NOT commit.
"""

import os
import sys
import glob
import hashlib
import subprocess

def get_sha256(filepath: str) -> str:
    if not os.path.exists(filepath):
        return "FILE_NOT_FOUND"
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().upper()

def run_cmd(cmd: list[str]) -> str:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError:
        return "NONE (Initial commit pending)"
    except Exception as e:
        return f"ERROR: {e}"

def main():
    print("=" * 60)
    print("FREIGHTPROSPECTING — GITHUB BACKUP & STATUS REPORT")
    print("=" * 60)

    # 1. Git branch
    branch = run_cmd(["git", "branch", "--show-current"])
    print(f"Current Git Branch       : {branch}")

    # 2. Last commit SHA
    last_commit = run_cmd(["git", "log", "-1", "--format=%H %s"])
    print(f"Latest Git Commit        : {last_commit}")

    # 3. Uncommitted changes
    status_short = run_cmd(["git", "status", "--porcelain"])
    uncommitted_count = len(status_short.splitlines()) if status_short else 0
    print(f"Uncommitted Changes      : {uncommitted_count} file(s) modified/untracked")

    # 4. Active Database SHA-256
    active_db = os.path.join("data", "prospects.db")
    active_sha = get_sha256(active_db)
    active_size = os.path.getsize(active_db) if os.path.exists(active_db) else 0
    print(f"Active DB Path           : {active_db}")
    print(f"Active DB Size           : {active_size:,} bytes")
    print(f"Active DB SHA-256        : {active_sha}")

    # 5. Latest GitHub snapshot SHA-256
    snapshot_dir = os.path.join("backup", "github")
    snapshots = sorted(glob.glob(os.path.join(snapshot_dir, "prospects_*.db")))
    if snapshots:
        latest_snapshot = snapshots[-1]
        latest_sha = get_sha256(latest_snapshot)
        latest_size = os.path.getsize(latest_snapshot)
        print(f"Latest Snapshot Path     : {latest_snapshot}")
        print(f"Latest Snapshot Size     : {latest_size:,} bytes")
        print(f"Latest Snapshot SHA-256  : {latest_sha}")
    else:
        latest_snapshot = None
        latest_sha = "NONE"
        print("Latest Snapshot Path     : NONE FOUND")

    # 6. Status comparison
    print("-" * 60)
    if not latest_snapshot:
        print("Snapshot Sync Status     : NEW SNAPSHOT REQUIRED (no snapshots exist)")
    elif active_sha == latest_sha:
        print("Snapshot Sync Status     : SYNCHRONIZED (Active DB matches latest snapshot)")
    else:
        print("Snapshot Sync Status     : NEW SNAPSHOT NEEDED (Active DB differs from snapshot)")
    print("=" * 60)

if __name__ == "__main__":
    main()
