"""Exercise the real authenticated routes against isolated SQLite copies."""
import shutil
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from src.backend.main import app
from src.backend import team


@pytest.fixture
def database(tmp_path, monkeypatch, session_test_db):
    path = tmp_path / "team.db"
    shutil.copy2(session_test_db, path)
    monkeypatch.setenv("FREIGHT_DB_PATH", str(path))
    with sqlite3.connect(path) as conn:
        for table in ('team_company_alerts', 'team_notification_reads', 'team_notifications', 'outreach_authors', 'assignment_history', 'company_assignments', 'team_sessions', 'team_login_attempts', 'team_users'):
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                conn.execute(f"DELETE FROM {table}")
    team.initialize()
    return path


def login(name, password="12345"):
    client = TestClient(app)
    response = client.post("/login", data={"username": name, "password": password}, follow_redirects=False)
    assert response.status_code == 303, response.text
    return client


def state(client, company=1):
    return client.get("/api/team/state").json()[str(company)]


def test_auth_permissions_and_csrf(database):
    guest = TestClient(app)
    assert guest.get("/prospects", follow_redirects=False).status_code == 303
    assert guest.get("/api/companies").status_code == 401
    assert guest.get("/docs", follow_redirects=False).status_code == 303
    selena = login("selena")
    assert selena.get("/admin").status_code == 403
    assert selena.post("/api/admin/users", json={"username": "Other", "password": "12345"}).status_code == 403
    assert selena.post("/api/team/companies/1", json={"action": "claim"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert selena.post("/api/team/companies/1", json={"action": "claim"}, headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert selena.post("/api/outreach", json={"company_id": 1, "disposition": "INTERESTED"}).status_code == 409
    assert selena.get("/prospects").status_code == 200
    assert selena.get("/prospects/1").status_code == 200
    cookie = selena.cookies.get(team.COOKIE)
    assert cookie and len(cookie) >= 40
    with sqlite3.connect(database) as conn:
        assert all(row[0] != "12345" for row in conn.execute("SELECT password_hash FROM team_users"))
        assert conn.execute("SELECT 1 FROM team_sessions WHERE token_hash=?", (cookie,)).fetchone() is None
    selena.post("/logout")
    assert selena.get("/api/team/state").status_code == 401


def test_shared_calls_transfer_restart_and_disable(database):
    selena, kevin, admin = login("Selena"), login("Kevin"), login("Admin")
    before = len(selena.get("/api/outreach/history?company_id=1").json())
    assert selena.post("/api/team/companies/1", json={"action": "claim"}).status_code == 200
    assert state(kevin)["owner_name"] == "Selena"
    assert kevin.post("/api/team/companies/1", json={"action": "claim"}).status_code == 409
    assert kevin.post("/api/outreach/1/clear", json={}).status_code == 409
    assert kevin.post("/api/outreach", json={"company_id": 1, "disposition": "NO_ANSWER"}).status_code == 409
    call = selena.post("/api/outreach", json={"company_id": 1, "disposition": "INTERESTED", "feedback_notes": "Team test", "follow_up_at": "2030-01-02T09:00:00Z"})
    assert call.status_code == 201, call.text
    assert state(kevin)["last_broker_name"] == "Selena"
    assert state(kevin)["outreach_status"] == "INTERESTED"
    selena.post("/logout")
    selena = login("Selena")
    assert state(selena)["owner_name"] == "Selena"
    assert state(selena)["next_follow_up_at"]
    subprocess.run([sys.executable, "-c", "from src.backend import team; team.initialize(); s=team.snapshot()[1]; assert s['owner_name']=='Selena' and s['outreach_status']=='INTERESTED' and s['next_follow_up_at']"], check=True)
    kevin_id = next(u["id"] for u in kevin.get("/api/team/users").json() if u["username"] == "Kevin")
    assert selena.post("/api/team/companies/1", json={"action": "transfer", "target_id": kevin_id, "note": "Call Friday"}).status_code == 200
    assert state(selena)["owner_name"] == "Kevin"
    assert selena.post("/api/outreach/1/clear", json={}).status_code == 409
    assert kevin.post("/api/outreach/1/clear", json={"action": "cancel_follow_up"}).status_code == 200
    assert admin.post(f"/api/admin/users/{kevin_id}", json={"action": "disable"}).status_code == 200
    assert kevin.get("/api/team/state").status_code == 401
    assert state(selena)["owner_id"] is None
    history = selena.get("/api/outreach/history?company_id=1").json()
    assert len(history) == before + 1 and history[0]["broker_name"] == "Selena"
    assert state(selena)["outreach_status"] == "INTERESTED"
    with sqlite3.connect(database) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert conn.execute("SELECT note FROM assignment_history WHERE action='TRANSFER'").fetchone()[0] == "Call Friday"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM outreach_logs")


def test_simultaneous_claim_has_one_winner(database):
    clients = [login("Selena"), login("Kevin")]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda c: c.post("/api/team/companies/1", json={"action": "claim"}).status_code, clients))
    assert sorted(results) == [200, 409]
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT count(*) FROM company_assignments WHERE company_id=1").fetchone()[0] == 1


def test_admin_accounts_and_password_revocation(database):
    admin = login("Admin")
    assert admin.post("/api/admin/users", json={"username": "Robin", "password": "12345"}).status_code == 201
    assert admin.post("/api/admin/users", json={"username": "robin", "password": "12345"}).status_code == 409
    robin = login("Robin")
    uid = next(u["id"] for u in robin.get("/api/team/users").json() if u["username"] == "Robin")
    assert admin.post(f"/api/admin/users/{uid}", json={"action": "password", "password": "new-pass"}).status_code == 200
    assert robin.get("/api/team/state").status_code == 401
    assert login("Robin", "new-pass").get("/prospects?team_view=available").status_code == 200
    assert admin.get("/admin").status_code == 200


def test_admin_rename_preserves_ownership_history_and_sessions(database):
    selena, admin = login("Selena"), login("Admin")
    uid = next(u['id'] for u in admin.get('/api/team/users').json() if u['username'] == 'Selena')
    assert selena.post('/api/team/companies/1', json={'action': 'claim'}).status_code == 200
    assert selena.post('/api/outreach', json={'company_id': 1, 'disposition': 'INTERESTED', 'feedback_notes': 'Rename test'}).status_code == 201
    before = selena.get('/api/outreach/history?company_id=1').json()
    assert selena.post(f'/api/admin/users/{uid}', json={'action':'rename','username':'New name'}).status_code == 403
    for name, code in [('Kevin', 409), (' ', 400), ('<script>', 400)]:
        assert admin.post(f'/api/admin/users/{uid}', json={'action':'rename','username':name}).status_code == code
    assert admin.post(f'/api/admin/users/{uid}', json={'action':'rename','username':'Selena Smith'}).status_code == 200
    after = selena.get('/api/outreach/history?company_id=1').json()
    assert [row['id'] for row in after] == [row['id'] for row in before]
    assert after[0]['broker_name'] == 'Selena Smith'
    assert state(selena)['owner_id'] == uid and state(selena)['owner_name'] == 'Selena Smith'
    assert login('Selena Smith').get('/prospects?team_view=mine').status_code == 200
    assert TestClient(app).post('/login', data={'username':'Selena','password':'12345'}).status_code == 401


def test_login_rate_limit(database):
    client = TestClient(app)
    for _ in range(5):
        assert client.post("/login", data={"username": "Selena", "password": "wrong"}).status_code == 401
    assert client.post("/login", data={"username": "Selena", "password": "12345"}).status_code == 429


def test_team_views_expiry_and_disabled_handoff(database):
    selena, kevin, admin = login("Selena"), login("Kevin"), login("Admin")
    assert selena.post("/api/team/companies/1", json={"action": "claim"}).status_code == 200
    assert [c["company_id"] for c in selena.get("/api/companies?team_view=mine").json()] == [1]
    assert not kevin.get("/api/companies?team_view=mine").json()
    facilities = selena.get("/api/prospects?stage=ALL&team_view=mine&page=1&page_size=25").json()
    assert facilities["items"] and all(f["company_id"] == 1 for f in facilities["items"])
    assert all(f["company_id"] == 1 for f in selena.get("/api/prospects?stage=ALL&team_view=mine").json())
    assert kevin.get("/api/prospects?stage=ALL&team_view=mine&page=1&page_size=25").json()["total_count"] == 0
    assert selena.get("/prospects?view=facilities&team_view=mine").status_code == 200
    assert all(c["company_id"] != 1 for c in kevin.get("/api/companies?team_view=available").json())
    assert selena.get("/prospects?team_view=mine").status_code == 200
    uid = state(selena)["owner_id"]
    kevin_id = next(u["id"] for u in admin.get("/api/team/users").json() if u["username"] == "Kevin")
    assert admin.post(f"/api/admin/users/{uid}", json={"action": "disable", "target_id": kevin_id}).status_code == 200
    assert state(kevin)["owner_name"] == "Kevin"
    assert selena.get("/api/team/state").status_code == 401
    assert kevin.post("/api/team/companies/1", json={"action": "release"}).status_code == 200
    assert state(kevin)["owner_id"] is None
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE team_sessions SET expires_at=0 WHERE user_id=?", (kevin_id,))
    assert kevin.get("/api/team/state").status_code == 401


def test_owner_can_move_between_every_call_status(database):
    from itertools import permutations
    selena, kevin = login("Selena"), login("Kevin")
    assert selena.post("/api/team/companies/1", json={"action": "claim"}).status_code == 200
    outcomes = {"INTERESTED": "INTERESTED", "FOLLOW_UP": "CALL_BACK",
                "NO_ANSWER": "NO_ANSWER", "NOT_INTERESTED": "NOT_INTERESTED"}
    before = len(selena.get("/api/outreach/history?company_id=1").json())
    for source, destination in permutations(outcomes, 2):
        for status in (source, destination):
            payload = {"company_id": 1, "disposition": outcomes[status],
                       "feedback_notes": "Status transition on isolated test database"}
            if status == "FOLLOW_UP":
                payload["follow_up_at"] = "2030-01-02T09:00:00Z"
            response = selena.post("/api/outreach", json=payload)
            assert response.status_code == 201, response.text
        current = state(selena)
        assert current["outreach_status"] == outcomes[destination]
        assert bool(current["next_follow_up_at"]) == (destination == "FOLLOW_UP")
        for tab in outcomes:
            groups = selena.get("/api/companies", params={"outreach": tab}).json()
            assert any(c["company_id"] == 1 for c in groups) == (tab == destination)
    assert kevin.post("/api/outreach", json={"company_id": 1, "disposition": "INTERESTED"}).status_code == 409
    history = selena.get("/api/outreach/history?company_id=1").json()
    assert len(history) == before + 24
    assert all(call["broker_name"] == "Selena" for call in history[:24])


def test_broker_status_tabs_default_to_mine_but_allow_other_views(database):
    import json
    import re
    selena, kevin, admin = login("Selena"), login("Kevin"), login("Admin")
    for client, company_id in [(selena, 1), (kevin, 3)]:
        assert client.post(f"/api/team/companies/{company_id}", json={"action": "claim"}).status_code == 200
    def companies(response):
        assert response.status_code == 200
        return {c["company_id"] for c in json.loads(re.search(
            r'<script id="company-groups-data"[^>]*>(.*?)</script>', response.text, re.S).group(1))}
    for status in ("INTERESTED", "FOLLOW_UP", "NO_ANSWER"):
        for client, company_id in [(selena, 1), (kevin, 3)]:
            payload = {"company_id": company_id, "disposition": "CALL_BACK" if status == "FOLLOW_UP" else status}
            if status == "FOLLOW_UP":
                payload["follow_up_at"] = "2030-01-02T09:00:00Z"
            assert client.post("/api/outreach", json=payload).status_code == 201
        for client, company_id in [(selena, 1), (kevin, 3)]:
            own = client.get("/prospects", params={"outreach": status})
            assert own.url.params["team_view"] == "mine"
            assert companies(own) == {company_id}
            assert {1, 3} <= companies(client.get("/prospects", params={"outreach": status, "team_view": "all"}))
            assert not ({1, 3} & companies(client.get("/prospects", params={"outreach": status, "team_view": "available"})))
        assert {1, 3} <= companies(admin.get("/prospects", params={"outreach": status}))
    for client, company_id in [(selena, 1), (kevin, 3)]:
        available = client.get("/prospects")
        assert available.url.params["team_view"] == "available"
        assert not ({1, 3} & companies(available))
        assert '/prospects?team_view=available' in available.text
        assert companies(client.get("/prospects?team_view=mine")) == {company_id}
        assert {1, 3} <= companies(client.get("/prospects?team_view=all"))
    assert "team_view" not in admin.get("/prospects").url.params


def test_calling_times_filter_preserves_scope_and_pagination(database, monkeypatch):
    from datetime import datetime, timezone
    from src.backend import calling_times
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 5, 14, tzinfo=timezone.utc)
    monkeypatch.setattr(calling_times, 'datetime', FixedClock)
    with sqlite3.connect(database) as conn:
        conn.execute("UPDATE facilities SET city='Windsor',state_prov='ON',country='CA' WHERE company_id=1")
        conn.execute("UPDATE facilities SET city='Phoenix',state_prov='AZ',country='US' WHERE company_id=3")
    selena, kevin = login('Selena'), login('Kevin')
    assert selena.post('/api/team/companies/1',json={'action':'claim'}).status_code == 200
    all_open = kevin.get('/api/companies?calling_now=true&team_view=all').json()
    assert 1 in {c['company_id'] for c in all_open}
    assert 3 not in {c['company_id'] for c in all_open}
    available = kevin.get('/api/companies?calling_now=true&team_view=available').json()
    assert 1 not in {c['company_id'] for c in available}
    paged = kevin.get('/api/companies?calling_now=true&team_view=all&page=1&page_size=2').json()
    assert paged['total_count'] == len(all_open)
    assert len(paged['items']) == min(2,len(all_open))
    toronto = kevin.get('/api/companies?calling_zone=America/Toronto&team_view=all').json()
    assert 1 in {c['company_id'] for c in toronto}
    assert 3 not in {c['company_id'] for c in toronto}
    assert kevin.get('/prospects?calling_now=true').status_code == 200
    assert kevin.get('/calling-times').status_code == 200
    assert kevin.get('/api/calling-times?at=2026-12-01T16:00:00Z').json()['zones']['America/Vancouver']['offset'] == -420
    assert kevin.get('/api/calling-times?at=2026-12-01').status_code == 400
    assert kevin.get('/api/companies?calling_zone=Not/AZone').status_code == 400
    assert kevin.get('/prospects?calling_start=17&calling_end=9').status_code == 400


