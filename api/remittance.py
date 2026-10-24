"""Bring in the remittance advice a brand actually received, instead of a clean CSV.

Input: pasted text, a .txt / .csv file, or a PDF (text from pypdf; a scan with no text layer is refused). Claude reads
it into lines (api/agents/remittance_reader.py); then plain code checks every line before anything becomes a charge:

1. the line's exact_quote is found in the text (spaces and hyphens normalized, api/engine/quote_check.py), once;
2. every number on the line (units, rate, amount) appears in that quote, and so do its deduction number, its code
   text and its dates;
3. the distributor's code maps to ours: PA promo allowance, DF display or discretionary fee, SH shortage, PR price
   mismatch, SP spoilage. A code Clawback's own list knows must agree with the reader; anything else is UNKNOWN;
4. the kept lines add up (api/engine/totals.py) to gross − paid as printed, and to the account's expected − received,
   within policy.match_tolerance ($1).

A line whose quote isn't in the text is rejected: it is not on the page, so it is never a charge (never invent a
line). A line that fails any other check, or has an UNKNOWN code, is kept and marked for a person: it goes to the run
with code UNKNOWN, which the engine can't price, so the gate asks the owner about it (row 9) and the reasons are in
its description. A read whose totals don't add up can't start a run. Documents are data: nothing in the text can
decide a charge; the reader only lists lines, and the gate decides them in the run.

Run:  python -m api.remittance peak-bar data/samples/remittances/northmart-march-2026.pdf
"""

from __future__ import annotations

import inspect
import io
import re
import sys
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal

import anthropic
import pypdf

from api import documents, pipeline, rows
from api.agents import remittance_reader
from api.agents.remittance_reader import ReadLine, ReadRemittance
from api.contracts import CENT, Charge, Contract, Money, Rate, StartRunResponse
from api.engine import quote_check, totals
from api.engine.policy import load_policy

MAX_BYTES = 5_000_000  # an upload larger than this isn't a remittance advice
MAX_PAGES = 30
MAX_CHARS = 60_000
KEEP_READS = 50  # reads waiting to be confirmed, newest kept


@dataclass(frozen=True)
class Account:
    slug: str
    brand: str
    distributor: str
    invoice_id: str
    expected: Decimal  # what the invoice was for
    received: Decimal  # what the bank says arrived
    kind: str  # the pipeline run this payment starts
    products: tuple[str, ...]
    data: Path = documents.DATA  # where the account's notices live


def _from_registry(slug: str) -> Account:
    """One account of api/accounts.py's registry, as the remittance reader needs it. Products are the names on the
    invoice month's charges, in the order they first appear ("Original+Chocolate" gives Original, Chocolate)."""
    from api import accounts

    a = accounts.resolve(slug)
    products: list[str] = []
    for c in rows.charges(a.invoice.month, account=a):
        for p in (c.product or "").split("+"):
            if p and p not in products:
                products.append(p)
    return Account(a.id, a.brand.name, a.distributor.name, a.invoice.id, a.invoice.expected, a.invoice.received,
                   a.invoice.month, tuple(products), a.dir)


CODE_NAMES = {"PA": "promo allowance", "DF": "display fee", "SH": "shortage", "PR": "price mismatch",
              "SP": "spoilage", "UNKNOWN": "unknown"}
# Distributor wording Clawback knows, after _code_key (upper case, punctuation to spaces). The reader maps anything else.
CODE_ALIASES = {
    "PA": "PA", "PROMO": "PA", "PROMO ALLOW": "PA", "PROMO ALLOWANCE": "PA", "PROMOTIONAL ALLOWANCE": "PA",
    "DF": "DF", "DISPLAY": "DF", "DISPLAY FEE": "DF",
    "SH": "SH", "SHORTAGE": "SH", "SHORT SHIP": "SH", "SHORT SHIPPED": "SH",
    "PR": "PR", "PRICE DIFF": "PR", "PRICE DIFFERENCE": "PR", "PRICE MISMATCH": "PR", "PRICING": "PR",
    "SP": "SP", "SPOILS": "SP", "SPOILAGE": "SP", "UNSALEABLES": "SP",
}
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class InputError(ValueError):
    """The upload can't be read as a remittance (empty, too big, not text, a PDF with no text). The route says 422."""


