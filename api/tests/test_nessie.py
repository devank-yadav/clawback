"""F15: Northmart's $41,350 deposit in Nessie starts the run (and each of Peak Bar Co.'s other distributors' deposits
starts theirs); GET /summary reads live runs; the Connections page shows what the poller saw."""

import json
import time
from decimal import Decimal as D
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from api import accounts, pipeline, sources
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
        assert request.url.scheme == "https"  # the live API is HTTPS only
        if self.fail:
            self.fail -= 1
            return httpx.Response(503)
        if request.method == "GET":
            return httpx.Response(200, json=self.deposits)
        body = json.loads(request.content)
        if "status" not in body:  # the live API answers 400 without it
            return httpx.Response(400, json={"code": 400, "message": "status is required"})
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


# Manasv posted this $41,350 Northmart deposit while setting up the account (DECISIONS.md, 02:30). It's history.
SETUP_DEPOSIT = {"_id": "9dce7f01-d664-4826-8d9a-84aaa4d09723", "amount": 41350.0, "status": "pending",
                 "description": "Northmart remittance INV-3102", "transaction_date": "2026-10-24"}


def test_a_deposit_posted_before_the_poller_starts_never_starts_a_run():
    fake = FakeNessie([SETUP_DEPOSIT])
    poller = nessie.Poller(client_for(fake), starter(ScenarioClaude()))
    assert poller.tick() == [] and poller.tick() == [] and not pipeline.RUNS
    made = client_for(fake).post_deposit()  # the "Northmart pays" button during the demo
    assert [d.id for d in poller.tick()] == [made.id] and len(pipeline.RUNS) == 1
    assert pipeline.latest("march").events[0].data.remittance.nessie_tx_id == made.id


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
    assert (body["amount"], body["description"], body["medium"], body["status"]) == (
        41350.0, "Northmart remittance INV-3102", "balance", "pending")
    run = pipeline.RUNS[r["run_id"]]
    assert wait_for(run, "waiting") and run.events[0].data.remittance.nessie_tx_id == "dep-1"


def test_pay_button_leaves_the_run_to_a_running_poller(api, monkeypatch):
    from api.routes import payments
    fake = FakeNessie()
    monkeypatch.setattr(nessie, "client", lambda: client_for(fake))
    monkeypatch.setattr(payments, "POLLER_WAIT_S", 0.3)
    nessie.poller = nessie.Poller(client_for(fake), starter(ScenarioClaude()), interval=60)
    nessie.poller.start()
    r = api.post("/payments/northmart").json()
    assert (r["via"], r["run_id"]) == ("nessie", None) and "poller" in r["message"]
    assert not pipeline.RUNS  # the button left it to the poller, which looks again in 60 s


def test_pay_button_returns_the_run_the_poller_started(api, monkeypatch):
    """With a run already on the board, the button must hand back the new run, not the previous one."""
    fake = FakeNessie()
    monkeypatch.setattr(nessie, "client", lambda: client_for(fake))
    previous = pipeline.start("march", ScenarioClaude(), background=False)
    nessie.poller = nessie.Poller(client_for(fake), starter(ScenarioClaude()), interval=0.05)
    nessie.poller.start()
    for _ in range(100):
        if nessie.poller.seen is not None:
            break
        time.sleep(0.02)
    r = api.post("/payments/northmart").json()
    assert r["via"] == "nessie" and r["run_id"] not in (None, previous.id) and "saw it" in r["message"]
    run = pipeline.RUNS[r["run_id"]]
    assert run.deposit.id == r["deposit_id"] and previous.replaced_by == run.id and wait_for(run, "waiting")


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


# ---------------------------------------------------------------- every distributor of Peak Bar Co.

PEAK_BAR = ("peak-bar", "peak-bar-kehe", "peak-bar-walmart", "peak-bar-five-below")


def stub_start(started):
    """pipeline.start without the agents: the run is registered for its account and nothing is processed, so a fee
    account's routing is tested without its readers' recordings."""
    def start(kind=None, client=None, background=True, deposit=None, account=None, charges=None):
        a = accounts.resolve(account)
        run = pipeline.Run(id=f"run-{a.invoice.month}-{a.id}-{len(started)}", kind=kind or a.invoice.month, account=a,
                           deposit=deposit, charges={c.id: c for c in charges or ()})
        pipeline.RUNS[run.id] = run
        started.append(run)
        return run
    return start


def test_each_peak_bar_distributor_has_its_own_deposit(every_account):
    found = {a.id: a for a in every_account}
    for account_id in PEAK_BAR:
        a = found[account_id]
        assert a.brand.name == "Peak Bar Co." and accounts.for_deposit(a.config.nessie_description).id == account_id
    assert {found[i].config.nessie_description for i in PEAK_BAR} == {
        "Northmart remittance INV-3102", "KeHE Distributors remittance PBK-2603", "Walmart remittance PBW-2603",
        "Five Below remittance PBF-2603"}


