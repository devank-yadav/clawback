"""Eval harness (F12): run the 30 planted charges in data/eval/ and score them against the answer key.

Run: make eval   (or: python eval/run.py [--data DIR] [--json] [--out FILE | --no-save])

Each run saves its summary to eval/latest.json (gitignored); GET /eval/latest serves it to the scoreboard.

Mode today is "engine": the reading and investigating are stood in by the case row itself (the deal terms the
row states, a reader disagreement where the key says readers disagree, a strong finding everywhere), so the
score measures the math engine and the decision gate alone. The live mode, with the Deal Reader and the
Investigator in the loop, plugs in at build_case() once those agents land; the scoring stays the same.

Metrics, from docs/design.md "Proof, tests and responsible design": correct decisions out of 30, correct
amounts to the cent, wrong automatic actions (target 0) and unnecessary questions.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.engine.allowed import compute_allowed, split_products  # noqa: E402
from api.engine.gate import decide  # noqa: E402
from api.engine.policy import load_policy  # noqa: E402
from api.engine.types import (  # noqa: E402
    Charge,
    DecisionKind,
    Finding,
    PriorPayment,
    Rule,
    SalesWeek,
    Term,
    TermStatus,
    TermType,
    money,
)

DEFAULT_DATA = Path(os.environ.get("CLAWBACK_DATA_DIR", ROOT / "data"))
LATEST = ROOT / "eval" / "latest.json"  # the newest summary, for GET /eval/latest
COUNTERPARTY = "Northmart"
ACTS = {DecisionKind.DISPUTE, DecisionKind.SPLIT, DecisionKind.ACCEPT}  # automatic actions; Ask and Skip are not

# Rule #1 as data/CLAUDE.md states it. Cases whose saved_rule is R1 run with it saved; the rest with no rules.
RULE_1 = Rule(
    id="R1",
    pattern_text="Display fee charged at the distributor's discretion with written notice",
    term_type=TermType.FEE_DISCRETION,
    counterparty=COUNTERPARTY,
    condition="notice_days >= 14",
    decision=DecisionKind.ACCEPT,
    else_decision=DecisionKind.DISPUTE,
)
SAVED_RULES = {"R1": RULE_1}


@dataclass
class Case:
    id: str
    charge: Charge
    terms: list[Term]
    sales: list[SalesWeek]
    priors: list[PriorPayment]
    rules: list[Rule]
    finding: Finding
    tag: str  # the answer key's reason tag, e.g. rate_over


@dataclass
class Expected:
    decision: DecisionKind
    disputed: Decimal
    accepted: Decimal
    reason: str


@dataclass
class Result:
    case_id: str
    tag: str
    expected: Expected
    decision: DecisionKind
    disputed: Decimal
    accepted: Decimal
    gate_row: int
    reason: str
    verdict: str = ""  # correct · wrong_action · unnecessary_question · wrong_amount · other
    notes: list[str] = field(default_factory=list)


def _d(value: str) -> date:
    return date.fromisoformat(value)


def _is_approved(sender: str, policy) -> bool:
    return sender.strip().lower() in {s.lower() for s in policy.approved_amendment_senders}


def build_case(row: dict[str, str], key: dict[str, str], policy) -> Case:
    """One eval row -> the engine's inputs. Everything an agent would produce comes from the row."""
    cid = row["case_id"]
    tag = key["reason"].split(":", 1)[0].strip()
    start, end = _d(row["period_start"]), _d(row["period_end"])
    products = () if row["product"].strip().lower() == "none" else split_products(row["product"])
    notice = end - timedelta(days=int(row["notice_days"])) if row["notice_days"] else None
    charge = Charge(cid, row["ref"], row["code"], row["description"], products, int(row["units"]),
                    money(row["rate"]), money(row["amount"]), start, end, COUNTERPARTY, notice)

    clause = row["clause_text"]
    # The key says the two readers could not agree on this wording: stand in for that with a disputed term.
    disagree = tag == "readers_disagree"
    deal_start, deal_end = row["deal_start"], row["deal_end"]
    terms: list[Term] = []
    if row["code"] == "PA":
        status = TermStatus.DISPUTED if disagree else TermStatus.VERIFIED
        rate = row["deal_rate"] or "0"
        scope = split_products(row["deal_products"]) if row["deal_products"] else ()
        terms += [
            Term(f"{cid}-rate", TermType.PROMO_RATE, {"rate": rate}, clause, _d(deal_start), _d(deal_end), status=status),
            Term(f"{cid}-scope", TermType.PRODUCT_SCOPE, {"products": list(scope)}, clause, status=status),
            Term(f"{cid}-dates", TermType.DATE_RANGE, {"start": deal_start, "end": deal_end}, clause),
        ]
        if row["deal_cap"]:
            terms.append(Term(f"{cid}-cap", TermType.UNIT_CAP, {"max_units": int(row["deal_cap"])}, clause))
        if row["doc_text"]:
            # A change by email: the dates come from the charge it claims to cover, extra units from the case.
            terms.append(Term(
                f"{cid}-email", TermType.AMENDMENT, {"extra_units": _extra_units(row["doc_text"], int(row["units"]))},
                row["doc_text"], _d(deal_end) + timedelta(days=1), end,
                source_doc_id=f"{cid}-email", source_approved=_is_approved(row["doc_sender"], policy),
            ))
    else:
        terms.append(Term(f"{cid}-fee", TermType.FEE_DISCRETION, {"max_fee": row["fee_max"] or "0"}, clause,
                          discretion=True))

    sales: list[SalesWeek] = []
    if row["code"] == "PA":
        # Promoted units already sold under this deal before the charge's period, then the charge's own units.
        before = int(row["units_before"] or 0)
        if before:
            day0 = _d(deal_start)
            sales.append(SalesWeek(day0, min(start - timedelta(days=1), _d(deal_end)), products[0] if products else "", before))
        per = _split_units(int(row["units"]), products)
        sales += [SalesWeek(start, end, p, u) for p, u in per]

    priors: list[PriorPayment] = []
    if row["prior_payment"]:
        ref, paid_on, p_start, p_end, units, amount = row["prior_payment"].split(":")
        priors.append(PriorPayment(ref, _d(paid_on), "EVAL", products, _d(p_start), _d(p_end), int(units), money(amount)))

    rules = [SAVED_RULES[r] for r in row["saved_rule"].split(";") if r.strip() in SAVED_RULES]
    finding = Finding(cid, Decimal("0.95"), (f"{cid}-deal", f"{cid}-sales"), independent_sources=2, comeback_answered=True)
    return Case(cid, charge, terms, sales, priors, rules, finding, tag)


