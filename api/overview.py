"""GET /accounts/{id}/overview: an account's last six months and its current payment, computed by code from its
history/ files (api/account_rows.py) and its newest invoice-month run, never by an AI. Every sum goes through the
engine's total_of (api/engine/totals.py); this module only picks rows and groups them by month and charge code.

- months: the six months ending with the invoice month. invoiced: history/invoices.csv by invoice date; paid and
  deducted: history/remittances.csv by the month of the invoice each pays (else its own date); recovered:
  history/deductions.csv by its month. The current month adds the account's invoice and, once its payment arrived
  (a run started), that payment and the charges taken. A history row for the current invoice isn't counted twice.
- kpis: the months added up; recovery_rate is recovered / deducted. open_disputes counts the deductions still in
  dispute: history rows whose outcome is open, and the current run's open dispute lines. open_balance is what's still
  owed: the open history rows' unrecovered amounts, plus the current invoice's balance (all of it until the payment
  arrives; then expected - received - the credit memos posted).
- deductions_by_type: history deductions in the window plus the current run's charges (a history row with the same
  ref as one of them counts once), by code.
- recent_remittances: the newest six payments, the current one included once it arrived.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

from api import account_rows, accounts
from api.contracts import (
    MONTHS, AccountKpis, AccountListItem, AccountOverview, CurrentPayment, DeductionTypeTotal, MonthTotals,
    RemittanceRow,
)
from api.engine.totals import total_of

WINDOW = 6
RECENT = 6
LABELS = {"PA": "Promotional allowance", "DF": "Display fee", "SH": "Shortage", "PR": "Price mismatch",
          "SP": "Spoilage"}
OPEN_OUTCOMES = {"open", "disputed", "pending", "in dispute", "in_dispute"}
ZERO = Decimal("0.00")
_ISO = re.compile(r"^(\d{4})-(\d{1,2})(?:-\d{1,2})?$")
_NAMED = re.compile(r"^([a-z]+)\.?(?:\s+(\d{4}))?$")


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def window(account: accounts.Account) -> list[str]:
    """The six month keys ending with the invoice month, oldest first."""
    year, month = account.invoice.period_end.year, MONTHS.index(account.invoice.month) + 1
    keys = []
    for back in range(WINDOW - 1, -1, -1):
        y, m = divmod(year * 12 + month - 1 - back, 12)
        keys.append(f"{y:04d}-{m + 1:02d}")
    return keys


def parse_month(text: str, last: str) -> str | None:
    """A deductions row's month as YYYY-MM: "2026-02", "2026-02-28", "February 2026", "Feb 2026", or "february"
    (a month without a year is the latest one up to `last`). None if it isn't a month."""
    text = " ".join(text.strip().lower().split())
    if m := _ISO.match(text):
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}" if 1 <= int(m.group(2)) <= 12 else None
    m = _NAMED.match(text)
    if not m:
        return None
    number = next((i + 1 for i, name in enumerate(MONTHS) if name.startswith(m.group(1)) and len(m.group(1)) >= 3),
                  None)
    if number is None:
        return None
    year = int(m.group(2)) if m.group(2) else int(last[:4]) - (number > int(last[5:]))
    return f"{year:04d}-{number:02d}"


def _sum(amounts: Iterable[Decimal]) -> Decimal:
    return total_of(list(amounts) or [ZERO])


# ---------------------------------------------------------------- the current run

class Current:
    """What the account's newest invoice-month run says, from its events (live, or saved before a restart)."""

    def __init__(self, run_id: str | None, events: list):
        self.run_id, self.events = run_id, events
        runs = [e.data for e in events if e.type == "run"]
        self.status = runs[-1].status if runs else ("started" if run_id else "waiting_for_payment")
        remittance = next((r.remittance for r in runs if r.remittance), None)
        self.paid = remittance is not None
        self.received = remittance.received if remittance else None
        self.paid_on = remittance.received_at.date() if remittance and remittance.received_at else None
        totals = [e.data for e in events if e.type == "totals"]
        self.taken = totals[-1].taken if totals else None
        self.charges = {e.data.id: e.data for e in events if e.type == "charge"}
        disputes, posts = {}, {}
        for e in events:
            if e.type == "dispute":
                disputes[e.data.id] = e.data
            elif e.type == "ledger_post":
                posts[e.data.id] = e.data
        self.open_lines = [ln for d in disputes.values() if d.status not in ("resolved", "withdrawn") for ln in d.lines]
        self.credited = _sum(p.amount for p in posts.values() if p.qbo_entity == "credit_memo" and p.status == "posted")


