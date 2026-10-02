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
        for table in ('outreach_authors', 'assignment_history', 'company_assignments', 'team_sessions', 'team_login_attempts', 'team_users'):
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
