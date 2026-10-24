"""Check every account under data/accounts/ against the shared account layout.

Run: python scripts/check_accounts.py
Exits 1 and lists every failure if anything is off. Needs PyYAML (in api/requirements.txt) for account.yaml.

For every account:
- account.yaml has every field of the layout, with valid values;
- the month's charges sum to invoice.expected - invoice.received, and units x rate = amount on every charge;
- every line_ref exists in the delivery records, and the invoice equals the month's deliveries at their invoiced prices;
- every ops-term quote appears word for word in its source document, and its value appears in the quote;
- every deal number the math uses (promo plan, Schedule A prices) appears in the deal text;
- expected.csv covers every charge, disputed + accepted = amount for every non-ask charge, and each decision
  follows from the files (worked out again here with the math and gate in docs/design.md);
- history: paid + deducted = invoice amount for every remittance, deductions sum per month, outcomes are valid,
  and the current invoice and prior payments appear in it;
- history detail (the lookback re-checks past deductions with the same math): every deduction's deducted_on is the
  date of a remittance for that month's invoice and they sum to its deducted amount; units x rate = amount; every
  past PA row has its promo in history/promo-plan.csv and its weeks in history/sales.csv; every SH/PR row has its
  delivery line (history/deliveries.csv, or deliveries/pod.csv for the current invoice); the dispute window
  (ops term dispute_window_days, quoted from the deal; else 90 days) and the "as of" date (qbo.payment_date, else
  invoice.period_end + 20 days); and each history/expected-lookback.csv row recomputes (allowed, wrongly taken,
  claimable / past_window / settled / fair / not_checked). Fee-schedule accounts (fees/fees.yaml) skip these;
- document stems are unique across accounts (and start with the account id, except Peak Bar's original ones).

An account with fees/fees.yaml and terms/fee-terms.csv (a real contract priced by fee schedules: Copperline <- Walmart,
Fizzwick <- Five Below) gets its own checks instead of the promo, delivery and history ones: every contract account.yaml
names exists and an excerpt (fees.yaml excerpts) is exactly its source's line ranges; every fee-term quote appears in its source (whitespace aside), its
numbers are written in the quote and its discretion flag matches its wording; POs, backup and charges add up to the
invoice and the remittance; the backup's bases match our records; every expected row cites known clauses and source
documents, and its decision, amounts and gate row follow from the files.

A folder with only history/ (Peak Bar until its other files move in) gets the history checks, read against
Peak Bar's files where they are now.
"""

import csv
import email
import email.utils
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is missing: pip install -r api/requirements.txt (or pip install pyyaml)")

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ACCOUNTS = DATA / "accounts"
POLICY = yaml.safe_load((ROOT / "config" / "policy.yaml").read_text(encoding="utf-8"))
LIMIT = Decimal(str(POLICY["auto_dispute_limit_usd"]))
TOLERANCE = Decimal(str(POLICY["match_tolerance_usd"]))
DISCRETION_WORDS = tuple(w.lower() for w in POLICY["discretion_words"])

CODES = {"PA", "DF", "SH", "PR", "SP"}  # promo allowance, discretionary fee, shortage, price mismatch, spoilage
# An account with fees/fees.yaml (fee schedules, api/fee_accounts.py) also knows OI (an off-invoice allowance recovered
# by deduction) and the charge codes its fees.yaml maps to the deal's fees. Its decisions are worked out by the engine
# itself in api/tests (test_lantern_hill.py), not again here.
FEE_CODES = {"OI"}
DECISIONS = {"dispute", "accept", "split", "ask"}
OUTCOMES = {"recovered", "accepted", "written_off", "open"}
INVOICE_STATUSES = {"paid", "open"}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
HISTORY_MONTHS = 6

CHARGE_COLS = ["charge_id", "ref", "code", "description", "product", "units", "rate", "amount", "period_start",
               "period_end", "line_ref"]
COLS = {
    "sales/store-sales.csv": ["week_start", "week_end", "product", "promo_units", "total_units"],
    "payments/prior.csv": ["ref", "paid_on", "promo_id", "product", "period_start", "period_end", "units", "amount"],
    "plan/promo-plan.csv": ["promo_id", "product", "rate", "starts", "ends", "cap"],
    "deliveries/pod.csv": ["line_ref", "product", "shipped_units", "received_units", "unit_price", "received_by",
                           "received_at"],
    "pricing/price-list.csv": ["product", "agreed_price", "effective_from", "effective_to", "source_doc"],
    "terms/ops-terms.csv": ["key", "value", "source_doc", "quote"],
    "expected.csv": ["charge_id", "decision", "disputed", "accepted", "why"],
    "history/invoices.csv": ["invoice", "date", "amount", "status"],
    "history/remittances.csv": ["date", "invoice", "paid", "deducted"],
    "history/deductions.csv": ["month", "ref", "code", "description", "amount", "outcome", "recovered", "deducted_on",
                               "product", "units", "rate", "period_start", "period_end", "line_ref"],
    "history/promo-plan.csv": ["promo_id", "product", "rate", "starts", "ends", "cap"],
    "history/sales.csv": ["week_start", "week_end", "product", "promo_units", "total_units"],
    "history/deliveries.csv": ["line_ref", "product", "shipped_units", "received_units", "unit_price", "received_by",
                               "received_at"],
    "history/expected-lookback.csv": ["ref", "allowed", "wrongly_taken", "status", "why"],
}
LOOKBACK_STATUSES = {"claimable", "past_window", "settled", "fair", "not_checked"}
CHECKED_CODES = {"PA", "SH", "PR"}  # the lookback leaves fees and unsaleables as they are (not_checked)
DEFAULT_WINDOW = 90  # days, for an account whose deal states no dispute window
PAYMENT_LAG = 20  # days after the invoice period ends, when account.yaml has no qbo.payment_date
DOC_DIRS = {"deals": ".md", "emails": ".eml", "notices": ".md"}

# Peak Bar's files before they move into data/accounts/peak-bar/, and its fixed demo numbers (data/CLAUDE.md).
PEAK_BAR = "peak-bar"
LEGACY = {"charges/march.csv": "charges/northmart-march.csv", "payments/prior.csv": "payments/prior.csv"}
PEAK_BAR_INVOICE = ("INV-3102", Decimal("48200.00"), Decimal("41350.00"), Decimal("6850.00"))

EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)*\.example$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
CENT = Decimal("0.01")

passed = 0
failures = []


def check(name, ok, detail=""):
    global passed
    if ok:
        passed += 1
        print(f"  ok   {name}")
    else:
        failures.append(name)
        print(f"  FAIL {name}" + (f": {detail}" if detail else ""))
    return ok


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def is_date(value):
    try:
        date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def day(value):
    return date.fromisoformat(str(value))


def products(text):
    """'A+B' (charges, prior payments) or 'A; B' (promo plan) -> a set of product names."""
    return {p.strip() for p in text.replace(";", "+").split("+") if p.strip()}


def words(d):
    """date(2026, 3, 1) -> 'March 1', the way the deals write dates."""
    return f"{d:%B} {d.day}"


def has_discretion(text):
    low = text.lower()
    return [w for w in DISCRETION_WORDS if re.search(rf"\b{re.escape(w)}\b", low)]


