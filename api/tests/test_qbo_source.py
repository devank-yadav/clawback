"""QuickBooks as a source: a payment recorded against an account's invoice starts that account's run, once; Clawback's
own $0 payments and the payments already there never do. A fake sandbox here; never the live API."""

import json
import re
from decimal import Decimal as D
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from api import accounts, pipeline, sources
from api.integrations import nessie, qbo, qbo_source, replay
from api.tests.test_nessie import PEAK_BAR, stub_start
from api.tests.test_pipeline import ScenarioClaude

REALM = "realm-1"


class FakeSandbox:
    """The QuickBooks sandbox's query and payment endpoints for a few invoices (shapes as Intuit's Payment entity)."""

    def __init__(self, invoices: dict[str, tuple[str, str, D]], payments=(), fail: int = 0):
        # DocNumber -> (invoice Id, customer Id, balance)
        self.invoices = {no: {"Id": i, "DocNumber": no, "CustomerRef": {"value": c}, "Balance": float(b),
                              "SyncToken": "0"} for no, (i, c, b) in invoices.items()}
        self.payments = [dict(p) for p in payments]
        self.fail, self.requests, self.next_id = fail, [], 500

    def pay(self, invoice_no: str, amount, note: str = "", pid: str | None = None) -> dict:
        inv = self.invoices[invoice_no]
        self.next_id += 1
        p = {"Id": pid or str(self.next_id), "SyncToken": "0", "CustomerRef": dict(inv["CustomerRef"]),
             "TotalAmt": float(amount), "TxnDate": "2026-04-20", "PrivateNote": note,
             "Line": [{"Amount": float(amount), "LinkedTxn": [{"TxnId": inv["Id"], "TxnType": "Invoice"}]}]}
        self.payments.append(p)
        return p

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["Authorization"] == "Bearer test-access-token"
        assert request.url.path.startswith(f"/v3/company/{REALM}/")
        if self.fail:
            self.fail -= 1
            return httpx.Response(503, text="Service Unavailable")
        path = request.url.path.removeprefix(f"/v3/company/{REALM}")
        params = parse_qs(urlparse(str(request.url)).query)
        if request.method == "GET" and path == "/query":
            q = params["query"][0]
            if m := re.fullmatch(r"select \* from Invoice where DocNumber = '(.+)'", q):
                found = [self.invoices[m.group(1)]] if m.group(1) in self.invoices else []
                return httpx.Response(200, json={"QueryResponse": {"Invoice": found} if found else {}})
            if m := re.fullmatch(r"select \* from Payment where CustomerRef = '(.+)' MAXRESULTS 1000", q):
                found = [p for p in self.payments if p["CustomerRef"]["value"] == m.group(1)]
                return httpx.Response(200, json={"QueryResponse": {"Payment": found} if found else {}})
            raise AssertionError(f"unexpected query {q}")
        if request.method == "POST" and path == "/payment":
            body = json.loads(request.content)
            if params.get("operation") == ["delete"]:
                gone = next(p for p in self.payments if p["Id"] == body["Id"])
                self.payments.remove(gone)
                for inv in self.invoices.values():
                    if any(lt["TxnId"] == inv["Id"] for ln in gone["Line"] for lt in ln["LinkedTxn"]):
                        inv["Balance"] += gone["TotalAmt"]
                return httpx.Response(200, json={"Payment": {"Id": body["Id"], "status": "Deleted"}})
            inv_id = body["Line"][0]["LinkedTxn"][0]["TxnId"]
            inv = next(i for i in self.invoices.values() if i["Id"] == inv_id)
            inv["Balance"] -= body["TotalAmt"]
            self.next_id += 1
            made = {"Id": str(self.next_id), "SyncToken": "0", **body}
            self.payments.append(made)
            return httpx.Response(200, json={"Payment": made})
        raise AssertionError(f"unexpected {request.method} {path}")


def books_for(fake) -> qbo.LiveBooks:
    http = httpx.Client(base_url=f"{qbo.BASE}/{REALM}", transport=httpx.MockTransport(fake))
    return qbo.LiveBooks(REALM, lambda: "test-access-token", http=http)


NORTHMART = {"INV-3102": ("130", "58", D("6850.00"))}  # the seed's $41,350 payment is already applied
SEED_PAYMENT = {"Id": "131", "SyncToken": "0", "CustomerRef": {"value": "58"}, "TotalAmt": 41350.0,
                "TxnDate": "2026-04-20", "Line": [{"Amount": 41350.0, "LinkedTxn": [{"TxnId": "130", "TxnType": "Invoice"}]}]}


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "FIXTURES", tmp_path)
    pipeline.reset()
    qbo_source.poller = nessie.poller = None
    yield
    for p in (qbo_source.poller, nessie.poller):
        if p:
            p.stop()
    qbo_source.poller = nessie.poller = None
    pipeline.reset()


