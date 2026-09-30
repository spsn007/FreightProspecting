# FreightProspecting V1 — Source-Policy Catalog

This document establishes the project policies, legal boundaries, update cadences, and capabilities for all data sources evaluated for the FreightProspecting project.

---

## 1. Core Source Policies & Legal Guardrails

1. **Strict Prohibition of Automated SAFER Scraping:**
   * *Project Policy:* **No automated scraping of `safer.fmcsa.dot.gov`.**
   * *Permitted Access:* All automated motor carrier queries must use the official FMCSA Developer REST API or official DOT Open Data bulk census downloads. The public SAFER Company Snapshot website is reserved strictly for manual, user-directed, single-record ad-hoc browser lookups via in-app links.
2. **Unverified Directory Terms Rule:**
   * For industry directories where an official written API or terms-of-use policy has not been legally verified, the access status is strictly designated:
     `UNVERIFIED — MANUAL-ONLY BY PROJECT POLICY PENDING TERMS REVIEW`
   * No automated harvesting, crawling, or scraping scripts may be built against these directories.
3. **Commercial Load-Board Exclusion for V1:**
   * Commercial load boards (DAT One, Truckstop.com, 123Loadboard) require paid commercial credentials and formal API licensing agreements.
   * They are **hard-excluded from automated data collection in V1**. The software architecture provides abstract connector interfaces (`BaseLoadBoardConnector`) solely for future authorized integrations.
4. **Historical Import Records $\neq$ Active Freight:**
   * Government import records (e.g. Canadian Importers Database) document historical transactions by reporting year. They prove corporate trade activity, but must **never be presented as active spot freight opportunities**.
5. **No-Paid-AI-API & No-Programmable-Search-API Policy:**
   * FreightProspecting V1 does **not** integrate with or require paid AI APIs (Gemini Developer API, OpenAI API) or paid programmable search APIs (Google Custom Search API).
   * External web research is supported by launching standard URLs in the user's desktop browser (e.g. Google Search queries, company websites).
   * Optional external Gemini research using a personal Google AI Pro consumer account is an unautomated, human-in-the-loop workflow conducted in a normal browser window. It must never be treated as an API integration or automated login.

---

## 2. Master Source-Feasibility Catalog