class Account:
    def __init__(self, folder):
        self.dir = folder
        self.id = folder.name
        self.label = folder.name
        self.yaml = None
        fees = folder / "fees" / "fees.yaml"
        self.fees = (yaml.safe_load(fees.read_text(encoding="utf-8")) or {}) if fees.exists() else None
        self.codes = CODES | (FEE_CODES | set(self.fees.get("codes", {})) if self.fees is not None else set())

    def path(self, rel):
        """The account's file, or Peak Bar's file where it is now if it hasn't moved yet."""
        p = self.dir / rel
        if not p.exists() and self.id == PEAK_BAR and rel in LEGACY:
            p = DATA / LEGACY[rel]
        return p

    def rows(self, rel, cols=None, required=True):
        p = self.path(rel)
        if not p.exists():
            if required:
                check(f"{self.label}: {rel} exists", False)
            return None
        with p.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            data = list(reader)
            got = reader.fieldnames or []
        want = cols or COLS.get(rel)
        if want:
            if want == CHARGE_COLS:  # line_ref is optional for an account with no SH/PR charges
                ok = got in (CHARGE_COLS, CHARGE_COLS[:-1]) or (self.fees is not None and got == CHARGE_COLS
                                                                 + ["deducted_on"])
            elif rel == "expected.csv" and self.fees is not None:  # may add gate_row and asked
                ok = got[:4] == want[:4] and set(want) <= set(got)
            elif rel == "history/deductions.csv" and self.fees is not None:  # no lookback detail yet
                ok = got in (want, want[:7])
            else:
                ok = got == want
            check(f"{self.label}: {rel} columns", ok, got)
        return data

    def docs(self):
        """doc id (file stem) -> (folder, path) for every deal, email and notice."""
        out = {}
        for sub, ext in DOC_DIRS.items():
            for p in sorted((self.dir / sub).glob(f"*{ext}")):
                out[p.stem] = (sub, p)
        for name in (self.yaml or {}).get("contracts", []):  # a real contract under data/contracts/, its own name
            p = DATA / "contracts" / name
            out[p.stem] = ("deals", p)
        return out


# ---------------------------------------------------------------- account.yaml

def check_yaml(acct, docs):
    y = acct.yaml
    print(f"{acct.label}: account.yaml")

    def field(path, kind=str):
        node = y
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                check(f"{acct.label}: account.yaml has {path}", False)
                return None
            node = node[key]
        ok = isinstance(node, kind) and node not in ("", None)
        check(f"{acct.label}: account.yaml {path} is a {kind.__name__ if not isinstance(kind, tuple) else 'number'}",
              ok, repr(node))
        return node if ok else None

    check(f"{acct.label}: id matches the folder", y.get("id") == acct.id, y.get("id"))
    for path in ("brand.name", "brand.kind", "brand.city", "brand.initials", "brand.owner.name",
                 "distributor.name", "distributor.portal_name", "invoice.id", "qbo.customer",
                 "qbo.invoice_no", "nessie_description"):
        field(path)
    initials = field("brand.initials")
    if initials:
        check(f"{acct.label}: brand initials are 2-3 capitals", re.fullmatch(r"[A-Z]{2,3}", initials) is not None)
    for path in ("brand.colors.primary", "brand.colors.accent", "distributor.colors.primary",
                 "distributor.colors.accent"):
        v = field(path)
        if v:
            check(f"{acct.label}: {path} is a #RRGGBB color", HEX.match(v) is not None, v)
    owner = field("brand.owner.email")
    desk = field("distributor.desk_email")
    for label, v in (("owner email", owner), ("desk email", desk)):
        if v:
            check(f"{acct.label}: {label} uses an .example domain", EMAIL.match(v) is not None, v)

    expected = field("invoice.expected", (int, float))
    received = field("invoice.received", (int, float))
    if expected is not None and received is not None:
        check(f"{acct.label}: invoice received is below expected", money(received) < money(expected))
    month = field("invoice.month")
    start, end = field("invoice.period_start", (str, date)), field("invoice.period_end", (str, date))
    if start and end:
        ok = is_date(start) and is_date(end)
        check(f"{acct.label}: invoice period dates are YYYY-MM-DD", ok, f"{start} {end}")
        if ok:
            check(f"{acct.label}: invoice period starts before it ends", day(start) <= day(end))
            if month:
                check(f"{acct.label}: invoice.month is the period's month in lowercase",
                      month == MONTHS[day(start).month - 1], month)

    deal_docs = field("deal_docs", list)
    if deal_docs:
        missing = [d for d in deal_docs if d not in docs]
        check(f"{acct.label}: every deal_docs id is a document in the account", not missing, missing)
        check(f"{acct.label}: deal_docs lists the deal first", docs.get(deal_docs[0], ("",))[0] == "deals",
              deal_docs[0])
        check(f"{acct.label}: deal_docs has no repeats", len(set(deal_docs)) == len(deal_docs))
    senders = field("approved_senders", list)
    if senders:
        bad = [s for s in senders if not EMAIL.match(str(s))]
        check(f"{acct.label}: approved senders are .example emails", not bad, bad)
        check(f"{acct.label}: the owner is an approved sender", owner in senders)
        check(f"{acct.label}: the distributor's desk is not an approved sender", desk not in senders)
    start_no = field("dispute_start", int)
    if start_no is not None:
        check(f"{acct.label}: dispute_start is positive", start_no > 0, start_no)
    inv_id, dist = y.get("invoice", {}).get("id"), y.get("distributor", {}).get("name")
    check(f"{acct.label}: nessie_description is '<Distributor> remittance <invoice id>'",
          y.get("nessie_description") == f"{dist} remittance {inv_id}", y.get("nessie_description"))
    return y


# ---------------------------------------------------------------- documents

def check_docs(acct, docs):
    print(f"{acct.label}: documents")
    check(f"{acct.label}: has a deal in deals/", any(sub == "deals" for sub, _ in docs.values()))
    contracts = {Path(n).stem for n in (acct.yaml or {}).get("contracts", [])}
    for stem, (sub, path) in docs.items():
        if stem in contracts:
            check(f"{acct.label}: contract {path.name} is in data/contracts/", path.is_file())
            continue
        text = path.read_text(encoding="utf-8")
        if acct.id != PEAK_BAR:
            check(f"{acct.label}: {sub}/{path.name} stem starts with the account id", stem.startswith(f"{acct.id}-"))
            check(f"{acct.label}: {sub}/{path.name} reads like a real document (no 'fictional' or 'demo')",
                  not re.search(r"\b(fictional|demo)\b", text, re.I))
        if sub == "emails":
            msg = email.message_from_string(text)
            sender = email.utils.parseaddr(msg.get("From", ""))[1]
            check(f"{acct.label}: {path.name} has a From address on an .example domain", bool(EMAIL.match(sender)),
                  sender)
            ok = bool(msg.get("Date"))
            if ok:
                try:
                    email.utils.parsedate_to_datetime(msg["Date"])
                except (TypeError, ValueError):
                    ok = False
            check(f"{acct.label}: {path.name} has a valid Date header", ok, msg.get("Date"))


def doc_text(docs, doc_id):
    return docs[doc_id][1].read_text(encoding="utf-8") if doc_id in docs else ""


# ---------------------------------------------------------------- terms, prices, plan