def test_the_poller_starts_each_distributors_run(every_account, monkeypatch):
    started = []
    monkeypatch.setattr(pipeline, "start", stub_start(started))
    fake = FakeNessie([OLD])
    poller = nessie.Poller(client_for(fake), pipeline.start_for_deposit)
    poller.tick()
    for account_id in PEAK_BAR:
        a = accounts.get(account_id)
        fake.deposits.append({"_id": f"dep-{account_id}", "amount": float(a.invoice.received),
                              "description": a.config.nessie_description, "transaction_date": "2026-04-10"})
    assert [d.id for d in poller.tick()] == [f"dep-{i}" for i in PEAK_BAR]
    assert [r.account.id for r in started] == list(PEAK_BAR)
    assert [r.deposit.amount for r in started] == [accounts.get(i).invoice.received for i in PEAK_BAR]
    for run in started:  # the Connections page: each account's deposit and the run it started
        seen = sources.last("bank", run.account.id)
        assert seen.run_id == run.id and f"started run {run.id}" in seen.text
    assert poller.tick() == [] and len(started) == 4


@pytest.mark.parametrize("account_id", PEAK_BAR)
def test_send_a_test_payment_posts_that_distributors_deposit(every_account, monkeypatch, account_id):
    from api.main import app

    started = []
    monkeypatch.setattr(pipeline, "start", stub_start(started))
    fake = FakeNessie()
    monkeypatch.setattr(nessie, "client", lambda: client_for(fake))
    r = TestClient(app).post(f"/payments/{account_id}").json()
    a = accounts.get(account_id)
    body = json.loads(fake.requests[-1].content)
    assert (body["amount"], body["description"]) == (float(a.invoice.received), a.config.nessie_description)
    assert (r["via"], r["deposit_id"], r["run_id"]) == ("nessie", "dep-1", started[0].id)
    assert started[0].account.id == account_id and started[0].deposit.id == "dep-1"
    assert sources.last("bank", account_id).run_id == started[0].id


def test_connections_show_the_last_poll_and_deposit(monkeypatch):
    from api.main import app

    monkeypatch.setenv("NESSIE_API_KEY", "test-nessie-key")
    monkeypatch.setenv("NESSIE_ACCOUNT_ID", "acct-1")
    fake = FakeNessie([OLD])
    nessie.poller = nessie.Poller(client_for(fake), starter(ScenarioClaude()), interval=60)
    nessie.poller.tick()
    fake.deposits.append(NORTHMART)
    nessie.poller.tick()
    nessie.poller._thread = SimpleNamespace(is_alive=lambda: True)  # as if its loop were running
    bank = next(c for c in TestClient(app).get("/connections?account=peak-bar").json() if c["id"] == "bank")
    run = pipeline.latest("march")
    assert bank["status"] == "connected" and bank["checked_at"] and bank["problem"] is None
    assert bank["run_id"] == run.id and bank["last_seen"].startswith("Deposit dep-new of $41,350.00")
    assert "Checked every 5 seconds" in bank["detail"]
    fake.fail = 2
    nessie.poller.tick()
    bank = next(c for c in TestClient(app).get("/connections?account=peak-bar").json() if c["id"] == "bank")
    assert "503" in bank["problem"] and bank["run_id"] == run.id  # what it last found stays


def test_a_deposit_that_cant_start_a_run_never_stops_the_poller():
    def broken(d):
        raise RuntimeError("no charges file")

    fake = FakeNessie([OLD])
    poller = nessie.Poller(client_for(fake), broken)
    poller.tick()
    fake.deposits.append(NORTHMART)
    assert poller.tick() == [] and "couldn't start the run" in sources.last("bank", "peak-bar").text


def test_a_deposit_that_couldnt_start_a_run_is_tried_once_more_later():
    calls, clock = [], [0.0]

    def flaky(d):
        calls.append(d.id)
        if len(calls) == 1:
            raise RuntimeError("database restarting")
        return pipeline.start_for_deposit(d, client=ScenarioClaude(), background=False)

    fake = FakeNessie([OLD])
    poller = nessie.Poller(client_for(fake), flaky, retry_after=60, clock=lambda: clock[0])
    poller.tick()
    fake.deposits.append(NORTHMART)
    assert poller.tick() == [] and calls == ["dep-new"]
    assert "trying once more in 60 s" in sources.last("bank", "peak-bar").text
    clock[0] = 30
    assert poller.tick() == [] and len(calls) == 1  # not yet
    clock[0] = 61
    assert [d.id for d in poller.tick()] == ["dep-new"] and len(calls) == 2 and len(pipeline.RUNS) == 1
    assert "started run" in sources.last("bank", "peak-bar").text
    clock[0] = 500
    assert poller.tick() == [] and len(calls) == 2  # once started, never again


def test_a_deposit_that_fails_twice_is_left_to_a_person():
    calls, clock = [], [0.0]

    def broken(d):
        calls.append(d.id)
        raise RuntimeError("no charges file")

    fake = FakeNessie([OLD])
    poller = nessie.Poller(client_for(fake), broken, retry_after=60, clock=lambda: clock[0])
    poller.tick()
    fake.deposits.append(NORTHMART)
    poller.tick()
    clock[0] = 61
    assert poller.tick() == [] and len(calls) == 2
    assert "still couldn't start the run" in sources.last("bank", "peak-bar").text
    clock[0] = 1000
    poller.tick()
    assert len(calls) == 2  # tried once more, and only once
