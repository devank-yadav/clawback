"""Evidence for one run: every deal sentence, email, notice, sales week, charge row and prior payment the
agents may cite, plus the operations records (proof of delivery, agreed prices, ops terms), with stable IDs.
The drawer opens these ("Why?"); agents cite them by ID and code checks every cited ID exists.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal

from api import documents, rows
from api.contracts import (
    Charge, DeliveryRow, Evidence, MathPart, OpsTerm, PriceRow, PriorPayment, Quote, SalesRow, Term,
)
from api.engine import quote_check
from api.engine.allowed import OPS_CODES, SPOILS_ALLOWANCE, product_key, usd

def day(d, year: bool = False) -> str:
    """Mar 7, or Mar 7, 2026 with year. Built by hand: strftime has no portable day without a leading zero (Windows raises)."""
    return f"{d:%b} {d.day}, {d.year}" if year else f"{d:%b} {d.day}"


_SECTION = re.compile(r"(\d+\.\d+)\s+$")
_HEADING = re.compile(r"^(\d+\.\d+)[ \t]+\S", re.M)  # a numbered section heading on its own line


def _paragraph(text: str, start: int, end: int) -> tuple[str, str]:
    a = text.rfind("\n\n", 0, start)
    a = 0 if a == -1 else a + 2
    b = text.find("\n\n", end)
    b = len(text.rstrip("\n")) if b == -1 else b
    return text[a:start], text[end:b]


def quote_in(doc_id: str, text: str, start: int, end: int, sentence: str) -> Quote:
    """The sentence at text[start:end] with the rest of its paragraph, for highlighting in place."""
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
        "fee_schedule": lambda: _fee_summary(t),
        "dispute_window": lambda: f"disputes are due within {p.get('days')} days of the {p.get('from', 'deduction')}",
        "notice_period": lambda: f"a change needs {p.get('days')} days' notice",
        "quantity_variance": lambda: f"the buyer may accept up to {p.get('pct')}% over or short"
                                     + (", at its discretion" if t.discretion else ""),
    }[t.type]()


def _fee_summary(t: Term) -> str:
    p = t.params
    rate = p.get("rate")
    how = {"percent": f"{rate}%", "per_unit": f"${rate} per unit", "per_carton": f"${rate} per carton",
           "per_po": f"${rate} per PO", "flat": f"${rate} flat", "annual_percent": f"{rate}% a year",
           "as_assessed": "as the distributor assesses it"}.get(p.get("basis"), str(rate))
    if p.get("tiers"):
        how = ", ".join(f"{x['rate']}{'%' if p.get('basis') == 'percent' else ''} for {x['from_days']}"
                        + (f"-{x['to_days']}" if x.get("to_days") is not None else "+") + " days" for x in p["tiers"])
    limits = [f"{name} ${Decimal(str(p[key])):,}" for key, name in (("min", "minimum"), ("max", "maximum"))
              if p.get(key) is not None]
    per = f" per {p.get('per')}" if limits and p.get("per") else ""
    out = f"{p.get('fee_code')} fee: {how}" + (f", {' and '.join(limits)}{per}" if limits else "")
    out += ", backup required" if p.get("requires_proof") else ""
    out += f", only on {p['applies_to']} orders" if p.get("applies_to") else ""
    out += ", only for the supplier's own failure" if p.get("requires_fault") else ""
    out += ", on top of each other fee" if p.get("add_on") else ""
    return out + (", depending on someone's judgment" if t.discretion else "")


def clause_id(t: Term) -> str:
    """ev-spring-promo-3.2 for a numbered deal section; ev-<doc> for an email, notice or amendment."""
    doc, text = documents.load(t.source_doc_id)
    if doc.kind == "deal" and (m := _SECTION.search(text[max(0, t.char_start - 12):t.char_start])):
        return f"ev-{doc.id}-{m.group(1)}"
    if doc.kind == "deal" and (heads := _HEADING.findall(text[:t.char_start])):  # "6.4 Manufacturer Charge Backs"
        return f"ev-{doc.id}-{heads[-1]}"
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
            kind, label = "claim", f"{doc.sender} email {day(doc.received_at)} (claim)"
            summary = f"Says: {summary}. This sender can't change the deal, so it's a claim, not a change."
        elif doc.kind == "email":
            kind, label = "email", f"Email from {doc.sender} {day(doc.received_at)}"
        else:
            kind, label = "clause", f"§{section}" if section else f"{doc.id}"
        out[ev_id] = Evidence(id=ev_id, kind=kind, label=label, summary=summary[0].upper() + summary[1:] + ("" if summary.endswith(".") else "."),
                              quote=quote_in(doc.id, text, ts[0].char_start, ts[0].char_end, ts[0].exact_quote),
                              sender=doc.sender, approved_sender=doc.approved_sender if doc.kind == "email" else None,
                              sent_at=doc.received_at if doc.kind == "email" else None)
    return out


def from_notices() -> dict[str, Evidence]:
    out = {}
    for n in rows.notices():
        doc, text = documents.load(n.doc_id)
        m = re.search(r"Northmart will charge[^.]*\.", text, re.S)
        quote = quote_in(doc.id, text, m.start(), m.end(), " ".join(m.group().split())) if m else None
        out[f"ev-{n.doc_id}"] = Evidence(
            id=f"ev-{n.doc_id}", kind="notice", label=f"Notice {day(n.notice_date)}",
            summary=f"Northmart gave written notice of a ${n.amount:,.2f} fee on {day(n.notice_date, year=True)}.",
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
            id=f"ev-sales-{start}", kind="sales", label=f"Sales {day(rs[0].week_start)}–{day(rs[0].week_end)}",
            summary=f"{units:,} promoted bars of the deal's products sold {day(rs[0].week_start)} to {day(rs[0].week_end)}.",
            rows=[r.model_dump(mode="json") for r in rs])
    for key, rs in sorted(other.items()):
        units = sum(r.promo_units for r in rs)
        out[f"ev-sales-{key}"] = Evidence(
            id=f"ev-sales-{key}", kind="sales", label=f"{rs[0].product} sales",
            summary=f"{units:,} promoted {rs[0].product} bars sold {day(min(r.week_start for r in rs))} to "
                    f"{day(max(r.week_end for r in rs))}. {rs[0].product} isn't a deal product.",
            rows=[r.model_dump(mode="json") for r in rs])
    return out


def from_charges(charges: Iterable[Charge]) -> dict[str, Evidence]:
    return {f"ev-charge-{c.id}": Evidence(id=f"ev-charge-{c.id}", kind="charge", label=f"Charge {c.id} ({c.ref})",
                                          summary=f"Northmart's remittance line {c.ref}: {c.description}, ${c.amount:,.2f}.",
                                          rows=[c.model_dump(mode="json")])
            for c in charges}


def from_payments(payments: Iterable[PriorPayment]) -> dict[str, Evidence]:
    return {f"ev-payment-{p.ref}": Evidence(
        id=f"ev-payment-{p.ref}", kind="prior_payment", label=f"Paid {day(p.paid_on)} ({p.ref})",
        summary=f"Northmart already took ${p.amount:,.2f} for {p.units:,} units sold {day(p.period_start)} to "
                f"{day(p.period_end)}, on {day(p.paid_on)}.",
        rows=[p.model_dump(mode="json")]) for p in payments}


def pod_id(line_ref: str) -> str:
    return f"ev-pod-{line_ref.strip()}"


def price_id(product: str) -> str:
    """ev-price-original; a product name of several words is joined with hyphens (ev-price-oat-milk)."""
    return f"ev-price-{product_key(product).replace(' ', '-')}"


def term_id(key: str) -> str:
    return f"ev-term-{key}"


def from_deliveries(deliveries: Iterable[DeliveryRow]) -> dict[str, Evidence]:
    """One item per proof-of-delivery line (ev-pod-L-1001): shipped, received, who signed, and the unit price invoiced."""
    out = {}
    for r in deliveries:
        signed = (f", signed for by {r.received_by}" if r.received_by else "") + (
            f" on {day(r.received_at, year=True)}" if r.received_at else "")
        out[pod_id(r.line_ref)] = Evidence(
            id=pod_id(r.line_ref), kind="delivery", label=f"Delivery {r.line_ref}",
            summary=f"{r.shipped_units:,} units of {r.product} shipped and {r.received_units:,} received{signed}, "
                    f"invoiced at {usd(r.unit_price)} a unit.",
            rows=[r.model_dump(mode="json")])
    return out


def from_prices(prices: Iterable[PriceRow]) -> dict[str, Evidence]:
    """The agreed price list, one item per product (ev-price-original) holding all of that product's rows."""
    grouped: dict[str, list[PriceRow]] = defaultdict(list)
    for r in prices:
        grouped[price_id(r.product)].append(r)
    out = {}
    for ev_id, rs in grouped.items():
        rs = sorted(rs, key=lambda r: r.effective_from)
        spans = "; ".join(f"{usd(r.agreed_price)} a unit from {day(r.effective_from, year=True)}"
                          + (f" to {day(r.effective_to, year=True)}" if r.effective_to else "") for r in rs)
        docs = sorted({r.source_doc for r in rs if r.source_doc})
        out[ev_id] = Evidence(
            id=ev_id, kind="price", label=f"Price list: {rs[0].product}",
            summary=f"Agreed price for {rs[0].product}: {spans}" + (f", per {', '.join(docs)}" if docs else "") + ".",
            rows=[r.model_dump(mode="json") for r in rs])
    return out


