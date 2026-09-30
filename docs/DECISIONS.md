# FreightProspecting V1 — Decisions & Architecture Log

* **Date Established:** 2026-09-26  
* **Architecture Freeze Baseline:** Revision 4.1 (Schema Freeze Candidate)

---

## 1. Confirmed User Decisions (A through H)

### Decision A: Geography / Alaska Boundary
* **Status:** **CONFIRMED**
* **Decision:** Alaska is **EXCLUDED by default** from normal V1 prospecting queries.
* **Core V1 Geography:** Lower 48 US domestic, Canada domestic, US $\rightarrow$ Canada, Canada $\rightarrow$ US. Hawaii and Mexico are hard exclusions.
* **Rationale:** OTR freight to/from Alaska requires either Alcan Highway bonded transit through BC/Yukon (2,500+ miles, severe winter equipment) or Puget Sound marine barge connection. The application preserves the ability to add an Alaska toggle in Settings later, but Alaska is not part of standard V1 prospecting.

### Decision B: Outreach Workflow Emphasis
* **Status:** **CONFIRMED**
* **Decision:** **PHONE-FIRST**, with full preservation of verified business emails.
* **Rationale:** Freight brokerage prospecting relies heavily on calling plant shipping desks, asking gatekeepers for outbound traffic coordinators, and negotiating rates verbally. The UI must prioritize phone numbers, extensions, call logging, gatekeeper/decision-maker outcome tracking, and call notes, while also preserving verified emails and introductory email generation.

### Decision C: Seed Candidate 4 Approval
* **Status:** **CONFIRMED**
* **Decision:** **WMG Technologies (Windsor, ON)** is approved as the replacement Seed Candidate 4.
* **Condition:** Before actual insertion in Stage 2, re-verify WMG's precise current 2026 legal/organizational placement inside the TI Automotive group. Historical acquisition events remain `VERIFIED`; unresolved present-day hierarchy remains `UNKNOWN` until verified.

### Decision D: Initial Database Seeding Policy
* **Status:** **CONFIRMED**
* **Decision:** Use the approved audited proof-of-schema seed set (**Beasley, Kenwal, DECAST, WMG**) when Stage 2 occurs.
* **Condition:** Do NOT insert any seed records during Stage 1. Stage 1 remains strictly documentation, asset vendoring, and project foundation.

### Decision E: Verified Private-Fleet Treatment
* **Status:** **CONFIRMED**
* **Decision:** Verified private-fleet companies remain **VISIBLE by default** on the Shortlist.
* **Rationale:** A company operating proprietary equipment (e.g. Beasley Logistics, DECAST AZ drivers) often supplements with outside commercial flatbeds or brokers for overflow, seasonal volume, and backhaul lanes. The UI must display a prominent "Private Fleet" badge and allow fleet presence to influence ranking through configurable rules, but fleet owners are never silently hidden.

### Decision F: Customer & Suppression Import Strategy
* **Status:** **CONFIRMED**
* **Decision:** V1 starts with **MANUAL entry** for existing customer, already routed, and do-not-contact statuses.
* **Rationale:** The user has not provided an existing customer list or approved an import file format. Bulk CSV import is deferred; no CSV specification is frozen or implemented during Stage 1.

### Decision G: Approved V1 Technical Stack
* **Status:** **CONFIRMED**
* **Decision:** The approved local V1 stack consists of:
  * Python 3.11+ (verified under Python 3.13.7)
  * FastAPI
  * SQLite with Write-Ahead Logging (WAL mode)
  * Local browser UI with 100% locally served CSS
  * Locally vendored Alpine.js (v3.14.8, zero CDN runtime dependencies)
  * Five-screen navigation architecture (Shortlist, Master Directory, Loads & Margins, Carriers & Capacity, Settings)
  * Windows desktop launcher (`run_app.bat`)

### Decision H: Confirmed No-Paid-AI-API Requirement
* **Status:** **CONFIRMED USER REQUIREMENT**
* **Decision:** FreightProspecting V1 **MUST function without requiring**:
  * Gemini API
  * OpenAI API
  * Google Search API
  * Paid AI APIs or LLM subscriptions
  * Paid programmable search APIs
  * Any user-supplied AI API key
* **Rationale & Operational Rules:**
  1. FreightProspecting is a local research database, prospecting workspace, evidence ledger, outreach tracker, and matching tool. Normal local operation does not depend on an external AI service.
  2. All core features (viewing/searching prospects, recording claims, logging calls/emails, scoring, suppression, margin calculations, loads, carriers, capacity matching, public structured data refreshes, backups, local UI) work 100% locally without AI.
  3. External web research is supported via standard browser links (e.g. "Open Google Search", "Open Company Website", "Open FMCSA"), requiring zero programmable search API dependencies.
  4. Optional consumer Gemini research through the user's logged-in Google AI Pro account in a standard browser tab is strictly a manual human-in-the-loop workflow (copy research prompt, paste findings). It is not an automated programmatic API integration and must not attempt to scrape or automate consumer logins.
  5. Any future optional AI capabilities must degrade gracefully to standard non-AI operation.

