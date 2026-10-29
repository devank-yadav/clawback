"""Readable document names from file names (api/library.readable_name), for documents whose text has no heading."""

import pytest

from api import accounts, library


@pytest.fixture
def every_account(monkeypatch):
    monkeypatch.setattr(accounts, "ONLY", None)  # Peak Bar Co.'s six distributors
    accounts.clear()
    yield
    accounts.clear()


@pytest.mark.parametrize("account_id, doc_id, name", [
    ("peak-bar-five-below", "five-below-vendor-agreement-2023-excerpt-peak-bar", "Five Below vendor agreement, 2023 (excerpt)"),
    ("peak-bar-sams", "sams-club-grocery-merchandise-agreement-2020-excerpt-peak-bar", "Sam's Club grocery merchandise agreement, 2020 (excerpt)"),
    ("peak-bar-sams", "peak-bar-sams-sampling-fee-2026-03-10", "Sam's Club sampling fee, Mar 10, 2026"),
    ("peak-bar-unfi", "unfi-clearvue-supplier-agreement-2010-peak-bar", "UNFI ClearVue supplier agreement, 2010"),
    ("peak-bar-kehe", "peak-bar-kehe-promotion-2026-03", "KeHE Distributors promotion, March 2026"),
    ("peak-bar", "spring-promo", "Spring promo"),
])
def test_a_file_name_reads_as_a_name(every_account, account_id, doc_id, name):
    assert library.readable_name(doc_id, accounts.get(account_id)) == name
