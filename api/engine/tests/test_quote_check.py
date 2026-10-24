from decimal import Decimal

from api.engine.quote_check import (
    DISPUTED, REJECTED, VERIFIED, check_quote, find_quote, missing_numbers, normalize, numbers_in,
    readers_agree, verify_term,
)

# The three clauses from data/CLAUDE.md, word for word, inside some contract text (wrapped mid-sentence
# the way a markdown file often is). data/deals/spring-promo.md is Manasv's; this test doesn't read it.
S31 = ("Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and "
       "Peak Bar Chocolate sold between March 1 and March 31, 2026.")
S32 = "The promotional allowance applies to a maximum of 5,000 units in total."
S54 = ("Northmart may charge a display fee of up to $1,500 per month at its discretion, "
       "with written notice to Supplier.")
DEAL = f"""# Spring Promotion Agreement (fictional)

## 3. Promotional allowance
3.1 Supplier will fund a promotional allowance of $1.00 per unit on Peak Bar Original and
Peak Bar Chocolate sold between March 1 and March 31, 2026.
3.2 The promotional allowance applies to a maximum of 5,000 units in total.

## 5. Fees
5.4 Northmart may charge a display fee of up to $1,500 per month at its discretion, with written
notice to Supplier.
"""


def term(type_, params, quote, **kw):
    return {"type": type_, "params": params, "exact_quote": quote, **kw}


SPRING_TERMS = [
    term("promo_rate", {"rate": "1.00", "unit": "unit"}, S31),
    term("product_scope", {"products": ["Peak Bar Original", "Peak Bar Chocolate"]}, S31),
    term("date_range", {"start": "2026-03-01", "end": "2026-03-31"}, S31),
    term("unit_cap", {"max_units": 5000}, S32),
    term("fee_discretion", {"max_fee": Decimal("1500"), "period": "month"}, S54, discretion=True),
]


# --- normalization and finding ------------------------------------------------------------------

def test_normalize_collapses_spaces_and_dash_variants():
    assert normalize("  March 1–March  31,\n2026 ") == "March 1 March 31, 2026"
    assert normalize("week-to-week") == normalize("week — to week") == "week to week"
    assert normalize("allow­ance") == "allowance"
    assert normalize("“at its discretion”") == '"at its discretion"'


def test_find_quote_returns_offsets_in_original_text():
    start, end = find_quote(DEAL, S31)
    # The source has a line break where the quote has a space; the span still covers the whole sentence.
    assert normalize(DEAL[start:end]) == normalize(S31)
    assert DEAL[start:end].startswith("Supplier will fund")
    assert DEAL[start:end].endswith("2026.")


def test_find_quote_prefers_occurrence_near_reader_offset():
    src = "Rate is $1.00. Later: Rate is $1.00."
    second = src.rindex("Rate")
    assert find_quote(src, "Rate is $1.00.") == (0, 14)
    assert find_quote(src, "Rate is $1.00.", near=second) == (second, len(src))


# --- check 1: quote found word for word ---------------------------------------------------------

def test_all_spring_terms_pass_the_quote_check():
    for t in SPRING_TERMS:
        qc = check_quote(DEAL, t)
        assert qc.ok, (t["type"], qc.reasons)


def test_planted_fake_quote_is_rejected():
    fake = term("promo_rate", {"rate": "1.50"},
                "Supplier will fund a promotional allowance of $1.50 per unit on Peak Bar Original and "
                "Peak Bar Chocolate sold between March 1 and March 31, 2026.")
    qc = check_quote(DEAL, fake)
    assert not qc.ok
    assert "quote not found in source" in qc.reasons


def test_paraphrase_is_rejected():
    para = term("unit_cap", {"max_units": 5000}, "The allowance is capped at 5,000 units.")
    assert not check_quote(DEAL, para).ok


def test_same_sentence_with_different_spacing_and_hyphens_is_accepted():
    spaced = ("Supplier  will fund a promotional\tallowance of $1.00 per unit on Peak Bar Original and\n"
              "Peak Bar Chocolate sold between March 1 and March 31, 2026.")
    hyphen_src = "Fees: Northmart may charge a display-fee of up to $1,500 per month."
    assert check_quote(DEAL, term("promo_rate", {"rate": 1}, spaced)).ok
    assert check_quote(hyphen_src, term("fee_discretion", {"max_fee": 1500},
                                        "Northmart may charge a display – fee of up to $1,500 per month.")).ok


