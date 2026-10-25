"""Check every number and fixed wording in Peak Bar's data (data/accounts/peak-bar/) against data/CLAUDE.md.

Run: python scripts/check_data.py
Exits 1 and lists every failure if anything is off. Standard library only.
"""

import csv
import email
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "accounts" / "peak-bar"

INVOICED = Decimal("48200.00")
PAID = Decimal("41350.00")
TAKEN = Decimal("6850.00")
DISPUTED = Decimal("4120.00")
ACCEPTED = Decimal("2730.00")
QUESTIONS = 1

SPRING_CLAUSES = [
    "Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and Peak Bar Chocolate "
    "sold between March 1 and March 31, 2026.",
    "The promotional allowance applies to a maximum of 5,000 units in total.",
    "Northmart may charge a display fee of up to $1,500 per month at its discretion, with written notice to Supplier.",
]

MARCH_CHARGES = [
    # charge_id, ref, code, product, units, rate, amount, period_start, period_end
    ("C1", "NM-2229", "PA", "Original+Chocolate", 1200, "1.50", "1800.00", "2026-03-01", "2026-03-07"),
    ("C2", "NM-2231", "PA", "Original+Chocolate", 980, "1.00", "980.00", "2026-03-08", "2026-03-14"),
    ("C3", "NM-2240", "PA", "Original+Chocolate", 330, "1.00", "330.00", "2026-04-01", "2026-04-07"),
    ("C4", "NM-2236", "PA", "Original+Chocolate", 1540, "1.00", "1540.00", "2026-03-22", "2026-03-31"),
    ("C5", "NM-2237", "PA", "Mint", 1000, "1.00", "1000.00", "2026-03-01", "2026-03-31"),
    ("C6", "NM-2238", "DF", "none", 1, "1200.00", "1200.00", "2026-03-01", "2026-03-31"),
]

# charge_id -> (decision, disputed, accepted)
EXPECTED = {
    "C1": ("split", "600.00", "1200.00"),
    "C2": ("dispute", "980.00", "0.00"),
    "C3": ("accept", "0.00", "330.00"),
    "C4": ("dispute", "1540.00", "0.00"),
    "C5": ("dispute", "1000.00", "0.00"),
    "C6": ("ask", "0.00", "1200.00"),  # owner answers, saved rule accepts it
}

APRIL_CHARGES = [
    ("A1", "NM-2301", "DF", "1200.00", "notices/display-fee-2026-04-12.md", 18, "accept"),
    ("A2", "NM-2302", "DF", "800.00", "notices/display-fee-2026-04-25.md", 5, "dispute"),
]

WEEKLY_PROMO = [
    ("2026-03-01", "2026-03-07", 1200),
    ("2026-03-08", "2026-03-14", 980),
    ("2026-03-15", "2026-03-21", 2820),
    ("2026-03-22", "2026-03-31", 1540),
    ("2026-04-01", "2026-04-07", 330),
]

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


def text(rel):
    path = DATA / rel
    if not path.exists():
        check(f"{rel} exists", False)
        return ""
    return path.read_text(encoding="utf-8")


def rows(rel):
    path = DATA / rel
    if not path.exists():
        check(f"{rel} exists", False)
        return [], []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or [], list(reader)


def money(s):
    return Decimal(s).quantize(Decimal("0.01"))


def days_to_month_end(d):
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return (nxt - d).days - 1


def check_totals():
    print("Invoice and payment")
    check("invoice - paid = taken", INVOICED - PAID == TAKEN, f"{INVOICED} - {PAID}")
    check("disputed + accepted = taken", DISPUTED + ACCEPTED == TAKEN)


def check_deals():
    print("Deals")
    spring = text("deals/spring-promo.md")
    for clause in SPRING_CLAUSES:
        check(f"spring-promo.md has clause '{clause[:45]}...'", clause in spring)
    for label in ("3.1 Supplier will fund", "3.2 The promotional allowance", "5.4 Northmart may charge"):
        check(f"spring-promo.md numbers clause {label[:3]}", label in spring)
    check("spring-promo.md carries no fictional label", "FICTIONAL" not in spring)

    amend = text("deals/amendment-1.md")
    check("amendment-1.md raises cap to 6,000", "maximum of 6,000 units" in amend)
    check("amendment-1.md signed by Dana Okafor", "Dana Okafor" in amend)
    check("amendment-1.md signed by Northmart category manager", "Category Manager" in amend)

    summer = text("deals/summer-draft.md")
    fee = next((ln for ln in summer.splitlines() if "display fee" in ln and "discretion" in ln), "")
    check("summer-draft.md has discretion display fee", bool(fee))
    check("summer-draft.md display fee has no notice period", fee and "notice" not in fee.lower(), fee)
    cap = next((ln for ln in summer.splitlines() if "maximum of" in ln and "units" in ln), "")
    check("summer-draft.md has a unit cap", bool(cap))
    check("summer-draft.md never mentions extensions", "extend" not in summer.lower() and "extension" not in summer.lower())
    check("summer-draft.md names products in prose", "Peak Bar Original and Peak Bar Chocolate" in summer)
    check("summer-draft.md has no item numbers",
          not any(w in summer.lower() for w in ("sku", "item no", "item number", "upc")))


