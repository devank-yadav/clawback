"""Value per run, the six-month lookback, the dispute packet and the owner's summary text, through the routes.

Peak Bar replays its recorded March offline (DEMO_MODE, as test_acceptance_p0.py does); the lookback runs on the small
test account api/tests/data/accounts/test-look, whose numbers are worked out by hand below.
"""

import io
from datetime import date
from decimal import Decimal

import pypdf
import pytest
from fastapi.testclient import TestClient

from api import accounts, pipeline
from api.integrations import sms
from api.main import app
from api.tests.conftest import TEST_ACCOUNTS
from api.tests.test_acceptance_p0 import _march, _offline_demo_mode, _wait  # noqa: F401 - the offline fixture

D = Decimal


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def look(monkeypatch):
    """Peak Bar plus api/tests/data/accounts/test-look (Cove Tea Co. <- Lakeport, fictional)."""
    monkeypatch.setattr(accounts, "ONLY", {"peak-bar", "test-look"})
    monkeypatch.setattr(accounts, "ROOTS", [*accounts.ROOTS, TEST_ACCOUNTS])
    accounts.clear()
    yield accounts.get("test-look")
    accounts.clear()


# ---------------------------------------------------------------- Peak Bar: value, owner text, deadlines, packet

SUMMARY = ("Clawback checked Northmart's 6 deductions: $4,120 being recovered, $1,530 fair, 1 question for you. "
           "6-month check: $0 still claimable.")


def test_peak_bar_value_owner_text_and_file_by(client):
    march = _march(client)
    first = next(e.data.value for e in march.events if e.type == "totals" and e.data.value)
    assert (first.disputed, first.accepted, first.questions, first.charges) == (D(4120), D(1530), 1, 6)
    assert first.ai_calls > 0 and first.ai_cost_usd == 0.0  # every answer was recorded: nothing billed now
    assert first.manual_minutes is None and first.manual_minutes_per_charge is None  # policy sets no figure yet
    assert first.seconds_to_decided is not None and first.seconds_to_decided >= 0

    # One summary text to Dana, after the gate and before anything waits on her; numbers from value and lookback.
    owner = [text for role, text in sms.outbox if role == "owner"]
    assert owner[-1] == SUMMARY and owner.count(SUMMARY) == 1
    (msg,) = client.get("/inbox").json()["messages"]
    assert (msg["run_id"], msg["text"], msg["channel"]) == (march.id, SUMMARY, "inbox")  # DEMO_MODE sends nothing

    # Paid Apr 20 (qbo.payment_date), Peak Bar states no window: the policy's 90 days, to Jul 19.
    dispute = next(e.data for e in march.events if e.type == "dispute")
    assert {(ln.file_by, ln.days_left) for ln in dispute.lines} == {(date(2026, 7, 19), 90)}

    client.post("/questions/Q-1/answer", json={"text": "accept if notice is at least 14 days"})
    _wait(march.id, "finished")
    final = [e.data for e in march.events if e.type == "totals"][-1]
    assert (final.disputed, final.accepted, final.questions) == (D(4120), D(2730), 1)
    assert (final.value.disputed, final.value.accepted, final.value.ai_calls) == (D(4120), D(2730), first.ai_calls)
    assert [text for role, text in sms.outbox if role == "owner"].count(SUMMARY) == 1  # the answer sends no second

    current = client.get("/accounts/peak-bar/overview").json()["current"]
    assert (current["value"]["disputed"], current["value"]["accepted"]) == (4120.0, 2730.0)


