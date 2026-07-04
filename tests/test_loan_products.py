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

# a strong salaried-style profile that clears every product, including the
# prospect-score floors (0.95 is above the strictest 0.60 mortgage floor)
STRONG = dict(
    true_monthly_income=100000.0,
    income_volatility=0.05,
    total_emi=10000.0,  # dti 0.10
    months_history=18,
    confidence_band="high",
    investable_surplus=40000.0,
    prospect_score=0.95,
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
        prospect_score=row["prospect_score"],
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


def test_lists_all_failing_criteria():
    # everything fails; the reason lists every failing criterion, not just one
    r = _one(
        MORTGAGE_LOAN,
        months_history=3,
        confidence_band="low",
        income_volatility=0.9,
        total_emi=90000.0,
        prospect_score=0.1,
    )
    assert r["status"] == "not_eligible"
    assert "months history" in r["reason"]
    assert "confidence" in r["reason"]
    assert "income too volatile" in r["reason"]
    assert "debt-to-income too high" in r["reason"]
    assert "prospect score" in r["reason"]


def test_fail_only_prospect_floor_has_explicit_reason():
    # passes DTI/volatility/history/confidence for Home, fails ONLY the floor
    r = _one(HOME_LOAN, prospect_score=0.31)
    assert r["status"] == "not_eligible"
    assert r["reason"] == (
        "Overall prospect score (0.31) is below the 0.55 threshold required for "
        "Home Loan, despite meeting the individual income/debt criteria"
    )
    assert r["suggested_amount"] is None


def test_fail_prospect_floor_and_ratio_lists_both():
    # high DTI AND a low prospect score for Mortgage -> both reasons appear
    r = _one(MORTGAGE_LOAN, total_emi=50000.0, prospect_score=0.20)  # dti 0.50 > 0.35
    assert r["status"] == "not_eligible"
    assert "debt-to-income too high" in r["reason"]
    assert "overall prospect score (0.20) is below the 0.60 threshold" in r["reason"]
    # not the "despite ..." phrasing, since a ratio also failed
    assert "despite meeting" not in r["reason"]


def test_personal_has_no_prospect_floor():
    # personal loan floor is None: a very low score alone does not disqualify
    r = _one(PERSONAL_LOAN, prospect_score=0.01)
    assert r["status"] == "eligible"


def test_missing_score_skips_prospect_floor():
    # an unscored customer (e.g. batch scored without the model) is not penalised
    r = _one(HOME_LOAN, prospect_score=None)
    assert r["status"] == "eligible"


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