class NotWired(RuntimeError):
    """api/pipeline.py's start() doesn't take charges yet: see HOOK."""


class CannotRun(ValueError):
    """The read's totals don't add up (or it has no charges), so it can't start a run. The route says 409."""


# The hook in api/pipeline.py (start(..., charges=)); kept here so the route explains itself if it's ever missing.
# start() takes the confirmed charges and the run reads them instead of the files:
#     def start(kind="march", client=None, background=True, deposit=None, charges: list[Charge] | None = None) -> Run:
#         run = Run(id=..., kind=kind, deposit=deposit, charges={c.id: c for c in charges or ()})
#     in _process:
#         charges = [c.model_copy(update=...) for c in (list(run.charges.values()) or rows.charges(run.kind))]
# start_with_charges() below finds the `charges` parameter by itself, so nothing else changes once it's there.
HOOK = ("api/pipeline.py's start() doesn't take charges yet. Add `charges: list[Charge] | None = None` to start(), "
        "pass `charges={c.id: c for c in charges or ()}` to Run(...), and in _process read "
        "`list(run.charges.values()) or rows.charges(run.kind)` instead of `rows.charges(run.kind)`.")


# ---------------------------------------------------------------- what a read returns

LineStatus = Literal["verified", "needs_person", "rejected"]
ProblemKind = Literal["read", "quote", "numbers", "code", "dates", "notice", "header", "totals"]


class RemittanceLine(Contract):
    n: int  # 1-based, in the order the reader returned the lines
    charge_id: str | None  # "C1"; None when rejected (not a charge)
    status: LineStatus
    reasons: list[str] = []  # why it was rejected or needs a person
    ref: str | None
    line_ref: str | None
    code_text: str
    code: str  # PA, DF, SH, PR, SP or UNKNOWN: what the line is (the charge carries UNKNOWN when it needs a person)
    description: str
    product: str | None
    units: int | None
    rate: Rate | None
    amount: Money
    period_start: date | None
    period_end: date | None
    exact_quote: str
    char_start: int | None = None  # where the quote is in `text`, for highlighting
    char_end: int | None = None


class Problem(Contract):
    kind: ProblemKind
    text: str
    line: int | None = None


class RemittanceHeader(Contract):
    payer: str | None
    payment_ref: str | None
    payment_date: date | None
    invoice_id: str | None


class RemittanceTotals(Contract):
    """Every amount from api/engine/totals.py. short = gross − paid as printed; account_short = expected − received."""

    lines: Money  # the kept lines added up
    gross: Money | None
    paid: Money | None
    short: Money | None
    expected: Money
    received: Money
    account_short: Money
    matches_remittance: bool
    matches_account: bool


class RemittanceRead(Contract):
    read_id: str
    account: str
    brand: str
    distributor: str
    input: Literal["text", "pdf"]
    source: Literal["live", "fixture"]
    ok: bool  # every line verified, totals add up, nothing to look at
    can_run: bool  # totals add up and there are charges: confirming starts a run
    header: RemittanceHeader | None
    lines: list[RemittanceLine]
    charges: list[Charge]
    problems: list[Problem]
    totals: RemittanceTotals | None
    unclear: list[str] = []
    text: str  # the text that was read (from the PDF, when it was one), for highlighting each quote


class RemittanceRunRequest(Contract):
    read_id: str


_READS: OrderedDict[str, RemittanceRead] = OrderedDict()
_reads_lock = threading.Lock()


# ---------------------------------------------------------------- input