def check_emails():
    print("Emails")
    cases = [
        ("emails/broker-2026-03-28.eml", "jordan@peakbar-broker.example", "28 Mar 2026",
         "Northmart asked to extend Spring Promo through April 7, same terms, up to 500 additional units. Approved."),
        ("emails/northmart-2026-03-30.eml", "deductions@northmart.example", "30 Mar 2026",
         "Per our call, the Spring Promo rate is $1.50 per unit."),
    ]
    for rel, sender, day, body in cases:
        raw = text(rel)
        if not raw:
            continue
        msg = email.message_from_string(raw)
        check(f"{rel} from {sender}", sender in (msg["From"] or ""))
        check(f"{rel} dated {day}", day in (msg["Date"] or ""))
        check(f"{rel} body word for word", body in msg.get_payload())


def check_notices():
    print("Notices")
    march = text("notices/display-fee-2026-03-11.md")
    check("March notice dated March 11, 2026", "March 11, 2026" in march)
    check("March notice is $1,200.00 for month ending March 31", "$1,200.00" in march and "March 31, 2026" in march)
    check("March notice gives 20 days", days_to_month_end(date(2026, 3, 11)) == 20 and "20 days" in march)
    check("March notice names charge ref NM-2238 (C6)", "**Charge ref:** NM-2238" in march)


def check_sales():
    print("Sales")
    cols, data = rows("sales/store-sales.csv")
    check("store-sales.csv columns", cols == ["week_start", "week_end", "product", "promo_units", "total_units"], cols)
    for start, end, want in WEEKLY_PROMO:
        got = sum(int(r["promo_units"]) for r in data if r["week_start"] == start and r["week_end"] == end
                  and r["product"] in ("Peak Bar Original", "Peak Bar Chocolate"))
        check(f"promo units {start} to {end} = {want:,}", got == want, got)
    mint = sum(int(r["promo_units"]) for r in data if r["product"] == "Peak Bar Mint" and r["week_start"].startswith("2026-03"))
    check("Mint March promo units = 1,000", mint == 1000, mint)
    running = sum(w for s, _, w in WEEKLY_PROMO if s <= "2026-03-15")
    check("running total through week 3 = 5,000 (cap reached)", running == 5000, running)
    check("total_units >= promo_units on every row", all(int(r["total_units"]) >= int(r["promo_units"]) for r in data))
    known = {"Peak Bar Original", "Peak Bar Chocolate", "Peak Bar Mint"}
    check("only known products in sales", all(r["product"] in known for r in data))


def check_prior():
    print("Prior payments")
    cols, data = rows("payments/prior.csv")
    check("prior.csv columns",
          cols == ["ref", "paid_on", "promo_id", "product", "period_start", "period_end", "units", "amount"], cols)
    want = [
        ("NM-2178", "2026-03-14", "SPRING-26", "Original+Chocolate", "2026-03-08", "2026-03-14", 980, "980.00"),
        ("NM-2201", "2026-03-28", "SPRING-26", "Original+Chocolate", "2026-03-15", "2026-03-21", 2820, "2820.00"),
    ]
    got = [(r["ref"], r["paid_on"], r["promo_id"], r["product"], r["period_start"], r["period_end"],
            int(r["units"]), str(money(r["amount"]))) for r in data]
    check("prior.csv rows match", got == want, got)


