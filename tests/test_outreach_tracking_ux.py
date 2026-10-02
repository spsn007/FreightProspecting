import os
import shutil
import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from src.backend.main import app, OUTREACH_LABELS
from src.backend.db.queries import log_outreach_call, get_outreach_history


@pytest.fixture
def tracking_db(tmp_path, monkeypatch, session_test_db):
    path = tmp_path / "tracking.db"
    shutil.copy2(session_test_db, path)
    monkeypatch.setenv("FREIGHT_DB_PATH", str(path))
    return path


@pytest.mark.parametrize("outcome", ["INTERESTED", "CALL_BACK", "NO_ANSWER", "NOT_INTERESTED"])
def test_call_survives_writer_exit_and_fresh_app_client(tracking_db, outcome):
    # A separate process writes and exits, like shutting down the application.
    subprocess.run(
        [sys.executable, "-c",
         "from src.backend.db.queries import log_outreach_call; "
         "import sys; log_outreach_call(company_id=1, disposition=sys.argv[1], "
         "follow_up_at='2030-01-02T09:00:00Z')", outcome],
        env=os.environ.copy(), check=True, capture_output=True, text=True,
    )
    with TestClient(app) as client:
        history = client.get("/api/outreach/history?company_id=1").json()
        assert history[0]["disposition"] == outcome
        groups = client.get("/api/companies", params={"outreach": outcome}).json()
        assert any(c["company_id"] == 1 for c in groups)
        followups = client.get("/api/companies", params={"outreach": "FOLLOW_UP"}).json()
        assert any(c["company_id"] == 1 for c in followups)


def test_clear_tracking_keeps_history_and_attempts(tracking_db):
    log_outreach_call(company_id=1, disposition="INTERESTED", follow_up_at="2030-01-02T09:00:00Z")
    before = get_outreach_history(company_id=1)
    client = TestClient(app)
    cancelled = client.post("/api/outreach/1/clear", json={"action": "cancel_follow_up"})
    assert cancelled.status_code == 200
    state = cancelled.json()["data"]
    assert state["current_outreach_status"] == "INTERESTED"
    assert state["next_follow_up_at"] is None
    cleared = client.post("/api/outreach/1/clear", json={"action": "clear_status"})
    assert cleared.status_code == 200
    state = cleared.json()["data"]
    assert state["current_outreach_status"] == "UNCONTACTED"
    assert state["attempt_count"] == len(before)
    assert state["last_contacted_at"] == before[0]["contacted_at"]
    assert state["status_source_outreach_log_id"] is None
    assert get_outreach_history(company_id=1) == before
    assert all(c["company_id"] != 1 for c in client.get("/api/companies?outreach=INTERESTED").json())
    assert all(c["company_id"] != 1 for c in client.get("/api/companies?outreach=FOLLOW_UP").json())
    with sqlite3.connect(tracking_db) as conn:
        assert conn.execute("SELECT sql FROM sqlite_schema WHERE name='trg_outreach_logs_no_delete'").fetchone()
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM outreach_logs")


def test_clear_tracking_validation_and_origin(tracking_db):
    client = TestClient(app)
    assert client.post("/api/outreach/1/clear", json={"action": "erase_history"}).status_code == 422
    assert client.post("/api/outreach/999999/clear", json={}).status_code == 400
    assert client.post("/api/outreach/1/clear", json={}, headers={"Origin": "https://example.com"}).status_code == 403


def test_labels_match_modal_directory_and_filters():
    client = TestClient(app)
    html = client.get("/prospects").text
    for outcome, label in OUTREACH_LABELS.items():
        if outcome in ("UNCONTACTED", "FOLLOW_UP", "FOLLOW_UPS"):
            continue
        assert f'value="{outcome}" x-model="disposition"' in html
        assert f"toggleOutreach('{outcome}')" in html
        assert f"<span>{label}</span>" in html
    assert "Connected (DM)" not in html
    assert "Unconnected & Other Outcomes" not in html
    assert "Set a date below to put this company in Follow-Ups" in html
    assert "Clear Call Status" in html and "Cancel Follow-Up" in html