def test_personal_transfer_notifications_and_admin_announcements(database):
    selena, kevin, admin = login("Selena"), login("Kevin"), login("Admin")
    kevin_id = next(u["id"] for u in kevin.get("/api/team/users").json() if u["username"] == "Kevin")
    assert selena.post("/api/team/companies/1", json={"action":"claim"}).status_code == 200
    assert not kevin.get("/api/notifications").json()["items"]
    assert selena.post("/api/team/companies/1", json={"action":"transfer", "target_id":kevin_id, "note":"Call the shipping desk Friday"}).status_code == 200
    items = kevin.get("/api/notifications").json()["items"]
    assert len(items) == 1 and items[0]["kind"] == "TRANSFER"
    assert "Selena transferred" in items[0]["message"] and "shipping desk Friday" in items[0]["message"]
    assert items[0]["url"].startswith("/prospects/")
    assert not selena.get("/api/notifications").json()["items"]
    # Only the recipient can affect that recipient's unread state.
    assert selena.post("/api/notifications/read", json={"keys":[items[0]["key"]]}).status_code == 200
    assert kevin.get("/api/notifications").json()["unread_count"] == 1
    assert kevin.post("/api/notifications/read", json={"keys":[items[0]["key"]]}).status_code == 200
    kevin.post("/logout")
    kevin = login("Kevin")
    assert kevin.get("/api/notifications").json()["unread_count"] == 0
    announcement = {"title":"Team update", "message":"Please review your follow-ups."}
    assert selena.post("/api/admin/announcements", json=announcement).status_code == 403
    assert admin.post("/api/admin/announcements", json={"title":" ","message":"x"}).status_code == 422
    assert admin.post("/api/admin/announcements", json=announcement).json()["recipients"] == 2
    for broker in (selena, kevin):
        announcements = [n for n in broker.get("/api/notifications").json()["items"] if n["kind"] == "ANNOUNCEMENT"]
        assert len(announcements) == 1 and announcements[0]["message"] == announcement["message"]
    assert kevin.post("/api/notifications/read", json={}).status_code == 200
    assert kevin.get("/api/notifications").json()["unread_count"] == 0
    assert selena.get("/api/notifications").json()["unread_count"] == 1
    # Admin assignment sends a personal alert, without duplicating an unchanged assignment.
    assert admin.post("/api/team/companies/3", json={"action":"transfer", "target_id":kevin_id}).status_code == 200
    assert admin.post("/api/team/companies/3", json={"action":"transfer", "target_id":kevin_id}).status_code == 200
    assert len([i for i in kevin.get("/api/notifications").json()["items"] if i["kind"] == "TRANSFER"]) == 2
    with sqlite3.connect(database) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def test_follow_up_notifications_use_local_dates_and_current_owner(database, monkeypatch):
    from datetime import datetime, timezone
    class Clock(datetime):
        instant = datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc)
        @classmethod
        def now(cls, tz=None):
            return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)
    monkeypatch.setattr(team, "datetime", Clock)
    selena, kevin = login("Selena"), login("Kevin")
    assert selena.post("/api/team/companies/1", json={"action":"claim"}).status_code == 200
    call = {"company_id":1,"disposition":"CALL_BACK","follow_up_at":"2030-01-02T04:00:00Z"}
    assert selena.post("/api/outreach", json=call).status_code == 201
    def reminders(client, tz="Asia/Kolkata"):
        return [i for i in client.get("/api/notifications", params={"tz":tz}).json()["items"] if i["due_at"]]
    assert reminders(selena)[0]["kind"] == "TODAY"  # Jan 2 locally, Jan 1 UTC.
    upcoming = reminders(selena, "UTC")[0]
    assert upcoming["kind"] == "UPCOMING"
    assert not reminders(kevin)
    assert selena.post("/api/notifications/read", json={"keys":[upcoming["key"]]}).status_code == 200
    assert reminders(selena, "UTC")[0]["read_at"]
    Clock.instant = datetime(2030, 1, 2, 1, 0, tzinfo=timezone.utc)
    assert reminders(selena, "UTC")[0]["kind"] == "TODAY"
    assert not reminders(selena, "UTC")[0]["read_at"]
    Clock.instant = datetime(2030, 1, 3, 1, 0, tzinfo=timezone.utc)
    assert reminders(selena)[0]["kind"] == "OVERDUE"
    kevin_id = next(u["id"] for u in kevin.get("/api/team/users").json() if u["username"] == "Kevin")
    assert selena.post("/api/team/companies/1", json={"action":"transfer","target_id":kevin_id}).status_code == 200
    assert not reminders(selena)
    assert len(reminders(kevin)) == 1
    assert kevin.post("/api/outreach/1/clear", json={"action":"cancel_follow_up"}).status_code == 200
    assert not reminders(kevin)
    assert kevin.get("/api/notifications?tz=Invalid/Zone").status_code == 400


