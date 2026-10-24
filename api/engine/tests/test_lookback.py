"""The six-month lookback (api/engine/lookback.py) on a small hand-worked history. Every number below is worked out
by hand in the comments, not read back from the code."""

from datetime import date
from decimal import Decimal

from api.engine.lookback import PastDeduction, PlanPromo, deadline, lookback, month_end
from api.engine.types import Delivery, OpsData, SalesWeek

D = Decimal
# Winter promo: $0.50 a bar on Original and Chocolate, Jan 4 to 31, at most 3,000 bars.
PLAN = [PlanPromo("WINTER-26", ("Original", "Chocolate"), D("0.50"), date(2026, 1, 4), date(2026, 1, 31), 3000)]
# Promoted bars: week 1 1,000 (600 + 400), week 2 1,200, week 3 1,100, week 4 500 -> the cap is reached in week 3.
SALES = [
    SalesWeek(date(2026, 1, 4), date(2026, 1, 10), "Original", 600),
    SalesWeek(date(2026, 1, 4), date(2026, 1, 10), "Chocolate", 400),
    SalesWeek(date(2026, 1, 11), date(2026, 1, 17), "Original", 1200),
    SalesWeek(date(2026, 1, 18), date(2026, 1, 24), "Original", 1100),
    SalesWeek(date(2026, 1, 25), date(2026, 1, 31), "Original", 500),
]
OPS = OpsData(deliveries=(Delivery("DL-1", "Original", 100, 96, D("4.00")),))
W1, W2, W3 = (date(2026, 1, 4), date(2026, 1, 10)), (date(2026, 1, 11), date(2026, 1, 17)), (date(2026, 1, 18),
                                                                                            date(2026, 1, 24))


def pa(ref, units, rate, amount, period, deducted_on, products=("Original",), outcome="accepted", recovered="0"):
    return PastDeduction(ref=ref, month=f"{deducted_on:%Y-%m}", code="PA", amount=D(amount), outcome=outcome,
                         recovered=D(recovered), deducted_on=deducted_on, products=products, units=units,
                         rate=D(rate), period_start=period[0], period_end=period[1])


ROWS = [
    # 1,000 bars x $0.75 taken; the plan says $0.50: allowed $500, $250 wrongly taken.
    pa("R1", 1000, "0.75", "750.00", W1, date(2026, 2, 10), ("Original", "Chocolate")),
    # 1,200 x $0.50 = $600, exactly the plan.
    pa("R2", 1200, "0.50", "600.00", W2, date(2026, 2, 17)),
    # 1,100 x $0.50 = $550 taken; 2,200 bars before week 3 leave 800 under the cap: allowed $400, $150 wrong.
    pa("R3", 1100, "0.50", "550.00", W3, date(2026, 2, 24), outcome="written_off"),
    # Week 2 again, after R2 took it: allowed $0, $600 wrong; already in dispute.
    pa("R4", 1200, "0.50", "600.00", W2, date(2026, 3, 5), outcome="open"),
    # Mint isn't in the promo: allowed $0, $150 wrong, and all $150 already recovered.
    pa("R5", 300, "0.50", "150.00", W1, date(2026, 2, 12), ("Mint",), outcome="recovered", recovered="150.00"),
    # A display fee needs the deal read.
    PastDeduction(ref="R6", month="2026-01", code="DF", amount=D("1000.00"), deducted_on=date(2026, 2, 1)),
    # 10 bars short claimed at $4; the signed delivery shows 4 short: allowed $16, $24 wrong, long past the window.
    PastDeduction(ref="R7", month="2025-10", code="SH", amount=D("40.00"), deducted_on=date(2025, 10, 1), units=10,
                  rate=D("4.00"), period_start=date(2025, 9, 20), period_end=date(2025, 9, 20), line_ref="DL-1"),
    # No units: can't be checked.
    PastDeduction(ref="R8", month="2026-02", code="PA", amount=D("90.00"), products=("Original",),
                  period_start=W1[0], period_end=W1[1]),
]
AS_OF = date(2026, 4, 20)


