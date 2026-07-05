"""Loan calculator math over the existing product rules — pure and I/O-free.

Sequenced the way a bank underwrites: qualification first (the existing
`evaluate_product` gates — income/DTI/volatility/history/confidence/prospect
floor), then affordability (how large an EMI the customer can carry), then the
optional requested amount checked against that headroom and the product's DTI
cap. Nothing here reads a "_" ground-truth column, touches the database, or
adds a pipeline stage; every threshold is a named constant.

The affordable EMI is the tighter of two caps:
  * surplus cap — MAX_EMI_TO_SURPLUS_RATIO x investable surplus (the same
    constant the suggested-amount rule already uses), and
  * FOIR cap    — FOIR_CAP x income minus existing EMIs (Fixed Obligation to
    Income Ratio, the standard bank affordability measure).
An over-committed customer (existing EMIs already past the FOIR line) gets a
headroom of exactly 0, never a negative number.
"""

from __future__ import annotations

from aayai.gold.loan_products import (
    MAX_EMI_TO_SURPLUS_RATIO,
    PRODUCTS_BY_KEY,
    evaluate_product,
)

# Fixed-Obligation-to-Income cap: total monthly obligations (existing EMIs plus
# the new loan's EMI) may consume at most this share of reconstructed income.
FOIR_CAP = 0.50


def emi(principal: float, annual_rate_pct: float, months: int) -> float:
    """Reducing-balance EMI: P·r(1+r)^n / ((1+r)^n − 1), r = monthly rate.

    Zero rate degrades to straight-line P/n. Non-positive principal or tenure
    yields 0 — there is no loan to price.
    """
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate_pct / 12 / 100
    if r == 0:
        return principal / months
    growth = (1 + r) ** months
    return principal * r * growth / (growth - 1)


def max_principal(emi_afford: float, annual_rate_pct: float, months: int) -> float:
    """Largest principal whose EMI at this rate/tenure fits emi_afford.

    The algebraic inverse of emi(): P = E·((1+r)^n − 1) / (r(1+r)^n), with the
    zero-rate branch E·n. Non-positive headroom or tenure yields 0.
    """
    if emi_afford <= 0 or months <= 0:
        return 0.0
    r = annual_rate_pct / 12 / 100
    if r == 0:
        return emi_afford * months
    growth = (1 + r) ** months
    return emi_afford * (growth - 1) / (r * growth)


def affordable_emi(
    true_monthly_income: float, total_emi: float, investable_surplus: float
) -> tuple[float, str]:
    """The binding monthly-EMI headroom and which cap bound it.

    Returns (headroom, cap) where cap is "surplus" or "foir". The headroom is
    the tighter of the surplus cap and the FOIR cap, floored at 0 so an
    over-committed customer reads as "no headroom", never negative.
    """
    surplus_cap = MAX_EMI_TO_SURPLUS_RATIO * max(investable_surplus, 0.0)
    foir_cap = FOIR_CAP * true_monthly_income - total_emi
    if surplus_cap <= foir_cap:
        return max(surplus_cap, 0.0), "surplus"
    return max(foir_cap, 0.0), "foir"


def calculate(
    product_key: str,
    *,
    annual_rate_pct: float,
    tenure_months: int | None = None,
    requested_amount: float | None = None,
    true_monthly_income: float,
    income_volatility: float,
    total_emi: float,
    months_history: int,
    confidence_band: str,
    investable_surplus: float,
    prospect_score: float | None = None,
) -> dict:
    """Full per-product calculation: qualification, affordability, requested P.

    1. Qualification — the existing gate rules. A failure is terminal: the max
       loan is 0 and any requested amount is not eligible, carrying the gate's
       reasons verbatim.
    2. Affordability — for a qualified customer, the affordable EMI (tighter of
       the surplus and FOIR caps) and the max principal it buys at this
       rate/tenure. Tenure defaults to the product's standard tenure.
    3. Requested amount (optional) — its exact EMI, post-loan FOIR/DTI, total
       repayment/interest, and an eligible verdict requiring the EMI to fit the
       headroom AND post-loan obligations to stay within the product's max DTI;
       every failing reason is listed.

    Raises:
        ValueError: unknown product key (callers map this to a 404).
    """
    product = PRODUCTS_BY_KEY.get(product_key)
    if product is None:
        raise ValueError(f"unknown loan product '{product_key}'")
    tenure = (
        tenure_months if tenure_months is not None else product.standard_tenure_months
    )

    dti = total_emi / true_monthly_income if true_monthly_income > 0 else float("inf")
    base = evaluate_product(
        product,
        dti=dti,
        income_volatility=income_volatility,
        months_history=months_history,
        confidence_band=confidence_band,
        investable_surplus=investable_surplus,
        prospect_score=prospect_score,
    )
    qualified = base["status"] == "eligible"

    if qualified:
        headroom, binding_cap = affordable_emi(
            true_monthly_income, total_emi, investable_surplus
        )
        max_loan = max_principal(headroom, annual_rate_pct, tenure)
    else:
        # gate failure is terminal: no headroom, no loan, whatever the terms
        headroom, binding_cap, max_loan = 0.0, None, 0.0

    affordability = {
        "affordable_emi": round(headroom, 2),
        "binding_cap": binding_cap,
        "max_loan_amount": round(max_loan, 2),
        "current_dti": round(dti, 4) if true_monthly_income > 0 else None,
    }

    requested = None
    if requested_amount is not None:
        emi_req = emi(requested_amount, annual_rate_pct, tenure)
        post_dti = (
            (total_emi + emi_req) / true_monthly_income
            if true_monthly_income > 0
            else None
        )
        reasons: list[str] = []
        if not qualified:
            reasons.append(base["reason"])
        else:
            if emi_req > headroom:
                reasons.append(
                    f"EMI of ₹{emi_req:,.0f}/month exceeds the affordable headroom "
                    f"of ₹{headroom:,.0f}/month (bound by the {binding_cap} cap)"
                )
            if post_dti is not None and post_dti > product.max_dti:
                reasons.append(
                    f"post-loan obligations reach {post_dti:.0%} of income, above "
                    f"the {product.max_dti:.0%} {product.label} cap"
                )
        total_repayment = emi_req * tenure
        requested = {
            "amount": round(requested_amount, 2),
            "emi": round(emi_req, 2),
            "post_loan_dti": round(post_dti, 4) if post_dti is not None else None,
            "total_repayment": round(total_repayment, 2),
            "total_interest": round(total_repayment - requested_amount, 2),
            "status": "eligible" if not reasons else "not_eligible",
            "reasons": reasons,
        }

    return {
        "product": product.key,
        "label": product.label,
        "terms": {"annual_rate_pct": annual_rate_pct, "tenure_months": tenure},
        "base_eligibility": base,
        "affordability": affordability,
        "requested": requested,
    }