def ops_quote(t: OpsTerm) -> Quote | None:
    """Where an ops term's quote sits in its source document: found word for word (spaces and dashes normalized, as
    for deal terms) and stating the term's value. None otherwise, and the term is rejected."""
    try:
        doc, text = documents.load(t.source_doc)
    except (KeyError, OSError):
        return None
    span = quote_check.find_quote(text, t.quote)
    if span is None or quote_check.missing_numbers(t.value, t.quote):
        return None
    return quote_in(doc.id, text, *span, t.quote)


def from_ops_terms(terms: Iterable[OpsTerm]) -> dict[str, Evidence]:
    """One item per ops term (ev-term-spoils_allowance_pct) with its sentence highlighted in the deal. A term whose
    quote isn't found word for word gets none: it's rejected, like a deal term."""
    out = {}
    for t in terms:
        if (quote := ops_quote(t)) is None:
            continue
        doc, _ = documents.load(quote.doc_id)
        name, pct = t.key.removesuffix("_pct").replace("_", " "), t.key.endswith("_pct")
        section = _SECTION.search(quote.context_before[-12:]) if doc.kind == "deal" else None
        out[term_id(t.key)] = Evidence(
            id=term_id(t.key), kind="policy", label=f"§{section.group(1)} {name}" if section else name.capitalize(),
            summary=f"The {'deal' if doc.kind == 'deal' else doc.kind} sets the {name} at {t.value}{'%' if pct else ''}.",
            quote=quote, rows=[t.model_dump(mode="json")])
    return out


