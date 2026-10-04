# Carrier & Capacity Network Module — Shipper IQ

## 1. Executive Summary & Core Philosophy

Shipper IQ began as a broker prospecting and evidence tracking platform focusing on the shipper side of freight brokerage:
$$\text{Shipper} \longrightarrow \text{Facility} \longrightarrow \text{Contact} \longrightarrow \text{Evidence} \longrightarrow \text{Freight / Load Opportunity}$$

The **Carrier & Capacity Network** adds the complementary carrier side:
$$\text{Carrier} \longrightarrow \text{Authority / Verification} \longrightarrow \text{Equipment} \longrightarrow \text{Available Capacity} \longrightarrow \text{Preferred Lanes} \longrightarrow \text{Business Contacts} \longrightarrow \text{Carrier Outreach}$$

These two distinct domains connect exclusively through:
$$\text{Discrete Load} \longleftrightarrow \text{Available Capacity} \longleftrightarrow \text{Deterministic Match} \longleftrightarrow \text{Quote} \longleftrightarrow \text{Booking}$$

### Core Invariants Preserved
1. **Strict Entity Separation**: Shippers and carriers are never conflated into a single polymorphic entity. A facility prospect exists independently of active freight demand; a carrier directory entry exists independently of live truck capacity.
2. **Deterministic Matching**: Zero opaque AI/ML scoring. 100% deterministic, explainable, and testable business logic.
3. **Neutrality of `UNKNOWN`**: Missing information contributes 0 points (strictly neutral) and is never penalized with negative points.
4. **Append-Only Outreach**: Database triggers strictly forbid `UPDATE` and `DELETE` on outreach history records.
5. **Quote History Preservation**: Counteroffers and rate negotiations append new quote rounds; historical quotes are never overwritten.
6. **Zero-Scraping Compliance**: No automated scraping of third-party subscription load boards (DAT, Truckstop, 123Loadboard, Trucker Path, Loadlink). Direct FMCSA SAFER official query builder and manual intake only.

---

## 2. Domain Model & Relational Schema

### A. Extended Tables
- **`carriers`**: Legal entity profile extended with physical address, phone, email, website, driver count, cargo categories, FMCSA authority status (`VERIFIED_AUTHORIZED`, `VERIFIED_NOT_AUTHORIZED`, `VERIFIED_OUT_OF_SERVICE`, `UNKNOWN`), verification timestamps, and cross-border capability (`US_ONLY`, `CANADA_ONLY`, `US_CANADA_CAPABLE`, `UNKNOWN`).
- **`carrier_lane_activity`**: Historical and preferred lane routes (`DISPATCHER_PREFERRED`, `RECURRING_LANE`) with origin/destination regions and equipment types.
- **`capacity_postings`**: Live truck postings with status (`TRUCK_CONFIRMED_AVAILABLE_NOW`, `POSTED_TENTATIVE`, `COVERED_BOOKED`, `EXPIRED`), available date windows, origin city/state, destination preferences, desired rates, and expiration timestamps.
- **`load_capacity_matches`**: Explicit relational join between `load_opportunities` and `capacity_postings` with match scoring, workflow statuses (`CANDIDATE`, `CONTACTED`, `QUOTED`, `ACCEPTED`, `REJECTED`, `BOOKED`), agreed rates, and booking timestamps.

