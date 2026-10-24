"""Shared test fixtures for api/tests (api/conftest.py keeps live services away from every test)."""

from pathlib import Path

import pytest

from api import accounts

TEST_ACCOUNTS = Path(__file__).parent / "data" / "accounts"  # test-oat: Hill Oat Co. <- Eastway (fictional)


@pytest.fixture(autouse=True)
def only_peak_bar(monkeypatch):
    """Tests see Peak Bar alone unless they ask for more, so adding an account to data/accounts/ changes no test
    (scripts/check_accounts.py checks the real ones; test_every_data_account_loads loads them all)."""
    monkeypatch.setattr(accounts, "ONLY", {"peak-bar"})
    accounts.clear()
    yield
    accounts.clear()


@pytest.fixture
def every_account(monkeypatch):
    monkeypatch.setattr(accounts, "ONLY", None)
    accounts.clear()
    yield accounts.every()
    accounts.clear()


@pytest.fixture
def two_accounts(monkeypatch):
    """Peak Bar plus the test account api/tests/data/accounts/test-oat; returns the test account."""
    monkeypatch.setattr(accounts, "ONLY", {"peak-bar", "test-oat"})
    monkeypatch.setattr(accounts, "ROOTS", [*accounts.ROOTS, TEST_ACCOUNTS])
    accounts.clear()
    yield accounts.get("test-oat")
    accounts.clear()