def extract_text(data: bytes, filename: str | None = None) -> tuple[str, Literal["text", "pdf"]]:
    """The remittance's text from an upload: a PDF's text layer, or the file decoded as UTF-8."""
    if len(data) > MAX_BYTES:
        raise InputError(f"That file is over {MAX_BYTES // 1_000_000} MB; a remittance advice is much smaller.")
    if data.lstrip()[:5] == b"%PDF-" or (filename or "").lower().endswith(".pdf"):
        return _pdf_text(data), "pdf"
    try:
        return data.decode("utf-8-sig"), "text"
    except UnicodeDecodeError:
        raise InputError("That file isn't text or a PDF. Upload the PDF, or paste the remittance's text.") from None


def _pdf_text(data: bytes) -> str:
    try:
        pdf = pypdf.PdfReader(io.BytesIO(data))
        if pdf.is_encrypted and not pdf.decrypt(""):
            raise InputError("That PDF is password-protected. Paste the remittance's text instead.")
        if len(pdf.pages) > MAX_PAGES:
            raise InputError(f"That PDF has {len(pdf.pages)} pages; a remittance advice has a few.")
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except InputError:
        raise
    except Exception as e:  # noqa: BLE001 - pypdf raises many kinds of errors on a broken file
        raise InputError(f"That PDF can't be opened ({type(e).__name__}). Paste the remittance's text instead.") from e
    if not text.strip():
        raise InputError("That PDF has no text in it (it's probably a scan). Paste the remittance's text instead.")
    return text


# ---------------------------------------------------------------- read and check

def known(slug: str) -> bool:
    from api import accounts

    try:
        accounts.resolve(slug)
    except accounts.UnknownAccount:
        return False
    return True


def account(slug: str) -> Account:
    if not known(slug):
        raise KeyError(slug)
    return _from_registry(slug)


def read(slug: str, text: str, input_kind: Literal["text", "pdf"] = "text",
         client: anthropic.Anthropic | None = None) -> RemittanceRead:
    """Claude reads the remittance, code checks it, and the read waits (by read_id) for the person to confirm it."""
    acct = account(slug)
    if not text.strip():
        raise InputError("The remittance is empty. Paste its text or upload the PDF.")
    if len(text) > MAX_CHARS:
        raise InputError(f"That's {len(text):,} characters; a remittance advice is far shorter.")
    ans = remittance_reader.read(text, brand=acct.brand, distributor=acct.distributor, products=list(acct.products),
                                 invoice_id=acct.invoice_id, expected=acct.expected, received=acct.received,
                                 client=client)
    read_id = f"RR-{uuid.uuid4().hex[:8]}"
    if ans.value is None:
        why = ans.errors[-1] if ans.errors else "no answer"
        result = RemittanceRead(read_id=read_id, account=slug, brand=acct.brand, distributor=acct.distributor,
                                input=input_kind, source=ans.source, ok=False, can_run=False, header=None, lines=[],
                                charges=[], totals=None, text=text,
                                problems=[Problem(kind="read", text="Clawback couldn't read this remittance (its answer "
                                                  f"failed twice: {why[:300]}). A person needs to look at it.")])
    else:
        result = check(acct, text, ans.value, read_id=read_id, input_kind=input_kind, source=ans.source)
    with _reads_lock:
        _READS[read_id] = result
        while len(_READS) > KEEP_READS:
            _READS.popitem(last=False)
    return result