def starter(client):
    return lambda p: pipeline.start_for_deposit(p, client=client, background=False, account=p.account_id)


def test_a_new_payment_on_the_invoice_starts_one_run():
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    poller = qbo_source.Poller(books_for(fake), starter(ScenarioClaude()))
    assert poller.tick() == [] and not pipeline.RUNS  # the seed's payment is history
    assert "1 payment already recorded" in sources.last("quickbooks").text
    fake.pay("INV-3102", "41350.00", pid="200")
    got = poller.tick()
    assert [(p.id, p.amount, p.account_id) for p in got] == [("200", D("41350.00"), "peak-bar")]
    run = pipeline.latest("march")
    rem = run.events[0].data.remittance
    assert (rem.received, rem.nessie_tx_id, run.deposit.source) == (D("41350.00"), None, "quickbooks")
    assert any("QuickBooks: a payment of $41,350 from Northmart was recorded against invoice INV-3102 (payment 200)."
               == e.data.text for e in run.events if e.type == "log")
    t = [e.data for e in run.events if e.type == "totals"][-1]
    assert (t.disputed, t.waiting) == (D("4120.00"), D("1200.00"))  # Peak Bar's numbers, unchanged
    assert poller.tick() == [] and len(pipeline.RUNS) == 1  # the same payment never starts a second run
    seen = sources.last("quickbooks", "peak-bar")
    assert seen.run_id == run.id and seen.text == f"Payment 200 of $41,350.00 on INV-3102 (Northmart): started run {run.id}"


def test_the_same_payment_from_two_looks_or_a_restart_is_one_run():
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    p = qbo_source.Payment(id="200", amount=D("41350.00"), description="Northmart payment on INV-3102",
                           account_id="peak-bar", total=D("41350.00"), txn_date=None)
    a = pipeline.start_for_deposit(p, client=ScenarioClaude(), background=False, account="peak-bar")
    b = pipeline.start_for_deposit(p, client=ScenarioClaude(), background=False, account="peak-bar")
    assert a is b and len(pipeline.RUNS) == 1
    fresh = qbo_source.Poller(books_for(fake), starter(ScenarioClaude()))  # after a restart: what's there is history
    fake.pay("INV-3102", "41350.00", pid="201")
    assert fresh.tick() == [] and fresh.tick() == [] and len(pipeline.RUNS) == 1


def test_an_invoice_seeded_after_the_poller_started_brings_its_payment_as_history():
    fake = FakeSandbox({})
    poller = qbo_source.Poller(books_for(fake), starter(ScenarioClaude()))
    assert poller.tick() == [] and poller.seen == set()  # nothing seeded yet
    fake.invoices.update(FakeSandbox(NORTHMART).invoices)  # scripts/seed_quickbooks.py runs now
    fake.payments.append(dict(SEED_PAYMENT))
    poller._missing.clear()  # don't wait the ten minutes before looking for it again
    assert poller.tick() == [] and not pipeline.RUNS
    fake.pay("INV-3102", "41350.00", pid="200")
    assert [p.id for p in poller.tick()] == ["200"] and len(pipeline.RUNS) == 1


def test_clawbacks_own_payments_never_start_a_run():
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    started = []
    poller = qbo_source.Poller(books_for(fake), started.append)
    poller.tick()
    fake.pay("INV-3102", 0, note="Clawback LP-A-1")  # the $0 payment that applies a credit memo
    fake.pay("INV-3102", "2730.00", note="Clawback LP-A-2")
    assert poller.tick() == [] and started == []


def test_a_payment_on_a_shared_customer_goes_to_the_account_whose_invoice_it_pays(every_account, monkeypatch):
    """KeHE Distributors pays both Peak Bar (PBK-2603) and Lantern Hill in the one sandbox company."""
    started = []
    monkeypatch.setattr(pipeline, "start", stub_start(started))
    invoices = {a.config.qbo.invoice_no: (f"9{n}", "kehe" if a.distributor.name.startswith("KeHE") else f"c{n}", D(0))
                for n, a in enumerate(every_account)}
    fake = FakeSandbox(invoices)
    poller = qbo_source.Poller(books_for(fake), lambda p: pipeline.start_for_deposit(p, account=p.account_id))
    poller.tick()
    kehe = accounts.get("peak-bar-kehe")
    fake.pay("PBK-2603", kehe.invoice.received, pid="300")
    assert [p.account_id for p in poller.tick()] == ["peak-bar-kehe"]
    assert started[0].account.id == "peak-bar-kehe" and started[0].deposit.amount == kehe.invoice.received
    other = next(a for a in every_account if a.id != "peak-bar-kehe" and a.config.qbo.customer == "KeHE Distributors")
    fake.pay(other.config.qbo.invoice_no, "100.00", pid="301")
    assert [p.account_id for p in poller.tick()] == [other.id]


