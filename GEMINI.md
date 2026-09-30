# FreightProspecting — Workspace Project Rules

> **Workspace Path**: `D:\FreightProspecting`  
> **Status**: Frozen Architecture Baseline (Revision 4.1, Stage 1 / Stage 1.1 Complete)  
> **Rule Scope**: Applies to all coding, planning, debugging, and data workflows in this workspace.

---

## 1. Business Purpose & Operating Philosophy

- **Application Purpose**: A personal, beginner-friendly, local browser application for freight brokerage prospecting, evidence tracking, outreach workflow, load/capacity matching, and gross margin analysis.
- **Quality Over Quantity**: Target a curated, high-converting shortlist of approximately 100 evidence-backed shipper prospects rather than thousands of low-yield, unverified cold leads.
- **Core Stance**: Zero hallucination, field-level provenance, strict time semantics, and deterministic business logic.

---

## 2. Freight & Equipment Scope

- **Target Equipment**: Full Truckload (FTL) **Flatbed**, **Step Deck**, and **Dry Van**.
- **Trailer Length Invariant**: Trailer length (48-ft vs 53-ft) is an equipment/load capacity attribute, **never** a hard "53-ft only" restriction. Both 48' and 53' configurations are valid and must be modeled as attributes.
- **Excluded Commodities/Categories (Hard Exclusions)**:
  - Hazardous materials (Hazmat / Placarded).
  - High-value precious cargo (Jewelry, bullion, currency).
  - Live animals / livestock.
  - Fresh seafood / raw fish.
  - Refrigerated / Temperature-controlled target categories (Reefer is out of primary V1 scope).

---

## 3. Geographic Scope & Boundaries

- **Eligible Territory**:
  - Domestic US Lower 48 states.
  - Domestic Canada (10 provinces).
  - US $\leftrightarrow$ Canada cross-border lanes.
- **Hard Exclusions**:
  - Hawaii (no truckload service).
  - Mexico (out of V1 operational and regulatory scope).
- **Confirmed User Decision A (Alaska)**:
  - **Alaska is excluded by default in V1**.
  - All standard prospecting, lane matching, and search defaults exclude Alaska unless the user explicitly enables an Alaska override toggle.

---

## 4. Outreach Principles & Channels

- **Confirmed User Decision B (Channel Strategy)**:
  - **Phone-first prospecting**: A verified direct phone number or direct extension is the highest-value outreach asset.
  - **Email remains supported and important**: Valid email addresses are preserved, displayed, and actionable for follow-ups, quotes, and rate confirmations.
- **Gatekeeper Navigation**: Distinguish clearly between general corporate switchboards (with gatekeepers) and direct logistics desk / dock lines.

---

## 5. Zero-Hallucination & Field-Level Provenance Standards

- **Strict Fabrication Prohibition**:
  - **NEVER** invent contact names, job titles, direct telephone numbers, phone extensions, email addresses, directness indicators, broker acceptance, load availability, freight rates, fleet counts, carrier authority, or parent-subsidiary relationships.
- **Field-Level Claim Statuses**:
  - `VERIFIED`: Confirmed by primary-source documentation (e.g., official corporate website, SEC filing, state corporate registry, direct phone confirmation).
  - `INFERRED`: Derived logically from verified operational evidence (e.g., steel pipe manufacturing strongly infers flatbed suitability). Must be marked as inferred.
  - `UNKNOWN`: Insufficient evidence. Default state for unverified fields.
- **Scoring Invariant for `UNKNOWN`**:
  - `UNKNOWN` is neutral (0 points). It is **never** penalized with negative points.
