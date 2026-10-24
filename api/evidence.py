"""Evidence for one run: every deal sentence, email, notice, sales week, charge row and prior payment the
agents may cite, with stable IDs. The drawer opens these ("Why?"); agents cite them by ID and code checks
every cited ID exists.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from decimal import Decimal

from api import documents, rows
from api.contracts import Charge, Evidence, PriorPayment, Quote, SalesRow, Term
from api.engine.allowed import product_key

_SECTION = re.compile(r"(\d+\.\d+)\s+$")


def _paragraph(text: str, start: int, end: int) -> tuple[str, str]:
    a = text.rfind("\n\n", 0, start)
    a = 0 if a == -1 else a + 2
    b = text.find("\n\n", end)
    b = len(text.rstrip("\n")) if b == -1 else b
    return text[a:start], text[end:b]


def _quote(doc_id: str, text: str, start: int, end: int, sentence: str) -> Quote:
    before, after = _paragraph(text, start, end)
    return Quote(doc_id=doc_id, text=sentence, char_start=start, char_end=end, context_before=before,
                 context_after=after)


def _term_summary(t: Term) -> str:
    p = t.params
    return {
        "promo_rate": lambda: f"${p.get('rate')} per unit",
        "product_scope": lambda: "covers " + ", ".join(p.get("products", [])),
        "date_range": lambda: f"runs {p.get('start')} to {p.get('end')}",
        "unit_cap": lambda: f"at most {int(p.get('max_units', 0)):,} units",
        "fee_discretion": lambda: f"a fee of up to ${Decimal(str(p.get('max_fee'))):,}" + (", at the distributor's discretion" if t.discretion else ""),
        "amendment": lambda: f"up to {int(p.get('extra_units', 0)):,} more units, {t.effective_from} to {t.effective_to}",
    }[t.type]()


def clause_id(t: Term) -> str:
    """ev-spring-promo-3.2 for a numbered deal section; ev-<doc> for an email, notice or amendment."""
    doc, text = documents.load(t.source_doc_id)
    if doc.kind == "deal" and (m := _SECTION.search(text[max(0, t.char_start - 12):t.char_start])):
        return f"ev-{doc.id}-{m.group(1)}"
    return f"ev-{doc.id}"


def from_terms(terms: Iterable[Term]) -> dict[str, Evidence]:
    """One evidence item per quoted sentence; terms sharing a sentence share it."""
    grouped: dict[str, list[Term]] = defaultdict(list)
    for t in terms:
        if t.status != "rejected":
            grouped[clause_id(t)].append(t)
    out = {}
    for ev_id, ts in grouped.items():
        doc, text = documents.load(ts[0].source_doc_id)
        summary = "; ".join(_term_summary(t) for t in ts)
        section = ev_id.rsplit("-", 1)[-1] if doc.kind == "deal" else None
        if doc.kind == "email" and not documents.can_change_deal(doc):
            kind, label = "claim", f"{doc.sender} email {doc.received_at:%b %-d} (claim)"
            summary = f"Says: {summary}. This sender can't change the deal, so it's a claim, not a change."
        elif doc.kind == "email":
            kind, label = "email", f"Email from {doc.sender} {doc.received_at:%b %-d}"
        else:
            kind, label = "clause", f"§{section}" if section else f"{doc.id}"
        out[ev_id] = Evidence(id=ev_id, kind=kind, label=label, summary=summary[0].upper() + summary[1:] + ("" if summary.endswith(".") else "."),
                              quote=_quote(doc.id, text, ts[0].char_start, ts[0].char_end, ts[0].exact_quote),
                              sender=doc.sender, approved_sender=doc.approved_sender if doc.kind == "email" else None,
                              sent_at=doc.received_at if doc.kind == "email" else None)
    return out


def from_notices() -> dict[str, Evidence]:
    out = {}
    for n in rows.notices():
        doc, text = documents.load(n.doc_id)
        m = re.search(r"Northmart will charge[^.]*\.", text, re.S)
        quote = _quote(doc.id, text, m.start(), m.end(), " ".join(m.group().split())) if m else None
        out[f"ev-{n.doc_id}"] = Evidence(
            id=f"ev-{n.doc_id}", kind="notice", label=f"Notice {n.notice_date:%b %-d}",
            summary=f"Northmart gave written notice of a ${n.amount:,.2f} fee on {n.notice_date:%b %-d, %Y}.",
            quote=quote, sender=doc.sender,
            rows=[{"notice_date": n.notice_date.isoformat(), "charge_ref": n.ref, "amount": float(n.amount)}])
    return out


def from_sales(rows: Sequence[SalesRow], deal_products: Iterable[str]) -> dict[str, Evidence]:
    """Deal products grouped per week (ev-sales-2026-03-01); any other product over all weeks (ev-sales-mint)."""
    deal = {product_key(p) for p in deal_products}
    weeks: dict[str, list[SalesRow]] = defaultdict(list)
    other: dict[str, list[SalesRow]] = defaultdict(list)
    for r in rows:
        (weeks[r.week_start.isoformat()] if product_key(r.product) in deal else other[product_key(r.product)]).append(r)
    out = {}
    for start, rs in sorted(weeks.items()):
        units = sum(r.promo_units for r in rs)
        out[f"ev-sales-{start}"] = Evidence(
            id=f"ev-sales-{start}", kind="sales", label=f"Sales {rs[0].week_start:%b %-d}–{rs[0].week_end:%b %-d}",
            summary=f"{units:,} promoted bars of the deal's products sold {rs[0].week_start:%b %-d} to {rs[0].week_end:%b %-d}.",
            rows=[r.model_dump(mode="json") for r in rs])
    for key, rs in sorted(other.items()):
        units = sum(r.promo_units for r in rs)
        out[f"ev-sales-{key}"] = Evidence(
            id=f"ev-sales-{key}", kind="sales", label=f"{rs[0].product} sales",
            summary=f"{units:,} promoted {rs[0].product} bars sold {min(r.week_start for r in rs):%b %-d} to "
                    f"{max(r.week_end for r in rs):%b %-d}. {rs[0].product} isn't a deal product.",
            rows=[r.model_dump(mode="json") for r in rs])
    return out


def from_charges(charges: Iterable[Charge]) -> dict[str, Evidence]:
    return {f"ev-charge-{c.id}": Evidence(id=f"ev-charge-{c.id}", kind="charge", label=f"Charge {c.id} ({c.ref})",
                                          summary=f"Northmart's remittance line {c.ref}: {c.description}, ${c.amount:,.2f}.",
                                          rows=[c.model_dump(mode="json")])
            for c in charges}


def from_payments(payments: Iterable[PriorPayment]) -> dict[str, Evidence]:
    return {f"ev-payment-{p.ref}": Evidence(
        id=f"ev-payment-{p.ref}", kind="prior_payment", label=f"Paid {p.paid_on:%b %-d} ({p.ref})",
        summary=f"Northmart already took ${p.amount:,.2f} for {p.units:,} units sold {p.period_start:%b %-d} to "
                f"{p.period_end:%b %-d}, on {p.paid_on:%b %-d}.",
        rows=[p.model_dump(mode="json")]) for p in payments}


def build(terms: Sequence[Term], charges: Sequence[Charge], sales: Sequence[SalesRow],
          payments: Sequence[PriorPayment]) -> dict[str, Evidence]:
    scope = next((t for t in terms if t.type == "product_scope" and t.status == "verified" and t.source_approved), None)
    return {**from_terms(terms), **from_notices(), **from_sales(sales, scope.params["products"] if scope else []),
            **from_charges(charges), **from_payments(payments)}