def test_each_peak_bar_distributors_payment_starts_its_run(every_account, monkeypatch):
    started = []
    monkeypatch.setattr(pipeline, "start", stub_start(started))
    found = {a.id: a for a in every_account}
    fake = FakeSandbox({found[i].config.qbo.invoice_no: (f"7{n}", f"c{n}", D(0)) for n, i in enumerate(PEAK_BAR)})
    poller = qbo_source.Poller(books_for(fake), lambda p: pipeline.start_for_deposit(p, account=p.account_id),
                               every=lambda: [found[i] for i in PEAK_BAR])
    poller.tick()
    for i in PEAK_BAR:
        fake.pay(found[i].config.qbo.invoice_no, found[i].invoice.received)
    poller.tick()
    assert [r.account.id for r in started] == list(PEAK_BAR)
    assert [r.deposit.amount for r in started] == [found[i].invoice.received for i in PEAK_BAR]


def test_a_failed_look_is_noted_and_tried_again():
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT], fail=2)  # both tries of the first call fail
    poller = qbo_source.Poller(books_for(fake), starter(ScenarioClaude()))
    assert poller.tick() == [] and poller.errors == 1 and poller.seen is None
    assert "503" in sources.state("quickbooks").error
    poller.tick()
    assert sources.state("quickbooks").error is None and poller.seen == {"131"}