def value_in_quote(value, quote):
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        d = day(value)
        return words(d) in quote and str(d.year) in quote
    if re.fullmatch(r"\d+(\.\d+)?", value):
        found = {Decimal(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", quote) if n.strip(",")}
        return Decimal(value) in found
    if ";" in value:
        return all(p.strip() in quote for p in value.split(";"))
    return value.lower() in quote.lower()


def check_terms(acct, docs, terms):
    print(f"{acct.label}: ops terms")
    keys = Counter(t["key"] for t in terms)
    check(f"{acct.label}: ops-term keys are unique", all(n == 1 for n in keys.values()),
          [k for k, n in keys.items() if n > 1])
    for t in terms:
        text = doc_text(docs, t["source_doc"])
        check(f"{acct.label}: {t['key']} source {t['source_doc']} exists", bool(text))
        check(f"{acct.label}: {t['key']} quote appears word for word", t["quote"] in text, t["quote"][:60])
        check(f"{acct.label}: {t['key']} value {t['value']} appears in its quote", value_in_quote(t["value"], t["quote"]))
        found = has_discretion(t["quote"])
        check(f"{acct.label}: {t['key']} quote has no discretion word", not found, found)
    return {t["key"]: t["value"] for t in terms}


def check_prices(acct, docs, prices):
    print(f"{acct.label}: price list")
    for p in prices:
        text = doc_text(docs, p["source_doc"])
        price = f"${money(p['agreed_price']):,}"
        check(f"{acct.label}: {p['product']} {price} is in {p['source_doc']}", p["product"] in text and price in text)
        ok = is_date(p["effective_from"]) and is_date(p["effective_to"])
        check(f"{acct.label}: {p['product']} price dates are valid", ok and day(p["effective_from"]) <= day(p["effective_to"]))


def agreed_price(prices, product, when):
    hits = [p for p in prices if p["product"] == product
            and day(p["effective_from"]) <= when <= day(p["effective_to"])]
    return money(hits[0]["agreed_price"]) if len(hits) == 1 else None


def check_plan(acct, docs, plan, terms):
    print(f"{acct.label}: promo plan against the deal")
    if not plan:
        check(f"{acct.label}: promo-plan.csv has a row", False)
        return None
    deal_id = (acct.yaml or {}).get("deal_docs", [None])[0]
    deal = doc_text(docs, deal_id) if deal_id else ""
    if not deal and acct.id == PEAK_BAR:
        deal = (DATA / "deals" / "spring-promo.md").read_text(encoding="utf-8")
    p = plan[0]
    rate, cap = money(p["rate"]), int(p["cap"])
    starts, ends = day(p["starts"]), day(p["ends"])
    check(f"{acct.label}: deal states the promo rate ${rate}", f"${rate}" in deal)
    check(f"{acct.label}: deal states the cap of {cap:,} units", f"{cap:,} units" in deal)
    check(f"{acct.label}: deal states the promo dates {words(starts)} to {words(ends)}, {ends.year}",
          words(starts) in deal and f"{words(ends)}, {ends.year}" in deal)
    for prod in sorted(products(p["product"])):
        check(f"{acct.label}: deal names promoted product {prod}", prod in deal)
    if terms:
        check(f"{acct.label}: ops-term promo_rate = plan rate", money(terms.get("promo_rate", "-1")) == rate)
        check(f"{acct.label}: ops-term promo_cap_units = plan cap", terms.get("promo_cap_units") == str(cap))
        check(f"{acct.label}: ops-term promo dates = plan dates",
              terms.get("promo_start") == p["starts"] and terms.get("promo_end") == p["ends"])
        check(f"{acct.label}: ops-term promo_products = plan products",
              products(terms.get("promo_products", "")) == products(p["product"]))
    return {"rate": rate, "cap": cap, "starts": starts, "ends": ends, "products": products(p["product"])}


# ---------------------------------------------------------------- charges and the math

def check_charges(acct, charges, pod, prices, sales, plan):
    y = acct.yaml
    print(f"{acct.label}: charges")
    ids, refs = Counter(c["charge_id"] for c in charges), Counter(c["ref"] for c in charges)
    check(f"{acct.label}: charge ids and refs are unique",
          all(n == 1 for n in ids.values()) and all(n == 1 for n in refs.values()))
    pod_by_ref = {r["line_ref"]: r for r in pod or []}
    weeks = {(r["week_start"], r["week_end"]) for r in sales or []}
    for c in charges:
        cid = c["charge_id"]
        check(f"{acct.label}: {cid} code {c['code']} is known", c["code"] in acct.codes)
        check(f"{acct.label}: {cid} units x rate = amount",
              money(Decimal(c["units"]) * Decimal(c["rate"])) == money(c["amount"]), c["amount"])
        check(f"{acct.label}: {cid} period dates are valid",
              is_date(c["period_start"]) and is_date(c["period_end"]) and c["period_start"] <= c["period_end"])
        line_ref = c.get("line_ref") or ""
        if c["code"] in ("SH", "PR"):
            check(f"{acct.label}: {cid} names a delivery line", bool(line_ref))
        if line_ref:
            row = pod_by_ref.get(line_ref)
            if check(f"{acct.label}: {cid} line_ref {line_ref} exists in the delivery records", row is not None):
                check(f"{acct.label}: {cid} product matches delivery {line_ref}", c["product"] == row["product"])
        if c["code"] == "PA" and plan and sales is not None:
            starts = {s for s, _ in weeks}
            ends = {e for _, e in weeks}
            check(f"{acct.label}: {cid} period lines up with store-sales weeks",
                  c["period_start"] in starts and c["period_end"] in ends)
    total = sum((money(c["amount"]) for c in charges), Decimal(0))
    if y:
        want = money(y["invoice"]["expected"]) - money(y["invoice"]["received"])
        check(f"{acct.label}: charges sum to expected - received (${want:,})", total == want, total)
    return total


def check_deliveries(acct, pod, prices, charges):
    print(f"{acct.label}: deliveries")
    y = acct.yaml
    refs = Counter(r["line_ref"] for r in pod)
    check(f"{acct.label}: delivery line_refs are unique", all(n == 1 for n in refs.values()))
    pr_lines = {c["line_ref"] for c in charges if c["code"] == "PR"}
    for r in pod:
        check(f"{acct.label}: {r['line_ref']} received <= shipped and a valid date",
              0 <= int(r["received_units"]) <= int(r["shipped_units"]) and is_date(r["received_at"]))
        agreed = agreed_price(prices, r["product"], day(r["received_at"])) if prices is not None else None
        if prices is not None:
            check(f"{acct.label}: {r['line_ref']} product has one agreed price that day", agreed is not None)
            if agreed is not None and money(r["unit_price"]) != agreed:
                check(f"{acct.label}: {r['line_ref']} invoiced ${r['unit_price']} vs agreed ${agreed} has a PR charge",
                      r["line_ref"] in pr_lines)
    if y:
        start, end = day(y["invoice"]["period_start"]), day(y["invoice"]["period_end"])
        value = sum((money(Decimal(r["shipped_units"]) * Decimal(r["unit_price"])) for r in pod
                     if start <= day(r["received_at"]) <= end), Decimal(0))
        check(f"{acct.label}: invoice = the period's deliveries at their invoiced prices",
              value == money(y["invoice"]["expected"]), value)


def allowed_for(c, plan, sales, prior, pod, prices, terms):
    """What the deal allows for one charge (docs/design.md "Math engine" and the account layout's SH/PR/SP rules).
    Returns (allowed, reason_to_ask): reason_to_ask is set when the math can't settle it."""
    taken = money(c["amount"])
    code = c["code"]
    if code == "DF":
        return None, "discretionary fee with no saved rule"
    if code == "PA":
        if not plan:
            return None, "no promo plan"
        mine = products(c["product"]) & plan["products"]
        if not mine:
            return Decimal(0), None
        p_start, p_end = day(c["period_start"]), day(c["period_end"])
        running = in_dates = 0
        for s in sorted((s for s in sales if s["product"] in plan["products"]),
                        key=lambda s: (s["week_start"], s["product"])):
            ws, we, units = day(s["week_start"]), day(s["week_end"]), int(s["promo_units"])
            in_charge = p_start <= ws and we <= p_end and s["product"] in mine
            if plan["starts"] <= ws and we <= plan["ends"]:
                room = max(0, min(units, plan["cap"] - running))
                running += units
                if in_charge:
                    in_dates += room
        covered = min(int(c["units"]), in_dates)
        paid = sum(int(p["units"]) for p in prior if p["period_start"] == c["period_start"]
                   and p["period_end"] == c["period_end"] and products(p["product"]) & mine)
        covered = max(0, covered - paid)
        return money(covered * plan["rate"]), None
    if code in ("SH", "PR"):
        row = {r["line_ref"]: r for r in pod}.get(c.get("line_ref") or "")
        if row is None:
            return None, "no delivery line"
        if code == "SH":
            short = int(row["shipped_units"]) - int(row["received_units"])
            return money(min(int(c["units"]), short) * Decimal(row["unit_price"])), None
        agreed = agreed_price(prices, row["product"], day(row["received_at"]))
        if agreed is None:
            return None, "no agreed price"
        return money(int(c["units"]) * max(Decimal(0), Decimal(row["unit_price"]) - agreed)), None
    if code == "SP":
        pct = terms.get("spoils_allowance_pct")
        if pct is None:
            return None, "the deal's unsaleables term has no single reading"
        p_start, p_end = day(c["period_start"]), day(c["period_end"])
        shipped = sum((Decimal(r["shipped_units"]) * Decimal(r["unit_price"]) for r in pod
                       if p_start <= day(r["received_at"]) <= p_end), Decimal(0))
        return min(taken, money(Decimal(pct) / 100 * shipped)), None
    return None, f"unknown code {code}"


def gate(taken, allowed, ask_reason):
    """The gate's money rows: (decision, disputed, accepted); ask leaves both at 0."""
    zero = Decimal("0.00")
    if ask_reason:
        return "ask", zero, zero
    delta = taken - allowed
    if abs(delta) <= TOLERANCE or delta < 0:
        return "accept", zero, taken
    if delta > LIMIT:
        return "ask", zero, zero
    if allowed > 0:
        return "split", delta, allowed
    return "dispute", taken, zero


def check_expected(acct, charges, expected, recompute):
    print(f"{acct.label}: expected decisions")
    by_id = {c["charge_id"]: c for c in charges}
    got = Counter(e["charge_id"] for e in expected)
    check(f"{acct.label}: expected.csv covers every charge once",
          set(got) == set(by_id) and all(n == 1 for n in got.values()),
          sorted(set(by_id) ^ set(got)))
    totals = {"disputed": Decimal(0), "accepted": Decimal(0), "asks": 0}
    for e in expected:
        c = by_id.get(e["charge_id"])
        if c is None:
            continue
        cid, amount = e["charge_id"], money(c["amount"])
        decision, disputed, accepted = e["decision"], money(e["disputed"]), money(e["accepted"])
        check(f"{acct.label}: {cid} decision '{decision}' is known", decision in DECISIONS)
        check(f"{acct.label}: {cid} has a why", bool(e["why"].strip()))
        if decision == "ask":
            totals["asks"] += 1
            check(f"{acct.label}: {cid} ask amounts are within the charge",
                  disputed >= 0 and accepted >= 0 and disputed + accepted <= amount)
            continue
        totals["disputed"] += disputed
        totals["accepted"] += accepted
        check(f"{acct.label}: {cid} {decision}: disputed {disputed} + accepted {accepted} = amount {amount}",
              disputed + accepted == amount)
        shape = {"dispute": accepted == 0, "accept": disputed == 0, "split": disputed > 0 and accepted > 0}
        check(f"{acct.label}: {cid} amounts fit '{decision}'", shape.get(decision, False))
    if recompute is not None:
        for e in expected:
            c = by_id.get(e["charge_id"])
            if c is None:
                continue
            allowed, reason = recompute(c)
            want = gate(money(c["amount"]), allowed, reason)
            have = (e["decision"], money(e["disputed"]), money(e["accepted"]))
            why = reason or (f"allowed ${allowed:,}" if allowed is not None else "")
            check(f"{acct.label}: {e['charge_id']} {have[0]} follows from the files ({why})", have == want,
                  f"files give {want[0]} {want[1]} / {want[2]}")
    print(f"  ..   {acct.label}: disputed ${totals['disputed']:,} · accepted ${totals['accepted']:,} · "
          f"{totals['asks']} ask(s)")


# ---------------------------------------------------------------- history

def month_key(d):
    return f"{d.year}-{d.month:02d}"


def check_history(acct, charges, prior):
    print(f"{acct.label}: history")
    invoices = acct.rows("history/invoices.csv")
    remits = acct.rows("history/remittances.csv")
    deductions = acct.rows("history/deductions.csv")
    if invoices is None or remits is None or deductions is None:
        return set()
    inv = {}
    for r in invoices:
        ok = is_date(r["date"]) and r["status"] in INVOICE_STATUSES and money(r["amount"]) > 0
        check(f"{acct.label}: invoice {r['invoice']} has a date, amount and paid/open status", ok, r)
        check(f"{acct.label}: invoice {r['invoice']} listed once", r["invoice"] not in inv)
        inv[r["invoice"]] = r
    months = sorted({month_key(day(r["date"])) for r in invoices if is_date(r["date"])})
    check(f"{acct.label}: history covers {HISTORY_MONTHS} months", len(months) == HISTORY_MONTHS, months)
    if months:
        y0, m0 = map(int, months[0].split("-"))
        run = [f"{y0 + (m0 - 1 + i) // 12}-{(m0 - 1 + i) % 12 + 1:02d}" for i in range(len(months))]
        check(f"{acct.label}: history months are consecutive", months == run, months)
    if acct.yaml:
        end = month_key(day(acct.yaml["invoice"]["period_start"]))
    else:
        end = "2026-03"  # Peak Bar: six months ending March 2026
    check(f"{acct.label}: history ends in the current month {end}", bool(months) and months[-1] == end,
          months[-1:] if months else None)

    by_invoice = defaultdict(list)
    for r in remits:
        by_invoice[r["invoice"]].append(r)
        i = inv.get(r["invoice"])
        if not check(f"{acct.label}: remittance {r['date']} pays a known invoice {r['invoice']}", i is not None):
            continue
        check(f"{acct.label}: {r['invoice']} paid + deducted = invoice amount",
              money(r["paid"]) + money(r["deducted"]) == money(i["amount"]),
              f"{r['paid']} + {r['deducted']} vs {i['amount']}")
        check(f"{acct.label}: {r['invoice']} remittance comes after the invoice",
              is_date(r["date"]) and is_date(i["date"]) and day(r["date"]) >= day(i["date"]))
    check(f"{acct.label}: every invoice has exactly one remittance",
          all(len(by_invoice[k]) == 1 for k in inv), [k for k in inv if len(by_invoice[k]) != 1])

    refs = Counter(d["ref"] for d in deductions)
    check(f"{acct.label}: deduction refs are unique", all(n == 1 for n in refs.values()),
          [k for k, n in refs.items() if n > 1])
    per_month = defaultdict(Decimal)
    open_months = set()
    for d in deductions:
        amount, recovered = money(d["amount"]), money(d["recovered"])
        check(f"{acct.label}: deduction {d['ref']} code {d['code']} and outcome {d['outcome']} are known",
              d["code"] in acct.codes and d["outcome"] in OUTCOMES)
        if d["outcome"] == "recovered":
            ok = Decimal(0) < recovered <= amount
        else:
            ok = recovered == 0
        check(f"{acct.label}: deduction {d['ref']} recovered ${recovered} fits '{d['outcome']}'", ok)
        check(f"{acct.label}: deduction {d['ref']} month {d['month']} is a history month", d["month"] in months)
        per_month[d["month"]] += amount
        if d["outcome"] == "open":
            open_months.add(d["month"])
    for m in months:
        deducted = sum((money(r["deducted"]) for r in remits if r["invoice"] in inv
                        and month_key(day(inv[r["invoice"]]["date"])) == m), Decimal(0))
        check(f"{acct.label}: {m} deductions sum to the month's remittance deductions (${deducted:,})",
              per_month[m] == deducted, per_month[m])
        has_open_invoice = any(r["status"] == "open" for r in invoices if month_key(day(r["date"])) == m)
        check(f"{acct.label}: {m} has an open invoice exactly when it has open deductions",
              has_open_invoice == (m in open_months))

    # The current invoice and its charges.
    if acct.yaml:
        cur, expected, received = (acct.yaml["invoice"]["id"], money(acct.yaml["invoice"]["expected"]),
                                   money(acct.yaml["invoice"]["received"]))
        deducted = expected - received
    else:
        cur, expected, received, deducted = PEAK_BAR_INVOICE
    i, r = inv.get(cur), (by_invoice.get(cur) or [None])[0]
    check(f"{acct.label}: current invoice {cur} is ${expected:,}, open",
          i is not None and money(i["amount"]) == expected and i["status"] == "open")
    check(f"{acct.label}: current remittance paid ${received:,}, deducted ${deducted:,}",
          r is not None and money(r["paid"]) == received and money(r["deducted"]) == deducted)
    by_ref = {d["ref"]: d for d in deductions}
    if charges is not None and i is not None:
        cur_month = month_key(day(i["date"]))
        bad = [c["ref"] for c in charges
               if not (c["ref"] in by_ref and by_ref[c["ref"]]["month"] == cur_month
                       and money(by_ref[c["ref"]]["amount"]) == money(c["amount"])
                       and by_ref[c["ref"]]["code"] == c["code"] and by_ref[c["ref"]]["outcome"] == "open")]
        check(f"{acct.label}: every current charge is an open {cur_month} deduction with the same amount and code",
              not bad, bad)
    if prior is not None:
        for p in prior:
            d = by_ref.get(p["ref"])
            ok = d is not None and money(d["amount"]) == money(p["amount"]) and d["outcome"] == "accepted"
            check(f"{acct.label}: prior payment {p['ref']} is an accepted deduction of ${money(p['amount']):,}", ok)
            if d is not None:
                on_day = [x for x in remits if x["date"] == p["paid_on"] and x["invoice"] in inv
                          and month_key(day(inv[x["invoice"]]["date"])) == d["month"]]
                check(f"{acct.label}: prior payment {p['ref']} was taken on the {p['paid_on']} remittance",
                      len(on_day) == 1)
    return set(inv)


# ---------------------------------------------------------------- fee-schedule accounts (fees/fees.yaml)
# A real contract (data/contracts/) priced by fee schedules: Walmart's Supplier Agreement, Five Below's Vendor Agreement.
# terms/fee-terms.csv is the hand-made key of the clauses the charges use (what both readers should return), each
# with its quote; the checks below rebuild every expected decision from it and from our side's records.

FEE_TERM_COLS = ["key", "version", "fee_code", "basis", "rate", "max", "per", "condition", "discretion", "source_doc",
                 "quote"]
FEE_CHARGE_COLS = CHARGE_COLS + ["deducted_on"]
FEE_EXPECTED_COLS = ["charge_id", "decision", "disputed", "accepted", "gate_row", "asked", "why", "clause", "sources"]
MONEY_BASES = {"percent", "flat", "annual_percent", "per_document_day"}
NOT_SUPPLIERS_FAULT = {"carrier", "retailer"}  # the appointment log's cause when the other side or its carrier caused it


def norm(text):
    return " ".join(text.split())


def fee_numbers_in(value, quote):
    """Every number of value (a rate, a cap, '30', 'issued_on>=2026-03-01') is written in the quote."""
    for d in re.findall(r"\d{4}-\d{2}-\d{2}", value):
        if not (words(day(d)) in quote and str(day(d).year) in quote):
            return False
    rest = re.sub(r"\d{4}-\d{2}-\d{2}", "", value)
    found = {Decimal(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", quote) if n.strip(",")}
    return all(Decimal(n) in found for n in re.findall(r"\d+(?:\.\d+)?", rest))


def check_fee_contracts(acct, fees):
    """account.yaml names its contracts, each under data/contracts/; an excerpt (fees.yaml excerpts) is exactly its
    source's lines joined by '[...]'."""
    print(f"{acct.label}: contracts")
    names = (acct.yaml or {}).get("contracts") or []
    check(f"{acct.label}: account.yaml names its contracts", bool(names))
    out = {}
    for name in names:
        path = DATA / "contracts" / name
        if check(f"{acct.label}: contract {name} exists in data/contracts/", path.is_file()):
            out[path.stem] = path.read_text(encoding="utf-8")
    for doc_id, ex in (fees.get("excerpts") or {}).items():
        lines = (DATA / ex["source"]).read_text(encoding="utf-8").split("\n")
        parts = ["\n".join(lines[a - 1:b]) for a, b in ex["lines"]]
        check(f"{acct.label}: {doc_id} is {ex['source']} lines {ex['lines']} word for word",
              out.get(doc_id) == "\n\n[...]\n\n".join(parts) + "\n")
    return out


def check_fee_terms(acct, terms, texts):
    print(f"{acct.label}: fee terms")
    keys = Counter(t["key"] for t in terms)
    check(f"{acct.label}: fee-term keys are unique", all(n == 1 for n in keys.values()),
          [k for k, n in keys.items() if n > 1])
    for t in terms:
        k = t["key"]
        text = texts.get(t["source_doc"], "")
        check(f"{acct.label}: {k} source {t['source_doc']} exists", bool(text))
        check(f"{acct.label}: {k} quote appears word for word", norm(t["quote"]) in norm(text), t["quote"][:60])
        for col in ("rate", "max", "condition"):
            if t[col]:
                check(f"{acct.label}: {k} {col} {t[col]} is written in its quote", fee_numbers_in(t[col], t["quote"]))
        check(f"{acct.label}: {k} discretion={t['discretion']} matches its wording",
              (t["discretion"] == "yes") == bool(has_discretion(t["quote"])), has_discretion(t["quote"]))


def fee_version(terms, on):
    """The contract version that governs a purchase issued on `on` (the version rows' issued_on conditions)."""
    for t in terms:
        if t["basis"] != "version":
            continue
        op, d = re.fullmatch(r"issued_on(>=|<)(\S+)", t["condition"]).groups()
        if (on >= day(d)) if op == ">=" else (on < day(d)):
            return t["version"]
    return "all"


def fee_allowed(c, f):
    """(allowed, ask_reason, gate_row_if_ask, past_window) for one fee charge, from the files."""
    lines = f["backup"].get(c["ref"], [])
    if not lines:
        return None, "no backup", 9, False
    on = day(lines[0]["on"])
    ver = fee_version(f["terms"], on)
    fee_code = f["codes"][c["code"]]
    mine = [t for t in f["terms"] if t["version"] in ("all", ver)
            and fee_code in [x.strip() for x in t["fee_code"].split(";")]]
    window = [t for t in f["terms"] if t["basis"] == "dispute_window" and t["version"] in ("all", ver)]
    past = False
    if window and c["deducted_on"]:
        closes = day(c["deducted_on"]) + timedelta(days=int(window[0]["rate"]))
        past = closes < f["as_of"]
    po = lines[0]["group"]
    purchase = f["purchases"].get(po)
    appt = f["appointments"].get(po, {})
    ask = None
    for t in mine:
        cond = t["condition"]
        if not cond or t["basis"] in MONEY_BASES and cond.startswith("working_days"):
            continue
        if cond.startswith("po_type="):
            ok = purchase is not None and purchase["po_type"] == cond.split("=", 1)[1]
        elif cond == "supplier_fault":
            ok = appt.get("cause", "") not in NOT_SUPPLIERS_FAULT
        elif cond.startswith("grace_days="):
            debit = f["debits"].get(po)
            late = (day(debit["paid_on"]) - day(debit["due_on"])).days if debit else 0
            ok = late > int(cond.split("=", 1)[1])
        elif cond == "year_end_claim":
            ok = day(c["period_end"]).month == 1 and day(c["period_end"]).day == 31
        elif cond.startswith("variance_pct="):
            ok = True
            if purchase is not None:
                over = abs(int(purchase["received_units"]) - int(purchase["units"])) * 100 / int(purchase["units"])
                if over <= float(cond.split("=", 1)[1]) and t["discretion"] == "yes":
                    ask = ask or ("within the variance the buyer may permit at its sole discretion", 4)
        else:
            return None, f"unknown condition {cond}", 9, past
        if not ok:
            return Decimal("0.00"), None, None, past  # no violation: neither the fee nor the admin fee is owed
    money_rows = [t for t in mine if t["basis"] in MONEY_BASES]
    if len(money_rows) > 1:
        return None, f"the agreement states {len(money_rows)} rules for {fee_code}", 9, past
    if any(t["basis"] == "discretion" for t in mine):
        return None, "the amount is set at the other side's discretion", 4, past
    if ask:
        return None, ask[0], ask[1], past
    if not money_rows:
        return None, f"no fee schedule for {fee_code}", 9, past
    t = money_rows[0]
    rate = Decimal(t["rate"])
    base = sum((Decimal(ln["base_amount"]) for ln in lines), Decimal(0))
    if t["basis"] == "percent":
        fee = base * rate / 100
    elif t["basis"] == "annual_percent":
        fee = base * rate / 100 * int(lines[0]["days"] or 0) / 365
    elif t["basis"] == "per_document_day":
        fee = rate * int(lines[0]["units"]) * int(lines[0]["days"] or 0)
    else:
        fee = rate
    fee = money(fee)
    if t["max"]:
        fee = min(fee, money(t["max"]))
    admin = [a for a in f["terms"] if a["fee_code"] == "*" and a["basis"] == "flat" and a["version"] in ("all", ver)]
    fee += sum((money(a["rate"]) for a in admin), Decimal(0))
    fee += sum((money(ln["pass_through"]) for ln in lines), Decimal(0))
    return money(fee), None, None, past


def fee_gate(taken, allowed, ask_reason, ask_row, past):
    zero = Decimal("0.00")
    if past and (ask_reason or abs(taken - allowed) > TOLERANCE):
        return "accept", zero, taken, 10
    if ask_reason:
        return "ask", zero, zero, ask_row
    decision, disputed, accepted = gate(taken, allowed, None)
    row = {"accept": 5, "split": 7, "dispute": 7, "ask": 8}[decision]
    return decision, disputed, accepted, row


def check_fee_facts(acct, f, charges):
    """The backup's bases match our records: PO costs, overage and short units, the invoice, rejected units."""
    print(f"{acct.label}: backup against our records")
    inv = acct.yaml["invoice"]
    for c in charges:
        lines = f["backup"].get(c["ref"], [])
        if not check(f"{acct.label}: {c['charge_id']} has backup lines", bool(lines)):
            continue
        for ln in lines:
            if ln["proof_doc"]:
                check(f"{acct.label}: {c['charge_id']} proof {ln['proof_doc']} exists", ln["proof_doc"] in f["texts"])
        p = f["purchases"].get(lines[0]["group"])
        base = sum((money(ln["base_amount"]) for ln in lines), Decimal(0))
        if p is None:
            continue
        if c["code"] == "FN":  # dated by Walmart's notice; a fine's base is the amount it assessed
            check(f"{acct.label}: {c['charge_id']} assessed amount is the charge", base == money(c["amount"]))
            continue
        if c["code"] != "RJ":  # a rejection is dated by Walmart's notice
            check(f"{acct.label}: {c['charge_id']} backup date is PO {p['po']}'s date", lines[0]["on"] == p["written_on"])
        cost = Decimal(p["unit_cost"])
        if c["code"] == "OV":
            want = money((int(p["received_units"]) - int(p["units"])) * cost)
        elif c["code"] == "BO":
            want = money((int(p["units"]) - int(p["received_units"])) * cost)
        elif c["code"] == "RJ":
            want = money(int(lines[0]["units"]) * cost)
            check(f"{acct.label}: {c['charge_id']} rejected goods pass through at price", money(lines[0]["pass_through"]) == want)
        elif base:
            want = money(p["po_cost"])
        else:
            continue
        check(f"{acct.label}: {c['charge_id']} backup base ${base:,} matches PO {p['po']} (${want:,})", base == want)
    for c in charges:
        if c["code"] == "DM":
            base = sum((money(ln["base_amount"]) for ln in f["backup"].get(c["ref"], [])), Decimal(0))
            check(f"{acct.label}: {c['charge_id']} allowance base is the invoice", base == money(inv["expected"]))


def check_fee_account(acct, docs, fees):
    """An account priced by fee schedules (fees/fees.yaml + terms/fee-terms.csv)."""
    y = acct.yaml
    texts = {stem: p.read_text(encoding="utf-8") for stem, (_, p) in docs.items()}
    texts.update(check_fee_contracts(acct, fees))
    terms = acct.rows("terms/fee-terms.csv", FEE_TERM_COLS) or []
    check_fee_terms(acct, terms, texts)

    print(f"{acct.label}: purchases and charges")
    purchases = {r["po"]: r for r in acct.rows("purchases/purchase-orders.csv", required=True) or []}
    for p in purchases.values():
        check(f"{acct.label}: PO {p['po']} units x cost = PO cost",
              money(int(p["units"]) * Decimal(p["unit_cost"])) == money(p["po_cost"]))
        if "invoiced_amount" in p:
            check(f"{acct.label}: PO {p['po']} invoiced units x cost = invoiced amount",
                  money(int(p["invoiced_units"]) * Decimal(p["unit_cost"])) == money(p["invoiced_amount"]))
    start, end = day(y["invoice"]["period_start"]), day(y["invoice"]["period_end"])
    billed = sum((money(p.get("invoiced_amount") or p["po_cost"]) for p in purchases.values()
                  if start <= day(p["received_on"]) <= end), Decimal(0))
    check(f"{acct.label}: invoice = the period's POs as invoiced", billed == money(y["invoice"]["expected"]), billed)
    if y.get("qbo", {}).get("lines"):
        qbo = sum((money(ln["qty"] * Decimal(str(ln["unit_price"]))) for ln in y["qbo"]["lines"]), Decimal(0))
        check(f"{acct.label}: QuickBooks lines sum to the invoice", qbo == money(y["invoice"]["expected"]), qbo)

    charges = acct.rows(f"charges/{y['invoice']['month']}.csv", FEE_CHARGE_COLS) or []
    older = acct.rows(fees["older_charges"], FEE_CHARGE_COLS) if fees.get("older_charges") else []
    every_charge = charges + (older or [])
    ids, refs = Counter(c["charge_id"] for c in every_charge), Counter(c["ref"] for c in every_charge)
    check(f"{acct.label}: charge ids and refs are unique",
          all(n == 1 for n in ids.values()) and all(n == 1 for n in refs.values()))
    codes = fees.get("codes") or {}
    for c in every_charge:
        cid = c["charge_id"]
        check(f"{acct.label}: {cid} code {c['code']} is in fees.yaml codes", c["code"] in codes)
        check(f"{acct.label}: {cid} units x rate = amount",
              money(Decimal(c["units"]) * Decimal(c["rate"])) == money(c["amount"]), c["amount"])
        check(f"{acct.label}: {cid} dates are valid", is_date(c["period_start"]) and is_date(c["period_end"])
              and c["period_start"] <= c["period_end"] and is_date(c["deducted_on"]))
    total = sum((money(c["amount"]) for c in charges), Decimal(0))
    want = money(y["invoice"]["expected"]) - money(y["invoice"]["received"])
    check(f"{acct.label}: the month's charges sum to expected - received (${want:,})", total == want, total)

    backup = defaultdict(list)
    for r in acct.rows("fees/backup.csv") or []:
        backup[r["deduction_ref"]].append(r)
    check(f"{acct.label}: every backup line belongs to a charge", set(backup) <= set(refs), sorted(set(backup) - set(refs)))
    f = {
        "terms": terms, "codes": codes, "backup": backup, "purchases": purchases, "texts": texts,
        "appointments": {r["po"]: r for r in acct.rows("deliveries/appointments.csv", required=False) or []},
        "debits": {r["debit_ref"]: r for r in acct.rows("payments/debit-balances.csv", required=False) or []},
        "as_of": day(fees["as_of"]),
    }
    check_fee_facts(acct, f, every_charge)

    print(f"{acct.label}: expected decisions")
    expected = acct.rows("expected.csv", FEE_EXPECTED_COLS) or []
    by_id = {c["charge_id"]: c for c in every_charge}
    got = Counter(e["charge_id"] for e in expected)
    check(f"{acct.label}: expected.csv covers every charge once",
          set(got) == set(by_id) and all(n == 1 for n in got.values()), sorted(set(by_id) ^ set(got)))
    term_keys = {t["key"] for t in terms}
    tables = {"purchases/purchase-orders.csv": purchases, "fees/backup.csv": backup,
              "deliveries/appointments.csv": f["appointments"], "payments/debit-balances.csv": f["debits"],
              "shipments/documents.csv": {r["po"]: r for r in acct.rows("shipments/documents.csv", required=False) or []}}
    totals = {"disputed": Decimal(0), "accepted": Decimal(0), "asked": Decimal(0)}
    for e in expected:
        c = by_id.get(e["charge_id"])
        if c is None:
            continue
        cid, taken = e["charge_id"], money(c["amount"])
        clauses = [k.strip() for k in e["clause"].split(";") if k.strip()]
        check(f"{acct.label}: {cid} cites clauses in fee-terms.csv", bool(clauses) and set(clauses) <= term_keys,
              set(clauses) - term_keys)
        for s in (x.strip() for x in e["sources"].split(";") if x.strip()):
            if "#" in s:
                rel, key = s.split("#", 1)
                ok = key in tables.get(rel, {})
            else:
                ok = s in texts
            check(f"{acct.label}: {cid} source {s} exists", ok)
        check(f"{acct.label}: {cid} has a why", bool(e["why"].strip()))
        check(f"{acct.label}: {cid} asked={e['asked']} matches decision {e['decision']}",
              (e["asked"] == "yes") == (e["decision"] == "ask"))
        allowed, reason, ask_row, past = fee_allowed(c, f)
        want = fee_gate(taken, allowed, reason, ask_row, past)
        have = (e["decision"], money(e["disputed"]), money(e["accepted"]), int(e["gate_row"]))
        why = reason or (f"allowed ${allowed:,}" if allowed is not None else "")
        check(f"{acct.label}: {cid} {have[0]} {have[1]} / {have[2]} (row {have[3]}) follows from the files ({why})",
              have == want, f"files give {want}")
        if c in charges:
            if e["decision"] == "ask":
                totals["asked"] += taken
            else:
                totals["disputed"] += have[1]
                totals["accepted"] += have[2]
    check(f"{acct.label}: disputed + accepted + asked = the month's charges",
          totals["disputed"] + totals["accepted"] + totals["asked"] == total)
    print(f"  ..   {acct.label}: disputed ${totals['disputed']:,} · accepted ${totals['accepted']:,} · "
          f"asked ${totals['asked']:,}")


# ---------------------------------------------------------------- history detail and the lookback

def plain_rows(acct, rel):
    p = acct.path(rel)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def as_of(y):
    """The day the lookback counts from: the account's payment date, else the invoice period's end + 20 days."""
    paid = (y.get("qbo") or {}).get("payment_date")
    return day(paid) if paid else day(y["invoice"]["period_end"]) + timedelta(PAYMENT_LAG)


def dispute_window(acct, docs, terms):
    """(days, stated): the ops term's window (its quote is checked against the deal here), else 90 days; stated is
    a window the deal states in words when there's no ops term, so the check can show the fallback changes nothing."""
    deal_id = acct.yaml["deal_docs"][0]
    if "dispute_window_days" in terms:
        row = next(t for t in plain_rows(acct, "terms/ops-terms.csv") if t["key"] == "dispute_window_days")
        check(f"{acct.label}: dispute_window_days is quoted from the deal {deal_id}",
              row["source_doc"] == deal_id and row["quote"] in doc_text(docs, deal_id), row["source_doc"])
        return int(terms["dispute_window_days"]), None
    m = re.search(r"within (\d+) days of the remittance date", doc_text(docs, deal_id))
    return DEFAULT_WINDOW, (int(m.group(1)) if m else None)


def promo_for(row, plan):
    """The past promo a PA row claims: the one whose dates overlap its period (preferring one with its products),
    else the latest one that ended before the period (a claim after the end date)."""
    ps, pe, mine = day(row["period_start"]), day(row["period_end"]), products(row["product"])
    hits = [p for p in plan if day(p["starts"]) <= pe and ps <= day(p["ends"])]
    if len(hits) > 1:
        hits = [p for p in hits if products(p["product"]) & mine] or hits
    if not hits:
        before = sorted((p for p in plan if day(p["ends"]) < ps), key=lambda p: p["ends"])
        hits = before[-1:]
    return hits[0] if len(hits) == 1 else None


def lookback(row, earlier, plan, sales, pod, prices, outcome, days, window, tolerance=TOLERANCE):
    """(allowed, wrongly_taken, status) for one past deduction, by the engine's math (allowed_for)."""
    amount = money(row["amount"])
    if row["code"] not in CHECKED_CODES or (row["code"] == "PR" and not prices):
        return None, None, "not_checked"
    if row["code"] == "PA":
        p = promo_for(row, plan)
        if p is None:
            return None, None, "not_checked"
        promo = {"rate": money(p["rate"]), "cap": int(p["cap"]), "starts": day(p["starts"]), "ends": day(p["ends"]),
                 "products": products(p["product"])}
        allowed, _ = allowed_for(row, promo, sales, earlier, pod, prices, {})
    else:
        allowed, _ = allowed_for(row, None, sales, earlier, pod, prices, {})
    if allowed is None:
        return None, None, "not_checked"
    wrong = amount - allowed
    if wrong <= tolerance:
        return allowed, Decimal("0.00"), "fair"
    if outcome == "recovered":
        return allowed, wrong, "settled"
    return allowed, wrong, "past_window" if days > window else "claimable"


def check_lookback(acct, docs, terms, charges, pod, prices):
    print(f"{acct.label}: history detail and lookback")
    y = acct.yaml
    deductions = acct.rows("history/deductions.csv") or []
    plan = acct.rows("history/promo-plan.csv") or []
    sales = acct.rows("history/sales.csv") or []
    hist_pod = acct.rows("history/deliveries.csv") or []
    expected = acct.rows("history/expected-lookback.csv") or []
    remits = plain_rows(acct, "history/remittances.csv")
    invoices = {r["invoice"]: r for r in plain_rows(acct, "history/invoices.csv")}
    current = {c["ref"] for c in charges or []}
    window, stated = dispute_window(acct, docs, terms)
    today = as_of(y)
    print(f"  ..   {acct.label}: as of {today}, dispute window {window} days")

    # Every deduction is taken on a remittance for its month's invoice, and they add up to what it deducted.
    taken_on = defaultdict(Decimal)
    for d in deductions:
        ok = is_date(d["deducted_on"]) and any(
            r["date"] == d["deducted_on"] and r["invoice"] in invoices
            and invoices[r["invoice"]]["date"][:7] == d["month"] for r in remits)
        check(f"{acct.label}: {d['ref']} deducted_on {d['deducted_on']} is a remittance for a {d['month']} invoice", ok)
        taken_on[d["deducted_on"]] += money(d["amount"])
        check(f"{acct.label}: {d['ref']} units x rate = amount",
              bool(d["units"] and d["rate"]) and money(Decimal(d["units"]) * Decimal(d["rate"])) == money(d["amount"]),
              f"{d['units']} x {d['rate']}")
        check(f"{acct.label}: {d['ref']} has a product and a valid period",
              bool(d["product"]) and is_date(d["period_start"]) and is_date(d["period_end"])
              and d["period_start"] <= d["period_end"])
    for r in remits:
        check(f"{acct.label}: deductions taken on {r['date']} sum to its remittance's ${money(r['deducted']):,}",
              taken_on[r["date"]] == money(r["deducted"]), taken_on[r["date"]])

    for p in plan:
        check(f"{acct.label}: past promo {p['promo_id']} has valid dates, rate and cap",
              is_date(p["starts"]) and is_date(p["ends"]) and p["starts"] <= p["ends"] and money(p["rate"]) > 0
              and int(p["cap"]) > 0)
    check(f"{acct.label}: past promo ids are unique", len({p["promo_id"] for p in plan}) == len(plan))
    check(f"{acct.label}: history sales rows are valid", all(
        is_date(s["week_start"]) and is_date(s["week_end"]) and s["week_start"] <= s["week_end"]
        and int(s["total_units"]) >= int(s["promo_units"]) >= 0 for s in sales))
    check(f"{acct.label}: history sales have one row per week and product",
          len({(s["week_start"], s["product"]) for s in sales}) == len(sales))
    for r in hist_pod:
        check(f"{acct.label}: past delivery {r['line_ref']} received <= shipped and a valid date",
              0 <= int(r["received_units"]) <= int(r["shipped_units"]) and is_date(r["received_at"]))
    lines = {r["line_ref"]: r for r in [*(pod or []), *hist_pod]}
    check(f"{acct.label}: past delivery line_refs are unique and not in deliveries/pod.csv",
          len(lines) == len(pod or []) + len(hist_pod))

    past = [d for d in deductions if d["ref"] not in current]
    for d in past:
        ref = d["ref"]
        if d["code"] == "PA":
            promo = promo_for(d, plan)
            check(f"{acct.label}: {ref} claims a promo in history/promo-plan.csv", promo is not None)
            ps, pe = day(d["period_start"]), day(d["period_end"])
            spans = sorted({(day(s["week_start"]), day(s["week_end"])) for s in sales
                            if ps <= day(s["week_start"]) and day(s["week_end"]) <= pe})
            tiled = bool(spans) and spans[0][0] == ps and spans[-1][1] == pe and all(
                b[0] == a[1] + timedelta(1) for a, b in zip(spans, spans[1:]))
            check(f"{acct.label}: {ref} period {ps} to {pe} is covered week by week in history/sales.csv", tiled)
            if promo is not None:
                start = day(promo["starts"])
                before = {day(s["week_start"]) for s in sales if start <= day(s["week_start"]) < ps}
                need = {start + timedelta(7 * i) for i in range((ps - start).days // 7)}
                check(f"{acct.label}: {ref} has the promo's earlier weeks for the cap", need <= before,
                      sorted(need - before))
        if d["code"] in ("SH", "PR"):
            row = lines.get(d["line_ref"])
            if check(f"{acct.label}: {ref} line_ref {d['line_ref'] or '(blank)'} is a delivery line", row is not None):
                check(f"{acct.label}: {ref} product matches delivery {d['line_ref']}", row["product"] == d["product"])
                check(f"{acct.label}: {ref} delivery was in {d['month']}, before the deduction",
                      row["received_at"][:7] == d["month"] and row["received_at"] <= d["deducted_on"])
                if d["code"] == "PR":
                    check(f"{acct.label}: {ref} delivery has one agreed price that day",
                          not prices or agreed_price(prices, row["product"], day(row["received_at"])) is not None)
        elif d["code"] != "PA":
            check(f"{acct.label}: {ref} {d['code']} row has no line_ref", not d["line_ref"])

    # expected-lookback.csv: one row per past deduction, each recomputed.
    got = Counter(e["ref"] for e in expected)
    check(f"{acct.label}: expected-lookback.csv covers every past deduction once",
          set(got) == {d["ref"] for d in past} and all(n == 1 for n in got.values()),
          sorted(set(got) ^ {d["ref"] for d in past}))
    by_ref = {d["ref"]: d for d in past}
    order = sorted(past, key=lambda d: (d["deducted_on"], d["ref"]))
    totals = defaultdict(Decimal)
    counts = Counter()
    differs = []
    for e in expected:
        d = by_ref.get(e["ref"])
        if d is None:
            continue
        earlier = [x for x in order[:order.index(d)] if x["code"] == d["code"] and x["outcome"] != "recovered"]
        days = (today - day(d["deducted_on"])).days
        allowed, wrong, status = lookback(d, earlier, plan, sales, list(lines.values()), prices, d["outcome"], days,
                                          window)
        have = (money(e["allowed"]) if e["allowed"] else None, money(e["wrongly_taken"]) if e["wrongly_taken"] else None,
                e["status"])
        check(f"{acct.label}: lookback {e['ref']} status '{e['status']}' is known and has a why",
              e["status"] in LOOKBACK_STATUSES and bool(e["why"].strip()))
        check(f"{acct.label}: lookback {e['ref']} recomputes ({status}, allowed {allowed}, wrongly taken {wrong})",
              have == (allowed, wrong, status), f"file has {have}")
        if status == "settled":
            check(f"{acct.label}: lookback {e['ref']} settled: recovered = wrongly taken",
                  money(d["recovered"]) == wrong, d["recovered"])
        if status == "fair":
            check(f"{acct.label}: lookback {e['ref']} fair: nothing was recovered", d["outcome"] != "recovered")
        if stated and stated != window and status in ("claimable", "past_window"):
            alt = "past_window" if days > stated else "claimable"
            if alt != status:
                differs.append(e["ref"])
        counts[status] += 1
        if wrong:
            totals[status] += wrong
    if stated and stated != window:
        check(f"{acct.label}: the deal's {stated}-day window gives the same statuses as the {window}-day fallback",
              not differs, differs)
    checked = sum(counts[s] for s in ("claimable", "past_window", "settled", "fair"))
    wrong_n = sum(counts[s] for s in ("claimable", "past_window", "settled"))
    print(f"  ..   {acct.label}: {len(past)} past deductions, {checked} checked, {wrong_n} not allowed "
          f"({100 * wrong_n / max(len(past), 1):.0f}%) · claimable ${totals['claimable']:,} ({counts['claimable']}) · "
          f"past window ${totals['past_window']:,} ({counts['past_window']}) · settled ${totals['settled']:,} "
          f"({counts['settled']}) · fair {counts['fair']} · not checked {counts['not_checked']}")


# ---------------------------------------------------------------- one account

def check_account(acct):
    print(f"\n== {acct.id}")
    yaml_path = acct.dir / "account.yaml"
    if yaml_path.exists():
        acct.yaml = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    docs = acct.docs()
    if yaml_path.exists():
        check_yaml(acct, docs)
        check_docs(acct, docs)
    elif acct.id != PEAK_BAR:
        check(f"{acct.label}: account.yaml exists", False)
        return docs, set()

    fees_path = acct.dir / "fees" / "fees.yaml"
    if acct.yaml and fees_path.exists() and (acct.dir / "terms" / "fee-terms.csv").exists():
        check_fee_account(acct, docs, yaml.safe_load(fees_path.read_text(encoding="utf-8")) or {})
        return docs, set()

    month = acct.yaml["invoice"]["month"] if acct.yaml else "march"
    charges = acct.rows(f"charges/{month}.csv", CHARGE_COLS)
    prior = acct.rows("payments/prior.csv")
    if not acct.yaml:  # Peak Bar before its files move: history only
        return docs, check_history(acct, charges, prior)

    fee_account = acct.fees is not None  # its promo is counted on purchase orders, not store sales
    sales = acct.rows("sales/store-sales.csv", required=not fee_account)
    plan_rows = acct.rows("plan/promo-plan.csv", required=not fee_account)
    codes = {c["code"] for c in charges or []}
    needs_ops = bool(codes & {"SH", "PR", "SP"})
    pod = acct.rows("deliveries/pod.csv", required=needs_ops)
    prices = acct.rows("pricing/price-list.csv", required=needs_ops)
    term_rows = acct.rows("terms/ops-terms.csv", required=needs_ops)
    expected = acct.rows("expected.csv")

    terms = check_terms(acct, docs, term_rows) if term_rows is not None else {}
    if prices is not None:
        check_prices(acct, docs, prices)
    plan = check_plan(acct, docs, plan_rows, terms) if plan_rows is not None else None
    if sales is not None:
        print(f"{acct.label}: sales")
        check(f"{acct.label}: total_units >= promo_units on every sales row",
              all(int(s["total_units"]) >= int(s["promo_units"]) >= 0 for s in sales))
        check(f"{acct.label}: sales weeks are valid", all(is_date(s["week_start"]) and is_date(s["week_end"])
                                                          and s["week_start"] <= s["week_end"] for s in sales))
    if charges is not None:
        check_charges(acct, charges, pod, prices, sales, plan)
        if pod is not None:
            check_deliveries(acct, pod, prices, charges)
        if expected is not None:
            recompute = None
            if term_rows is not None and None not in (plan, sales, prior, pod, prices):
                def recompute(c):
                    return allowed_for(c, plan, sales, prior, pod, prices, terms)
            older = acct.rows(acct.fees["older_charges"], CHARGE_COLS) if fee_account and acct.fees.get(
                "older_charges") else []
            check_expected(acct, charges + (older or []), expected, recompute)
    invoices = check_history(acct, charges, prior)
    if not fee_account:  # fee-schedule accounts' deductions are fees counted on POs: no lookback math for them yet
        check_lookback(acct, docs, terms, charges, pod, prices)
    return docs, invoices


def main():
    folders = sorted(p for p in ACCOUNTS.iterdir() if p.is_dir()) if ACCOUNTS.exists() else []
    check("data/accounts/ has account folders", bool(folders))
    stems, starts, invoice_ids = defaultdict(list), defaultdict(list), defaultdict(list)
    for folder in folders:
        acct = Account(folder)
        docs, history_invoices = check_account(acct)
        for stem in docs:
            stems[stem].append(acct.id)
        for inv in history_invoices:
            invoice_ids[inv].append(acct.id)
        if acct.yaml and "dispute_start" in acct.yaml:
            starts[acct.yaml["dispute_start"]].append(acct.id)

    print("\n== across accounts")
    legacy = {p.stem for sub, ext in DOC_DIRS.items() for p in (DATA / sub).glob(f"*{ext}")}
    clash = {s: ids for s, ids in stems.items() if len(ids) > 1 or (s in legacy and ids != [PEAK_BAR])}
    check("document stems are unique across accounts", not clash, clash)
    check("dispute_start is different for every account", all(len(v) == 1 for v in starts.values()), dict(starts))
    check("invoice numbers are unique across accounts", all(len(v) == 1 for v in invoice_ids.values()),
          {k: v for k, v in invoice_ids.items() if len(v) > 1})

    print()
    if failures:
        print(f"{len(failures)} check(s) failed, {passed} passed:")
        for name in failures:
            print(f"  - {name}")
        sys.exit(1)
    print(f"All {passed} checks passed.")


if __name__ == "__main__":
    main()
