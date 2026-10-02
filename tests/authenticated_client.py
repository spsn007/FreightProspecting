"""Legacy feature checks run as Admin; authentication itself uses raw TestClient.

Claims are made through the real endpoint before legacy outreach assertions.
This helper never bypasses production authentication or ownership checks.
"""
from fastapi.testclient import TestClient as RawTestClient

from src.backend import team
from src.backend.db.connection import get_db_path, DEFAULT_DB_PATH


class TestClient(RawTestClient):
    __test__ = False

    def request(self, method, url, **kwargs):
        if get_db_path().exists() and str(url).split('?')[0] not in ("/login", "/logout"):
            assert get_db_path().resolve() != DEFAULT_DB_PATH.resolve(), "Authenticated feature tests must use an isolated database"
            team.initialize()
            if not team.session_user(self.cookies.get(team.COOKIE)):
                result = super().request("POST", "/login", data={"username": "Admin", "password": "12345"}, follow_redirects=False)
                assert result.status_code == 303, result.text
            if method.upper() == "POST" and str(url).startswith("/api/outreach"):
                company_id = kwargs.get("json", {}).get("company_id")
                if not company_id:
                    parts = str(url).split("/")
                    if len(parts) > 3 and parts[3].isdigit():
                        company_id = int(parts[3])
                if company_id:
                    claimed = super().request("POST", f"/api/team/companies/{company_id}", json={"action": "claim"})
                    if claimed.status_code == 409:
                        # Production may already contain real broker assignments; isolate
                        # legacy feature checks by explicitly reassigning the copied company.
                        released = super().request("POST", f"/api/team/companies/{company_id}", json={"action": "release"})
                        assert released.status_code == 200, released.text
                        claimed = super().request("POST", f"/api/team/companies/{company_id}", json={"action": "claim"})
                    assert claimed.status_code in (200,404), claimed.text
        return super().request(method, url, **kwargs)
