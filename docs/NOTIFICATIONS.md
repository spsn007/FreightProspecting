# In-app notifications

The header bell shows unread alerts for the signed-in profile. The list refreshes with the existing team poll (every 15 seconds while the page is visible) and when the bell opens.

## Alerts

- Company handovers: the receiving broker gets the sender, company, and handoff note. Admin reassignment, including reassignment when disabling a profile, also creates an alert. Self-claims and unchanged assignments do not create alerts.
- Follow-ups: reminders are derived from the current company assignment and scheduled date, using the browser timezone. Upcoming, Today, and Overdue are distinct reminder phases. Rescheduling changes the reminder; canceling it removes it; transferring ownership moves it to the new broker.
- Team announcements: only Admin can send. Open the bell, expand Send a team announcement, and enter a title and message. Delivery goes to currently active broker profiles.
- Reassigned away: the previous owner receives an alert when Admin or another authorized actor moves their company to another broker or releases it. A broker's own transfer/release does not notify that same broker.
- Admin rescheduling: Admin can open Team details and choose Reschedule Follow-Up for an assigned company with an existing follow-up. The new time must be in the future. The owner receives an alert showing the previous and new dates; original call records are preserved.
- Repeated No Answer: after three consecutive unanswered phone calls, the current owner receives one alert suggesting a different calling time or a contact review. Further unanswered calls update the count without creating another unread alert for the same streak. A different phone outcome ends the streak. The company must still be assigned to that broker with an active No Answer status. This alert does not change status or ownership.

Unread counts and Mark as read / Mark all as read are profile-specific and stored in SQLite. Opening a company marks its alert as read. Reading an Upcoming reminder does not suppress its later Today or Overdue reminder. No production sample announcements are inserted.

## Storage and permissions

Three additive tables: team_notifications, team_notification_reads and team_company_alerts. Existing company facts, evidence, contacts and outreach logs are retained. Before adding these tables to the production database, initialization creates a consistent SQLite backup using the existing backup mechanism.

API routes: GET /api/notifications, POST /api/notifications/read, and Admin-only POST /api/admin/announcements. Authentication and existing origin checks apply. Notification messages render as text. Each user can retrieve and mark only their own alerts.

Admin-only POST /api/admin/companies/{company_id}/follow-up reschedules an existing follow-up. The browser converts the selected local time to an explicit timezone-aware timestamp; the server stores UTC. Saving the same time again does not duplicate the alert.

The panel shows up to 100 alerts, prioritizing unread reminders due today/overdue, company alerts and announcements, then upcoming reminders. Mark all as read includes alerts outside the visible list.

These are in-app alerts. The shared app must be running; there is no email, SMS or operating-system push service.