def _extra_units(text: str, fallback: int) -> int:
    """'up to 500 additional units' / 'capped at 500 more units' -> 500. The Deal Reader does this live."""
    m = re.search(r"(\d[\d,]*)\s+(?:additional|more)\s+units", text)
    return int(m.group(1).replace(",", "")) if m else fallback


def _split_units(units: int, products: tuple[str, ...]) -> list[tuple[str, int]]:
    """Put the charge's units on its products (all on the first; the engine only sums them)."""
    if not products:
        return []
    return [(products[0], units)] + [(p, 0) for p in products[1:]]


def load(data_dir: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    with open(data_dir / "eval" / "charges-30.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    with open(data_dir / "eval" / "answer-key.csv", newline="") as f:
        key = {r["case_id"]: r for r in csv.DictReader(f)}
    return rows, key


def score(case: Case, expected: Expected, policy) -> Result:
    allowance = compute_allowed(case.charge, case.terms, case.sales, case.priors)
    d = decide(case.charge, allowance, case.finding, policy, case.rules)
    r = Result(case.id, case.tag, expected, d.kind, d.disputed, d.accepted, d.gate_row, d.reason)

    same_kind = d.kind == expected.decision
    same_amounts = d.disputed == expected.disputed and d.accepted == expected.accepted
    if same_kind and same_amounts:
        r.verdict = "correct"
    elif expected.decision == DecisionKind.ASK and d.kind in ACTS:
        r.verdict = "wrong_action"  # acted where the key says Ask
    elif expected.decision in ACTS and d.kind in ACTS:
        # Disputing a fair charge or accepting a wrong one is a wrong action; a right pile with wrong cents is not.
        bucket = {DecisionKind.SPLIT: DecisionKind.DISPUTE}
        if bucket.get(d.kind, d.kind) != bucket.get(expected.decision, expected.decision) or d.accepted > expected.accepted:
            r.verdict = "wrong_action"
        else:
            r.verdict = "wrong_amount"
    elif d.kind == DecisionKind.ASK:
        r.verdict = "unnecessary_question"
    else:
        r.verdict = "other"
    if not same_amounts:
        r.notes.append(f"amounts {d.disputed}/{d.accepted}, key {expected.disputed}/{expected.accepted}")
    return r


def run(data_dir: Path = DEFAULT_DATA) -> list[Result]:
    policy = load_policy()
    rows, key = load(data_dir)
    results = []
    for row in rows:
        k = key[row["case_id"]]
        exp = Expected(DecisionKind(k["expected_decision"]), money(k["expected_disputed"]),
                       money(k["expected_accepted"]), k["reason"])
        results.append(score(build_case(row, k, policy), exp, policy))
    return results


def summary(results: list[Result]) -> dict:
    count = lambda v: sum(1 for r in results if r.verdict == v)  # noqa: E731
    return {
        "mode": "engine",
        "cases": len(results),
        "correct": count("correct"),
        "correct_amounts": sum(1 for r in results if r.disputed == r.expected.disputed and r.accepted == r.expected.accepted),
        "asked": sum(1 for r in results if r.decision == DecisionKind.ASK),
        "wrong_actions": count("wrong_action"),
        "unnecessary_questions": count("unnecessary_question"),
        "wrong_amounts": count("wrong_amount"),
        "other": count("other"),
    }


def save(s: dict, path: Path = LATEST) -> dict:
    """Write the summary with the time it ran; written whole to a temp file first, so a reader never sees half."""
    saved = {**s, "run_at": datetime.now().astimezone().isoformat()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(saved, indent=2) + "\n")
    tmp.replace(path)
    return saved


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="data directory (default: data/)")
    ap.add_argument("--json", action="store_true", help="print the summary and misses as JSON")
    ap.add_argument("--out", type=Path, default=LATEST, help="where to save the summary (default: eval/latest.json)")
    ap.add_argument("--no-save", action="store_true", help="don't save the summary")
    args = ap.parse_args(argv)
    if not (args.data / "eval" / "charges-30.csv").exists():
        print(f"No eval set at {args.data / 'eval'}; merge the story branch or pass --data.", file=sys.stderr)
        return 2

    results = run(args.data)
    s = summary(results)
    misses = [r for r in results if r.verdict != "correct"]
    if not args.no_save:
        save(s, args.out)
    if args.json:
        s["misses"] = [{"case": r.case_id, "tag": r.tag, "verdict": r.verdict, "got": r.decision.value,
                        "expected": r.expected.decision.value, "gate_row": r.gate_row, "notes": r.notes} for r in misses]
        print(json.dumps(s, indent=2))
    else:
        print(f"Eval ({s['mode']} mode): {s['correct']}/{s['cases']} correct · {s['asked']} asked · "
              f"{s['wrong_actions']} wrong automatic actions · {s['unnecessary_questions']} unnecessary questions · "
              f"amounts right to the cent on {s['correct_amounts']}/{s['cases']}")
        for r in misses:
            print(f"  {r.verdict:<21} {r.case_id} {r.tag}: got {r.decision.value} (row {r.gate_row}), "
                  f"key {r.expected.decision.value}. {' '.join(r.notes)}")
    return 1 if s["wrong_actions"] else 0


if __name__ == "__main__":
    sys.exit(main())