### B. Dedicated Carrier Tables
- **`carrier_assignments`**: Exclusive broker ownership table (`carrier_id`, `owner_id`, `updated_at`).
- **`carrier_assignment_history`**: Audit trail of ownership changes (`CLAIM`, `TRANSFER`, `RELEASE`).
- **`carrier_engagement_state`**: Single-row projection per carrier recording relationship status (`UNCONTACTED`, `INTERESTED`, `CALL_BACK`, `NO_ANSWER`, `NOT_INTERESTED`), attempt count, and callback schedules.
- **`carrier_outreach_logs`**: Append-only log of carrier telephone/email interactions enforced by SQLite triggers (`trg_carrier_outreach_logs_no_update`, `trg_carrier_outreach_logs_no_delete`, `trg_carrier_outreach_logs_no_replace`).
- **`carrier_quotes`**: Preserved historical record of rate quotes across negotiation rounds (`INITIAL`, `COUNTER`, `FINAL`, `OFFERED`, `ACCEPTED`, `REJECTED`, `SUPERSEDED`).
- **`carrier_suppressions`**: Scoped suppression records preventing outreach or matching at three levels:
  - `CARRIER`: Suppress all interactions with a specific carrier.
  - `CONTACT`: Suppress a specific individual contact.
  - `LANE`: Suppress a specific origin-destination corridor.

---

## 3. Deterministic Matching Engine

The matching engine in `src/backend/matching/engine.py` evaluates candidate capacity postings against discrete load opportunities through a two-stage deterministic pipeline.

### Stage 1: Hard Exclusions (Binary Pass/Fail)
A candidate is immediately disqualified (score = 0%) if any of the following apply:
1. **Operating Authority**: Carrier is known `VERIFIED_NOT_AUTHORIZED` or `VERIFIED_OUT_OF_SERVICE`.
2. **Capacity Staleness**: Capacity is `EXPIRED` or available date end is in the past.
3. **Equipment Incompatibility**: Flatbed load matched against Dry Van, or vice versa (Step Deck is permitted for Flatbed cargo if compatible).
4. **Date Window Overlap**: Capacity ends before earliest pickup, or capacity begins after latest pickup.
5. **Cross-Border Mismatch**: Load crosses US-Canada international border, but carrier is `US_ONLY` or `CANADA_ONLY`.
6. **Scoped Suppression**: Carrier, contact, or lane has an active `DO_NOT_CONTACT` or `DO_NOT_USE` suppression record.

### Stage 2: Deterministic Scoring (0 to 100 Points)
For candidates passing hard exclusions, compatibility points are awarded additively:
- **Equipment Fit (up to 25 pts)**: Exact equipment match = 25 pts; Step Deck for Flatbed = 15 pts.
- **Origin Proximity (up to 25 pts)**: Calculated via Haversine great-circle distance.
  - $\le 50\text{ miles}$: 25 pts
  - $\le 125\text{ miles}$: 20 pts
  - $\le 250\text{ miles}$: 12 pts
  - $> 250\text{ miles}$ / Same State fallback: 18 pts
- **Destination / Preferred Lane Fit (up to 20 pts)**: Exact destination city match = 20 pts; destination state match = 15 pts; preferred lane match = 20 pts; preferred destination region = 10 pts.
- **Pickup Timing Overlap (up to 15 pts)**: Available on exact pickup date = 15 pts; window covers pickup = 10 pts.
- **Verified Authority (up to 10 pts)**: Active authority verified with FMCSA = 10 pts.
- **Capacity Freshness (up to 5 pts)**: Posted or reconfirmed within 24 hours = 5 pts; within 72 hours = 3 pts.
- **Commercial Rate Fit (up to 10 pts)**: Evaluated *only* when both target cost and carrier desired rate/quote are known. If within target cost = 10 pts; within 8% spread = 5 pts. If rates are unknown, contributes neutral 0 pts.

---

## 4. Source Adapter Architecture

Defined in `src/backend/adapters/carrier_sources.py`:
- `CarrierSourceAdapter`: Abstract interface specifying `lookup_carrier()` and `fetch_available_capacity()`.
- `ManualCarrierAdapter`: Validates user-entered carrier profiles and equipment.
- `FmcsaOfficialAdapter`: Generates official public web lookup URLs for FMCSA SAFER (`https://safer.fmcsa.dot.gov/query.asp`). Zero automated scraping or hammering of FMCSA infrastructure.
- `DisabledCommercialAdapter`: Clear, compliance-safe disabled stubs for DAT, Truckstop, Trucker Path, 123Loadboard, and Loadlink that raise descriptive errors explaining that automated scraping of commercial subscription boards is prohibited without official licensed API credentials.

