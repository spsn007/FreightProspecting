# FreightProspecting

A personal, deterministic, local browser application for freight brokerage prospecting, evidence tracking, outreach workflows, load/capacity matching, and gross margin analysis.

---

## Overview

- **Core Focus**: US Lower 48 and Canada (10 provinces) industrial Full Truckload (FTL) prospecting.
- **Target Equipment**: Flatbed, Step Deck, and Dry Van (48-ft and 53-ft configurations supported as capacity attributes).
- **Hard Exclusions**: Hazmat / Placarded cargo, high-value precious cargo (currency/bullion/jewelry), live animals, fresh seafood, refrigerated cargo (out of V1 scope), Mexico, and Alaska (excluded by default in V1).
- **Core Stance**: Zero hallucination, field-level provenance, strict 3D time semantics (`source_published_at`, `event_at`, `observed_at`), and deterministic business logic.
- **Architecture**: 100% local Python/FastAPI backend, SQLite 3 (WAL mode), Jinja2 HTML templates, local vendored Alpine.js v3.14.8, zero paid AI APIs, zero external CDN dependencies.

---

## Key Capabilities

1. **Authoritative Opportunity Engine**:
   - Classifies shipper prospects into explainable tiers (Tier A: Priority, Tier B: Worth Calling, Tier C: Secondary, Tier D: Backlog) based on verified operational evidence and carrier acceptance.
   - Strictly separates Corporate Entity $\neq$ Physical Facility $\neq$ Freight-Demand Signal $\neq$ Discrete Load $\neq$ Carrier Directory.
   - Enforces 10-way relational integrity with partial unique indexes on current accepted claims.

2. **Evidence-First Broker Outreach Workflow**:
   - Phone-first contact hierarchy prioritizing direct logistics desks, dispatch extensions, and shipping docks.
   - Offline and online evidence ingestion with primary-source verification audits.
   - Multilevel suppression system (Company, Facility, Company-Lane, Facility-Lane, Global-Lane).

3. **Disaster Recovery & Version Control**:
   - Application code, schemas, tests, scripts, and auditable reports are versioned in Git.
   - Immutable binary database snapshots are tracked with Git LFS under `backup/github/`.
   - See [docs/BACKUP_AND_RESTORE.md](docs/BACKUP_AND_RESTORE.md) for full disaster recovery, snapshot restoration, and SHA-256 verification instructions.

---

## Quick Start

### 1. Environment Setup
```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Database Restoration
If cloning fresh, restore the latest authoritative database snapshot:
```bash
# Verify Git LFS files are pulled
git lfs pull

# Restore snapshot to active runtime database
copy backup\github\prospects_20260930_6bd5b836.db data\prospects.db
```

### 3. Run Tests
```bash
pytest
```

### 4. Launch Application
```bash
# Run via batch script
run_app.bat

# Or run directly via Uvicorn
uvicorn src.backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Navigate to `http://127.0.0.1:8000` in your web browser.

---

## Disaster Recovery & Synchronization

For detailed step-by-step restoration instructions, SHA-256 verification procedures, and future synchronization workflows, refer to:
- [docs/BACKUP_AND_RESTORE.md](docs/BACKUP_AND_RESTORE.md)
- `python scripts/github_backup_status.py`
