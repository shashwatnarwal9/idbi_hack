"""Loan product eligibility rules: each pass/fail branch and reason string."""

from aayai.gold.loan_products import (
    AUTO_LOAN,
    HOME_LOAN,
    MAX_EMI_TO_SURPLUS_RATIO,
    MORTGAGE_LOAN,
    PERSONAL_LOAN,
    PRODUCTS,
    evaluate_all,
    evaluate_product,
    suggested_amount,
)

# a strong salaried-style profile that clears every product
STRONG = dict(
    true_monthly_income=100000.0,
    income_volatility=0.05,
    total_emi=10000.0,  # dti 0.10
    months_history=18,
    confidence_band="high",
    investable_surplus=40000.0,
)


def _one(product, **over):
    row = {**STRONG, **over}
    dti = row["total_emi"] / row["true_monthly_income"]
    return evaluate_product(
        product,
        dti=dti,
        income_volatility=row["income_volatility"],
        months_history=row["months_history"],
        confidence_band=row["confidence_band"],
        investable_surplus=row["investable_surplus"],
    )


def test_eligible_with_suggested_amount():
    r = _one(PERSONAL_LOAN)
    assert r["status"] == "eligible" and r["reason"] is None
    expected = round(
        40000.0 * MAX_EMI_TO_SURPLUS_RATIO * PERSONAL_LOAN.standard_tenure_months, -3
    )
    assert r["suggested_amount"] == expected


def test_fail_history_reason():
    r = _one(PERSONAL_LOAN, months_history=5)
    assert r["status"] == "not_eligible"
    assert r["reason"] == "needs 6 months history, has 5"
    assert r["suggested_amount"] is None


def test_fail_confidence_reason():
    r = _one(HOME_LOAN, confidence_band="medium")
    assert r["status"] == "not_eligible"
    assert r["reason"] == "needs high confidence, has medium"


def test_fail_volatility_reason():
    r = _one(PERSONAL_LOAN, income_volatility=0.40)
    assert r["status"] == "not_eligible"
    assert "income too volatile" in r["reason"] and "0.35" in r["reason"]


def test_fail_dti_reason():
    r = _one(PERSONAL_LOAN, total_emi=60000.0)  # dti 0.60 > 0.45
    assert r["status"] == "not_eligible"
    assert "debt-to-income too high" in r["reason"] and "45%" in r["reason"]


def test_reason_is_first_failing_criterion():
    # everything fails; history is checked first, so it is the reported reason
    r = _one(
        MORTGAGE_LOAN,
        months_history=3,
        confidence_band="low",
        income_volatility=0.9,
        total_emi=90000.0,
    )
    assert (
        r["reason"] == f"needs {MORTGAGE_LOAN.min_months_history} months history, has 3"
    )


def test_suggested_amount_scales_with_tenure_and_surplus():
    assert suggested_amount(AUTO_LOAN, 40000.0) == round(
        40000.0 * MAX_EMI_TO_SURPLUS_RATIO * AUTO_LOAN.standard_tenure_months, -3
    )
    assert suggested_amount(AUTO_LOAN, -5.0) == 0  # negative surplus -> no room


def test_evaluate_all_covers_four_products():
    out = evaluate_all(**STRONG)
    assert [e["product"] for e in out] == [p.key for p in PRODUCTS]
    assert all(e["status"] == "eligible" for e in out)


def test_zero_income_fails_dti_everywhere():
    out = evaluate_all(
        true_monthly_income=0.0,
        income_volatility=0.05,
        total_emi=5000.0,
        months_history=24,
        confidence_band="high",
        investable_surplus=0.0,
    )
    assert all(e["status"] == "not_eligible" for e in out)
