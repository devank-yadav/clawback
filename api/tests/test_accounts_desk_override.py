"""DESK_EMAIL_<ACCOUNT_ID> points a distributor's deductions desk at a real inbox on a server."""

from api import accounts


def test_desk_email_can_be_set_by_the_server(monkeypatch):
    monkeypatch.setenv("DESK_EMAIL_PEAK_BAR", "desk@example.org")
    accounts.clear()
    try:
        assert accounts.get("peak-bar").distributor.desk_email == "desk@example.org"
    finally:
        monkeypatch.delenv("DESK_EMAIL_PEAK_BAR")
        accounts.clear()
    assert accounts.get("peak-bar").distributor.desk_email != "desk@example.org"
