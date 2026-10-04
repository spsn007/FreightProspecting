# Refined Route UI

Implemented locally on 2026-10-03, following the approved Option 1 route theme and Option 2 confirmation styling.

## Presentation

- Transparent truck branding with a theme-aware HTML Shipper IQ wordmark on the sidebar and sign-in page.
- Decorative route, pins, and truck illustration in the header; hidden on small phone screens.
- Consistent system typography, buttons, focus outlines, forms, card corners, and modal surfaces in both themes.
- Existing company-card information and actions retained. No company logos added.
- Long company badges wrap on small screens; compact sidebar branding stays within its width.
- Reduced-motion preferences disable the added transitions.

## Confirmations

Clear call status, cancel follow-up, release ownership, and the existing claim warning use the shared native dialog. Cancel receives initial focus; Escape cancels; the background is inert while open. Dynamic message text is inserted safely as text. Endpoint calls and ownership guards remain unchanged.

## Verification

- `pytest -q tests/test_dashboard_workflow.py tests/test_team_workflow.py tests/test_calling_times.py`: 23 passed, one existing Starlette deprecation warning.
- Browser QA: both themes, Settings, Evidence Ledger, Team Management, Regions & Calling Times, and company cards.
- 375px viewport check: compact logo and wrapped company badges. Temporary viewport override reset.
- Cancel, Escape, and confirmed clear status exercised using a separate SQLite copy on port 8002. No production test calls or ownership/status mutations performed.
- Final browser console: no errors. Admin/light session restored; temporary browser tab closed.

## Asset provenance

`src/frontend/static/images/shipper-iq-truck.png` is a transparent adaptation generated from the user's selected truck logo. Prompt requested the same blue freight semi-truck with route and pin, no lettering, reduced glow, crisp compact masthead, and transparent background suitable for white and charcoal surfaces. The wordmark is rendered separately for theme contrast.

Review screenshots are in `C:/Users/DELL/.codex/visualizations/2026/09/27/01a0e368-944e-7b93-a167-6c8721a39630/`: `shipper-iq-refined-light.png`, `shipper-iq-refined-dark.png`, and `shipper-iq-refined-dialog.png`.

Changes remain uncommitted. Existing unrelated local changes are preserved.