def current_run(account: accounts.Account) -> Current:
    from api import pipeline
    from api.db import events as saved_events

    live = pipeline.latest(account.invoice.month, account)
    if live:
        return Current(live.id, list(live.events))
    run_id = saved_events.latest_run(account.invoice.month, account.id)
    return Current(run_id, (saved_events.load(run_id) or []) if run_id else [])


# ---------------------------------------------------------------- the overview

def overview(account: accounts.Account, item: AccountListItem, now: Current | None = None) -> AccountOverview:
    now = now or current_run(account)
    inv, keys = account.invoice, window(account)
    last = keys[-1]
    invoices = account_rows.invoices(account)
    remittances = account_rows.remittances(account)
    deductions = account_rows.deductions(account)
    invoice_month = {r.invoice: month_key(r.date) for r in invoices} | {inv.id: last}

    invoiced, paid, deducted, recovered = (defaultdict(list) for _ in range(4))
    for r in invoices:
        if r.invoice != inv.id:
            invoiced[month_key(r.date)].append(r.amount)
    invoiced[last].append(inv.expected)
    current_in_history = any(r.invoice == inv.id for r in remittances)
    for r in remittances:
        key = invoice_month.get(r.invoice, month_key(r.date))
        paid[key].append(r.paid)
        deducted[key].append(r.deducted)
    if now.paid and not current_in_history:
        paid[last].append(now.received)
        deducted[last].append(now.taken if now.taken is not None else total_of([inv.expected, -now.received]))
    in_window, taken_now = [], {c.ref for c in now.charges.values()}
    for r in deductions:
        key = parse_month(r.month, last)
        if key is not None:
            recovered[key].append(r.recovered)
            if key in keys and r.ref not in taken_now:  # a charge of the current run counts once, from the run
                in_window.append(r)

    months = [MonthTotals(month=k, invoiced=_sum(invoiced[k]), paid=_sum(paid[k]), deducted=_sum(deducted[k]),
                          recovered=_sum(recovered[k])) for k in keys]
    by_code: dict[str, list[Decimal]] = defaultdict(list)
    for r in in_window:
        by_code[r.code].append(r.amount)
    for c in now.charges.values():
        by_code[c.code].append(c.amount)
    types = sorted((DeductionTypeTotal(code=code, label=LABELS.get(code, code), count=len(amounts),
                                       amount=_sum(amounts)) for code, amounts in by_code.items()),
                   key=lambda t: (-t.amount, t.code))

    still_open = [r for r in deductions if (r.outcome or "").strip().lower() in OPEN_OUTCOMES]
    if now.paid:
        balance = total_of([inv.expected, -now.received, -now.credited])
    else:  # nothing paid yet, unless history already has the current invoice's payment
        balance = total_of([inv.expected, *(-r.paid for r in remittances if r.invoice == inv.id)])
    sums = {f: _sum(getattr(m, f) for m in months) for f in ("invoiced", "paid", "deducted", "recovered")}
    rate = float((sums["recovered"] / sums["deducted"]).quantize(Decimal("0.0001"))) if sums["deducted"] else 0.0
    kpis = AccountKpis(invoiced_6m=sums["invoiced"], collected_6m=sums["paid"], deducted_6m=sums["deducted"],
                       recovered_6m=sums["recovered"], recovery_rate=rate,
                       open_disputes=len(still_open) + len(now.open_lines),
                       open_balance=total_of([*(total_of([r.amount, -r.recovered]) for r in still_open), balance]))

    recent = [RemittanceRow(date=r.date, invoice=r.invoice, paid=r.paid, deducted=r.deducted) for r in remittances]
    if now.paid and not current_in_history:
        recent.append(RemittanceRow(date=now.paid_on or inv.period_end, invoice=inv.id, paid=now.received,
                                    deducted=months[-1].deducted))
    recent = sorted(recent, key=lambda r: r.date, reverse=True)[:RECENT]

    current = CurrentPayment(invoice=inv.id, expected=inv.expected, received=inv.received,
                             deducted=total_of([inv.expected, -inv.received]), run_id=now.run_id, status=now.status)
    return AccountOverview(account=item, kpis=kpis, months=months, deductions_by_type=types,
                           recent_remittances=recent, current=current)
