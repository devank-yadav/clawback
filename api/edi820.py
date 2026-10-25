"""EDI 820 remittance advice, read by plain code (no AI): the RMR / ADX segments become the same lines the Payment
reader returns (api/agents/remittance_reader.ReadRemittance), and api/remittance.check() then checks them exactly as
it checks a PDF or pasted text: each line's printed segments found in the file, every number and date on them, the
codes, and that the lines add up to what the payment is short. Nothing here adds money up or decides anything.

The layout is ASC X12 004010's 820 (Payment Order/Remittance Advice), positions as in Stedi's 004010 reference
(stedi.com/edi/x12-004010/820 and its segment and element pages):
- ISA … IEA / GS … GE envelope, optional. The element separator is the character after "ISA" (or "ST"); the segment
  terminator is the character after ISA16 (the sixteenth element), else "~", else a line break.
- BPR02 the payment amount, BPR16 its date (CCYYMMDD). TRN02 the trace number (the payment's reference).
  N1*PR the payer's name.
- RMR loop, one per invoice paid: RMR01 the qualifier (IV, the seller's invoice number), RMR02 the invoice number,
  RMR04 the amount paid on it, RMR05 the invoice's amount before the deductions (RMR04 = RMR05 minus them).
- ADX loop under an RMR, one per deduction from that invoice: ADX01 the amount (negative: it reduces the payment),
  ADX02 the adjustment reason code (element 426), ADX03 / ADX04 a reference qualifier and the deduction number
  (DB, the buyer's debit memo). After it in the loop: NTE02 the description; REF the promotion or other reference,
  REF03 the distributor's own wording for the code ("PROMO ALLOW"); DTM the period (015 / 016 promotion start / end,
  193 / 194 period start / end, 150 / 151 service period, 196 / 197 start / end), CCYYMMDD; IT1 the item: IT102 the
  quantity, IT104 the unit price, IT106 / IT107 (and further pairs) the item's ids.

Codes: ADX02 A8 "Promotional Allowance" is PA, 01 "Pricing Error" PR, 59 "Item not received" and 06 "Quantity
Contested" SH, 04 "Item Not Accepted - Damaged", 11 "Returns - Damage" and GJ "Unsalable Payments Deduction" SP;
anything else (ZZ "Mutually Defined" among them) is the distributor's REF03 wording, through the same list a printed
remittance's codes go through (api/remittance.CODE_ALIASES), else UNKNOWN, which a person decides. Products: an item
id names one of the account's products when that product's name is in it ("PB-ORIGINAL" is Original). An item id
that names none, a promotion line with no item, an adjustment that adds to the payment or one not netted to the
account's invoice is noted for a person; the line still goes through the checks.

The file is data, never instructions: free text in NTE or REF is copied into descriptions and nothing else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from api.agents.remittance_reader import ReadLine, ReadRemittance

# ADX02, element 426: the codes Clawback maps itself (Stedi's 004010 element 426 list). The rest go by REF03's wording.
REASON_CODES = {"A8": "PA", "01": "PR", "06": "SH", "59": "SH", "04": "SP", "11": "SP", "GJ": "SP"}
PERIOD_START = ("015", "193", "150", "196")
PERIOD_END = ("016", "194", "151", "197")
LOOP_ENDS = {"ADX", "RMR", "ENT", "SE", "GE", "IEA", "ST", "TXP", "DED", "LX", "N9", "RYL"}

_START = re.compile(r"\A\s*(ISA|ST)(\W)")


class EdiError(ValueError):
    """It looks like an 820 but can't be read as one; a person reads it."""


@dataclass(frozen=True)
class Segment:
    tag: str
    elements: tuple[str, ...]  # elements[0] is the segment's 01 element
    start: int  # where it is in the text, terminator not included
    end: int

    def el(self, n: int) -> str:
        return self.elements[n - 1].strip() if 0 < n <= len(self.elements) else ""


@dataclass
class _Deduction:
    adx: Segment
    segments: list[Segment] = field(default_factory=list)


@dataclass
class _Invoice:
    rmr: Segment
    deductions: list[_Deduction] = field(default_factory=list)


