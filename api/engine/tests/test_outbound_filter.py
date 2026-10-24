from decimal import Decimal

import pytest

from api.engine.outbound_filter import OutboundContext, check_message

S31 = ("Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and "
       "Peak Bar Chocolate sold between March 1 and March 31, 2026.")
S32 = "The promotional allowance applies to a maximum of 5,000 units in total."

TERMS = [
    {"type": "promo_rate", "params": {"rate": "1.00"}, "exact_quote": S31},
    {"type": "unit_cap", "params": {"max_units": 5000}, "exact_quote": S32},
]
# Engine numbers for dispute D-0417 (data/CLAUDE.md): C1 split, C2, C4, C5 disputed; totals.
AMOUNTS = [Decimal("1800.00"), Decimal("1200.00"), Decimal("600.00"), Decimal("980.00"),
           Decimal("1540.00"), Decimal("1000.00"), Decimal("4120.00"), Decimal("1.50")]
FINDINGS = ["Week 4 promo is over the 5,000-unit cap reached in week 3."]

CTX = OutboundContext.build(amounts=AMOUNTS, terms=TERMS, findings=FINDINGS)

GOOD = (
    'Dispute D-0417, line C4: the deal says "The promotional allowance applies to a maximum of 5,000 units '
    'in total." Weeks 1 to 3 reached 5,000 units, so the $1,540.00 taken for week 4 is not covered by the deal. '
    'Line C1: you charged $1.50 per unit; the deal says "$1.00 per unit on Peak Bar Original and Peak Bar '
    'Chocolate", so we dispute $600 and accept $1,200. If the cap changed, please send the signed amendment.'
)


def test_a_correct_dispute_message_passes():
    result = check_message(GOOD, CTX)
    assert result.ok, result.feedback()


def test_dollar_figure_not_in_finding_is_blocked():
    result = check_message("For line C4 we are disputing $1,450.", CTX)
    assert not result.ok
    assert [(v.kind, v.text) for v in result.violations] == [("amount", "$1,450")]


@pytest.mark.parametrize("text", ["USD 4,121", "4121 dollars", "$ 4,121.00", "4,121 USD"])
def test_every_way_of_writing_dollars_is_checked(text):
    assert not check_message(f"Total disputed: {text}.", CTX).ok
    assert check_message(f"Total disputed: {text.replace('4,121', '4,120').replace('4121', '4120')}.", CTX).ok


def test_amounts_compare_by_value():
    assert check_message("We dispute $980 on line C2 (also written $980.00).", CTX).ok


def test_invented_quote_is_blocked():
    text = 'The deal says "Promotional allowance is limited to 4,000 units per month." so week 4 is over.'
    result = check_message(text, CTX)
    assert [v.kind for v in result.violations] == ["quote"]


def test_quote_with_curly_marks_and_different_spacing_passes():
    text = "The deal says “The promotional  allowance applies to a maximum of\n5,000 units in total.”"
    assert check_message(text, CTX).ok


def test_figures_inside_a_verified_quote_are_not_double_checked():
    # $1.00 is not in AMOUNTS, but it sits inside the verified §3.1 quote.
    assert check_message(f'The deal says "{S31}"', CTX).ok
    assert not check_message("The deal rate is $1.25.", CTX).ok


@pytest.mark.parametrize("kind,text", [
    ("promise", "We promise this won't happen again."),
    ("promise", "We guarantee faster replies next month."),
    ("promise", "We will refund the difference on the next invoice."),
    ("promise", "We'll absorb the display fee."),
    ("discount", "We can offer a 10% off on the next order."),
    ("discount", "We'll give you a discount if you drop C4."),
    ("discount", "We would waive line C5 as goodwill."),
    ("discount", "Let's split the difference on line C1."),
    ("discount", "We could settle for half."),
    ("deadline", "Please respond by Friday."),
    ("deadline", "Please respond by March 31."),
    ("deadline", "Payment is due within 10 business days."),
    ("deadline", "Reply no later than 2026-04-15."),
    ("deadline", "This is the final notice."),
    ("deadline", "The deadline is next week."),
])
def test_promises_discounts_and_deadlines_are_blocked(kind, text):
    result = check_message(text, CTX)
    assert not result.ok
    assert kind in {v.kind for v in result.violations}


def test_commitment_words_inside_a_verified_quote_are_allowed():
    ctx = OutboundContext.build(terms=[{"params": {}, "exact_quote": "Northmart will refund any duplicate charge by March 31."}])
    assert check_message('Per the deal: "Northmart will refund any duplicate charge by March 31."', ctx).ok


def test_policy_set_phrase_is_exempt():
    ctx = OutboundContext.build(amounts=AMOUNTS, allowed_phrases=["within 30 days"])
    assert check_message("Please reply within 30 days with the signed amendment.", ctx).ok
    assert not check_message("Please reply within 10 days with the signed amendment.", ctx).ok


def test_ordinary_words_do_not_trip_the_deadline_check():
    text = "Week 4 is not covered by the deal. The cap was reached before week 4. May we have the amendment?"
    assert check_message(text, CTX).ok


def test_feedback_lists_every_violation():
    result = check_message("We promise to refund $99 by Monday.", CTX)
    kinds = sorted(v.kind for v in result.violations)
    assert kinds == ["amount", "deadline", "promise"]
    assert result.feedback().count("\n") == 2