def from_ops(deliveries: Iterable[DeliveryRow] = (), prices: Iterable[PriceRow] = (),
             terms: Iterable[OpsTerm] = ()) -> dict[str, Evidence]:
    """All of an account's operations evidence, to merge into build()'s."""
    return {**from_deliveries(deliveries), **from_prices(prices), **from_ops_terms(terms)}


_POD_STEP = re.compile(r"Delivery (\S+): ")


def _ops_link(step: str, charge: Charge, ev: Mapping[str, Evidence]) -> str | None:
    """SH / PR / SP steps (allowed.py's fixed forms): a delivery line opens its proof of delivery, the price list the
    agreed price of the charge's delivery line, the spoils allowance its ops term, and what's claimed the charge row."""
    line = pod_id(charge.line_ref) if charge.line_ref else None
    if m := _POD_STEP.match(step):
        target = pod_id(m.group(1))
    elif step.startswith("Price list:"):
        pod = ev.get(line) if line else None
        target = price_id(str(pod.rows[0]["product"])) if pod and pod.rows else None
    elif step.startswith("Spoils allowance"):
        target = term_id(SPOILS_ALLOWANCE)
    elif step.startswith("Claimed") or (charge.code == "PR" and step.startswith("Invoiced ")):
        target = f"ev-charge-{charge.id}"
    elif " units x $" in step:  # SH: the delivery's unit price; PR: the units claimed
        target = line if charge.code == "SH" else f"ev-charge-{charge.id}"
    else:
        target = None
    return target if target in ev else None


def math_parts(steps: Sequence[str], used: Iterable, charge: Charge, terms: Iterable[Term],
               ev: Mapping[str, Evidence]) -> list[MathPart]:
    """The engine's math steps (allowed.py writes each in a fixed form), each linked to the evidence it rests on, so
    every number on the card opens its source (F7). `used` is the allowance's engine terms. A step with nothing to
    point at stays plain text."""
    if charge.code in OPS_CODES:
        return [MathPart(text=step, evidence_id=_ops_link(step, charge, ev)) for step in steps]
    by_id = {t.id: t for t in terms}

    def clause(kind: str) -> str | None:
        t = next((by_id[u.id] for u in used if u.type.value == kind and u.id in by_id), None)
        return clause_id(t) if t and clause_id(t) in ev else None

    def found(kind: str, match) -> str | None:
        hits = [e.id for e in ev.values() if e.kind == kind]
        return next((i for i in hits if match(ev[i])), hits[0] if hits else None)

    start, out = charge.period_start.isoformat(), []
    for step in steps:
        if step.startswith("Store sales show"):
            sales = next((i for i in (f"ev-sales-{start}", f"ev-sales-{product_key(charge.product)}") if i in ev), None)
        else:
            sales = None
        target = (sales if step.startswith("Store sales show") else
                  clause("unit_cap") if step.startswith("Cap ") else
                  clause("amendment") if "covered by an approved amendment" in step else
                  next((clause_id(t) for t in by_id.values() if t.type == "amendment" and clause_id(t) in ev), None)
                  if step.startswith("The approved extension adds units only") else
                  found("prior_payment", lambda e: any(r.get("period_start") == start for r in e.rows))
                  if step.startswith("A prior payment") else
                  clause("promo_rate") if " units x $" in step else
                  clause("product_scope") if "is not a product the deal covers" in step else
                  clause("fee_discretion") if step.startswith("Deal allows a fee") else
                  found("notice", lambda e: any(r.get("charge_ref") == charge.ref for r in e.rows))
                  if step.startswith("Written notice came") else None)
        out.append(MathPart(text=step, evidence_id=target))
    return out


def build(terms: Sequence[Term], charges: Sequence[Charge], sales: Sequence[SalesRow],
          payments: Sequence[PriorPayment]) -> dict[str, Evidence]:
    scope = next((t for t in terms if t.type == "product_scope" and t.status == "verified" and t.source_approved), None)
    return {**from_terms(terms), **from_notices(), **from_sales(sales, scope.params["products"] if scope else []),
            **from_charges(charges), **from_payments(payments)}