- **Absence of Evidence Invariant**:
  - Absence of evidence is **not** evidence of absence. (e.g., Not seeing a private fleet mentioned on a shipper's homepage does **not** equal "No private fleet").

---

## 6. Core Entity Separations & Reality Distinctions

The application enforces ten non-negotiable real-world distinctions:

1. **Company $\neq$ Facility**:
   - `companies` = Corporate legal entity (headquarters, ownership, credit, policies).
   - `facilities` = Physical shipping/receiving locations (docks, physical loading requirements, dock hours).
2. **Shipper Prospect $\neq$ Freight-Demand Signal $\neq$ Discrete Load**:
   - A facility prospect exists independently of active demand.
   - An observed signal (job posting, plant expansion, RFP announcement) indicates potential freight activity.
   - A discrete load is an actual, bookable transportation requirement with origin, destination, and pickup timeframe.
3. **Carrier Directory $\neq$ Historical Lane Activity $\neq$ Capacity Posting**:
   - Carrier directory = Registered trucking company profile and safety record.
   - Lane activity = Historical routes or regular commercial runs.
   - Capacity posting = A specific truck confirmed available on a given lane/date.
4. **Specific Match Invariant**:
   - A valid match exists **only** between an actual `load_opportunity` and an actual `capacity_posting`.
   - Never match a vague facility prospect directly to a general carrier directory entry.
5. **Category A Operational Evidence $\neq$ Category B Freight-Demand Signal**:
   - Category A = General facility operations (forklift driver hiring, dock hours, shipping receiving contacts).
   - Category B = Verified freight demand (outbound shipping coordinator hiring, third-party logistics tenders, freight RFP notices).
6. **Commercial Carrier Use $\neq$ Broker Acceptance**:
   - Evidence that a company uses commercial carriers (e.g., seeing Werner or Schneider trailers at their dock) does **not** prove they work with freight brokers.
7. **Equipment Suitability Inference $\neq$ Verified Equipment Usage**:
   - An inference that structural steel requires flatbeds remains `INFERRED` until verified by shipping instructions or bills of lading.
8. **Named Person $\neq$ Direct Communication Channel**:
   - Knowing an executive's name does not mean having their direct phone or email. Directness must be verified separately.
9. **Direct-Only Broker Policy $\neq$ Do-Not-Contact Customer Suppression**:
   - A company policy stating "We only deal with asset carriers directly" is an operational policy note, not an exclusion/blacklist suppression.
10. **Time Distinction (`observed_at` $\neq$ `event_at` $\neq$ `source_published_at`)**:
    - The date an agent reads a webpage is **not** the date the event happened or the date the document was published.

---

## 7. Evidence, Claims & Relational Integrity

- **Prohibition of Polymorphic Foreign Keys**: Polymorphic `(entity_type, entity_id)` patterns are forbidden.
- **Subject Relational Integrity**: The `claims` table contains exactly 10 explicit nullable foreign keys:
  1. `company_id`
  2. `company_relationship_id`
  3. `facility_id`
  4. `facility_commodity_id`
  5. `contact_id`
  6. `freight_demand_signal_id`
  7. `load_opportunity_id`
  8. `carrier_id`
  9. `carrier_lane_activity_id`
  10. `capacity_posting_id`
- **Exact-1 Check Constraint**: Every claim row must reference exactly one subject:
  ```sql
  CHECK (
    (CASE WHEN company_id IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN company_relationship_id IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN facility_id IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN facility_commodity_id IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN contact_id IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN freight_demand_signal_id IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN load_opportunity_id IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN carrier_id IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN carrier_lane_activity_id IS NOT NULL THEN 1 ELSE 0 END +
     CASE WHEN capacity_posting_id IS NOT NULL THEN 1 ELSE 0 END) = 1
  )
  ```
- **Single Current Accepted Claim Invariant**:
  - At most one claim per subject + `claim_field` may have `is_current_accepted = 1`.
  - Enforced via SQLite partial unique indexes: `WHERE is_current_accepted = 1`.
  - When a newer claim is accepted, the previously accepted claim is atomically changed to `is_current_accepted = 0`.
  - The historical claim remains preserved in the claims ledger; no hard deletion of superseded evidence/claim history during ordinary supersession.
- **Offline Evidence Support**: `evidence_records.source_url` is **nullable** to support phone conversations, direct emails, and site visits.

---

## 8. Three-Dimensional Time Model

1. **`source_published_at`**: Timestamp when the primary source document/article was officially published.
2. **`event_at`**: Timestamp when the real-world event occurred.
   - For persistent facts (e.g., facility address, corporate headquarters phone), `event_at` is `NULL`.
   - **Never** store text strings like "Active", "Current", "Recent", or "N/A" into timestamp fields.
3. **`observed_at`**: Timestamp when the information was retrieved or verified by the user/system.
- **Signal Freshness & Decay**:
  - Demand signals decay in priority: $\le 30\text{ days}$ (Fresh/Active), $31\text{--}60\text{ days}$ (Aging), $> 60\text{ days}$ (Stale).
  - Calculations for "Signals in last 30 days" must strictly use `event_at` (or `observed_at` if `event_at` is null).

---

## 9. Freight-Demand Signals vs. Discrete Loads

- **No Placeholder Loads**: A facility without confirmed freight must never have a dummy load record created.
- **`freight_demand_signals`**: Records signals such as hiring spikes, facility expansions, shipping tenders, or load board chatter.
- **State-Dependent Validation for `load_opportunities`**:
  - `IDENTIFIED`: Initial intake stage. Permits missing/unknown pickup dates or rates while researching.
  - `CONFIRMED_AVAILABLE_NOW`: Strict validation. Mandatory fields include:
    - Verified origin and destination locations.
    - Verified equipment type.
    - Explicit pickup date window.
    - Verified operational requirements and expiry timestamp.

---

## 10. Carrier Directory, Lane Activity & Capacity Postings

- **Carrier Safety & Authority**:
  - Operating authority defaults to `UNKNOWN` until verified via FMCSA SAFER.
  - **Never** default carrier status to `AUTHORIZED`.
- **Match Compatibility Logic (Tri-State)**:
  - Equipment and lane compatibility must evaluate to `COMPATIBLE`, `INCOMPATIBLE`, or `UNKNOWN`.
- **Cross-Border Capability**:
  - Explicitly classified as `US_ONLY`, `CANADA_ONLY`, `US_CANADA_CAPABLE`, or `UNKNOWN`.
  - A domestic-only carrier must **never** be matched to a cross-border load.

---

## 11. Commercial Metrics & Margin Policy

Keep three separate concepts:

- **A. Prospect Priority**:
  - Configurable explainable heuristic for deciding which prospect is worth attention.
  - May use approved evidence-backed factors.
  - Exact factors, weights, and multipliers remain configurable implementation settings unless explicitly approved.
- **B. Conversion Ease**:
  - Configurable explainable heuristic for estimating how easy/frictionless a prospect may be to convert.
  - Never represented as a proven probability.
  - Exact factors and weights remain configurable unless explicitly approved.
- **C. Gross Margin**:
  - Actual estimated financial spread for a discrete load when both rates are known:
    $$\text{Gross Margin} = \text{Shipper Target Rate} - \text{Carrier Target Cost}$$
    $$\text{Margin \%} = \frac{\text{Gross Margin}}{\text{Shipper Target Rate}} \times 100$$
  - If either shipper rate or carrier cost is missing:
    $$\text{Margin} = \text{UNKNOWN}$$
  - Independent of Priority and Conversion Ease.
  - **Confirmed Margin Rules**:
    - There is NO hard minimum margin requirement in V1.
    - Do not invent a minimum acceptable percentage.
    - Do not exclude a load merely because its margin is low.
    - Do not automatically demote a load because of an arbitrary threshold.
    - Known loads/opportunities may be sorted by actual estimated gross margin.
    - Future warning thresholds, target margins, or commercial preferences may be configurable only if explicitly approved later.
    - Missing margin information never becomes zero.

- **Confirmed Universal Scoring Rules**:
  - `UNKNOWN` contributes 0 points (neutral).
  - Do not invent scoring factors.
  - Do not hardcode unapproved weights.
  - Do not hardcode universal INFERRED multipliers.
  - Do not use arbitrary margin thresholds.
  - Do not automatically exclude private-fleet companies.
  - Missing data must not become a negative merely because it is missing.
  - If examples of possible scoring factors are kept in documentation, clearly label them as examples/proposals rather than confirmed rules.

---

## 12. Scoped Suppression System & Shipper Visibility

To prevent contacting restricted shippers or bidding on conflicting lanes, suppressions are evaluated across 5 scopes:
1. `COMPANY`: Suppress all facilities and contacts for an entire company.
2. `FACILITY`: Suppress a single physical shipping facility.
3. `COMPANY_LANE`: Suppress a specific origin-destination lane for a given company.
4. `FACILITY_LANE`: Suppress a specific origin-destination lane for a given facility.
5. `GLOBAL_LANE`: Suppress an entire geographic lane across all shippers (e.g., restricted corridors).

- **Manual V1 Suppression**: Customer, facility, and lane suppressions are entered manually via the UI in V1; no automated suppression scrapers.
- **Private-Fleet Visibility Invariant**: Shippers operating private fleets remain visible by default in prospecting views. Operating a private fleet is an operational evidence attribute, never an automatic exclusion or filter.

---

## 13. No-Paid-AI-API Requirement (Confirmed Decision H)

- **Strict Prohibition**: FreightProspecting V1 **must function completely without**:
  - Gemini Developer API
  - OpenAI API
  - Google Search API
  - Any paid AI or commercial search API
  - Any user-supplied API key
- **Pure Local Determinism**:
  - The local application is 100% deterministic Python, FastAPI, SQLite, Jinja2, and Alpine.js.
  - No background AI calls, automated LLM scrapers, or token consumption.
- **Browser Assistance Flow**:
  - The UI provides one-click Google Search launch buttons that open standard search queries in the user's regular browser.
  - The user can paste text or use consumer Gemini in Google AI Pro in their personal browser as a manual assistant.
  - The application provides structured forms and clipboard-paste helpers to ingest evidence manually.

---

## 14. Source Access & Compliance Policies

- **FMCSA SAFER**: No automated scraping or hammering of FMCSA servers. Manual lookups or official static data only.
- **Unverified Third-Party Directories**: Treat commercial lead aggregators with caution; require primary-source confirmation before setting claims to `VERIFIED`.
- **Offline Records**: Respect user manual notes from phone outreach, emails, and direct quotes.

---

## 15. Technical Stack & SQLite Implementation Errata

- **Language & Environment**: Python 3.13.7 in `D:\FreightProspecting\.venv`.
- **Backend**: FastAPI, Uvicorn, Jinja2, Pydantic v2.
- **Frontend**: Local HTML/CSS, vendored Alpine.js v3.14.8 (`static/js/vendor/alpine.min.js`), no external CDN dependencies.
- **Database**: SQLite 3 with WAL mode and `PRAGMA foreign_keys = ON`.
- **SQLite Syntax Errata**:
  - Nullable enum columns must use `CHECK(col IS NULL OR col IN ('VAL1', 'VAL2'))`.
  - Date and timestamp columns store canonical ISO-8601 strings (`YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ`), validated at the Pydantic/service layer.

---

## 16. Workspace Safety & Workflow Discipline

- **Stage Discipline**:
  - **Stage 1 & 1.1**: Workspace Foundation, Documentation & Dependencies (COMPLETE).
  - **Stage 2**: Database Schema, Claims Engine & Seed Ingestion (PENDING USER APPROVAL).
  - **Stage 3**: FastAPI Services & Deterministic Business Logic.
  - **Stage 4**: Web UI & Prospecting Workflow Screens.
  - **Stage 5**: Validation, Testing & Hardening.
- **Audited Seed Dataset & Seed 4 Approval**:
  - The approved four proposed/audited Stage 2 seeds remain:
    1. Beasley Forest Products / Beasley Group
    2. Kenwal Steel Corp. (Dearborn Steel Service Center, 8223 W. Warren, Dearborn, MI 48126)
    3. DECAST Ltd.
    4. WMG Technologies
  - WMG Technologies still requires current 2026 corporate-hierarchy re-verification before actual database insertion.
- **Execution Guardrails**:
  - Do **not** create `prospects.db`, initialize database tables, or write business code during planning or learning turns.
  - Do **not** modify files outside `D:\FreightProspecting`.
  - Always verify existing workspace contents before modifying code.