def result():
    return lookback(ROWS, PLAN, SALES, OPS, as_of=AS_OF, window_days=90, tolerance=D("1.00"), counterparty="Eastway")


def test_each_row_by_hand():
    by = {ln.ref: ln for ln in result().lines}
    got = {r: (ln.allowed, ln.wrongly_taken, ln.status) for r, ln in by.items()}
    assert got == {
        "R1": (D("500.00"), D("250.00"), "claimable"),
        "R2": (D("600.00"), D("0.00"), "fair"),
        "R3": (D("400.00"), D("150.00"), "claimable"),
        "R4": (D("0.00"), D("600.00"), "claimable"),
        "R5": (D("0.00"), D("150.00"), "settled"),
        "R6": (None, D("0.00"), "not_checked"),
        "R7": (D("16.00"), D("24.00"), "past_window"),
        "R8": (None, D("0.00"), "not_checked"),
    }
    # Feb 10 + 90 days = May 11, 21 days after Apr 20. Feb 24 + 90 = May 25, 35 days. Oct 1 + 90 = Dec 30, 111 days gone.
    assert (by["R1"].file_by, by["R1"].days_left) == (date(2026, 5, 11), 21)
    assert (by["R3"].file_by, by["R3"].days_left) == (date(2026, 5, 25), 35)
    assert (by["R7"].file_by, by["R7"].days_left) == (date(2025, 12, 30), -111)
    assert (by["R4"].file_by, by["R4"].days_left) == (None, None)  # already in dispute
    assert "display fee" in by["R6"].note and "units" in by["R8"].note


def test_totals_by_hand():
    # wrongly taken 250 + 150 + 600 + 150 + 24 = 1,174; past the window 24; claimable 250 + 150 + 600 = 1,000.
    assert result().totals == {"wrongly_taken": D("1174.00"), "lost_past_window": D("24.00"),
                               "claimable_now": D("1000.00"), "checked": 6, "not_checked": 2}


def test_partly_recovered_counts_only_whats_still_owed():
    row = pa("R1", 1000, "0.75", "750.00", W1, date(2026, 2, 10), ("Original", "Chocolate"), recovered="100.00")
    r = lookback([row], PLAN, SALES, OPS, as_of=AS_OF, window_days=90, tolerance=D("1.00"))
    assert (r.lines[0].status, r.totals["wrongly_taken"], r.totals["claimable_now"]) == (
        "claimable", D("250.00"), D("150.00"))


def test_within_a_dollar_is_fair_and_no_promo_is_not_checked():
    close = pa("R9", 1200, "0.50", "600.80", W2, date(2026, 2, 17))
    outside = pa("R10", 100, "0.50", "50.00", (date(2025, 12, 1), date(2025, 12, 7)), date(2026, 1, 2))
    by = {ln.ref: ln for ln in lookback([close, outside], PLAN, SALES, OPS, as_of=AS_OF, window_days=90,
                                        tolerance=D("1.00")).lines}
    assert (by["R9"].status, by["R9"].wrongly_taken) == ("fair", D("0.00"))
    assert by["R10"].status == "not_checked" and "plan" in by["R10"].note


def test_a_blank_deducted_on_uses_the_months_last_day():
    row = PastDeduction(ref="R11", month="2026-02", code="SH", amount=D("40.00"), units=10, rate=D("4.00"),
                        line_ref="DL-1")
    (ln,) = lookback([row], PLAN, SALES, OPS, as_of=AS_OF, window_days=90, tolerance=D("1.00")).lines
    assert (ln.file_by, ln.days_left, ln.status) == (date(2026, 5, 29), 39, "claimable")  # Feb 28 + 90 = May 29


def test_deadline_and_month_end():
    assert deadline(date(2026, 4, 20), date(2026, 4, 20), 90) == (date(2026, 7, 19), 90)
    assert month_end("2024-02") == date(2024, 2, 29)
