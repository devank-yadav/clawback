"""A payment the distributor sends from its portal waits as "received" until the admin presses "Run the agents":
POST /portal/payments/{account} records it (nothing runs), GET /payments/pending lists it, and
POST /payments/pending/{id}/run starts its run like the payment button and stops it waiting."""

import pytest
from fastapi.testclient import TestClient

from api import pipeline
from api.agents import claude as claude_mod
from api.integrations import replay
from api.routes import payments
from api.tests.test_nessie import wait_for
from api.tests.test_pipeline import ScenarioClaude


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset()
    payments.reset()
    yield
    payments.reset()
    pipeline.reset()


@pytest.fixture
def api(monkeypatch):
    from api.main import app

    fake = ScenarioClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _manual_runs():
    """These tests are about a received payment that waits for "Run the agents": the owner's autopilot is off."""
    from api import accounts, autopilot, suppliers

    autopilot.save(suppliers.supplier_of(accounts.get(accounts.DEFAULT)), autopilot.Autopilot(run_on_arrival=False))


def test_a_payment_sent_from_the_portal_waits_and_starts_nothing(api):
    sent = api.post("/portal/payments/peak-bar").json()
    assert (sent["account_id"], sent["distributor"], sent["source"]) == ("peak-bar", "Northmart", "portal")
    assert (sent["invoice_id"], sent["expected"], sent["received"]) == ("INV-3102", 48200, 41350)
    assert api.post("/portal/payments/peak-bar").json()["id"] == sent["id"]  # a second press is the same one
    assert [p["id"] for p in api.get("/payments/pending").json()] == [sent["id"]]
    assert pipeline.latest(account="peak-bar") is None


def test_run_the_agents_starts_the_run_and_the_payment_stops_waiting(api):
    sent = api.post("/portal/payments/peak-bar").json()
    r = api.post(f"/payments/pending/{sent['id']}/run").json()
    assert r["via"] == "direct" and r["run_id"].startswith("run-march-")
    assert api.get("/payments/pending").json() == []
    assert wait_for(pipeline.RUNS[r["run_id"]], "waiting")  # let the background run settle inside the test


def test_unknown_accounts_and_payments_are_404(api):
    assert api.post("/portal/payments/no-such-account").status_code == 404
    assert api.post("/payments/pending/PAY-nothing-1/run").status_code == 404


def test_a_demo_reset_forgets_waiting_payments(api):
    api.post("/portal/payments/peak-bar")
    assert api.post("/demo/reset").status_code == 200
    assert api.get("/payments/pending").json() == []