def check(acct: Account, text: str, out: ReadRemittance, read_id: str = "RR-check",
          input_kind: Literal["text", "pdf"] = "text", source: Literal["live", "fixture"] = "live") -> RemittanceRead:
    """The code checks after the read (module docstring). Plain code; the amounts come from api/engine/totals.py."""
    policy = load_policy()
    problems: list[Problem] = []
    lines: list[RemittanceLine] = []
    charges: list[Charge] = []
    used: list[tuple[int, int]] = []
    pool = rows.notices(acct.data)
    for n, ln in enumerate(out.lines, start=1):
        span = _locate(text, ln.exact_quote, used[-1][1] if used else 0, used)
        name = ln.ref or f"Line {n}"
        if span is None:
            again = quote_check.find_quote(text, ln.exact_quote) is not None
            why = "the same printed line was read twice" if again else "its quote isn't in the remittance"
            lines.append(_line(n, ln, None, "rejected", [why], ln.code, None))
            problems.append(Problem(kind="quote", line=n, text=f"{name}: rejected, {why}. It isn't a charge."))
            continue
        used.append(span)
        found = _line_checks(ln)
        code, code_problem = _code(ln)
        if code_problem:
            found.append(("code", code_problem))
        for kind, why in found:
            problems.append(Problem(kind=kind, line=n, text=f"{name}: {why}. A person decides this one."))
        reasons = [why for _, why in found]
        charge = _charge(acct, f"C{len(charges) + 1}", n, ln, code, reasons, out.payment_date)
        if not reasons and charge.code in rows.FEE_CODES:
            try:  # how much notice the distributor gave decides a display fee (Rule #1); the notices are on file
                charge = charge.model_copy(update={"notice_date": rows.notice_for(charge, pool).notice_date})
            except rows.DataError as e:
                problems.append(Problem(kind="notice", line=n, text=f"{name}: no notice on file for this fee ({e}). "
                                        "The run treats its notice as unknown."))
        charges.append(charge)
        lines.append(_line(n, ln, charge.id, "needs_person" if reasons else "verified", reasons, code, span))

    printed = set(quote_check.numbers_in(text))
    gross, paid = (_printed(v, label, printed, problems) for v, label in ((out.gross, "gross"), (out.paid, "paid")))
    header = RemittanceHeader(payer=out.payer, payment_ref=out.payment_ref, payment_date=out.payment_date,
                              invoice_id=out.invoice_id)
    wrong_invoice = bool(out.invoice_id) and _key(out.invoice_id) != _key(acct.invoice_id)
    if wrong_invoice:
        problems.append(Problem(kind="header", text=f"This remittance pays invoice {out.invoice_id}, not "
                                f"{acct.invoice_id}. It isn't the payment {acct.brand} is checking."))
    sums = _totals(acct, charges, gross, paid, policy.match_tolerance)
    if sums.short is None:
        problems.append(Problem(kind="totals", text="The remittance doesn't print both the invoice's gross amount and "
                                "what was paid, so Clawback can't check the lines add up."))
    elif not sums.matches_remittance:
        problems.append(Problem(kind="totals", text=f"The lines add up to ${sums.lines:,.2f}, but the remittance says "
                                f"${sums.gross:,.2f} − ${sums.paid:,.2f} = ${sums.short:,.2f} was taken."))
    if not sums.matches_account:
        problems.append(Problem(kind="totals", text=f"The lines add up to ${sums.lines:,.2f}, but {acct.invoice_id} "
                                f"was ${sums.expected:,.2f} and ${sums.received:,.2f} arrived: "
                                f"${sums.account_short:,.2f} short."))
    can_run = bool(charges) and sums.matches_remittance and sums.matches_account and not wrong_invoice
    ok = can_run and not problems and not out.unclear and all(ln.status == "verified" for ln in lines)
    return RemittanceRead(read_id=read_id, account=acct.slug, brand=acct.brand, distributor=acct.distributor,
                          input=input_kind, source=source, ok=ok, can_run=can_run, header=header, lines=lines,
                          charges=charges, problems=problems, totals=sums, unclear=out.unclear, text=text)


