# FreightProspecting V1 — Project Brief

## 1. Project Purpose & Scope

**FreightProspecting** is a beginner-friendly, local browser application designed for personal use as a freight brokerage prospecting and capacity-matching assistant on Windows, residing entirely at `D:\FreightProspecting`.

Its primary mission is to serve as a local:
* **Research database**
* **Prospecting workspace**
* **Evidence & claims ledger**
* **Outreach tracker**
* **Discrete load & capacity matching tool**

It identifies promising industrial manufacturing facilities with full-truckload (FTL) transportation requirements, tracks qualified motor carrier capacity, connects with genuine business personnel, and tracks daily operational outreach toward booked, profitable brokered loads.

### Quality Over Quantity Philosophy
The application explicitly rejects unvetted lead aggregation and massive cold lists. A small, high-conviction shortlist of approximately **100 thoroughly verified, evidence-backed facilities** is far more valuable than thousands of weak, unverified records. Every claim in the system must be traceable to a verified public source or direct telephone qualification.

---

## 2. Confirmed No-Paid-AI-API Requirement

FreightProspecting V1 **MUST function without requiring**:
* Gemini API
* OpenAI API
* Google Search API
* Any paid AI APIs or LLM subscriptions
* Any paid programmable search APIs
* Any user-supplied AI API key

### Local Standalone Operation
Normal local operation does **not** depend on an external AI service. All core features work 100% locally and offline without AI:
* Viewing, searching, and filtering prospects
* Recording and auditing evidence-backed claims
* Contact management with role & directness tracking
* Phone and email call/outreach logging
* Configurable scoring engines (Priority & Conversion Ease)
* Scoped customer & lane suppression
* Discrete load tracking & gross margin calculations
* Carrier roster & time-bound capacity tracking
* Discrete load $\leftrightarrow$ capacity matching
* Public structured open-data imports & refreshes
* Source freshness tracking & recheck flagging
* Local database backups
* Complete local browser UI

Any future AI features must degrade gracefully to standard non-AI operation.

---

## 3. Information Ingestion Pathways

Information enters FreightProspecting V1 through five distinct, structured channels:

1. **Manual Browser Research:**
   * Ordinary Google/web searches opened in the user's standard web browser.
   * Company websites, facility portals, dock instructions, and about/career pages.
   * Public business directories and state/provincial government listings.
2. **Public Permitted Structured Sources:**
   * Downloadable CSV/ZIP/JSON open-data files (e.g. state forestry mill directories).
   * Documented, genuinely free and authorized public APIs that do not require paid AI subscriptions (e.g. FMCSA Developer API, DOT DataHub).
3. **User-Entered Operational Information:**
   * Telephone conversations with receptionists, shipping clerks, and plant managers.
   * Email correspondence with shippers and carrier dispatchers.
   * Direct rate quotes, equipment specifications, and manual operational notes.
4. **Optional External Gemini Browser Research:**
   * The user may independently conduct research using Google Gemini through their personal, logged-in consumer browser account (e.g. Google AI Pro).
   * FreightProspecting may provide convenience helper actions such as:
     * *Prepare / Copy Research Prompt*
     * *Open Gemini in Browser*
     * *Paste / Import Structured Findings*
   * **Strict Boundary:** This is an external human-in-the-loop workflow. It must **never** be treated as a programmatic Gemini Developer API integration. The system must not attempt to scrape or automate consumer Gemini website logins, and it must not assume consumer Google AI Pro accounts include unrestricted programmatic API access.
5. **Future Optional Licensed Connectors:**
   * Commercial load boards (DAT, Truckstop), carrier TMS integrations, or proprietary broker networks, activated only if the user separately acquires authorized, licensed API access.

### Browser Research & Search Helper Model
The UI provides convenient action buttons such as:
* `[Open Google Search]`
* `[Open Company Website]`
* `[Open Source URL]`
* `[Open FMCSA SAFER]`
* `[Copy Research Query]`
* `[Open Gemini in Browser]`

These buttons launch standard URLs or search queries directly in the user's default desktop web browser. **Basic web research does not require a programmable search API.**

---

## 4. What Updates Automatically and What Does Not?

