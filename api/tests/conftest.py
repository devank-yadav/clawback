"""Shared test fixtures for api/tests (api/conftest.py keeps live services away from every test)."""

from pathlib import Path

import pytest

from api import accounts

TEST_ACCOUNTS = Path(__file__).parent / "data" / "accounts"  # test-oat: Hill Oat Co. <- Eastway (fictional)


@pytest.fixture
def two_accounts(monkeypatch):
    """Peak Bar plus the test account api/tests/data/accounts/test-oat; returns the test account."""
    monkeypatch.setattr(accounts, "ROOTS", [*accounts.ROOTS, TEST_ACCOUNTS])
    accounts.clear()
    yield accounts.get("test-oat")
    accounts.clear()
