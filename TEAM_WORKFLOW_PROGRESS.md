# Team workflow implementation — resume checkpoint

Product name: Shipper IQ (approved October 3, 2026). The repository and workspace remain FreightProspecting.
Local UI updates: compact company ownership headers, supplied radar logo, theme-aware sidebar and login,
and broker-facing Settings. These UI updates have not yet been committed or pushed.
Further October 3 updates: simplified, searchable and paged Evidence Ledger; unused operations navigation
and top-right badges removed; Priority Guide and grouped category browser; admin profile renaming with
stable IDs/history/sessions. Rename tests use isolated data; no production profile was renamed.
Verification: 43 focused checks passed after the guide copy correction; browser source search,
category filtering (Christmas Trees: 8 companies), profile editor and both themes checked.

Approved accounts: Selena (exact spelling), Kevin, Admin; initial passwords 12345.

Implemented locally:
- Persistent hashed-password login, server sessions, logout, same-origin writes, role authorization, login rate limiting.
- Admin create/reset/disable/enable profiles; disabling revokes sessions and releases or transfers companies, preserving history.
- One company owner; transactional claim/save/clear checks; release/transfer with recorded handoff notes.
- Shared broker call attribution without altering old outreach logs; old calls remain unattributed.
- All/My/Available views, SQL filtering, live ownership/status refresh, guarded call/email entry points.
- Existing navigation fixes preserved. User authorized committing and pushing the approved changes.

Database migration: additive six team tables, consistent backup at
D:/FreightProspecting/data/backups/prospects_pre_team_20261002_205218.db.
All original tables compare unchanged to that backup as of the last check; production still has its 3 real calls.
The human is already using the new accounts and creating real assignments. Do not clear those assignments.

Validation:
- Authenticated two-broker route tests and concurrency checks passed on isolated copies.
- Browser QA against isolated server port 8002 confirmed Selena→Kevin transfer, Kevin call attribution,
  shared Interested/follow-up visibility, and admin account list. No production QA calls were created.
- Existing feature tests now use tests/authenticated_client.py to log in and claim/reassign copied companies.
- Old frozen-baseline tests assume an obsolete database hash and zero real calls; do not change production to satisfy them.

Final verification so far:
- Full suite: 546 passed, 4 pre-existing obsolete baseline failures (TEMP/fp_team_verified_tests.txt).
- Focused final suite: 60 passed.
- Integrity ok; foreign_key_check 0; original data tables unchanged from pre-team backup.
- Production has Selena and Kevin real assignments from the human; preserve them.
Status: IMPLEMENTATION COMPLETE. Publication revision is tracked in Git history.
- Final team route suite: 6 passed, including paginated and unpaginated team facility filtering.
- Independent live Admin transfer automatically removed the company from Kevin's My Companies view.
- Sidebar account controls remain reachable with navigation sections expanded.
- Final Admin browser check showed Selena and Kevin, with real assignments intact and no console errors.
- Isolated browser QA tabs closed and port 8002 test server stopped; production port 8000 remains running.
- Visual proof: C:/Users/DELL/.codex/visualizations/2026/09/27/01a0e368-944e-7b93-a167-6c8721a39630/team-admin-dashboard.png.
- Usage interruption recovery: read this checkpoint and docs/TEAM_WORKFLOW.md, then review git diff.
  There is no remaining implementation step in the approved plan. Preserve the human's real assignments.
  Follow the user's next request; do not clear production data or rewrite historical freeze assertions.
Review git diff before continuing; preserve unrelated backups/reports/scripts.


2026-10-03 directory and sidebar refinement (local, uncommitted):
- Directory overview now uses three equal compact cards with live counts.
- Interested, Follow-Ups, No Answer and Not Interested have contextual page titles and omit directory-wide metrics, tier toolbar and facility switch. Search and follow-up date controls remain available.
- Ownership badges highlight another broker in amber and available/own companies in green; native details retain shared history and management controls.
- Evidence Ledger is a direct sidebar link. Compact desktop spacing verified without scrolling at 1440x700 and 1366x600, including Admin controls. Smaller heights retain overflow access.
- Both themes visually checked; no production calls, assignments or company facts changed for QA.
- Focused workflow/directory/outreach suites: 46 passed. Browser proof saved as shipper-iq-compact-directory.png and shipper-iq-focused-interested.png in the existing visualization directory.


2026-10-03 ownership controls and call-status clarification (local, uncommitted):
- User explicitly confirmed keeping ownership protection: Kevin must receive a transfer from Selena/Admin before editing Selena's company.
- Available-to-team badge and Start Working button now have matching 34px heights and 13.6px text, verified in live browser.
- Company action is Log Call / Update Status; blocked controls are visibly dimmed and explain the assigned broker and transfer instructions. Shared guard messages use the same explanation.
- Call Back requires a follow-up date in the UI so it enters Follow-Ups; other results may optionally have scheduled follow-ups. Existing history remains append-only.
- Isolated tests exercised all 12 directed status transitions with correct tab membership, preserved call author/history, and rejection of another broker's update. Modal harness verifies missing-date guard without submission.
- 13 focused team/workflow tests passed. Live Selena editor opened from Interested; Call Back and Tomorrow selected, then discarded without saving. Production company/call/assignment data was not changed for QA.
- Screenshot proof: shipper-iq-aligned-availability.png and shipper-iq-owner-follow-up-editor.png. QA browser restored to Admin/light theme, viewport reset, temporary tab closed.