def looks_like(text: str) -> bool:
    """An X12 820: it starts with an ISA or ST segment and has an ST*820."""
    m = _START.match(text or "")
    if not m:
        return False
    sep = re.escape(m.group(2))
    return re.search(rf"(?:\A|\W)\s*ST{sep}820{sep}", text[:5000]) is not None


def _delimiters(text: str) -> tuple[str, str]:
    m = _START.match(text)
    if not m:
        raise EdiError("it doesn't start with an ISA or ST segment")
    sep = m.group(2)
    if m.group(1) == "ISA":
        i, count = m.end() - 1, 1  # at the separator before ISA01
        while count < 16:  # the one before ISA16; the segment terminator follows ISA16, one character
            i = text.find(sep, i + 1)
            if i < 0:
                raise EdiError("its ISA segment is cut short")
            count += 1
        if i + 2 < len(text):
            return sep, text[i + 2]
    return sep, ("~" if "~" in text else "\n")


def segments(text: str) -> list[Segment]:
    sep, term = _delimiters(text)
    out, pos = [], 0
    for raw in text.split(term):
        lead = len(raw) - len(raw.lstrip())
        body = raw.strip()
        if body:
            start = pos + lead
            parts = body.split(sep)
            out.append(Segment(parts[0].strip().upper(), tuple(parts[1:]), start, start + len(body)))
        pos += len(raw) + len(term)
    return out


def _money(s: str, what: str) -> Decimal:
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        raise EdiError(f"{what} {s!r} isn't an amount") from None


def _date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y%m%d").date() if len(s) == 8 else None
    except ValueError:
        return None


