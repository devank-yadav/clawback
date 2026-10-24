"""One supplier tracking many distributors (api/suppliers.py): grouping, plain statuses, tracking."""

import pytest
from fastapi.testclient import TestClient

from api import pipeline, suppliers
from api.agents import claude as claude_mod
from api.tests.test_pipeline import ScenarioClaude


@pytest.fixture
def api(monkeypatch, tmp_path):
    from api.main import app

    monkeypatch.setenv("CLAWBACK_STATE_DIR", str(tmp_path))
    fake = ScenarioClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    pipeline.reset()
    yield TestClient(app), fake
    pipeline.reset()


def test_peak_bar_is_its_own_supplier_waiting_for_payment(api):
    client, _ = api
    (s,) = [s for s in client.get("/suppliers").json() if s["id"] == "peak-bar"]
    (d,) = s["distributors"]
    assert (d["account_id"], d["tracked"], d["status"]) == ("peak-bar", True, "waiting_for_payment")
    assert "$" not in d["status_label"]  # the home page shows no money figures


def test_a_run_waiting_on_the_owner_says_so(api):
    client, fake = api
    pipeline.start("march", fake, background=False)
    (s,) = [s for s in client.get("/suppliers").json() if s["id"] == "peak-bar"]
    assert (s["distributors"][0]["status"], s["distributors"][0]["status_label"]) == ("needs_you", "1 decision for you")


def test_untracking_moves_it_last_and_tracking_brings_it_back(api, two_accounts):
    client, _ = api
    assert suppliers.supplier_of(two_accounts) == "test-oat"
    r = client.post("/suppliers/peak-bar/tracking", json={"account_id": "peak-bar", "tracked": False})
    assert r.status_code == 200 and r.json()["distributors"][0]["tracked"] is False
    r = client.post("/suppliers/peak-bar/tracking", json={"account_id": "peak-bar", "tracked": True})
    assert r.json()["distributors"][0]["tracked"] is True
    assert client.post("/suppliers/peak-bar/tracking", json={"account_id": "test-oat", "tracked": False}).status_code == 404
