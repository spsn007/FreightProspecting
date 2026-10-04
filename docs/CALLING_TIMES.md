# Regions and calling times

Implemented: Regions & Calling Times navigation/page, compact facility-local clocks, company calling-hours filter, dual-time follow-up preview (including Admin rescheduling).

## Broker workflow

- Choose All countries, United States or Canada, then search by recognized city, state/province name or abbreviation, or timezone group. Country sections explicitly label US/Canadian local time and the equivalent office window in India. Short abbreviations match whole words; search ignores accents and punctuation. Native expandable region lists explain split-zone areas. Available Companies links preserve the unassigned-company scope.
- The 12-hour/24-hour toggle changes clocks, office-hour options and India conversions together, and is saved per profile in the browser. Green means within calling hours, orange means the last 30 minutes, and red means outside hours; every dot also has a text label. Master Directory repeats these live dots beside company names (primary facility) and facility rows (that facility). Unknown or unsynchronized times use a neutral hollow dot, with an explanatory accessible label and tooltip.
- Default calling guide is weekdays 09:00–17:00 local time. Each profile can adjust its same-day window on the guide page; preferences are saved in that browser. Closing soon means the last 30 minutes. These are estimated office hours, not confirmed opening hours. Holidays and individual desk hours are not inferred.
- Master Directory filter Within calling hours now runs on the server before pagination, intersecting existing ownership/search/tier filters. Company is eligible when at least one recognized facility matches. Primary-facility clock and child-facility clocks let the broker check the actual location before calling. Time filters use Company view; clear them to switch to Facilities.
- Unknown split-zone cities are labelled Time zone needs confirmation and excluded from the calling-hours filter. Location mappings are operational estimates, not accepted evidence claims. No company facts, evidence, call status, ownership or historical logs are rewritten.
- Follow-up inputs retain the existing device-local-time meaning. Preview displays company local date/time and India IST for the selected date, plus an advisory outside-hours/weekend warning. The broker may still schedule a time requested by the contact. Choosing another facility updates the preview. Corporate calls without a specific multi-site location cannot establish a company timezone.
- Admin rescheduling shows the same dual-time preview in Team details, using the displayed facility.

## Clock rules

Python ZoneInfo performs conversions using named IANA zones. tzdata 2026.4 is pinned for Windows. The official upstream Python tzdata IANA 2026e Winnipeg TZif file is vendored with commit/hash/source in src/backend/timezone_data/SOURCE.md, because the published package currently contains 2026d. This covers the recent Manitoba rule change without custom transition calculations. Remove that override when upgrading to a package containing 2026e or newer. Northwestern Ontario mappings follow the current IANA model and remain estimates.

The browser fetches server time and offsets every minute and ticks clocks every second from a monotonic server-time anchor, avoiding dependence on potentially older browser Canadian clock rules. Responses disable caching. Sync expires after two minutes; failed requests, device-clock jumps and returning to the tab invalidate calling guidance until a fresh response arrives. Focus, visibility and reconnect events trigger immediate synchronization. Follow-up previews request offsets for the selected instant. There are no paid APIs or external requests during normal app use.

Read-only authenticated endpoints: GET /calling-times and GET /api/calling-times?at=<aware ISO timestamp>. The existing company list accepts calling_zone, calling_now, calling_start and calling_end. Unknown zones and invalid windows are rejected.

Sources: https://www.iana.org/time-zones/releases/2026e ; https://www.transportation.gov/regulations/daylight-saving-time ; https://nrc.canada.ca/en/certifications-evaluations-standards/canadas-official-time

## Verification

22 focused tests passed across calling-time, authenticated team and dashboard workflow suites. Coverage includes split-zone cities, unknown locations, opening/closing/weekend boundaries, summer/winter rules, Phoenix, Vancouver and Winnipeg exceptions, ownership scope, pagination, date validation and existing call workflows. Browser QA verifies region search, timezone filtering, empty-state behavior, light/dark themes, dual-time winter conversion and midnight date rollover. Follow-up form testing used the isolated notifications QA database; no test call was saved.

Country-layout refinement: 4 focused tests passed, including a Node browser-clock harness covering search, display formats, per-second ticking, closing/weekend status, stale/offline protection, device-clock jumps and reconnect recovery. Live browser QA verified Windsor/ON search, country selection, 12/24-hour options, clock advancement and both themes with no console errors. No production calls, assignments or company facts were changed.