2026-10-03 personal broker status defaults (local, uncommitted):
- Interested, Follow-Ups and No Answer sidebar links open team_view=mine for brokers; direct status URLs without explicit scope redirect to the same default. Explicit All/Available scopes remain supported. Admin keeps the shared overview.
- Counts for those three sidebar tabs use current company ownership for the signed-in broker; Not Interested remains shared as before.
- Counts follow stable user IDs, including renamed profiles and later transfers.
- 15 team/dashboard tests passed, including two-broker default scope, explicit All/Available, admin scope and JavaScript owner-specific counts.
- Live Kevin QA confirmed Interested=2 with only Kevin's two companies; All Companies showed three including Selena Harrison's company; Follow-Ups and No Answer returned My Companies. No production calls/assignments/company facts changed by QA. Human edits to profiles/calls observed and preserved.
- Screenshot: shipper-iq-my-interested-default.png. QA session restored to Admin, viewport reset, temporary tab closed.


2026-10-03 compact cards with delayed action help (local, uncommitted):
- Removed permanent call-access/help paragraph from company action columns.
- Log Call / Update Status and Clear Call Status now use shared CSS tooltips: appear after 3s hover, disappear immediately on pointer leave; keyboard focus shows help without delay.
- Disabled-button wrappers remain keyboard reachable and describe ownership restrictions. Ownership checks unchanged.
- Tooltips are absolutely positioned and do not increase card height. Live browser measured first card at 300.8125px both before and during tooltip display; initial hover hidden, 3s delay computed, delayed appearance and immediate dismissal verified. Brief hover cancellation also verified.
- Both themes checked; 6 dashboard workflow tests passed; no production calls or assignments changed.
- Proof saved as shipper-iq-delayed-call-help.png and shipper-iq-compact-call-actions.png. QA tab closed and viewport/theme restored.


2026-10-03 in-app notifications (local, uncommitted):
- Added header notification bell, unread badge, personal list, Open company, persistent read state and Mark all as read.
- Transfer alerts belong only to the recipient and include actor/company/handoff note; Admin reassignment and account-disable handoffs also alert the recipient.
- Follow-up alerts derive from current ownership and local scheduled dates (Upcoming/Today/Overdue). Cancellation, reassignment, rescheduling and phase changes update reminders. Reading Upcoming does not suppress Today/Overdue.
- Admin-only announcement form sends to all currently active brokers; API enforces admin access. Message text is escaped via Alpine x-text.
- New additive team_notifications and team_notification_reads tables; pre-migration consistent backup created at data/backups/prospects_pre_team_20261003_072815.db (earlier established backup prefix). Production integrity_check ok, foreign_key_check 0.
- Tests verify recipient isolation, read persistence, denied broker broadcasts, timezone day boundaries, reminder cancellation/transfer and unchanged-assignment deduplication.
- Browser QA used TEMP/notifications_qa_d62dd524.db on port 8002: Kevin received transfer/upcoming/Admin alerts, read state survived reload, Admin form delivered to two isolated brokers. Both themes and 375px viewport checked without horizontal overflow.
- No production QA announcements, handovers or calls created. Port 8002 stopped; production remains running. QA browser account/theme/viewport restored and tab closed.
- Proof: shipper-iq-notifications-light.png and shipper-iq-notifications-dark.png. More detail: docs/NOTIFICATIONS.md.

2026-10-03 optional company alerts (local, uncommitted):
- Added private reassigned-away alerts for the prior owner when another authorized actor reassigns/releases their company.
- Admin can reschedule an existing follow-up in Team details; the owner receives previous/new dates. Call history and current call status are preserved.
- Added a No Answer alert after three consecutive unanswered phone calls, once per streak; further attempts retain the read state. Other outcomes reset the streak.
- Added team_company_alerts with consistent pre-migration backup data/backups/prospects_pre_notifications_20261003_073903.db.
- Focused team/dashboard suite: 19 passed. Production integrity_check ok; foreign_key_check 0.
- Isolated browser QA verified all three alerts and Admin rescheduling. No production QA calls, transfers or announcements created. Port 8002 stopped; production server retained. Browser account/theme/viewport restored and temporary tab closed.
- Proof: shipper-iq-optional-alerts.png in the existing visualization directory. Implementation details are in docs/NOTIFICATIONS.md.

