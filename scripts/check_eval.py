"""Check data/eval/: 30 cases, the 12 / 12 / 6 mix, and expected amounts on every row.

Run: python scripts/check_eval.py
Exits 1 and lists every failure if anything is off. Standard library only.
"""

import csv
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

EVAL = Path(__file__).resolve().parent.parent / "data" / "eval"

CHARGE_COLS = ["case_id", "ref", "code", "description", "product", "units", "rate", "amount", "period_start",
               "period_end", "deal_products", "deal_rate", "deal_start", "deal_end", "deal_cap", "fee_max",
               "units_before", "prior_payment", "doc_sender", "doc_text", "notice_days", "saved_rule", "clause_text"]
KEY_COLS = ["case_id", "expected_decision", "expected_disputed", "expected_accepted", "reason"]

# "split" is a dispute where part of the charge is allowed (same as C1 in the demo)
BUCKET = {"dispute": "dispute", "split": "dispute", "accept": "accept", "ask": "ask"}
MIX = {"dispute": 12, "accept": 12, "ask": 6}

# reason tag -> (bucket, count), from docs/design.md "Proof, tests and responsible design"
CATEGORIES = {
    "rate_over": ("dispute", 3),
    "duplicate": ("dispute", 3),
    "over_cap": ("dispute", 2),
    "product_not_covered": ("dispute", 2),
    "outside_dates": ("dispute", 1),
    "unsigned_claim": ("dispute", 1),
    "exact_match": ("accept", 5),
    "broker_extension": ("accept", 3),
    "under_charge": ("accept", 1),
    "rule_covered_fee": ("accept", 2),
    "within_tolerance": ("accept", 1),
    "discretion_no_rule": ("ask", 3),
    "readers_disagree": ("ask", 2),
    "over_5000": ("ask", 1),
}

APPROVED_SENDERS = {"dana@peakbar.example", "jordan@peakbar-broker.example"}

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


def load(name):
    path = EVAL / name
    if not path.exists():
        check(f"{name} exists", False)
        return [], []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames or [], list(reader)


def money(s):
    try:
        d = Decimal(s)
    except (InvalidOperation, TypeError):
        return None
    return d if d == d.quantize(Decimal("0.01")) else None


def main():
    print("Files")
    ccols, charges = load("charges-30.csv")
    kcols, key = load("answer-key.csv")
    check("charges-30.csv columns", ccols == CHARGE_COLS, ccols)
    check("answer-key.csv columns", kcols == KEY_COLS, kcols)
    check("outside-deal.md exists (placeholder until a non-teammate writes it)", (EVAL / "outside-deal.md").exists())
    check("charges-30.csv has 30 cases", len(charges) == 30, len(charges))
    check("answer-key.csv has 30 cases", len(key) == 30, len(key))
    cids = [r["case_id"] for r in charges]
    kids = [r["case_id"] for r in key]
    check("case ids unique", len(set(cids)) == len(cids) and len(set(kids)) == len(kids))
    check("same case ids in both files", set(cids) == set(kids))
    check("charge refs unique", len({r["ref"] for r in charges}) == len(charges))
    check("charges file holds no answers", not any(c in ccols for c in ("expected_decision", "reason")))

    print("Mix")
    decisions = [r["expected_decision"] for r in key]
    check("every decision is dispute/split/accept/ask", all(d in BUCKET for d in decisions), set(decisions))
    buckets = Counter(BUCKET.get(d) for d in decisions)
    for b, n in MIX.items():
        check(f"{n} {b}", buckets[b] == n, buckets[b])
    tags = Counter(r["reason"].split(":", 1)[0] for r in key)
    for tag, (bucket, n) in CATEGORIES.items():
        check(f"{n} x {tag} ({bucket})", tags[tag] == n, tags[tag])
    check("no unknown reason tags", set(tags) <= set(CATEGORIES), set(tags) - set(CATEGORIES))
    check("each reason tag sits in its bucket",
          all(BUCKET.get(r["expected_decision"]) == CATEGORIES.get(r["reason"].split(":", 1)[0], (None,))[0]
              for r in key))

    print("Expected amounts")
    by_id = {r["case_id"]: r for r in charges}
    for r in key:
        cid, dec = r["case_id"], r["expected_decision"]
        disp, acc = money(r["expected_disputed"]), money(r["expected_accepted"])
        amt = money(by_id.get(cid, {}).get("amount"))
        if disp is None or acc is None or amt is None:
            check(f"{cid} has amounts to the cent", False, r)
            continue
        if dec == "ask":
            ok = disp == 0 and acc == 0
        elif dec == "split":
            ok = disp > 0 and acc > 0 and disp + acc == amt
        elif dec == "dispute":
            ok = disp == amt and acc == 0
        else:
            ok = disp == 0 and acc == amt
        check(f"{cid} {dec}: disputed {disp} + accepted {acc} vs taken {amt}", ok)

    print("Case setup")
    for r in charges:
        tag = next((k["reason"].split(":", 1)[0] for k in key if k["case_id"] == r["case_id"]), "")
        cid = r["case_id"]
        if tag == "broker_extension":
            check(f"{cid} extension comes from an approved sender", r["doc_sender"] in APPROVED_SENDERS)
        if tag == "unsigned_claim":
            check(f"{cid} claim comes from a non-approved sender",
                  r["doc_sender"] and r["doc_sender"] not in APPROVED_SENDERS)
        if tag == "duplicate":
            check(f"{cid} names a prior payment", r["prior_payment"].count(":") == 5)
        if tag in ("rule_covered_fee", "discretion_no_rule"):
            check(f"{cid} fee clause uses discretion", "discretion" in r["clause_text"] and r["code"] == "DF")
            check(f"{cid} saved rule {'set' if tag == 'rule_covered_fee' else 'empty'}",
                  bool(r["saved_rule"]) == (tag == "rule_covered_fee"))
            check(f"{cid} has notice days", r["notice_days"].isdigit())
        if tag == "readers_disagree":
            check(f"{cid} has vague clause text", bool(r["clause_text"]))
        if tag == "over_5000":
            check(f"{cid} taken over $5,000", money(r["amount"]) > 5000)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed, {passed} passed:")
        for name in failures:
            print(f"  - {name}")
        sys.exit(1)
    print(f"All {passed} checks passed.")


if __name__ == "__main__":
    main()