To ensure complete clarity for a beginner user, the boundary between automated functions and manual research is strictly defined:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ WHAT UPDATES AUTOMATICALLY (OR SEMI-AUTOMATICALLY)                                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ • Permitted public datasets can refresh via scheduled or one-click import (e.g. daily   │
│   FMCSA Census downloads).                                                             │
│ • Stale verification dates and source recheck flags recalculate dynamically.           │
│ • Local prospect scores and rankings recalculate instantly as new claims are saved.    │
│ • Timestamp-based availability expiry is completely automatic (e.g. a load or truck   │
│   past its expiration date automatically displays as EXPIRED upon next view).          │
└────────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────────────┐
│ WHAT REQUIRES MANUAL OR ASSISTED HUMAN RESEARCH                                        │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ • Checking company websites, dock instructions, and executive changes.                 │
│ • Conducting Google web searches and reviewing search results.                         │
│ • Formulating research queries and prompting Gemini in an external browser tab.        │
│ • Calling the plant switchboard, identifying the shipping manager, and taking notes.   │
│ • Confirming whether a company accepts freight brokers vs. direct-only carriers.       │
│ • Verifying specific outbound freight volume and equipment requirements.               │
└────────────────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────────────────┐
│ WHAT IS NOT AVAILABLE WITHOUT LICENSED/AUTHORIZED DATA                                 │
├────────────────────────────────────────────────────────────────────────────────────────┤
│ • Complete, live, market-wide freight load feeds (requires paid DAT/Truckstop API).    │
│ • Complete, live, nationwide empty truck feeds (requires paid load-board access).      │
│ • Universal automatic web discovery (requires custom web-scale crawlers).              │
│ • Guaranteed real-time freight availability without direct shipper confirmation.       │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Freight & Equipment Scope

