import html
import re

import pytest
from tests.authenticated_client import TestClient

from src.backend.main import app


@pytest.mark.parametrize("return_to", [
    "/prospects?page=2&page_size=25&sort=name_asc&q=steel",
    "/prospects?outreach=INTERESTED",
    "/prospects?view=facilities&page=3",
    "/prospects",
])
def test_back_button_preserves_directory_url(return_to):
    response = TestClient(app).get("/prospects/23", params={"return_to": return_to})
    assert response.status_code == 200
    href = re.search(r'<a href="([^"]*)" id="back-to-results"', response.text).group(1)
    assert html.unescape(href) == return_to
    assert "← Back to Results" in response.text


@pytest.mark.parametrize("return_to", [
    "https://example.com/prospects",
    "//example.com/prospects",
    "javascript:alert(1)",
    "/settings",
    "/\\example.com/prospects",
    "http://[broken",
])
def test_back_button_rejects_invalid_return_destinations(return_to):
    response = TestClient(app).get("/prospects/23", params={"return_to": return_to})
    assert response.status_code == 200
    assert '<a href="/prospects" id="back-to-results"' in response.text


def test_direct_prospect_link_has_working_directory_fallback():
    response = TestClient(app).get("/prospects/23")
    assert response.status_code == 200
    assert '<a href="/prospects" id="back-to-results"' in response.text
