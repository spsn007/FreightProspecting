# FreightProspecting V1 — UI/UX Specification (Stage 2.5 Baseline)

* **Document Version:** Stage 2.5 Preview Baseline  
* **Philosophy:** Shipper / Prospect First CRM & Evidence Workspace  
* **Execution Boundary:** 100% Local Browser, Zero CDN, Zero Paid AI

---

## 1. Product Philosophy & Information Hierarchy

FreightProspecting V1 is structured as a **Freight Prospecting CRM + Evidence Workspace + Opportunity Workflow**, not a traditional carrier-dispatch TMS. Sourcing freight brokers begins with shipper relationships and manufacturing facility intelligence:

1. **Find Companies:** Pinpoint manufacturers that ship suitable equipment categories (FTL Flatbed, Step Deck, Dry Van).
2. **Understand Shipments:** Identify exact commodities produced (lumber, steel coils, precast concrete, automotive tooling).
3. **Locate Decision-Makers:** Separate direct logistics managers (`DIRECT_PERSON`) from corporate switchboards (`GENERAL_SWITCHBOARD`).
4. **Phone-First Outreach:** Prioritize direct phone lines for initial contact; preserve verified emails for follow-up documentation.
5. **Separate Signals from Loads:** Maintain strict entity boundaries: Shipper Prospect $\neq$ Freight-Demand Signal $\neq$ Discrete Load.
6. **Calculate Real Margin:** Calculate gross margin deterministically when rates are known; return `UNKNOWN` when rates are missing.

---

## 2. Visual Theme & Design Tokens

| Token | Value | Semantic Usage |
| :--- | :--- | :--- |
| `--sidebar-bg` | `#0f172a` | Dark slate navigation sidebar |
| `--sidebar-border` | `#1e293b` | Sidebar item & header dividers |
| `--sidebar-active-text` | `#38bdf8` | Highlighted active page indicator |
| `--bg-workspace` | `#f8fafc` | Warm light-slate canvas |
| `--color-surface` | `#ffffff` | Content cards, tables, elevated modals |
| `--color-border` | `#e2e8f0` | Standard card and table borders |
| `--color-primary` | `#0284c7` | Primary action links, headers, brand icon |
| `--verified-bg` / `color` | `#dcfce7` / `#15803d` | Confirmed claims backed by primary sources |
| `--inferred-bg` / `color` | `#fef3c7` / `#b45309` | Inferred claims (e.g. flatbed suitability) |
| `--unknown-bg` / `color` | `#f1f5f9` / `#475569` | Unverified fields (neutral, contributes 0 pts) |
| `--badge-fleet-bg` / `color` | `#ffedd5` / `#9a3412` | Verified private fleet badge (operational note) |

---

## 3. Approved Navigation Architecture

The left navigation sidebar provides 5 core primary destinations:

1. **Shortlist Cockpit (`/`)**: Today's prioritized shipper shortlist with immediate call buttons and next action callouts.
2. **Master Directory (`/prospects`)**: Complete ledger of audited manufacturing facilities with real-time Alpine.js filters.
3. **Loads & Margins (`/loads`)**: Bookable discrete loads with state-dependent validation and margin calculators (empty state).
4. **Carriers & Capacity (`/carriers`)**: Registered motor carriers and equipment capacity postings (empty state).
5. **Evidence Ledger (`/research`)**: Primary sources and field-level claims traceability.
6. **Settings & Controls (`/settings`)**: Decision A (Alaska toggle), Decision B (Phone-First), Decision H (No-Paid-AI).

---

## 4. Component Conventions

- **Badges:** Every badge pairs a symbol with text (`✓ Verified`, `◇ Inferred`, `? Unknown`) so meaning is never encoded by color alone.
- **Contact Blocks:** Phone numbers use high-contrast monospace typography with `tel:` links; directness is highlighted (`Direct Line` vs `Switchboard`).
- **Empty States:** When a table contains 0 rows (loads, capacity), an honest empty state explains the real-world workflow rather than presenting synthetic mock data.
- **External Research Launchers:** Ordinary desktop browser links launch Google Search and Gemini without consuming paid API tokens.