| Source Name | Authoritative URL | What It Can Prove | What It Cannot Prove | Expected Freshness / Cadence | Allowed Access Method | Verification Date |
| :--- | :--- | :--- | :--- | :---: | :--- | :---: |
| **FMCSA Open Data Program (Authoritative Overview)** | [fmcsa.dot.gov/mission/data/fmcsa-open-data-program](https://www.fmcsa.dot.gov/mission/data/fmcsa-open-data-program) | Official data architecture, data dictionaries, and programmatic guidelines for USDOT datasets. | Does not provide raw records directly (documentation portal). | Continuous official program guidance. | **Official Program Documentation:** Architectural reference. | 2026-09-26 |
| **FMCSA Company Census Dataset (DOT DataHub)** | [data.transportation.gov](https://data.transportation.gov/) *(Entities with a USDOT Number)* | Legal entity name, DBA name, physical address, USDOT number, MC/MX numbers, carrier operation type, power units count, driver count. | Does not prove freight rates, shipper shipping managers, or live spot load availability. Does not cover intrastate-only or non-registered shippers. | **Updated approximately daily** (from operational database ~24 hours old). Not real-time. | **Licensed Open Data:** Direct CSV download or SODA API for local SQLite indexing. | 2026-09-26 |
| **FMCSA SMS Safety Datasets (SMS Portal)** | [ai.fmcsa.dot.gov/SMS/Data/](https://ai.fmcsa.dot.gov/SMS/Data/) | Carrier safety measurement system inspection history, violation records, crash data, safety ratings. | Does not provide freight demand, rates, or shipper contacts. Distinct dataset family from Company Census. | **Updated monthly** in discrete snapshot releases. | **Licensed Open Data:** Monthly snapshot ZIP/CSV file download. | 2026-09-26 |
| **FMCSA Developer Portal (Official REST API)** | [developer.fmcsa.dot.gov](https://developer.fmcsa.dot.gov/) | Official REST API endpoints providing single-carrier snapshots, operating authority status, power units, and safety ratings by USDOT/MC. | Does not provide shipper logistics manager contacts or freight rates. | Authenticated programmatic access. Freshness varies by endpoint; preserve source snapshot dates. | **Authorized API:** User registers for a free personal developer `webKey`. REST queries with `?webKey=...`. | 2026-09-26 |
| **FMCSA SAFER Web Snapshot (Manual Single-Query)** | [safer.fmcsa.dot.gov](https://safer.fmcsa.dot.gov/CompanySnapshot.aspx) | Individual Company Snapshot showing real-time operating authority status, inspections, and safety ratings. | Does not list freight rates or shipping manager contacts. | Near real-time web snapshot. | **Manual Public Research:** User-directed single-record ad-hoc browser lookup. (In-app button opens official URL). Automated scraping prohibited by project policy. | 2026-09-26 |
| **Georgia Forestry Commission Wood Directories** | [gatrees.org/forest-management-conservation/directories](https://gatrees.org/forest-management-conservation/directories/) | Official directory of primary wood-using mills in GA: plant name, address, mill type (sawmill, ties), species, general phone. | Listed phone numbers connect to general mill office or timber procurement, not outbound freight desks. Does not prove freight rates. | Annual survey by state foresters. | **Manual Research & Public PDF/CSV:** Public state government publication. | 2026-09-26 |
| **Forest Products Locator (Southern US)** | [forestproductslocator.org](http://forestproductslocator.org) | Primary wood-processing mill directory covering 13 southern US states (sawmills, dimension lumber, poles). | Does not list freight desks or active outbound loads. | Annual survey updates. | **UNVERIFIED — MANUAL-ONLY BY PROJECT POLICY PENDING TERMS REVIEW.** Interactive public directory; manual lookups only. | 2026-09-26 |
| **National Precast Concrete Association (NPCA)** | [precast.org/find-members](https://precast.org/find-members/) | Producer members, manufacturing plant locations across US & Canada, certified product categories (pipe, box culverts, bridge beams), plant phone. | Does not list freight rates, shipping supervisors, or discrete outbound shipments. | Continuous member updates. | **UNVERIFIED — MANUAL-ONLY BY PROJECT POLICY PENDING TERMS REVIEW.** Interactive public directory; manual lookups only. | 2026-09-26 |
| **American Concrete Pipe Association (ACPA)** | [concretepipe.org](https://www.concretepipe.org/) | Manufacturing plant locations across North America, pipe diameter capabilities, facility contact phone. | General facility contacts; outbound shipping logistics handled per plant. No live loads. | Annual membership cycle. | **UNVERIFIED — MANUAL-ONLY BY PROJECT POLICY PENDING TERMS REVIEW.** Interactive public locator map; manual lookups only. | 2026-09-26 |
| **American Institute of Steel Construction (AISC)** | [aisc.org/certification](https://www.aisc.org/certification/) | Certified structural steel fabricators, bridge fabricators, and component manufacturers across North America. | Identifies high-volume steel shippers requiring flatbeds, but specific shipping manager must be qualified by phone. | Continuous audit-backed updates. | **UNVERIFIED — MANUAL-ONLY BY PROJECT POLICY PENDING TERMS REVIEW.** Public certification directory; manual lookups only. | 2026-09-26 |
| **Canadian Importers Database (ISED)** | [ic.gc.ca/eic/site/cid-dic.nsf/eng/home](https://www.ic.gc.ca/eic/site/cid-dic.nsf/eng/home) | Canadian businesses importing goods into Canada, searchable by commodity code (HS), city, and country of origin. | **Not a corporate registry or complete manufacturer directory.** Historical import records do not prove active freight loads today. | Maintained annually by federal reporting data. Preserves specific reporting year. | **Licensed Open Data:** Open Government Licence – Canada (unrestricted non-commercial and commercial reuse). | 2026-09-26 |
| **Commercial Load Boards (DAT, Truckstop)** | [dat.com](https://www.dat.com) & [truckstop.com](https://truckstop.com) | Live spot market freight postings, historical lane rates, available trucks, carrier credit ratings. | Does not replace shipper direct relationships. | Real-time. | **Restricted / Subscription-Only:** Paid commercial accounts and partner API licensing required. Hard exclusion for V1; architectural connector stubs only. | 2026-09-26 |

---

## 3. Web Search & Consumer Gemini Operational Models

### Standard Web Browser Search Helpers
To accelerate manual research without programmable search API costs, the UI will provide helper triggers that open pre-formatted search queries in the user's default browser:
* `[Open Google Search]`: Launches `https://www.google.com/search?q="Company+Name"+AND+"shipping"+OR+"flatbed"`
* `[Open Company Website]`: Opens the facility's verified homepage or contact URL directly.
* `[Open FMCSA SAFER]`: Opens `https://safer.fmcsa.dot.gov/CompanySnapshot.aspx` with pre-filled name/DOT.
* `[Copy Research Prompt]`: Copies a structured prompt to the clipboard for the user to paste into their preferred search or assistant tool.

### Consumer Gemini Workflow (Google AI Pro)
* If the user chooses to use Google Gemini through their consumer browser account:
  1. The user clicks `[Copy Gemini Research Prompt]` in FreightProspecting to copy a standardized research template.
  2. The user opens their personal Gemini session in their regular browser window.
  3. The user pastes the prompt, reviews Gemini's generated response, and manually copies verified facts back into FreightProspecting's data entry drawers.
* **Strict Implementation Rule:** The application will never attempt to automate consumer Google login sessions, never send automated HTTP requests to `gemini.google.com`, and never assume consumer account access provides programmatic developer API endpoints.
