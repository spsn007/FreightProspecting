# FreightProspecting V1 — Implementation Roadmap

* **Architecture Baseline:** Revision 4.1 (Schema Freeze Candidate)  
* **Storage Location:** `D:\FreightProspecting`

---

## Stage Status Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 0: Architecture Planning & Freeze              [ COMPLETE ]           │
│ STAGE 1: Workspace, Durable Docs & Local Assets       [ COMPLETE ]           │
│ STAGE 2: SQLite Schema, Claims & Seed Insertion       [ COMPLETE ]           │
│ STAGE 2.5: Visual UI/UX Preview (Shipper-First CRM)  [ COMPLETE ]           │
│ STAGE 3: Backend Core, Scoring & Matching Logic       [ PENDING APPROVAL ]   │
│ STAGE 4: Full Interactive UI & Outreach Logging       [ FUTURE STAGE ]       │
│ STAGE 5: End-to-End Walkthrough & Delivery            [ FUTURE STAGE ]       │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Stage 0: Architecture Planning & Freeze — [ COMPLETE ]
* **Objective:** Establish business scope, audit proposed seed records, resolve architectural contradictions, and freeze the data model.
* **Key Artifacts:** Revision 4.1 Master Implementation Plan.
* **Status:** Complete and approved as architecture baseline.

---

### Stage 1: Workspace, Durable Docs & Local Frontend Assets — [ COMPLETE ]
* **Objective:** Create the durable project foundation and documentation on `D:\FreightProspecting` so future sessions can implement the frozen architecture without losing or altering requirements.
* **Deliverables:**
  * Workspace directory layout on `D:\FreightProspecting`.
  * `docs/PROJECT_BRIEF.md` (confirmed requirements, core separations, No-Paid-AI-API baseline).
  * `docs/DECISIONS.md` (confirmed decisions A–H, architecture invariants, SQLite errata).
  * `docs/SOURCES.md` (source catalog, access policies, permitted retrieval).
  * `docs/ARCHITECTURE.md` (frozen DDL blueprint, single current claim uniqueness, three time dimensions, execution boundaries).
  * `docs/IMPLEMENTATION_ROADMAP.md` (frozen stage progression).
  * Minimal local CSS foundation (`app.css`, `components.css`) with zero CDN dependencies.
  * Vendored Alpine.js v3.14.8 local build (`src/frontend/static/js/vendor/alpine.min.js`).
  * Python project dependency declaration (`requirements.txt`, audited and smoke-tested under Python 3.13.7).
  * Safe foundation launcher (`run_app.bat`).
* **Stage 1.1 Foundation Correction (Completed):**
  * Incorporated Confirmed Decision H: V1 requires no paid AI APIs, no paid search APIs, and no user-supplied AI key.
  * Audited and verified Python 3.13.7 package pins (`fastapi==0.141.1`, `uvicorn[standard]==0.54.0`, `pydantic==2.13.5`, `jinja2==3.1.6`, `python-multipart==0.0.32`, `httpx==0.28.1`, `pytest==9.1.1`).
  * Verified 100% of core prospecting features operate standalone and offline without AI SDKs.
* **Strict Non-Goals for Stage 1 / Stage 1.1:**
  * DO NOT create `prospects.db`.
  * DO NOT insert seed records.
  * DO NOT implement backend APIs or UI screens.

---

### Stage 2: SQLite Schema, Normalized Claims & Audited Seeds — [ COMPLETE ]
* **Objective:** Initialize the local SQLite database at `D:\FreightProspecting\data\prospects.db` with WAL mode and foreign key enforcement, execute the frozen DDL blueprint, and insert the approved proof-of-schema seeds.
* **Key Tasks Completed:**
  * Implemented SQLite DDL with 10 subject foreign keys in `claims` and exact-1 subject CHECK constraint.
  * Implemented 10 partial unique indexes for single current accepted claims (`is_current_accepted = 1`).
  * Implemented strict ISO-8601 timestamp validation rejecting text placeholders.
  * Completed WMG Technologies' current 2026 corporate placement verification inside TI Automotive.
  * Seeded database according to confirmed Decision D (Beasley, Kenwal, DECAST, WMG) with full claims/evidence provenance.
  * Verified zero fake loads, zero fake capacity postings, and zero fake demand signals.
  * Automated comprehensive tests in `tests/test_stage2_schema.py` and `tests/test_stage2_seed.py` (43 passing).
* **Stage 2.1 Schema Correction (Completed):**
  * Conformed physical schema to frozen architecture by renaming accidental `suppression_status_records` to `suppressions` as a physical table and removing the temporary compatibility view.
  * Verified exact-17 physical tables and 0 views in `data/prospects.db`.
  * Transactional migration utility `scripts/migrate_stage2_1.py` created and tested with full data preservation.
