"""F15: Northmart's $41,350 deposit in Nessie starts the run; GET /summary reads live runs."""

import json
import time
from decimal import Decimal as D

import httpx
import pytest
from fastapi.testclient import TestClient

from api import pipeline
from api.agents import claude as claude_mod
from api.integrations import nessie, replay
from api.tests.test_pipeline import ScenarioClaude


class FakeNessie:
    """Nessie's deposits endpoints for one account: GET lists, POST creates (shapes as scripts/nessie_deposit.py)."""

    def __init__(self, deposits=(), fail=0):
        self.deposits = [dict(d) for d in deposits]
        self.fail, self.requests = fail, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.params["key"] == "test-nessie-key" and request.url.path == "/accounts/acct-1/deposits"
        if self.fail:
            self.fail -= 1
            return httpx.Response(503)
        if request.method == "GET":
            return httpx.Response(200, json=self.deposits)
        body = json.loads(request.content)
        made = {"_id": f"dep-{len(self.deposits) + 1}", "type": "deposit", "status": "pending", **body}
        self.deposits.append(made)
        return httpx.Response(201, json={"code": 201, "message": "Created deposit", "objectCreated": made})


def client_for(fake):
    http = httpx.Client(base_url=nessie.DEFAULT_BASE, transport=httpx.MockTransport(fake))
    return nessie.Nessie("test-nessie-key", "acct-1", http=http)


OLD = {"_id": "dep-old", "amount": 41350.0, "description": "Northmart remittance INV-3001", "transaction_date": "2026-02-20"}
NORTHMART = {"_id": "dep-new", "amount": 41350.0, "description": "Northmart remittance INV-3102",
             "transaction_date": "2026-04-20"}


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset()
    nessie.poller = None
    yield
    if nessie.poller:
        nessie.poller.stop()
    nessie.poller = None
    pipeline.reset()


def starter(fake_claude):
    return lambda d: pipeline.start_for_deposit(d, client=fake_claude, background=False)


def test_new_northmart_deposit_starts_one_march_run():
    fake = FakeNessie([OLD])
    poller = nessie.Poller(client_for(fake), starter(ScenarioClaude()))
    assert poller.tick() == [] and not pipeline.RUNS  # the first look: what's there already is history
    fake.deposits += [{"_id": "dep-other", "amount": 12.0, "description": "Interest", "transaction_date": None},
                      NORTHMART]
    started = poller.tick()
    assert [d.id for d in started] == ["dep-new"] and len(pipeline.RUNS) == 1
    run = pipeline.latest("march")
    rem = run.events[0].data.remittance
    assert (rem.received, rem.nessie_tx_id) == (D("41350.00"), "dep-new")
    assert any("Nessie: Northmart's deposit of $41,350 arrived (deposit dep-new)" in e.data.text
               for e in run.events if e.type == "log")
    assert poller.tick() == [] and len(pipeline.RUNS) == 1  # seen once, started once


def test_the_same_deposit_from_the_button_and_the_poller_starts_one_run():
    d = nessie.Deposit("dep-9", D("41350.00"), nessie.DESCRIPTION, None)
    fake = ScenarioClaude()
    a = pipeline.start_for_deposit(d, client=fake, background=False)
    b = pipeline.start_for_deposit(d, client=fake, background=False)
    assert a is b and len(pipeline.RUNS) == 1


def test_a_failed_poll_is_retried_next_time():
    fake = FakeNessie([OLD], fail=2)  # both tries of the first look fail
    poller = nessie.Poller(client_for(fake), starter(ScenarioClaude()))
    assert poller.tick() == [] and poller.errors == 1 and poller.seen is None
    poller.tick()
    fake.deposits.append(NORTHMART)
    assert [d.id for d in poller.tick()] == ["dep-new"]


def test_poller_thread_starts_the_run_within_seconds():
    fake = FakeNessie([OLD])
    poller = nessie.Poller(client_for(fake), starter(ScenarioClaude()), interval=0.05)
    nessie.poller = poller
    poller.start()
    for _ in range(100):
        if poller.seen is not None:
            break
        time.sleep(0.02)
    t0 = time.monotonic()
    fake.deposits.append(NORTHMART)
    while not pipeline.RUNS and time.monotonic() - t0 < 5:
        time.sleep(0.02)
    assert pipeline.RUNS and time.monotonic() - t0 < 5  # the design's bar is 10 seconds


@pytest.fixture
def api(monkeypatch):
    from api.main import app

    fake = ScenarioClaude()
    monkeypatch.setattr(claude_mod.anthropic, "Anthropic", lambda *a, **k: fake)
    return TestClient(app)


def wait_for(run, status, seconds=5):
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        if any(e.type == "run" and e.data.status == status for e in run.events):
            return True
        time.sleep(0.02)
    return False


def test_pay_button_without_nessie_starts_the_run_directly(api):
    r = api.post("/payments/northmart").json()
    assert (r["via"], r["deposit_id"]) == ("direct", None) and r["run_id"].startswith("run-march-")
    assert api.get("/runs/latest").json()["run_id"] == r["run_id"]
    assert wait_for(pipeline.RUNS[r["run_id"]], "waiting")  # let the background run settle inside the test


def test_pay_button_posts_the_deposit_to_nessie(api, monkeypatch):
    fake = FakeNessie()
    monkeypatch.setattr(nessie, "client", lambda: client_for(fake))
    r = api.post("/payments/northmart").json()
    assert (r["via"], r["deposit_id"]) == ("nessie", "dep-1") and r["run_id"]  # no poller: it starts the run
    body = json.loads(fake.requests[-1].content)
    assert (body["amount"], body["description"], body["medium"]) == (41350.0, "Northmart remittance INV-3102", "balance")
    run = pipeline.RUNS[r["run_id"]]
    assert wait_for(run, "waiting") and run.events[0].data.remittance.nessie_tx_id == "dep-1"


def test_pay_button_leaves_the_run_to_a_running_poller(api, monkeypatch):
    fake = FakeNessie()
    monkeypatch.setattr(nessie, "client", lambda: client_for(fake))
    nessie.poller = nessie.Poller(client_for(fake), starter(ScenarioClaude()), interval=60)
    nessie.poller.start()
    r = api.post("/payments/northmart").json()
    assert (r["via"], r["run_id"]) == ("nessie", None) and "poller" in r["message"]
    assert not pipeline.RUNS  # the button left it to the poller, which looks again in 60 s


def test_summary_reads_the_live_run(api, monkeypatch):
    monkeypatch.setenv("CLAWBACK_READONLY_TOKEN", "test-token")
    headers = {"Authorization": "Bearer test-token"}
    assert api.get("/summary", headers=headers).json()["run_id"] is None  # the recorded fake run
    run_id = api.post("/runs", json={"kind": "march"}).json()["run_id"]
    run = pipeline.RUNS[run_id]
    assert wait_for(run, "waiting")
    s = api.get("/summary", headers=headers).json()
    assert s["run_id"] == run_id and (s["totals"]["disputed"], s["totals"]["waiting"]) == (4120.0, 1200.0)
    assert [d["id"] for d in s["open_disputes"]] == ["D-0417"] and s["pending_question"]["charge_id"] == "C6"
    api.post(f"/questions/{s['pending_question']['id']}/answer", json={"text": "accept if notice is at least 14 days"})
    s = api.get("/summary", headers=headers).json()
    assert s["pending_question"] is None and [a["amount"] for a in s["pending_approvals"]] == [2730.0]