* **Mode:** Full-Truckload (FTL) only. Less-than-truckload (LTL) and parcel are out of scope.
* **Core Target Equipment:**
  * **Flatbed** (standard open deck, 48-ft / 53-ft configurations, pipe bunks, coil racks, chains, lumber/steel tarps)
  * **Step Deck / Single Drop** (machinery, tall tooling, industrial injection molds)
  * **Dry Van** (heavy solid commodities, pallets, automotive parts; trailer length e.g. 48' or 53' is a load/capacity attribute where known, not an artificial restriction to 53' only)
* **Hard Equipment Exclusions:** Temperature-controlled / refrigerated trailers (reefers) are strictly excluded as a target equipment category.

---

## 6. Commodity Scope & Exclusions

### Target Industrial Commodities
* **Lumber & Sawmills:** Hardwood/softwood lumber, pallet cants, railroad crossties, timber mats, crane mats, engineered wood.
* **Wood Products:** Plywood, OSB, structural timber, architectural millwork.
* **Steel & Metals:** Flat-rolled steel coils, structural beams, plate, tubing, fabricated metal products, commercial wheels.
* **Plastics & Industrial Tooling:** Heavy injection mold tooling, die sets, plastic resin pellets, molded industrial components.
* **Concrete & Building Materials:** Precast concrete pressure pipes, box culverts, bridge girders, concrete blocks, brick, drywall, roofing products, structural insulation.
* **Similar Heavy Solid Freight:** Non-perishable, industrial goods moving on open deck or dry van trailers.

### Hard Commodity Exclusions
* Hazardous Materials (Hazmat / Placarded loads)
* Live Animals / Livestock
* Fresh Fish / Seafood
* Jewelry, High-Value Bullion, or Uncut Currency

---

## 7. Geographical Scope

* **Domestic United States:** Lower 48 states.
* **Domestic Canada:** All provinces and industrial territories.
* **Cross-Border Lanes:**
  * United States $\rightarrow$ Canada
  * Canada $\rightarrow$ United States
* **Strict Geographic Exclusions:** Hawaii and Mexico.
* **Alaska Operational Decision (Confirmed Decision A):** Alaska is **EXCLUDED by default** from normal V1 prospecting queries. Because truckload transit to/from Alaska requires either crossing British Columbia and Yukon via the Alaska Highway (Alcan) — requiring Canadian customs-bonded equipment, extreme winter gearing, and 2,500+ mile transit — or marine barge intermodal transit via Puget Sound (Tacoma/Seattle), Alaska is not part of standard Lower 48 / Canadian operations. The ability to enable an Alaska toggle in Settings with an operational advisory badge is preserved for future phases.

---

## 8. Core Architectural & Evidence Separations

The application strictly enforces foundational separations:

1. **Company $\neq$ Facility:** A corporation or holding company is distinct from its individual manufacturing facilities, mills, or service centers. Contacts, fleet operations, and shipping desks belong primarily to operating facilities.
2. **Shipper Prospect $\neq$ Freight-Demand Signal $\neq$ Discrete Load Opportunity:**
   * A *Prospect* is an operating plant that manufactures target goods.
   * A *Freight-Demand Signal* is documented evidence that freight moves or moved (e.g. an RFP, tender, quote request).
   * A *Discrete Load Opportunity* is an actual identifiable shipment needing pricing, quote submission, or truck coverage. A qualified plant with no current demand has zero load records.
3. **Carrier Directory Record $\neq$ Historical Carrier Lane Activity $\neq$ Available Capacity Posting:**
   * A *Carrier Record* is a vetted motor carrier profile.
   * *Carrier Lane Activity* represents historical corridors where a carrier regularly operates.
   * A *Capacity Posting* represents verified, time-bound truck availability in a specific city/date window. A licensed carrier does not equal an available truck today.
4. **Specific Load $\leftrightarrow$ Specific Capacity Matching:** Matching operates strictly between an actual `load_opportunities` record and an actual `capacity_postings` record. Loads are never matched to abstract carrier profiles or historical lane summaries.
5. **Operational Evidence (Category A) $\neq$ Freight-Demand Signals (Category B):**
   * *Category A (Operational Evidence):* A logistics coordinator job ad, dock operating hours, flatbed driver requirement, or plant equipment list proves internal logistics capabilities, but does **not** create a freight-demand signal.
   * *Category B (Freight-Demand Signals):* A dated RFP, quote request, tender, load posting, or direct shipper communication. Only Category B produces demand signal records.
6. **Commercial Carrier Use $\neq$ Broker Acceptance:** A shipper stating that it uses "commercial carriers" alongside company trucks proves it hires for-hire motor carriers, but does **not** prove it accepts third-party property brokers. Broker acceptance remains `UNKNOWN` until verified.
7. **Commodity Suitability Inference $\neq$ Verified Equipment Usage:** Deducing that heavy steel coils or precast concrete pipes require flatbeds is an analytical inference (`INFERRED`), not proof of equipment physically contracted until verified by a primary source (`VERIFIED`).
8. **Source Publication Date $\neq$ Event Date $\neq$ Observation Date:**
   * `source_published_at`: When the document or website was published.
   * `event_at`: When the underlying freight movement or business event occurred.
   * `observed_at`: When our researcher or system checked the source.
   * Rechecking an old web page today updates `observed_at`, but never resets `event_at`.
9. **Contact Identity $\neq$ Communication Channel Directness:** Knowing a manager's name (e.g., Phil Clements, Sawmill Manager) does not convert a main plant switchboard number into a direct line. Contact identity (`NAMED_PERSON`) and phone directness (`GENERAL_SWITCHBOARD`) are decoupled.
10. **Direct-Only Broker Policy $\neq$ Account-Wide Do-Not-Contact:** A company stating that it operates a direct-carrier-only policy receives a negative conversion ease adjustment and is filtered from broker-friendly views, but is **not** automatically marked `DO_NOT_CONTACT`. `DO_NOT_CONTACT` requires an explicit user refusal decision.
11. **Zero Hallucination Standard:** Never invent, extrapolate, or estimate a person's name, published job title, telephone number, extension, email address, or email directness. What is not verified must remain `UNKNOWN`.

---

## 9. Commercial Prospecting Principles

### Outreach Workflow (Confirmed Decision B)
* **Phone-First:** Outreach prioritizes telephone communication, extension routing, gatekeeper navigation, and structured call outcome logging.
* **Email-Important:** Verified business email addresses remain important assets and are fully supported for introductory freight profile letters and rate confirmations. Phone-first does not mean phone-only.

### Private Fleet Policy (Confirmed Decision E)
* Verified private fleet owners remain **visible by default** on the Shortlist with a prominent "Private Fleet" badge.
* Operating private equipment does not mean a shipper never hires outside commercial carriers or brokers during seasonal surges or imbalanced backhauls.
* Fleet status influences ranking through configurable scoring weights, but fleet-owning companies are never silently hidden from the user.

### Provenance & Verification Granularity
* Every factual claim is evaluated at the field/claim level as `VERIFIED`, `INFERRED`, or `UNKNOWN`.
* `UNKNOWN` is strictly neutral and contributes exactly 0 points across all ranking calculations.
* "Not found" is never treated as a verified negative (e.g., no SAFER record $\neq$ "no private fleet"; no published policy $\neq$ "anti-broker").

### Gross Margin Rule
$$\text{Gross Margin} = \text{Shipper Target Rate} - \text{Carrier Target Cost}$$
$$\text{Margin \%} = \frac{\text{Gross Margin}}{\text{Shipper Target Rate}} \times 100$$
* If either rate is unknown: $\text{Margin} = \text{UNKNOWN}$.
* There is no minimum margin required for inclusion. Missing rates never demote or hide an otherwise promising load opportunity.

### Scoped Customer & Account Suppression (Confirmed Decision F)
* V1 starts with **manual entry** of suppression records (`EXISTING_CUSTOMER`, `ALREADY_ROUTED`, `DO_NOT_CONTACT`).
* Bulk CSV import is deferred to future phases.
* Suppression supports explicit scope boundaries: `COMPANY`, `FACILITY`, `COMPANY_LANE`, `FACILITY_LANE`, and `GLOBAL_LANE`. Suppressing a specific facility corridor does not suppress unrelated facilities or companies on the same geographic lane.