* **Testing Gates:**
  * Verify CHECK constraint: claim insertion fails if zero or $>1$ subject FK is populated.
  * Verify single current claim invariant: inserting a second active claim is blocked.
  * Verify carrier authority and safety rating default to `UNKNOWN`.
  * Verify `suppressions` is a physical table and `suppression_status_records` does not exist.

---

### Stage 2.5: Visual UI/UX Preview (Shipper-First CRM) — [ COMPLETE ]
* **Objective:** Deliver the first visual browser interface preview allowing the user to launch the local application, browse the 4 audited prospect families, inspect evidence provenance, and experience the shipper-first prospecting workflow.
* **Key Deliverables:**
  * FastAPI entry point at `src/backend/main.py` with read-only page routes and minimal API endpoints.
  * Read-only database query layer at `src/backend/db/queries.py` correctly separating corporate parents (ABC Technologies) from operating shipper facilities.
  * Dark navy sidebar navigation + light warm-gray workspace layout with zero external CDN dependencies.
  * Screen 1: Shortlist Cockpit (`index.html`) displaying the curated 4-prospect priority shortlist, phone-first contact blocks, and truthful top status metrics.
  * Screen 2: Master Directory (`prospects.html`) with Alpine.js live search and filters across equipment, fleet, and phone directness.
  * Screen 3: Loads & Margins (`loads.html`) with an honest empty state and deterministic margin formula explanation.
  * Screen 4: Carriers & Capacity (`carriers.html`) with an honest empty state and specific match invariant guide.
  * Screen 5/Research: Evidence Ledger (`research.html`) displaying all 10 verified primary sources and the three-dimensional time model.
  * Screen 5/Settings: Settings & Controls (`settings.html`) displaying Decision A, B, and H parameters.
  * Prospect Detail View (`prospect_detail.html`) answering the 7 core business questions with a full claims evidence drawer.
  * Functional launcher `run_app.bat` that detects `.venv`, starts Uvicorn on `127.0.0.1:8000`, and opens the default browser.
  * Automated 19 UI preview tests in `tests/test_stage2_5_preview.py` (total 62 passing workspace tests).
* **Strict Non-Goals Preserved:**
  * Zero mutation/write APIs implemented.
  * Zero final scoring or matching algorithms implemented.
  * Zero fake loads, zero fake trucks, zero fake demand signals introduced.
  * Zero AI SDKs, external search APIs, or token consumption.

---

### Stage 3: Backend API, Scoring Engines & Matching Logic — [ PENDING APPROVAL ]
* **Objective:** Implement the FastAPI application layer, independent commercial scoring engines, scoped suppression filtering, and specific load-to-capacity matching.
* **Key Tasks:**
  * Implement REST endpoints for prospects, contacts, signals, loads, carriers, and capacity.
  * Implement independent Prospect Priority (0–100), Conversion Ease (0–100), and Gross Margin engines.
  * Implement scoped suppression (Company, Facility, Company-Lane, Facility-Lane, Global-Lane).
  * Implement tri-state compatibility matching (`COMPATIBLE`, `INCOMPATIBLE`, `UNKNOWN`).
  * Implement state-dependent validation for loads transitioning to `CONFIRMED_AVAILABLE_NOW`.
* **Testing Gates:**
  * Verify `UNKNOWN` claims contribute exactly 0 points.
  * Verify missing rate inputs yield `Margin = UNKNOWN` without errors.
  * Verify undated demand signals cannot qualify for `SIGNAL_LAST_30_DAYS`.
  * Verify deterministic expiry derives from timestamps on read without background workers.

---

### Stage 4: Five-Screen Browser UI Implementation — [ FUTURE STAGE ]
* **Objective:** Build the local, responsive browser interface using locally served CSS and vendored Alpine.js.
* **Key Screens:**
  * *Screen 1: Shortlist Cockpit* (branching on Decision B phone-first layout and Decision E fleet visibility).
  * *Screen 2: Master Directory* (full search, filters, claims/evidence drawer).
  * *Screen 3: Loads & Margins* (discrete loads, demand signals, margin calculator).
  * *Screen 4: Carriers & Capacity* (roster, lane activity, specific load $\leftrightarrow$ capacity matcher).
  * *Screen 5: Settings & Geo Controls* (branching on Decision A Alaska toggle, scoring weight tuner, local DB backup button).
* **Testing Gates:**
  * Verify zero runtime CDN requests in browser network tab.
  * Verify full interactivity and layout rendering in offline mode.

---

### Stage 5: End-to-End Walkthrough & Delivery — [ FUTURE STAGE ]
* **Objective:** Conduct a complete operational prospecting cycle and verify backup durability.
* **Key Tasks:**
  * Review audited seed lead $\rightarrow$ log phone call $\rightarrow$ promote contact from general to direct $\rightarrow$ record freight demand signal $\rightarrow$ create discrete load opportunity $\rightarrow$ match specific capacity posting $\rightarrow$ verify margin calculation.
  * Verify timestamped database backup creation at `D:\FreightProspecting\data\backups\`.