def check_march():
    print("March charges")
    cols, data = rows("charges/march.csv")
    check("march.csv columns", cols == ["charge_id", "ref", "code", "description", "product", "units",
                                                  "rate", "amount", "period_start", "period_end"], cols)
    got = [(r["charge_id"], r["ref"], r["code"], r["product"], int(r["units"]), str(money(r["rate"])),
            str(money(r["amount"])), r["period_start"], r["period_end"]) for r in data]
    check("march.csv rows match", got == MARCH_CHARGES, got)
    for r in data:
        check(f"{r['charge_id']} units x rate = amount",
              money(Decimal(r["units"]) * Decimal(r["rate"])) == money(r["amount"]))
    total = sum((money(r["amount"]) for r in data), Decimal("0"))
    check("March charges sum to $6,850.00", total == TAKEN, total)

    print("Expected decisions")
    by_id = {r["charge_id"]: r for r in data}
    for cid, (decision, disp, acc) in EXPECTED.items():
        amt = money(by_id[cid]["amount"]) if cid in by_id else None
        check(f"{cid} {decision}: disputed {disp} + accepted {acc} = amount", amt == money(disp) + money(acc), amt)
    disputed = sum((money(d) for _, d, _ in EXPECTED.values()), Decimal("0"))
    accepted = sum((money(a) for _, _, a in EXPECTED.values()), Decimal("0"))
    check("disputed total = $4,120.00", disputed == DISPUTED, disputed)
    check("accepted total = $2,730.00", accepted == ACCEPTED, accepted)
    check("exactly 1 question", sum(1 for d, _, _ in EXPECTED.values() if d == "ask") == QUESTIONS)

    print("Decisions follow from the data")
    _, plan = rows("plan/promo-plan.csv")
    _, prior = rows("payments/prior.csv")
    deal_rate = Decimal(plan[0]["rate"]) if plan else Decimal("0")
    cap = int(plan[0]["cap"]) if plan else 0
    c1 = by_id.get("C1", {})
    if c1:
        over = money(Decimal(c1["units"]) * (Decimal(c1["rate"]) - deal_rate))
        check("C1 rate over deal: dispute = units x (1.50 - 1.00) = 600", over == money(EXPECTED["C1"][1]), over)
    c2 = by_id.get("C2", {})
    dup = [p for p in prior if c2 and p["period_start"] == c2["period_start"] and p["period_end"] == c2["period_end"]
           and p["units"] == c2["units"]]
    check("C2 duplicates prior payment NM-2178", len(dup) == 1 and dup[0]["ref"] == "NM-2178")
    c3 = by_id.get("C3", {})
    check("C3 inside broker extension (Apr 1-7, <= 500 units)",
          c3 and c3["period_start"] >= "2026-04-01" and c3["period_end"] <= "2026-04-07" and int(c3["units"]) <= 500)
    before_w4 = sum(w for s, _, w in WEEKLY_PROMO if s < "2026-03-22")
    check("C4 over cap: 5,000 used before week 4", before_w4 >= cap == 5000)
    covered = min(int(by_id["C4"]["units"]), 6000 - before_w4) if "C4" in by_id else 0
    check("C4 with amendment-1: $540 disputed + $1,000 accepted",
          covered == 1000 and int(by_id["C4"]["units"]) - covered == 540)
    plan_products = plan[0]["product"] if plan else ""
    check("C5 Mint not in plan", "Mint" not in plan_products)
    check("C6 display fee within $1,500 cap", money(by_id["C6"]["amount"]) <= Decimal("1500") if "C6" in by_id else False)


def check_april():
    print("April charges")
    cols, data = rows("charges/april.csv")
    check("april.csv columns", cols == ["charge_id", "ref", "code", "description", "product", "units",
                                                  "rate", "amount", "period_start", "period_end"], cols)
    by_id = {r["charge_id"]: r for r in data}
    for cid, ref, code, amount, notice_rel, days, decision in APRIL_CHARGES:
        r = by_id.get(cid)
        check(f"{cid} {ref} {code} ${amount}",
              r is not None and r["ref"] == ref and r["code"] == code and money(r["amount"]) == money(amount))
        notice = text(notice_rel)
        d = date.fromisoformat(Path(notice_rel).stem[-10:])
        check(f"{cid} notice gives {days} days ({decision} under Rule #1)",
              days_to_month_end(d) == days and f"{days} days" in notice and ref in notice)


def check_plan():
    print("Promo plan")
    cols, data = rows("plan/promo-plan.csv")
    check("promo-plan.csv columns", cols == ["promo_id", "product", "rate", "starts", "ends", "cap"], cols)
    want = [("SPRING-26", "Peak Bar Original; Peak Bar Chocolate", "1.00", "2026-03-01", "2026-03-31", "5000")]
    got = [(r["promo_id"], r["product"], str(money(r["rate"])), r["starts"], r["ends"], r["cap"]) for r in data]
    check("promo-plan.csv row matches", got == want, got)


def main():
    for step in (check_totals, check_deals, check_emails, check_notices, check_sales, check_prior,
                 check_march, check_april, check_plan):
        step()
    print()
    if failures:
        print(f"{len(failures)} check(s) failed, {passed} passed:")
        for name in failures:
            print(f"  - {name}")
        sys.exit(1)
    print(f"All {passed} checks passed.")


if __name__ == "__main__":
    main()
