"""
Pytest Configuration & Fixtures for FreightProspecting V1
Enforces strict test database isolation so the production database (data/prospects.db)
can NEVER be mutated by pytest.
"""

import os
from pathlib import Path
import shutil
import tempfile
import pytest

from src.backend.db.connection import DEFAULT_DB_PATH

# Global temporary directory for pytest session
_TEST_DB_DIR = None
_TEST_DB_PATH = None


def pytest_configure(config):
    """
    Called before test collection/import.
    Creates an isolated copy of the production database in a temporary directory
    and sets FREIGHT_DB_PATH and FP_TEST_MODE so all test modules, queries,
    and app routes automatically use this isolated copy.
    """
    global _TEST_DB_DIR, _TEST_DB_PATH
    os.environ["FP_TEST_MODE"] = "1"
    _TEST_DB_DIR = tempfile.mkdtemp(prefix="fp_pytest_")
    _TEST_DB_PATH = Path(_TEST_DB_DIR) / "prospects_test_isolated.db"
    if DEFAULT_DB_PATH.exists():
        shutil.copy2(DEFAULT_DB_PATH, _TEST_DB_PATH)
    os.environ["FREIGHT_DB_PATH"] = str(_TEST_DB_PATH)


def pytest_unconfigure(config):
    """Clean up isolated test database after pytest session completes."""
    global _TEST_DB_DIR
    if _TEST_DB_DIR and os.path.exists(_TEST_DB_DIR):
        try:
            shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)
        except Exception:
            pass


@pytest.fixture(scope="session")
def session_test_db():
    """Provides path to the session-wide isolated test database."""
    return _TEST_DB_PATH
