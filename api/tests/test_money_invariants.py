"""Money adds up everywhere, for every account (replayed from recordings, no AI):
- each charge: disputed + accepted + waiting (+ undecided) == the amount taken;
- each run: its totals' taken == the charges' amounts == disputed + accepted + waiting + undecided;
- its History row (GET /accounts/{id}/runs) says the same taken as its totals, so the Distributors page and Home agree;
- C3, fair because the broker's email extended the promo, says so from the data."""

from decimal import Decimal as D

import pytest

from api import accounts, disputes, history, pipeline, story, supplier_overview, tenancy
from api.engine import types as eng
from api.integrations import replay

ALL = sorted(p.parent.name for p in (accounts.DATA / "accounts").glob("*/account.yaml"))


@pytest.fixture
def every(monkeypatch):
    monkeypatch.setattr(accounts, "ONLY", None)
    accounts.clear(), pipeline.reset(), disputes.reset()
    yield
    accounts.clear(), pipeline.reset(), disputes.reset()


@pytest.mark.parametrize("account_id", ALL)
def test_every_charge_and_every_run_adds_up(every, account_id):
    a = accounts.get(account_id)
    with replay.replaying():
        run = pipeline.start(a.invoice.month, account=a, background=False)
    for cid, c in run.charges.items():
        d = run.decisions[cid]
        waiting = c.amount if d.kind in (eng.DecisionKind.ASK, eng.DecisionKind.SKIP) else D(0)
        assert d.disputed + d.accepted + waiting == c.amount, (account_id, cid, d)
        assert d.disputed >= 0 and d.accepted >= 0
    t = [e.data for e in run.events if e.type == "totals"][-1]
    assert t.taken == sum((c.amount for c in run.charges.values()), D(0))
    assert t.taken == t.disputed + t.accepted + t.waiting + t.undecided, account_id
    (row,) = [r for r in history.runs(a) if r.run_id == run.id]
    assert row.taken == t.taken and (row.disputed, row.accepted, row.waiting) == (t.disputed, t.accepted, t.waiting)


def test_home_equals_the_distributors_rows_and_the_open_disputes(every, monkeypatch):
    monkeypatch.setenv("DEMO_STORY", "on")
    story.build()
    who = tenancy.Caller(supplier_id="peak-bar", via="session")
    o = supplier_overview.overview(who)
    rows = [next(r for r in history.runs(accounts.get(aid)) if not r.replaced)
            for aid in {r.account.id for r in pipeline.RUNS.values()}]
    assert o.totals.taken == sum((r.taken for r in rows), D(0))
    assert o.totals.disputed == sum((r.disputed for r in rows), D(0))
    assert o.totals.fair == sum((r.accepted for r in rows), D(0))
    assert o.totals.taken == o.totals.disputed + o.totals.fair + o.totals.waiting
    assert o.totals.disputed_awaiting_reply == sum((d.amount for d in o.open_disputes), D(0))
    unfi = next(d for d in o.open_disputes if d.dispute_id == "D-1030")
    assert (unfi.total, unfi.agreed, unfi.amount) == (D("2320.00"), D("420.00"), D("1900.00"))


def test_c3_says_the_brokers_email_made_it_fair(every, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "true")
    run = pipeline.start("march", background=False)
    d = run.shown["C3"]
    assert (d.decision, d.accepted) == ("accept", D("330.00"))
    assert d.reason == ("Fair: Jordan Lee, an approved sender, extended the promo through Apr 7 by email on Mar 28 "
                        "(up to 500 more units).")