2026-10-03 Master Directory broker default (local, uncommitted):
- Broker sidebar Master Directory opens Available Companies. Direct directory URLs without an explicit team scope use the same default.
- Explicit My Companies / All Companies remain supported; personal status-tab defaults and Admin overview remain intact.
- Isolated two-broker scope regression passed, checking available excludes assigned companies, explicit scopes work, and Admin retains the shared default. No production company data changed.

2026-10-03 Regions & Calling Times (local, uncommitted):
- Implemented the approved four features: searchable region guide, compact facility-local clocks, server calling-hours filter before pagination, and company/India follow-up preview (also Admin rescheduling).
- Broker calling window defaults to weekdays 09:00–17:00 local; per-profile browser preferences can adjust it. Hours are explicitly estimated; holidays/contact hours are not asserted. Unrecognized split-zone locations show needs-confirmation.
- Timezone filters retain ownership protection and Company view. Multi-site matches are marked in Details when the primary facility differs. A compact refresh control rechecks active calling-hours results; clocks refresh independently.
- Uses server ZoneInfo and pinned Windows tzdata 2026.4; official upstream IANA 2026e Winnipeg TZif vendored with source commit/hash, covering newer Canadian rules without manual transitions. More details: docs/CALLING_TIMES.md and src/backend/timezone_data/SOURCE.md.
- Focused calling/team/dashboard suite: 22 passed. Final calling tests after integration polish: 3 passed. Browser verified Windsor search, zone filter, outside-hours empty state, both themes, winter follow-up conversion (19:30 IST = 09:00 Toronto) and date rollover/outside-hours warning.
- QA follow-up editor used isolated TEMP/notifications_qa_d62dd524.db on port 8002 and discarded the form. No production test calls or assignments created. Isolated server stopped; production remains running. Admin/light browser session restored.
- Screenshots in the existing visualization directory: shipper-iq-calling-times-light.png, shipper-iq-calling-times-dark.png and shipper-iq-dual-time-follow-up.png.

2026-10-03 country calling-guide refinement (local, uncommitted):
- Separate United States and Canada sections, country navigation, explicit India/US/Canadian time labels and local-to-India office-window comparisons.
- Per-profile 12/24-hour display toggle includes office-hour options. Search handles multiword/accented names and exact short state/province abbreviations.
- Green/red/white status dots with text labels. Live clocks tick every second from server time, synchronize every minute, and suppress calling guidance when stale, offline or after a device-clock jump. Returning to the tab/reconnecting immediately refreshes time.
- Focused tests: 4 passed, 13 deselected. Browser verified Windsor/ON search, format options, advancing seconds and light/dark layouts. No production calls, assignments or facts changed.
- Proof: shipper-iq-country-calling-times.png in the existing visualization directory. Production server retained; QA display preferences restored and temporary tab closed.

2026-10-03 calling-status dots (local, uncommitted):
- Shared colours now green within hours, orange closing soon, red outside hours. Neutral hollow dots remain for unknown/stale time.
- Live dots precede company names in cards and facility rows, using the existing synchronized clock store. Accessible labels/tooltips explain the time and primary-facility scope.
- Calling-time tests: 3 passed. Browser confirmed red dots beside company names with no console errors. No production data changed; QA tab closed.
- Proof: shipper-iq-company-calling-dots.png in the existing visualization directory.

2026-10-03 Refined Route UI (local, uncommitted):
- Implemented approved Option 1 route/truck branding with Option 2 confirmation dialogs. Theme-aware wordmark, transparent truck asset, slim SVG header route, system typography, consistent controls and focus styles.
- Existing company cards and workflows retained; long badges wrap on small screens. No company logos added.
- Clear status, cancel follow-up, release and claim warnings use the shared accessible native dialog. Research prompt copying uses the existing notice system.
- Focused dashboard/team/calling tests: 23 passed. Browser verified both themes and major screens; Cancel/Escape/Confirm tested against isolated SQLite copy on port 8002.
- No production QA calls, assignments or status changes. Temporary viewport reset and browser tab closed; Admin/light restored.
- Details and asset provenance: docs/REFINED_ROUTE_UI.md. Proof: shipper-iq-refined-light.png, shipper-iq-refined-dark.png and shipper-iq-refined-dialog.png in the existing visualization directory.
- No commit or push requested for this styling task; earlier unrelated local files preserved.

2026-10-03 branding and route refinement (local, uncommitted):
- Enlarged sidebar truck to fill the logo area's width; reduced sidebar wordmark to 1.3rem. Compact desktop spacing keeps navigation within the sidebar at the tested 712px height.
- Header route now grows across available space from the breadcrumb to the notification area. Replaced the outline truck with the detailed existing truck asset, plus shaded pins and subtle glowing route markers. No new asset generation or workflow changes.
- Browser checked light/dark, 1920px desktop geometry, and 375px layout. Navigation scrollHeight equals clientHeight at desktop sizes; no console errors. Viewport and Admin/light theme restored, QA tab closed.
- Proof: shipper-iq-route-expanded.png in the existing visualization directory. CSS cache version route5.
