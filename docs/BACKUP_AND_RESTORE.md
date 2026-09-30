# FreightProspecting — Disaster Recovery, Backup & Restoration Guide

This document provides full instructions for reconstructing and restoring the FreightProspecting project from the private GitHub repository (`spsn007/FreightProspecting`) in the event of hardware loss, environment corruption, or migration to a new machine.

---

## 1. Repository Clone Command

Clone the repository using Git with Git LFS support:

```bash
# Clone the repository
git clone https://github.com/spsn007/FreightProspecting.git
cd FreightProspecting

# Ensure Git LFS hooks and objects are pulled
git lfs install
git lfs pull
```

---

## 2. Python Environment Recreation

The project requires Python 3.11+ (tested on Python 3.13.x):

```powershell
# Windows PowerShell / CMD
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

---

## 3. Dependency Installation

Install the required pinned dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Authoritative Database Snapshots Storage

- **Location**: `backup/github/`
- **File Naming**: `prospects_<UTC_DATE>_<SHORT_SHA>.db` (e.g. `prospects_20260930_6bd5b836.db`)
- **Tracking**: Tracked in Git via **Git LFS** (`backup/github/*.db filter=lfs diff=lfs merge=lfs -text` in `.gitattributes`).
- **Immutability**: Database snapshots in this folder are read-only baseline records and must never be directly opened in read-write mode by the application runtime.

---

## 5. Restoring the Latest Snapshot to `data/prospects.db`

To restore the operational runtime database:

```powershell
# Ensure the runtime data directory exists
if (-not (Test-Path "data")) { New-Item -ItemType Directory -Path "data" }

# Copy the authoritative snapshot to the runtime path
Copy-Item -Path "backup\github\prospects_20260930_6bd5b836.db" -Destination "data\prospects.db" -Force
```

---

## 6. Verifying SHA-256 and Integrity

Verify that the restored database matches the authoritative SHA-256 hash byte-for-byte and passes SQLite integrity checks:

```powershell
python -c "
import hashlib, sqlite3

expected_sha = '6BD5B8360FA713630477D715C5794906F44CB8814DFAB8EDF47D676C672767D9'

with open('data/prospects.db', 'rb') as f:
    actual_sha = hashlib.sha256(f.read()).hexdigest().upper()

print('Restored DB SHA256:', actual_sha)
assert actual_sha == expected_sha, f'HASH MISMATCH! Expected {expected_sha}, got {actual_sha}'

conn = sqlite3.connect('data/prospects.db')
cur = conn.cursor()
integrity = cur.execute('PRAGMA integrity_check;').fetchall()
fk = cur.execute('PRAGMA foreign_key_check;').fetchall()
conn.close()

print('PRAGMA integrity_check:', integrity)
print('PRAGMA foreign_key_check:', fk)
assert integrity == [('ok',)], f'Integrity failed: {integrity}'
assert fk == [], f'Foreign key check failed: {fk}'
print('DATABASE RESTORATION VERIFIED SUCCESSFULLY!')
"
```

---

## 7. Running Pytest

Run the comprehensive test suite to confirm backend, database, and UI logic integrity:

```powershell
pytest
```

---

## 8. Starting the Application

Launch the local web server:

```powershell
# Via batch runner
.\run_app.bat

# Or directly via Uvicorn
uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

The application cockpit will be available at `http://127.0.0.1:8000`.

---

## 9. Files Deliberately NOT Committed

To maintain repository speed, prevent secret leaks, and avoid redundant storage, the following items are intentionally excluded via `.gitignore`:

1. **Virtual Environment (`.venv/`, `venv/`)**: Rebuilt on demand using `requirements.txt`.
2. **Local Runtime Database (`data/prospects.db`, `*.db-wal`, `*.db-shm`)**: Ephemeral runtime files; restored from immutable `backup/github/` snapshots.
3. **Local Redundant Backups (`data/backups/`)**: Contains dozens of intermediate local SQLite backup copies (~160+ MB) created before individual research batches. These are preserved locally on the primary machine but excluded from Git to prevent repository bloat.
4. **Throwaway Scratch Scripts & Databases (`scratch/`, `temp/`, `*.tmp`, `ALL`)**: Experimental scripts and simulation databases.
5. **Environment Secrets (`.env`, `.env.*`)**: Prevents credential leakage.
6. **Browser Profiles & Session Caches (`browser-profile/`)**: Prevents session cookie leakage.
7. **Python & Test Caches (`__pycache__/`, `.pytest_cache/`, `.mypy_cache/`)**: Automatically regenerated.

---

## 10. Future GitHub Backup & Synchronization Workflow

When future research phases or verified mutations are completed, follow this 5-step synchronization discipline:

1. **Verify Database Integrity**:
   Confirm active `data/prospects.db` passes `PRAGMA integrity_check` and `PRAGMA foreign_key_check`. Calculate its SHA-256.

2. **Create / Update Authoritative Snapshot**:
   When authoritative database truth changes, create a new immutable snapshot in `backup/github/`:
   ```powershell
   # Example: prospects_<YYYYMMDD>_<SHORT_SHA>.db
   Copy-Item "data\prospects.db" "backup\github\prospects_<YYYYMMDD>_<SHORT_SHA>.db"
   ```

3. **Check Status**:
   Run the read-only disaster-recovery status tool:
   ```powershell
   python scripts/github_backup_status.py
   git status
   ```

4. **Commit**:
   ```powershell
   git add -A
   git commit -m "FreightProspecting: <descriptive message of milestone or phase>"
   ```

5. **Push**:
   ```powershell
   git push origin main
   ```