def test_packet_pdf_for_the_live_dispute(client):
    _march(client)
    r = client.get("/portal/disputes/D-0417/packet.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    pdf = pypdf.PdfReader(io.BytesIO(r.content))
    assert len(pdf.pages) == 1
    text = " ".join(pdf.pages[0].extract_text().split())
    for want in ("Dispute D-0417", "to Northmart", "Invoice INV-3102", "File by: July 19, 2026",
                 "Total disputed: $4,120.00 on 4 lines", "$600.00 disputed", "$980.00 disputed", "$1,540.00 disputed",
                 "$1,000.00 disputed", "maximum of 5,000 units", "promo_units: 1600", "rows under line 1"):
        assert want in text, want
    assert "Math: Store sales show 1,540 promoted units for this period. Cap 5,000 units" in text  # math_parts' steps


def test_packet_pdf_without_a_run_prints_the_fixture_dispute(client):
    pdf = pypdf.PdfReader(io.BytesIO(client.get("/portal/disputes/D-0417/packet.pdf").content))
    text = " ".join(pdf.pages[0].extract_text().split())
    assert "Total disputed: $4,120.00 on 4 lines" in text and "File by: July 19, 2026" in text
    assert client.get("/portal/disputes/D-9999/packet.pdf").status_code == 404


# ---------------------------------------------------------------- the lookback, worked by hand (test-look)

def test_lookback_route_by_hand(client, look):
    body = client.get("/accounts/test-look/lookback").json()
    # Paid Jul 20 (qbo.payment_date); the deal's 7.2 says 60 days, its quote found word for word.
    assert (body["account_id"], body["as_of"], body["dispute_window_days"]) == ("test-look", "2026-07-20", 60)
    rows = {r["ref"]: r for r in body["rows"]}
    # LP-1101 (Nov) is outside the six months ending June; LP-9001 is this payment's own charge (the run decides it).
    assert list(rows) == ["LP-0201", "LP-0301", "LP-0501", "LP-0502"]
    got = {ref: (r["allowed"], r["wrongly_taken"], r["file_by"], r["days_left"], r["status"]) for ref, r in rows.items()}
    assert got == {
        # 30 units claimed short, the signed delivery shows 0: all $90 wrong. Feb 20 + 60 = Apr 21, 90 days gone.
        "LP-0201": (0.0, 90.0, "2026-04-21", -90, "past_window"),
        "LP-0301": (None, 0.0, None, None, "not_checked"),  # a display fee needs the deal read
        "LP-0501": (280.0, 0.0, None, None, "fair"),  # 700 x $0.40, under the 1,000 cap
        # 500 claimed after 700: 300 left under the cap, x $0.40 = $120 allowed, $80 wrong. May 25 + 60 = Jul 24.
        "LP-0502": (120.0, 80.0, "2026-07-24", 4, "claimable"),
    }
    assert rows["LP-0502"]["deducted_on"] == "2026-05-25" and "300 units x $0.40" in rows["LP-0502"]["note"]
    assert body["totals"] == {"wrongly_taken": 170.0, "lost_past_window": 90.0, "claimable_now": 80.0, "checked": 3,
                              "not_checked": 1}

    kpis = client.get("/accounts/test-look/overview").json()["kpis"]
    assert (kpis["wrongly_taken_6m"], kpis["lost_past_window"], kpis["claimable_now"]) == (170.0, 90.0, 80.0)
    assert client.get("/accounts/nobody/lookback").status_code == 404


def test_a_window_quote_not_in_the_deal_falls_back_to_the_policy(look, tmp_path, monkeypatch):
    from api import lookback

    monkeypatch.setattr(lookback.account_rows, "ops_terms", lambda _a: [lookback.account_rows.OpsTerm(
        key="dispute_window_days", value="60", source_doc="test-look-deal", quote="Disputes are allowed for 60 days.")])
    assert lookback.window_days(look) == 90  # the quote isn't in the deal, so the term can't count


def test_every_account_without_history_columns_still_looks_back(client):
    body = client.get("/accounts/peak-bar/lookback").json()
    assert body["as_of"] == "2026-04-20" and body["dispute_window_days"] == 90
    assert body["totals"]["checked"] + body["totals"]["not_checked"] == len(body["rows"])
    assert pipeline.owner_messages() == []