def test_admin_reschedules_and_reassigned_broker_gets_private_alert(database):
    selena, kevin, admin = login("Selena"), login("Kevin"), login("Admin")
    assert selena.post("/api/team/companies/1", json={"action":"claim"}).status_code == 200
    assert selena.post("/api/outreach", json={"company_id":1,"disposition":"INTERESTED","follow_up_at":"2030-01-02T09:00:00Z"}).status_code == 201
    history_before = selena.get("/api/outreach/history?company_id=1").json()
    endpoint = "/api/admin/companies/1/follow-up"
    payload = {"follow_up_at":"2030-01-03T09:00:00+05:30"}
    assert selena.post(endpoint, json=payload).status_code == 403
    assert admin.post(endpoint, json={"follow_up_at":"not a date"}).status_code == 400
    assert admin.post(endpoint, json={"follow_up_at":"2000-01-01T09:00:00Z"}).status_code == 400
    assert admin.post(endpoint, json=payload).status_code == 200
    assert state(selena)["next_follow_up_at"] == "2030-01-03T03:30:00Z"
    assert state(selena)["outreach_status"] == "INTERESTED"
    assert selena.get("/api/outreach/history?company_id=1").json() == history_before
    assert admin.post(endpoint, json=payload).status_code == 200
    changes = [i for i in selena.get("/api/notifications").json()["items"] if i["kind"] == "RESCHEDULED"]
    assert len(changes) == 1
    assert changes[0]["previous_due_at"] == "2030-01-02T09:00:00Z"
    assert changes[0]["due_at"] == "2030-01-03T03:30:00Z"
    assert not kevin.get("/api/notifications").json()["items"]
    kevin_id = next(u["id"] for u in kevin.get("/api/team/users").json() if u["username"] == "Kevin")
    assert admin.post("/api/team/companies/1", json={"action":"transfer","target_id":kevin_id}).status_code == 200
    outgoing = [i for i in selena.get("/api/notifications").json()["items"] if i["kind"] == "REASSIGNED"]
    assert len(outgoing) == 1 and "Admin reassigned" in outgoing[0]["message"] and "Kevin" in outgoing[0]["message"]
    assert not any(i["kind"] == "REASSIGNED" for i in kevin.get("/api/notifications").json()["items"])
    assert not any(i["kind"] == "UPCOMING" for i in selena.get("/api/notifications").json()["items"])
    assert any(i["kind"] == "UPCOMING" for i in kevin.get("/api/notifications").json()["items"])


