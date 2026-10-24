"""GET /accounts/{id}/lookback: an account's past six months of deductions, each run through the engine's math
(api/engine/lookback.py) with terms built in code from its own files, and how much can still be claimed.

This module only reads the account's files and maps them onto the engine's dataclasses and back:
- rows: history/deductions.csv in the overview's six-month window (api/overview.py), less any ref the invoice
  month's charges file holds (the run decides those);
- PA: history/promo-plan.csv plus plan/promo-plan.csv; history/sales.csv plus sales/store-sales.csv;
- SH / PR / SP: history/deliveries.csv plus deliveries/pod.csv, pricing/price-list.csv, terms/ops-terms.csv (a term
  counts only when its quote is found word for word, as for a live charge);
- the dispute window: terms/ops-terms.csv `dispute_window_days` (quote checked the same way), else config/policy.yaml
  `default_dispute_days`; as_of: the account's payment date (qbo.payment_date, else invoice.period_end + 20 days).
"""

from __future__ import annotations

from datetime import date, timedelta

from api import account_rows, accounts, adapters, overview, rows
from api.contracts import DeliveryRow, Lookback, LookbackRow, LookbackTotals, OpsTerm, PriceRow
from api.engine import lookback as engine
from api.engine import types as eng
from api.engine.policy import load_policy
from api.evidence import ops_quote

WINDOW_KEY = "dispute_window_days"
PAYMENT_AFTER_DAYS = 20  # the seed's default payment date: invoice.period_end + 20 days


def _products(text: str | None) -> tuple[str, ...]:
    return tuple(p.strip() for p in (text or "").replace(";", "+").split("+") if p.strip())


def as_of(account: accounts.Account) -> date:
    return account.config.qbo.payment_date or account.invoice.period_end + timedelta(days=PAYMENT_AFTER_DAYS)


def _checked_terms(account: accounts.Account) -> list[OpsTerm]:
    """The account's ops terms whose quote is found word for word in their document (the rest can't count)."""
    out = []
    for t in account_rows.ops_terms(account):
        if t.source_doc and t.quote:
            term = OpsTerm.model_validate(t.model_dump())
            if ops_quote(term):
                out.append(term)
    return out


def window_days(account: accounts.Account, policy: eng.Policy | None = None) -> int:
    for t in reversed(_checked_terms(account)):
        if t.key == WINDOW_KEY:
            try:
                days = int(t.value.strip())
            except ValueError:
                continue
            if days > 0:
                return days
    return (policy or load_policy()).default_dispute_days


def deadline(account: accounts.Account, policy: eng.Policy | None = None) -> tuple[date, int]:
    """A charge on the current payment: taken on the payment date, so file_by is as_of + the window."""
    day = as_of(account)
    return engine.deadline(day, day, window_days(account, policy))


def _ops(account: accounts.Account) -> eng.OpsData:
    """Deliveries from both files (a line in both counts once, the current file's), prices and ops terms, mapped the
    way a run maps them (api/pipeline.py _ops_rows): a term with no document or quote can't be checked."""
    ops = account_rows.ops(account)
    seen, lines = set(), []
    for d in (*ops.deliveries, *account_rows.past_deliveries(account)):
        if d.line_ref not in seen:
            seen.add(d.line_ref)
            lines.append(DeliveryRow.model_validate(d.model_dump()))
    prices = [PriceRow.model_validate({**p.model_dump(), "effective_from": p.effective_from or date.min})
              for p in ops.prices]
    terms = [OpsTerm.model_validate(t.model_dump()) for t in ops.terms if t.source_doc and t.quote]
    return adapters.to_engine_ops(lines, prices, terms)


def _sales(account: accounts.Account) -> list[eng.SalesWeek]:
    out: dict[tuple[date, str], eng.SalesWeek] = {}
    for r in account_rows.past_sales(account):
        out[(r.week_start, r.product)] = eng.SalesWeek(r.week_start, r.week_end, r.product, r.promo_units,
                                                        r.total_units)
    for r in rows.sales_from_files(account=account):  # the current weeks win over a history row for the same week
        out[(r.week_start, r.product)] = adapters.to_engine_sales(r)
    return list(out.values())


def _plan(account: accounts.Account) -> list[engine.PlanPromo]:
    past = [engine.PlanPromo(p.promo_id, _products(p.product), p.rate, p.starts, p.ends, p.cap)
            for p in account_rows.past_promos(account)]
    now = [engine.PlanPromo(p.promo_id, tuple(p.products), p.rate, p.starts, p.ends, p.cap)
           for p in rows.promo_plan_from_files(account=account)]
    ids = {p.promo_id for p in now}
    return [p for p in past if p.promo_id not in ids] + now


def _rows(account: accounts.Account) -> list[engine.PastDeduction]:
    keys = overview.window(account)
    current = {c.ref for c in rows.charges_from_files(account.invoice.month, account=account)}
    out = []
    for r in account_rows.deductions(account):
        month = overview.parse_month(r.month, keys[-1])
        if month not in keys or r.ref in current:
            continue
        out.append(engine.PastDeduction(
            ref=r.ref, month=month, code=r.code.strip().upper(), amount=r.amount, description=r.description or "",
            outcome=r.outcome or "", recovered=r.recovered, deducted_on=r.deducted_on, products=_products(r.product),
            units=r.units, rate=r.rate, period_start=r.period_start, period_end=r.period_end,
            line_ref=(r.line_ref or "").strip() or None))
    return out


def run(account: accounts.Account) -> engine.LookbackResult:
    policy = load_policy()
    return engine.lookback(_rows(account), _plan(account), _sales(account), _ops(account), as_of=as_of(account),
                           window_days=window_days(account, policy), tolerance=policy.match_tolerance,
                           counterparty=account.distributor.name)


def lookback(account: accounts.Account) -> Lookback:
    r = run(account)
    return Lookback(
        account_id=account.id, as_of=r.as_of, dispute_window_days=r.window_days,
        rows=[LookbackRow(ref=ln.ref, month=ln.month, code=ln.code, description=ln.description, taken=ln.taken,
                          allowed=ln.allowed, wrongly_taken=ln.wrongly_taken, outcome=ln.outcome,
                          recovered=ln.recovered, deducted_on=ln.deducted_on, file_by=ln.file_by,
                          days_left=ln.days_left, status=ln.status, note=ln.note) for ln in r.lines],
        totals=LookbackTotals(**r.totals))