def _key(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def _products(ids: list[str], products: list[str]) -> tuple[str | None, list[str]]:
    """The account's products the item ids name (in the account's order, joined with "+"), and the ids naming none."""
    named: list[str] = []
    unknown: list[str] = []
    for item in ids:
        hits = [p for p in products if _key(p) and _key(p) in _key(item)]
        longest = max((len(_key(p)) for p in hits), default=0)
        best = [p for p in hits if len(_key(p)) == longest]
        if len(best) != 1:
            unknown.append(item)
        elif best[0] not in named:
            named.append(best[0])
    ordered = [p for p in products if p in named]
    return ("+".join(ordered) or None), unknown


def _loops(segs: list[Segment]) -> tuple[list[_Invoice], list[Segment]]:
    """The RMR loops with their ADX loops, and any ADX not netted to an invoice (the ENT loop's own ADX)."""
    invoices: list[_Invoice] = []
    loose: list[Segment] = []
    current: _Invoice | None = None
    ded: _Deduction | None = None
    for s in segs:
        if s.tag == "RMR":
            current, ded = _Invoice(s), None
            invoices.append(current)
        elif s.tag == "ADX":
            if current is None:
                loose.append(s)
                ded = None
            else:
                ded = _Deduction(s)
                current.deductions.append(ded)
        elif s.tag in LOOP_ENDS:
            current, ded = None, None
        elif ded is not None:
            ded.segments.append(s)
    return invoices, loose


def _line(text: str, d: _Deduction, products: list[str]) -> tuple[ReadLine, list[str]]:
    """One ADX loop -> one line, and what about it needs a person (beyond the checks every line gets)."""
    adx = d.adx
    problems: list[str] = []
    ref = adx.el(4) or None
    refs = [s for s in d.segments if s.tag == "REF"]
    code_text = next((s.el(3) for s in refs if s.el(3)), "") or adx.el(2)
    reason = adx.el(2).upper()
    from api.remittance import CODE_ALIASES, _code_key  # the printed remittance's own list

    code = REASON_CODES.get(reason) or CODE_ALIASES.get(_code_key(code_text)) or "UNKNOWN"
    notes = [s.el(2) for s in d.segments if s.tag == "NTE" and s.el(2)]
    description = " ".join(notes) or code_text or f"Adjustment {reason}"
    starts = [_date(s.el(2)) for s in d.segments if s.tag == "DTM" and s.el(1) in PERIOD_START]
    ends = [_date(s.el(2)) for s in d.segments if s.tag == "DTM" and s.el(1) in PERIOD_END]
    it1 = next((s for s in d.segments if s.tag == "IT1"), None)
    units = rate = None
    product = None
    if it1 is not None:
        qty = _money(it1.el(2), "IT102") if it1.el(2) else None
        if qty is not None and qty == qty.to_integral_value():
            units = int(qty)
        elif qty is not None:
            problems.append(f"the quantity {it1.el(2)} isn't a whole number of units")
        rate = _money(it1.el(4), "IT104") if it1.el(4) else None
        ids = [it1.el(n + 1) for n in range(6, len(it1.elements) + 1, 2) if it1.el(n + 1)]
        product, unknown = _products(ids, products)
        if unknown:
            problems.append(f"the item {', '.join(unknown)} isn't one of the products ({', '.join(products)})")
    if code == "PA" and product is None:
        problems.append("a promotion line that names no item, so the deal's products can't be checked")
    amount = _money(adx.el(1), "ADX01")
    last = d.segments[-1] if d.segments else adx
    quote = text[adx.start:last.end]
    line = ReadLine(ref=ref, code_text=code_text, code=code, description=description, product=product,
                    units=units, rate=rate, amount=abs(amount), period_start=starts[0] if starts else None,
                    period_end=ends[0] if ends else None,
                    line_ref=next((s.el(2) for s in refs if s.el(2)), None), exact_quote=quote)
    return line, problems


def read(text: str, invoice_id: str, products: list[str]) -> tuple[ReadRemittance, dict[int, list[str]]]:
    """The 820 as ReadRemittance (the Payment reader's shape) for the account's invoice, plus, by line number (1-based,
    as api/remittance.check numbers them), anything about a line that needs a person. Raises EdiError."""
    segs = segments(text)
    tags = [s.tag for s in segs]
    if "ST" not in tags or not any(s.tag == "ST" and s.el(1) == "820" for s in segs):
        raise EdiError("it has no ST*820 (payment order / remittance advice) transaction")
    bpr = next((s for s in segs if s.tag == "BPR"), None)
    if bpr is None:
        raise EdiError("it has no BPR segment (the payment)")
    invoices, loose = _loops(segs)
    if not invoices:
        raise EdiError("it has no RMR segment (no invoice paid)")
    unclear: list[str] = []
    mine = [i for i in invoices if _key(i.rmr.el(2)) == _key(invoice_id)]
    chosen = mine[0] if mine else (invoices[0] if len(invoices) == 1 else None)
    if chosen is None:
        raise EdiError(f"it pays {len(invoices)} invoices and none is {invoice_id}")
    for other in invoices:
        if other is not chosen:
            unclear.append(f"It also pays {other.rmr.el(1)} {other.rmr.el(2)}; only {chosen.rmr.el(2)} is checked here.")
    for s in loose:
        unclear.append(f"An adjustment of {s.el(1)} (code {s.el(2)}) isn't netted to an invoice; a person looks at it.")
    lines: list[ReadLine] = []
    flagged: dict[int, list[str]] = {}
    for d in chosen.deductions:
        if _money(d.adx.el(1), "ADX01") >= 0:
            unclear.append(f"An adjustment of +{d.adx.el(1)} (code {d.adx.el(2)}) adds to the payment; it isn't a "
                           "deduction, so a person looks at it.")
            continue
        line, problems = _line(text, d, products)
        lines.append(line)
        if problems:
            flagged[len(lines)] = problems
    paid_s = chosen.rmr.el(4) or (bpr.el(2) if len(invoices) == 1 else "")
    gross_s = chosen.rmr.el(5)
    payer = next((s.el(2) for s in segs if s.tag == "N1" and s.el(1) == "PR"), None) or None
    trace = next((s.el(2) for s in segs if s.tag == "TRN"), None) or None
    out = ReadRemittance(payer=payer, payment_ref=trace, payment_date=_date(bpr.el(16)),
                         invoice_id=chosen.rmr.el(2) or None,
                         gross=_money(gross_s, "RMR05") if gross_s else None,
                         paid=_money(paid_s, "RMR04") if paid_s else None, lines=lines, unclear=unclear)
    return out, flagged
