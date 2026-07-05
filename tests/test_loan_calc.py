"""Loan calculator math: EMI, inverse, caps, verdicts. Pure functions, no DB."""

import pytest

from aayai.gold.loan_calc import (
    FOIR_CAP,
    affordable_emi,
    calculate,
    emi,
    max_principal,
)
from aayai.gold.loan_products import (
    HOME_LOAN,
    MAX_EMI_TO_SURPLUS_RATIO,
    PERSONAL_LOAN,
)

# a strong profile that clears every product gate (mirrors test_loan_products)
STRONG = dict(
    true_monthly_income=100000.0,
    income_volatility=0.05,
    total_emi=10000.0,  # dti 0.10
    months_history=18,
    confidence_band="high",
    investable_surplus=40000.0,
    prospect_score=0.95,
)


def _calc(product_key, **over):
    kwargs = {**STRONG, "annual_rate_pct": 10.0, **over}
    return calculate(product_key, **kwargs)


def test_emi_known_value():
    # ₹10,00,000 at 9% for 240 months ≈ ₹8,997.26 (standard reducing balance)
    assert emi(1_000_000, 9.0, 240) == pytest.approx(8997.26, abs=0.01)


def test_emi_edge_branches():
    assert emi(0, 9.0, 240) == 0.0
    assert emi(-5, 9.0, 240) == 0.0
    assert emi(120000, 9.0, 0) == 0.0
    assert emi(120000, 0.0, 12) == pytest.approx(10000.0)  # zero-rate: P/n


def test_max_principal_inverse_round_trip():
    for principal in (250_000, 1_000_000, 7_500_000):
        for rate, months in ((11.0, 36), (8.5, 240), (0.0, 60)):
            e = emi(principal, rate, months)
            assert max_principal(e, rate, months) == pytest.approx(principal, rel=1e-9)


def test_affordable_emi_cap_selection():
    # surplus cap 0.5*40000=20000 vs FOIR cap 0.5*100000-10000=40000 -> surplus
    headroom, cap = affordable_emi(100000.0, 10000.0, 40000.0)
    assert headroom == pytest.approx(MAX_EMI_TO_SURPLUS_RATIO * 40000.0)
    assert cap == "surplus"
    # FOIR cap 0.5*100000-45000=5000 vs surplus cap 30000 -> foir binds
    headroom, cap = affordable_emi(100000.0, 45000.0, 60000.0)
    assert headroom == pytest.approx(FOIR_CAP * 100000.0 - 45000.0)
    assert cap == "foir"


def test_affordable_emi_over_committed_floors_at_zero():
    # existing EMIs already past the FOIR line: headroom 0, never negative
    headroom, cap = affordable_emi(100000.0, 60000.0, 50000.0)
    assert headroom == 0.0
    assert cap == "foir"


def test_higher_rate_lowers_max_principal_not_headroom():
    low = _calc("personal", annual_rate_pct=8.0)
    high = _calc("personal", annual_rate_pct=14.0)
    assert (
        low["affordability"]["affordable_emi"]
        == high["affordability"]["affordable_emi"]
    )
    assert (
        high["affordability"]["max_loan_amount"]
        < low["affordability"]["max_loan_amount"]
    )


def test_requested_within_headroom_is_eligible():
    r = _calc("personal", requested_amount=300_000, tenure_months=36)
    # headroom is 20,000/month; ₹3L over 36mo at 10% is well inside it
    assert r["base_eligibility"]["status"] == "eligible"
    assert r["requested"]["status"] == "eligible"
    assert r["requested"]["reasons"] == []
    assert r["requested"]["emi"] > 0
    assert r["requested"]["total_interest"] > 0
    # total_repayment derives from the unrounded EMI; the response's emi field
    # is rounded to paise, so allow that rounding to accumulate over 36 months
    assert r["requested"]["total_repayment"] == pytest.approx(
        r["requested"]["emi"] * 36, abs=0.5
    )


def test_requested_beyond_headroom_not_eligible_with_reason():
    r = _calc("personal", requested_amount=50_000_000, tenure_months=36)
    assert r["requested"]["status"] == "not_eligible"
    assert any("headroom" in reason for reason in r["requested"]["reasons"])


def test_gate_failure_is_terminal():
    # low confidence fails Home's gate: max loan 0, requested carries gate reasons
    r = _calc(
        "home", confidence_band="low", requested_amount=1_000_000, tenure_months=180
    )
    assert r["base_eligibility"]["status"] == "not_eligible"
    assert r["affordability"]["max_loan_amount"] == 0.0
    assert r["affordability"]["affordable_emi"] == 0.0
    assert r["affordability"]["binding_cap"] is None
    assert r["requested"]["status"] == "not_eligible"
    assert r["requested"]["reasons"] == [r["base_eligibility"]["reason"]]


def test_tenure_defaults_to_product_standard():
    personal = _calc("personal")
    home = _calc("home")
    assert personal["terms"]["tenure_months"] == PERSONAL_LOAN.standard_tenure_months
    assert home["terms"]["tenure_months"] == HOME_LOAN.standard_tenure_months


def test_unknown_product_raises():
    with pytest.raises(ValueError, match="unknown loan product"):
        _calc("bogus")
