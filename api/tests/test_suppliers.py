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


def test_history_lists_runs_newest_first_and_marks_the_replaced_one(api):
    client, fake = api
    assert client.get("/accounts/peak-bar/runs").json() == []  # nothing until the agents have run
    first = pipeline.start("march", fake, background=False)
    second = pipeline.start("march", fake, background=False)
    got = client.get("/accounts/peak-bar/runs").json()
    assert [r["run_id"] for r in got] == [second.id, first.id]
    assert (got[0]["replaced"], got[1]["replaced"]) == (False, True)
    assert (got[0]["taken"], got[0]["disputed"], got[0]["questions"]) == (6850.0, 4120.0, 1)


def test_saved_lists_locked_deal_records_and_rules(api):
    client, fake = api
    got = client.get("/accounts/peak-bar/saved").json()
    deal = next(d for d in got["documents"] if d["id"] == "spring-promo")
    assert deal["locked"] is True and deal["chars"] > 0
    assert {r["label"] for r in got["records"]} >= {"Store sales", "Past payments"} and got["rules"] == []
    text = client.get("/accounts/peak-bar/documents/spring-promo").json()
    assert "maximum of 5,000 units" in text["text"] and text["locked"] is True
    assert client.get("/accounts/peak-bar/documents/nope").status_code == 404
    assert client.put("/accounts/peak-bar/documents/spring-promo", json={"text": "x"}).status_code == 405  # never edited


def test_connections_say_what_is_real(api):
    client, _ = api
    got = {c["id"]: c["status"] for c in client.get("/connections").json()}
    assert got["upload"] == "ready" and got["portals"] == "coming_soon"
    assert got["quickbooks"] == got["bank"] == "not_connected"  # tests blank every key
    assert got["inbox"] == "connected"  # shown as connected on every server


def test_contract_library_highlights_the_terms_the_agents_read(api):
    client, fake = api
    before = client.get("/accounts/peak-bar/contract").json()
    assert before["read_in_run"] is None and all(d["terms"] == [] for d in before["documents"])
    pipeline.start("march", fake, background=False)
    got = client.get("/accounts/peak-bar/contract").json()
    deal = next(d for d in got["documents"] if d["id"] == "spring-promo")
    assert got["read_in_run"] and deal["locked"] is True and deal["kind"] == "deal"
    cap = next(t for t in deal["terms"] if t["type"] == "unit_cap")
    assert deal["text"][cap["char_start"]:cap["char_end"]] == cap["quote"] and cap["label"] == "at most 5,000 units"
