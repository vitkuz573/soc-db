"""Shared fixtures and configuration for soc-db tests."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def sample_chip():
    return {
        "id": "sm8250_kona",
        "name": "Snapdragon 865",
        "vendor": "Qualcomm",
        "model": "SM8250",
        "cores": 8,
        "architecture": "ARMv8.2-A",
        "gpu": "Adreno 650",
        "process_nm": 7,
        "year": 2020,
        "completeness": 0.85,
    }


@pytest.fixture
def minimal_chip():
    return {
        "id": "test123",
        "name": "Test SoC",
        "vendor": "TestVendor",
    }


@pytest.fixture
def temp_data_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture(scope="module")
def db_conn():
    """Create a temporary SQLite database with migrated data for testing.

    Scope is ``module`` to amortize the migration cost across all tests
    in a module.  Returns the connection to the temp database.
    """
    from soc_db.db.connection import get_connection
    from soc_db.db.migrate import migrate

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        migrate(db_path, force=True)
        conn = get_connection(db_path)
        yield conn
        conn.close()


@pytest.fixture
def use_json_true(monkeypatch):
    """Set SOC_DB_USE_JSON=true for dual-read tests."""
    monkeypatch.setenv("SOC_DB_USE_JSON", "true")
    from soc_db.config import settings

    settings.use_json = True
    yield
    settings.use_json = False


@pytest.fixture
def use_wikidata_true(monkeypatch):
    """Set SOC_DB_USE_WIKIDATA=true for Wikidata integration tests."""
    monkeypatch.setenv("SOC_DB_USE_WIKIDATA", "true")
    from soc_db.config import settings

    settings.use_wikidata = True
    yield
    settings.use_wikidata = False
