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