---

## 5. Web User Interface & Workflows

1. **Carrier Directory (`/carriers`)**:
   - Live metrics summary pills (Total Carriers, Verified Active, Live Capacity, My Carriers).
   - Multi-group filtering: Ownership (`all`, `mine`, `unassigned`), Authority Status, Primary Equipment, Country (`US`, `CA`), and Capacity availability.
   - Card grid with direct dispatch phone, FMCSA verification status badge, power unit counts, and equipment tags.
   - Modal for adding new carriers with instant deduplication.

2. **Carrier Detail Profile (`/carriers/{id}`)**:
   - Header with legal name, DBA, DOT#, MC#, and 1-click external link to official FMCSA SAFER profile.
   - "Start Working" exclusive claim button with conflict detection.
   - Business contacts tab with direct desk/switchboard badges and primary contact indicator.
   - Equipment and preferred lanes tab.
   - Available capacity tab with quick "+ Post Capacity" modal.
   - Complete outreach timeline displaying call outcomes and notes.
   - Preserved quotes tab across discrete loads.

3. **Available Trucks Workspace (`/capacity`)**:
   - Filterable truck board by origin city/state, destination preference, equipment, and availability date.
   - Direct link to carrier profiles and 1-click "Book Load" workflow.

4. **Discrete Loads & Gross Margin Analysis (`/loads`)**:
   - Clear visual separation between physical shipper prospects and bookable discrete loads.
   - Real-time gross margin and margin percentage display ($ = \text{Shipper Rate} - \text{Carrier Cost}$).
   - "+ Create Load" modal with honest copy explaining that missing rates remain neutral and never invalidate an intake.

5. **Load-to-Capacity Match Workspace (`/loads/{id}/matches`)**:
   - Origin-destination banner, equipment requirement, and pickup date window.
   - Ranked candidate capacity postings sorted by deterministic match score.
   - Score badges (90–100% High, 70–89% Moderate, <70% Marginal) accompanied by full bullet-point explainability factor breakdown.
   - Inline quote entry and instant "Book Load" action with cascade status updates.

---

## 6. Verification & Test Architecture

- **Pytest Suite (`tests/test_carrier_network.py`)**:
  - `test_carrier_schema_migration_is_idempotent`: Idempotent schema upgrades and trigger integrity.
  - `test_carrier_creation_and_deduplication`: USDOT and MC number deduplication.
  - `test_append_only_carrier_outreach_logs`: Verified SQLite trigger blocks `UPDATE` and `DELETE` on `carrier_outreach_logs`.
  - `test_carrier_quotes_preservation`: Multi-round quote preservation without history loss.
  - `test_carrier_suppression_blocks_matching`: Scoped suppression prevents matching.
  - `test_matching_engine_hard_exclusions`: Hard exclusion filtering (equipment, authority, cross-border, timing, UNKNOWN neutrality).
  - `test_team_ownership_and_exclusive_claim`: Exclusive broker ownership with HTTP 409 Conflict protection.
  - `test_carrier_api_endpoints`: Full HTTP client validation across routes.
- **End-to-End Workflow QA (`scratch/e2e_carrier_workflow.py`)**:
  - 14-step multi-broker journey covering admin login, carrier creation, capacity posting, truck searching, exclusive claiming, outreach logging, load creation, deterministic matching, multi-round quoting, and load booking.
- **Performance Benchmark (`scratch/benchmark_carrier_network.py`)**:
  - Carrier Directory Query: **0.41 ms** average (P95: 0.76 ms)
  - Available Trucks Query: **0.28 ms** average (P95: 0.43 ms)
  - Match Engine Query: **0.07 ms** average (P95: 0.09 ms)
