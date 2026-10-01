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

from src.backend.db.connection import DEFAULT_DB_PATH, WORKSPACE_ROOT

# Global temporary directory for pytest session
_TEST_DB_DIR = None
_TEST_DB_PATH = None
_HISTORICAL_DB_PATH = None


def pytest_configure(config):
    """
    Called before test collection/import.
    Creates an isolated copy of the production database in a temporary directory
    and sets FREIGHT_DB_PATH and FP_TEST_MODE so all test modules, queries,
    and app routes automatically use this isolated copy.
    Also creates an isolated copy of the pre-Tier-A frozen historical baseline
    for historical regression tests.
    """
    global _TEST_DB_DIR, _TEST_DB_PATH, _HISTORICAL_DB_PATH
    os.environ["FP_TEST_MODE"] = "1"
    _TEST_DB_DIR = tempfile.mkdtemp(prefix="fp_pytest_")
    _TEST_DB_PATH = Path(_TEST_DB_DIR) / "prospects_test_isolated.db"
    if DEFAULT_DB_PATH.exists():
        shutil.copy2(DEFAULT_DB_PATH, _TEST_DB_PATH)

    historical_backup_src = WORKSPACE_ROOT / "data" / "backups" / "prospects_backup_pre_tier_a_phase_a_final_remediation_20260929_065851.db"
    _HISTORICAL_DB_PATH = Path(_TEST_DB_DIR) / "prospects_historical_stage3.db"
    if historical_backup_src.exists():
        shutil.copy2(historical_backup_src, _HISTORICAL_DB_PATH)

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


@pytest.fixture(scope="session")
def session_historical_db():
    """Provides path to the session-wide isolated historical database."""
    return _HISTORICAL_DB_PATH


@pytest.fixture(scope="module")
def use_historical_stage3_db():
    """
    Fixture for historical regression tests protecting earlier milestones (Stage 3A-3H, Batch 1).
    Points FREIGHT_DB_PATH to an isolated copy of the pre-Tier-A frozen baseline,
    then cleanly restores FREIGHT_DB_PATH to the session test database upon teardown.
    """
    global _HISTORICAL_DB_PATH, _TEST_DB_PATH
    old = os.environ.get("FREIGHT_DB_PATH")
    os.environ["FREIGHT_DB_PATH"] = str(_HISTORICAL_DB_PATH)
    yield _HISTORICAL_DB_PATH
    if old:
        os.environ["FREIGHT_DB_PATH"] = old
    elif _TEST_DB_PATH:
        os.environ["FREIGHT_DB_PATH"] = str(_TEST_DB_PATH)
    else:
        os.environ.pop("FREIGHT_DB_PATH", None)