---

## 2. Mandatory SQLite Implementation Errata

The following implementation errata are frozen and must be strictly adhered to during Stage 2 database creation:

### Erratum 1: Nullable Enums & Check Constraints
* **Problem:** In SQLite, `CHECK(value IN ('A', 'B', NULL))` does not evaluate as intended in SQL three-valued logic.
* **Mandatory Rule:** All nullable enum fields must use explicit `IS NULL` disjunctions:
  ```sql
  CHECK(value IS NULL OR value IN ('A', 'B'))
  ```
* **Application:** Must be applied across all nullable categorical columns (e.g., `equipment_required`, `operating_status`, `cross_border_capability`).

### Erratum 2: Date & Timestamp Validation
* **Problem:** SQLite uses dynamic type affinity and does not enforce date/time formats in `DATETIME` or `DATE` columns, allowing invalid text strings to be stored silently.
* **Mandatory Rule:** 
  1. All timestamps must be stored as canonical **ISO-8601 strings** (`YYYY-MM-DDTHH:MM:SSZ` or `YYYY-MM-DD`).
  2. The application/service layer must strictly validate all date/time inputs prior to database execution.
  3. Placeholder strings such as `"Active"`, `"Current"`, or `"N/A"` are **strictly forbidden** inside timestamp or date columns. Currentness is represented solely via boolean validity flags (`is_current_accepted = 1`) or time ranges.

---

## 3. Architecture Rules & Frozen Invariants

1. **Field-Level Provenance:** Every factual claim has an explicit verification status: `VERIFIED`, `INFERRED`, or `UNKNOWN`. Whole records are never labeled "verified."
2. **Neutrality of Unknowns:** `UNKNOWN` claims always contribute exactly 0 points across all ranking calculations.
3. **Single Current Claim Invariant:** For one specific subject entity and one `claim_field`, no more than one claim may have `is_current_accepted = 1` simultaneously. Enforced via SQLite partial unique indexes.
4. **Historical Claim Preservation:** Accepting a newer claim atomically sets `is_current_accepted = 0` on the older claim. Historical claims and contradictory evidence are never deleted.
5. **Decoupled Time Concepts:** `source_published_at` (publication), `event_at` (event occurrence), and `observed_at` (research inspection) remain independent.
6. **Decoupled Contact Directness:** Contact identity (`NAMED_PERSON`) is decoupled from communication channel directness (`GENERAL_SWITCHBOARD`).
7. **Demand Signal Decoupling:** Operational evidence (Category A: job ads, dock hours) never creates a freight demand signal (Category B).
8. **Carrier Authority Default:** Unverified carrier authority and safety ratings default strictly to `UNKNOWN`, never `AUTHORIZED` or `NONE`.
9. **Tri-State Match Compatibility:** Match dimensions are modeled as `COMPATIBLE`, `INCOMPATIBLE`, or `UNKNOWN`.
10. **Deterministic Expiry:** Time-dependent status (`CONFIRMED_AVAILABLE_NOW`, `TRUCK_CONFIRMED_AVAILABLE_NOW`, `SIGNAL_LAST_30_DAYS`) derives from raw timestamps at query time, preventing time drift when the PC is powered off.
11. **Scoped Suppression:** Suppression supports `COMPANY`, `FACILITY`, `COMPANY_LANE`, `FACILITY_LANE`, and `GLOBAL_LANE`.
12. **Policy vs. Suppression:** `broker_friendly_status = 'VERIFIED_DIRECT_ONLY'` does not create `DO_NOT_CONTACT`.
13. **Margin Rule:** Missing rates result in `Margin = UNKNOWN`. Missing rates never exclude an opportunity.
14. **No Paid AI APIs Required:** All core functionality operates standalone, offline-capable on the local machine without requiring external AI or search API keys.

---

## 4. Configurable Proposals (Stage 3 Tuning)

The following items are design proposals that will be implemented as configurable parameters rather than immutable business rules:

1. **Scoring Factor Numerical Weights:** Default proposals (+30 for commodity fit, +25 for broker acceptance, +20 for no fleet, etc.) are stored in the `settings` table and can be adjusted in the UI.
2. **Status Multipliers:** Proposing `VERIFIED = 1.0` and `INFERRED = 0.5` remains a configurable setting per factor.
3. **Suppression Import Schema:** A proposed 5-column CSV layout remains deferred for user review prior to Stage 4.