def test_no_answer_alert_is_once_per_consecutive_phone_streak(database):
    selena, kevin = login("Selena"), login("Kevin")
    assert selena.post("/api/team/companies/1", json={"action":"claim"}).status_code == 200
    def call(outcome):
        assert selena.post("/api/outreach", json={"company_id":1,"disposition":outcome}).status_code == 201
    def streaks(client=selena):
        return [i for i in client.get("/api/notifications").json()["items"] if i["kind"] == "NO_ANSWER_STREAK"]
    call("CONNECTED_DECISION_MAKER")
    for n in range(2):
        call("NO_ANSWER")
        assert not streaks()
    call("NO_ANSWER")
    first = streaks()[0]
    assert "3 unanswered calls" in first["title"]
    assert not streaks(kevin)
    assert selena.post("/api/notifications/read", json={"keys":[first["key"]]}).status_code == 200
    call("NO_ANSWER")
    assert len(streaks()) == 1 and streaks()[0]["key"] == first["key"] and streaks()[0]["read_at"]
    assert state(selena)["outreach_status"] == "NO_ANSWER"
    call("INTERESTED")
    assert not streaks()
    for n in range(3):
        call("NO_ANSWER")
    assert streaks()[0]["key"] != first["key"] and not streaks()[0]["read_at"]
    with sqlite3.connect(database) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