def test_polling_is_never_recorded_as_a_fixture(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORD_FIXTURES", "1")
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    qbo_source.Poller(books_for(fake), starter(ScenarioClaude())).tick()
    assert fake.requests and not list((tmp_path / "qbo").glob("*.json"))


def test_the_poller_runs_only_with_keys_and_outside_demo_mode(monkeypatch):
    assert qbo_source.start_poller(lambda p: None) is None  # no keys
    for k in qbo.KEYS:
        monkeypatch.setenv(k, "test")
    monkeypatch.setenv("DEMO_MODE", "true")
    qbo.reset()
    assert qbo_source.start_poller(lambda p: None) is None
    monkeypatch.delenv("DEMO_MODE")
    monkeypatch.setenv("QBO_POLL", "off")
    qbo.reset()
    assert qbo_source.start_poller(lambda p: None) is None
    qbo.reset()


def test_a_deposit_and_the_same_payment_in_quickbooks_are_one_run():
    deposit = nessie.Deposit("dep-9", D("41350.00"), nessie.DESCRIPTION, None)
    run = pipeline.start_for_deposit(deposit, client=ScenarioClaude(), background=False)
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    poller = qbo_source.Poller(books_for(fake), starter(ScenarioClaude()))
    poller.tick()
    fake.pay("INV-3102", "41350.00", pid="200")
    assert [p.id for p in poller.tick()] == ["200"] and list(pipeline.RUNS) == [run.id]
    assert sources.last("quickbooks", "peak-bar").text.endswith(f"the same payment as run {run.id}")
    assert any("QuickBooks shows the same payment" in e.data.text for e in run.events if e.type == "log")
    other = nessie.Deposit("dep-10", D("41350.00"), nessie.DESCRIPTION, None)  # a second deposit is a new payment
    assert pipeline.start_for_deposit(other, client=ScenarioClaude(), background=False) is not run


def test_pay_records_the_distributors_payment_for_the_demo():
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    books = books_for(fake)
    with pytest.raises(qbo.BooksError, match="--replace"):
        qbo_source.pay("peak-bar", books=books)  # INV-3102 already has its payment
    poller = qbo_source.Poller(books, starter(ScenarioClaude()))
    poller.tick()
    made = qbo_source.pay("peak-bar", replace=True, books=books)
    assert made["TotalAmt"] == 41350.0 and not made["PrivateNote"].startswith(qbo.MARK)
    assert [p["Id"] for p in fake.payments] == [made["Id"]] and fake.invoices["INV-3102"]["Balance"] == 6850.0
    assert [p.id for p in poller.tick()] == [made["Id"]] and len(pipeline.RUNS) == 1


def test_connections_show_the_last_sync(monkeypatch):
    from api.main import app

    for k in qbo.KEYS:
        monkeypatch.setenv(k, "test")
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    qbo_source.poller = qbo_source.Poller(books_for(fake), starter(ScenarioClaude()))
    qbo_source.poller.tick()
    fake.pay("INV-3102", "41350.00", pid="200")
    qbo_source.poller.tick()
    qbo_source.poller._thread = type("T", (), {"is_alive": lambda self: True})()
    card = next(c for c in TestClient(app).get("/connections?account=peak-bar").json() if c["id"] == "quickbooks")
    run = pipeline.latest("march")
    assert card["status"] == "connected" and card["checked_at"] and card["run_id"] == run.id
    assert "INV-3102 starts the agents" in card["detail"] and card["last_seen"].startswith("Payment 200 of $41,350.00")
    qbo.reset()


def test_a_payment_that_couldnt_start_a_run_is_tried_once_more_later():
    calls, clock = [], [0.0]
    start = starter(ScenarioClaude())

    def flaky(p):
        calls.append(p.id)
        if len(calls) == 1:
            raise RuntimeError("database restarting")
        return start(p)

    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    poller = qbo_source.Poller(books_for(fake), flaky, retry_after=60, clock=lambda: clock[0])
    poller.tick()
    fake.pay("INV-3102", "41350.00", pid="200")
    assert poller.tick() == [] and calls == ["200"]
    assert "trying once more in 60 s" in sources.last("quickbooks", "peak-bar").text
    clock[0] = 61
    assert [p.id for p in poller.tick()] == ["200"] and len(calls) == 2 and len(pipeline.RUNS) == 1
    clock[0] = 500
    assert poller.tick() == [] and len(calls) == 2


def test_a_payment_that_fails_twice_is_left_to_a_person():
    calls, clock = [], [0.0]

    def broken(p):
        calls.append(p.id)
        raise RuntimeError("no charges file")

    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    poller = qbo_source.Poller(books_for(fake), broken, retry_after=60, clock=lambda: clock[0])
    poller.tick()
    fake.pay("INV-3102", "41350.00", pid="200")
    poller.tick()
    clock[0] = 61
    poller.tick()
    clock[0] = 1000
    poller.tick()
    assert len(calls) == 2 and "still couldn't start the run" in sources.last("quickbooks", "peak-bar").text


def reseed(fake: FakeSandbox, new_id: str, seed_pid: str) -> None:
    """scripts/seed_quickbooks.py after the invoice was deleted: INV-3102 again, a new Id, the seed's payment on it."""
    fake.invoices["INV-3102"] = {**fake.invoices["INV-3102"], "Id": new_id}
    fake.payments = [p for p in fake.payments if p["Id"] != "131"]
    fake.payments.append({**SEED_PAYMENT, "Id": seed_pid,
                          "Line": [{"Amount": 41350.0, "LinkedTxn": [{"TxnId": new_id, "TxnType": "Invoice"}]}]})


def test_a_reseeded_invoice_is_watched_after_a_demo_reset(monkeypatch):
    from api.main import app

    started = []
    monkeypatch.setattr(pipeline, "start", stub_start(started))
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    qbo_source.poller = poller = qbo_source.Poller(books_for(fake), lambda p: pipeline.start_for_deposit(
        p, account=p.account_id), clock=lambda: 0.0)
    poller.tick()
    reseed(fake, "140", "141")
    fake.pay("INV-3102", "41350.00", pid="150")  # on the new invoice: the old Id's watcher can't see it
    assert poller.tick() == [] and not started
    assert TestClient(app).post("/demo/reset").status_code == 200  # forgets the invoice Ids
    assert poller.tick() == [] and not started  # the new invoice's payments already there are history
    fake.pay("INV-3102", "41350.00", pid="151")
    assert [p.id for p in poller.tick()] == ["151"] and started[0].deposit.id == "151"


def test_a_reseeded_invoice_is_found_again_without_a_reset():
    clock = [0.0]
    started = []
    fake = FakeSandbox(NORTHMART, [SEED_PAYMENT])
    poller = qbo_source.Poller(books_for(fake), started.append, clock=lambda: clock[0])
    poller.tick()
    reseed(fake, "140", "141")
    clock[0] = qbo_source.REFRESH_INVOICES_S + 1
    assert poller.tick() == [] and poller.invoices["peak-bar"]["Id"] == "140"
    fake.pay("INV-3102", "41350.00", pid="151")
    assert [p.id for p in poller.tick()] == ["151"] and [p.id for p in started] == ["151"]