def test_check_is_case_sensitive_and_word_for_word():
    lowered = term("unit_cap", {"max_units": 5000}, S32.lower())
    prefix = term("unit_cap", {"max_units": 5000}, "applies to a maximum of 5,000 units")
    assert not check_quote(DEAL, lowered).ok
    assert check_quote(DEAL, prefix).ok  # part of a real sentence is still found word for word
    swapped = term("unit_cap", {"max_units": 5000}, S32.replace("maximum", "minimum"))
    assert not check_quote(DEAL, swapped).ok


def test_empty_quote_is_rejected():
    assert not check_quote(DEAL, term("unit_cap", {"max_units": 5000}, "  ")).ok


# --- check 2: every number in params appears in the quote ---------------------------------------

def test_numbers_in_reads_contract_formats():
    assert numbers_in(S54) == [Decimal("1500")]
    assert numbers_in(S31) == [Decimal("1.00"), Decimal("1"), Decimal("31"), Decimal("2026")]
    assert numbers_in(S32) == [Decimal("5000")]


def test_param_number_not_in_quote_is_rejected_even_with_a_real_quote():
    wrong_rate = term("promo_rate", {"rate": "1.50"}, S31)
    qc = check_quote(DEAL, wrong_rate)
    assert not qc.ok
    assert any("1.50" in r for r in qc.reasons)


def test_number_match_is_by_value_and_recursive():
    assert missing_numbers({"rate": 1.0, "nested": {"cap": ["5,000"]}}, "$1.00 and 5,000 units") == []
    assert missing_numbers({"cap": 6000}, S32) == [Decimal("6000")]


def test_dates_and_booleans_in_params_are_not_numbers():
    assert missing_numbers({"start": "2026-03-01", "discretion": True}, "no digits here") == []


# --- check 3: two readers agree -----------------------------------------------------------------

def test_readers_agree_ignores_number_format_case_and_list_order():
    a = term("product_scope", {"products": ["Peak Bar Original", "Peak Bar Chocolate"], "rate": "1.00"}, S31)
    b = term("product_scope", {"products": ["peak bar chocolate", "Peak Bar Original"], "rate": 1}, S31)
    assert readers_agree(a, b)


def test_readers_disagree_on_type_or_params():
    a = term("unit_cap", {"max_units": 5000}, S32)
    assert not readers_agree(a, term("unit_cap", {"max_units": 6000}, S32))
    assert not readers_agree(a, term("promo_rate", {"max_units": 5000}, S32))
    assert not readers_agree(a, term("unit_cap", {"max_units": 5000, "scope": "per week"}, S32))


# --- merged verdict -----------------------------------------------------------------------------

def test_verify_term_verified_when_both_pass_and_agree():
    for t in SPRING_TERMS:
        v = verify_term(DEAL, t, dict(t))
        assert v.status == VERIFIED, (t["type"], v.reasons)
        assert v.char_start is not None and v.char_end > v.char_start


def test_verify_term_disputed_when_readers_disagree():
    a = term("fee_discretion", {"max_fee": 1500, "discretion": True}, S54)
    b = term("fee_discretion", {"max_fee": 1500, "discretion": False}, S54)
    v = verify_term(DEAL, a, b)
    assert v.status == DISPUTED
    assert v.reasons == ("readers disagree on type or params",)


def test_verify_term_disputed_when_one_reader_missed_it():
    t = SPRING_TERMS[3]
    assert verify_term(DEAL, t, None).status == DISPUTED
    assert verify_term(DEAL, None, t).status == DISPUTED


def test_verify_term_rejected_when_either_quote_fails():
    good = SPRING_TERMS[3]
    fake = term("unit_cap", {"max_units": 5000}, "The promotional allowance applies to a maximum of 5,000 units per week.")
    v = verify_term(DEAL, good, fake)
    assert v.status == REJECTED
    assert v.reasons == ("reader B: quote not found in source",)
    assert verify_term(DEAL, None, None).status == REJECTED
