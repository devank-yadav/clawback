from decimal import Decimal

from api.engine.value import run_value


def test_peak_bar_march_value():
    v = run_value(Decimal("4120"), Decimal("1530"), 1, 6, seconds_to_decided=12.34, ai_calls=19, ai_cost_usd=0.0,
                  manual_minutes_per_charge=None)
    assert (v.disputed, v.accepted, v.questions, v.charges, v.seconds_to_decided, v.ai_calls) == (
        Decimal("4120.00"), Decimal("1530.00"), 1, 6, 12.3, 19)
    assert v.ai_cost_usd == Decimal("0") and v.manual_minutes is None and v.manual_minutes_per_charge is None


def test_manual_minutes_is_charges_times_the_policy_figure():
    v = run_value(Decimal(0), Decimal(0), 0, 6, manual_minutes_per_charge=25)
    assert (v.manual_minutes, v.manual_minutes_per_charge) == (Decimal(150), Decimal(25))


def test_unpriced_ai_stays_none():
    assert run_value(Decimal(0), Decimal(0), 0, 1, ai_cost_usd=None).ai_cost_usd is None
