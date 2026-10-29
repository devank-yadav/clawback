"""The distributor's portal payment, edited before it's sent (api/routes/payments.py): the draft is the invoice's own
deductions; a preview totals the edits through the engine; "Send payment" with lines runs exactly those lines and the
amount they leave paid. Without a body nothing changes."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from api import autopilot, disputes, pipeline, suppliers, accounts
from api.routes import payments

PEAK = suppliers.supplier_of(accounts.get(accounts.DEFAULT))


@pytest.fixture(autouse=True)
def _demo(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    pipeline.reset(), disputes.reset(), payments.reset()
    yield
    pipeline.reset(), disputes.reset(), payments.reset()


@pytest.fixture
def api():
    from api.main import app

    return TestClient(app)


def _lines(draft):
    return [{"id": ln["id"], "units": ln["units"], "rate": ln["rate"]} for ln in draft["lines"]]


def test_the_draft_is_the_invoice_as_it_stands(api):
    d = api.get("/portal/payments/peak-bar/draft").json()
    assert d["invoice_id"] == "INV-3102" and d["expected"] == 48200 and d["paid"] == 41350 and d["taken"] == 6850
    assert [ln["id"] for ln in d["lines"]] == ["C1", "C2", "C3", "C4", "C5", "C6"]
    assert [ln["fee"] for ln in d["lines"]] == [False] * 5 + [True] and d["edited"] is False


def test_a_preview_totals_the_edits(api):
    lines = _lines(api.get("/portal/payments/peak-bar/draft").json())
    lines[4]["units"] = 1500  # Mint: 1,500 bars at $1.00
    lines[5]["rate"] = 900  # the display fee: $900
    del lines[1]  # week 2 isn't taken
    p = api.post("/portal/payments/peak-bar/preview", json={"lines": lines}).json()
    by = {ln["id"]: ln for ln in p["lines"]}
    assert by["C5"]["amount"] == 1500 and by["C6"]["amount"] == 900 and "C2" not in by
    assert p["taken"] == 1800 + 330 + 1540 + 1500 + 900 and p["paid"] == 48200 - p["taken"] and p["edited"] is True


def test_bad_lines_are_refused(api):
    assert api.post("/portal/payments/peak-bar/preview", json={"lines": [{"id": "C9", "units": 1, "rate": 1}]}).status_code == 422
    assert api.post("/portal/payments/peak-bar/preview", json={"lines": [{"id": "C1", "units": -1, "rate": 1}]}).status_code == 422


def test_an_edited_payment_runs_with_its_own_lines_and_amount(api):
    lines = _lines(api.get("/portal/payments/peak-bar/draft").json())
    lines[0]["rate"] = 1.0  # week 1 at the deal's $1.00: a fair charge now
    sent = api.post("/portal/payments/peak-bar", json={"lines": lines}).json()
    assert sent["received"] == 48200 - (6850 - 600) and sent["run_id"]  # autopilot starts it at once
    run = pipeline.RUNS[sent["run_id"]]
    end = __import__("time").monotonic() + 60
    while not any(e.type == "run" and e.data.status in ("waiting", "finished", "failed") for e in run.events):
        assert __import__("time").monotonic() < end
        __import__("time").sleep(0.1)
    assert run.charges["C1"].amount == Decimal("1200.00") and run.charges["C1"].rate == Decimal("1")
    started = next(e.data for e in run.events if e.type == "run" and e.data.remittance)
    assert started.remittance.received == Decimal("41950.00") and started.remittance.taken == Decimal("6250.00")
    assert any("from its portal" in e.data.text for e in run.events if e.type == "log")


def test_a_waiting_edited_payment_keeps_its_lines(api):
    autopilot.update(PEAK, None, run_on_arrival=False)
    lines = _lines(api.get("/portal/payments/peak-bar/draft").json())[:5]  # no display fee
    sent = api.post("/portal/payments/peak-bar", json={"lines": lines}).json()
    assert sent["run_id"] is None and sent["received"] == 48200 - 5650
    started = api.post(f"/payments/pending/{sent['id']}/run").json()
    assert set(pipeline.RUNS[started["run_id"]].charges) == {"C1", "C2", "C3", "C4", "C5"}


def test_no_body_sends_the_invoice_as_is(api):
    autopilot.update(PEAK, None, run_on_arrival=False)
    sent = api.post("/portal/payments/peak-bar").json()
    assert sent["received"] == 41350 and sent["run_id"] is None