def _locate(text: str, quote: str, after: int, used: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Where the quote is, preferring the first place after the previous line (lines come in printed order) and
    never a place another line already took: the same printed line read twice is one line."""
    for base in (after, 0):
        span = quote_check.find_quote(text[base:], quote)
        if span:
            span = (span[0] + base, span[1] + base)
            if not any(s < span[1] and span[0] < e for s, e in used):
                return span
    return None


def _norm(s: str) -> str:
    return quote_check.normalize(s).casefold()


def _date_on(quote: str, d: date) -> bool:
    """The date is printed in the quote: 2026-03-01, 03/01, 3/1/26, 03/01/2026, Mar 1 or March 1."""
    forms = [rf"{d.year}-{d.month:02d}-{d.day:02d}", rf"(?<!\d)0?{d.month}/0?{d.day}(?!\d)",
             rf"\b{_MONTHS[d.month - 1]}[a-z]*\.?\s+0?{d.day}(?!\d)"]
    return any(re.search(f, quote, re.I) for f in forms)


def _line_checks(ln: ReadLine) -> list[tuple[ProblemKind, str]]:
    """Check 2: everything the reader took from the line is printed on it."""
    found: list[tuple[ProblemKind, str]] = []
    numbers = {k: v for k, v in (("units", ln.units), ("rate", ln.rate), ("amount", ln.amount)) if v is not None}
    missing = quote_check.missing_numbers(numbers, ln.exact_quote)
    if missing:
        found.append(("numbers", "not printed on the line: " + ", ".join(f"{m:,}" for m in missing)))
    for label, value in (("deduction number", ln.ref), ("code", ln.code_text)):
        if value and _norm(value) not in _norm(ln.exact_quote):
            found.append(("numbers", f"the {label} {value} isn't printed on the line"))
    if ln.period_start is None or ln.period_end is None:
        found.append(("dates", "the line prints no dates, so the deal's dates can't be checked"))
    for label, d in (("start", ln.period_start), ("end", ln.period_end)):
        if d and not _date_on(ln.exact_quote, d):
            found.append(("dates", f"the period {label} {d.isoformat()} isn't printed on the line"))
    return found


def _code_key(code_text: str) -> str:
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", code_text.upper()).split())


def _code(ln: ReadLine) -> tuple[str, str | None]:
    """Check 3: Clawback's own list wins where it knows the wording; disagreeing with the reader needs a person."""
    known = CODE_ALIASES.get(_code_key(ln.code_text))
    if known and known != ln.code:
        return known, (f"the reader read \"{ln.code_text}\" as {CODE_NAMES[ln.code]}, but Clawback's list says "
                       f"{CODE_NAMES[known]}")
    code = known or ln.code
    if code == "UNKNOWN":
        return code, f"Clawback doesn't know the code \"{ln.code_text}\""
    return code, None


def _rate(r: Decimal) -> Decimal:
    """1.5 and 1.50 are the same rate; written as cents when that's exact, as the charge files write it."""
    return r.quantize(CENT) if r == r.quantize(CENT) else r


def _charge(acct: Account, cid: str, n: int, ln: ReadLine, code: str, reasons: list[str],
            payment_date: date | None) -> Charge:
    """A line that needs a person carries code UNKNOWN (the engine prices nothing it can't verify) and says why."""
    when = payment_date or date.today()  # only for a line with no dates, which needs a person anyway
    flat = ln.units is None or ln.rate is None
    return Charge(
        id=cid, remittance_id=f"REM-{acct.invoice_id}", ref=ln.ref or f"line {n}",
        code="UNKNOWN" if reasons else code,
        description=ln.description if not reasons else f"{ln.description} (Clawback couldn't check this line: "
                                                       f"{'; '.join(reasons)})",
        # Units × rate only when the line prints both; otherwise one flat amount, as the charge files write a fee.
        product=ln.product, units=ln.units if not flat else 1, rate=_rate(ln.rate if not flat else ln.amount),
        amount=ln.amount,
        period_start=ln.period_start or when, period_end=ln.period_end or ln.period_start or when)


def _line(n: int, ln: ReadLine, charge_id: str | None, status: LineStatus, reasons: list[str], code: str,
          span: tuple[int, int] | None) -> RemittanceLine:
    return RemittanceLine(n=n, charge_id=charge_id, status=status, reasons=reasons, ref=ln.ref, line_ref=ln.line_ref,
                          code_text=ln.code_text, code=code, description=ln.description, product=ln.product,
                          units=ln.units, rate=ln.rate, amount=ln.amount, period_start=ln.period_start,
                          period_end=ln.period_end, exact_quote=ln.exact_quote,
                          char_start=span[0] if span else None, char_end=span[1] if span else None)


def _key(s: str) -> str:
    return _norm(s).replace(" ", "")


def _printed(value: Decimal | None, label: str, printed: set[Decimal], problems: list[Problem]) -> Decimal | None:
    """Gross and paid count only when printed on the remittance (the reader saw the expected amounts as context)."""
    if value is None or value in printed:
        return value
    problems.append(Problem(kind="header", text=f"The {label} amount ${value:,.2f} isn't printed on the remittance."))
    return None


def _within(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    return abs(totals.remittance_short(a, b)) <= tolerance


def _totals(acct: Account, charges: list[Charge], gross: Decimal | None, paid: Decimal | None,
            tolerance: Decimal) -> RemittanceTotals:
    """Check 4. Sums and differences from the engine; this only compares them."""
    lines = totals.total_of(c.amount for c in charges)
    short = totals.remittance_short(gross, paid) if gross is not None and paid is not None else None
    account_short = totals.remittance_short(acct.expected, acct.received)
    return RemittanceTotals(lines=lines, gross=gross, paid=paid, short=short, expected=acct.expected,
                            received=acct.received, account_short=account_short,
                            matches_remittance=short is not None and _within(lines, short, tolerance),
                            matches_account=_within(lines, account_short, tolerance))


# ---------------------------------------------------------------- confirm: start a run

def saved(read_id: str) -> RemittanceRead | None:
    with _reads_lock:
        return _READS.get(read_id)


def start_with_charges(slug: str, charges: list[Charge], client: anthropic.Anthropic | None = None,
                       background: bool = True) -> pipeline.Run:
    """A run of the account's payment on these charges, with the account's documents and data, through the
    pipeline's public start(). Raises NotWired until start() takes charges (HOOK)."""
    acct = account(slug)
    params = inspect.signature(pipeline.start).parameters
    if "charges" not in params:
        raise NotWired(HOOK)
    extra = {"account": slug} if "account" in params else {}  # the multi-account pipeline, once it has one
    return pipeline.start(kind=acct.kind, client=client, background=background, charges=list(charges), **extra)


def run_read(slug: str, read_id: str, client: anthropic.Anthropic | None = None,
             background: bool = True) -> StartRunResponse:
    """Confirm a read: start a run on exactly the charges it checked. Raises KeyError (no such read), CannotRun,
    NotWired."""
    r = saved(read_id)
    if r is None or r.account != slug:
        raise KeyError(read_id)
    if not r.can_run:
        raise CannotRun("This remittance's lines don't add up to what the payment is short, so Clawback won't run "
                        "on it. Fix the file, or ask the distributor for the full remittance.")
    run = start_with_charges(slug, r.charges, client, background)
    return StartRunResponse(run_id=run.id, events_url=f"/runs/{run.id}/events")


def reset() -> None:
    with _reads_lock:
        _READS.clear()


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv

    load_dotenv()
    if len(argv) != 2:
        print("usage: python -m api.remittance <account> <remittance.pdf|.txt>")
        return 2
    path = Path(argv[1])
    text, kind = extract_text(path.read_bytes(), path.name)
    r = read(argv[0], text, kind)
    print(f"{path.name} ({kind}, {r.source})  ok={r.ok}  can_run={r.can_run}")
    for ln in r.lines:
        print(f"  {ln.charge_id or '--':3} {ln.status:12} {ln.ref or '':9} {ln.code:7} {ln.amount:>10,.2f}  {ln.description}")
        for why in ln.reasons:
            print(f"      {why}")
    if r.totals:
        t = r.totals
        print(f"  lines {t.lines:,.2f} · remittance short {t.short if t.short is None else f'{t.short:,.2f}'} · "
              f"account short {t.account_short:,.2f}")
    for p in r.problems:
        print(f"  problem ({p.kind}): {p.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
