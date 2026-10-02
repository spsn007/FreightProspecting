# Broker team workflow

## Sign in

Open http://127.0.0.1:8000/login. Initial profiles are Selena, Kevin and Admin;
initial password is 12345. Names are case-insensitive. Admin can reset passwords.
Passwords are hashed; server sessions expire after 12 hours and survive server restarts.

## Work together

- All Companies shows the shared directory and team activity.
- My Companies shows the logged-in broker's assigned companies.
- Available Companies excludes assigned companies, Not Interested results and company suppressions.
- Opening a profile does not reserve it. Click Start Working before calling or logging a call.
- One broker owns a company across all its facilities. Only that broker can log calls or clear call status.
- Release Company returns it to the team. Transfer Company records the receiving broker and optional note.
- Release, transfer, logout and restart preserve call history, statuses and follow-ups.
- A follow-up can accompany any call result. No Answer does not permanently disqualify a company.
- Every new dashboard call records the authenticated broker. Older calls remain explicitly unattributed.
- Team updates refresh every 15 seconds while the page is visible. Server transactions enforce ownership independently.

## Admin

Manage Team creates broker profiles, resets passwords and disables/enables profiles.
Disabling a profile revokes its sessions. Assigned companies can be released or handed to another broker.
The profile's name and historical calls remain saved. The Admin account cannot be disabled.

## Database and future hosting

The first authenticated page request adds six team tables and creates a consistent pre-migration backup
under data/backups/prospects_pre_team_*.db. Existing prospect, research and outreach rows are not rewritten.
All brokers must use one running backend and its central database; keep the database on persistent server storage.
The app remains bound to localhost through run_app.bat. Online deployment is a separate step:
use HTTPS, reset the temporary passwords, configure FP_ALLOWED_HOSTS and enable FP_SECURE_COOKIES=1.
FP_INITIAL_PASSWORD changes bootstrap passwords only for a database with no team accounts.
FREIGHT_DB_PATH selects the central SQLite file. Do not give each broker a separate database copy.

## Verification and resuming

Run .venv/Scripts/pytest -q tests/test_team_workflow.py for authentication, ownership races,
shared calls, transfers, account disabling, session expiry and process persistence.
Production data is protected during tests; browser QA uses an isolated database copy.
See TEAM_WORKFLOW_PROGRESS.md for the latest checkpoint and regression results.
