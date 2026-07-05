"""Loan calculator endpoint: per-customer, per-product terms → verdict.

One product per call, on top of the pure math in aayai.gold.loan_calc; the
Loan Details page fires the four product calls in parallel and aggregates.
Server-side math is authoritative — the frontend never fabricates a verdict or
a max-loan number. Amounts are illustrative, never offers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from aayai.api.deps import get_conn
from aayai.gold.loan_calc import calculate
from aayai.gold.loan_products import PRODUCTS_BY_KEY
from aayai.serving.queries import customer_profile

router = APIRouter(prefix="/customers", tags=["loan-calc"])

DISCLAIMER = (
    "All amounts are illustrative calculations from reconstructed income, "
    "not a loan offer or a credit decision."
)


@router.get("/{customer_id}/loan-calc")
def loan_calc(
    customer_id: str,
    product: str = Query(...),
    annual_rate: float = Query(..., ge=0, le=40),
    tenure_months: int | None = Query(None, ge=6, le=360),
    amount: float | None = Query(None, gt=0),
    conn=Depends(get_conn),
) -> dict:
    """Evaluate one product for one customer at the given rate/tenure/amount.

    404 on unknown customer or product; 422 (via validation) on a rate outside
    0-40, a tenure outside 6-360 months, or a non-positive amount. Tenure
    defaults to the product's standard tenure when omitted.
    """
    if product not in PRODUCTS_BY_KEY:
        raise HTTPException(404, f"unknown loan product '{product}'")
    analysis = customer_profile(conn, customer_id)
    if analysis is None:
        raise HTTPException(404, f"customer '{customer_id}' not found")

    profile = analysis["profile"]
    score = analysis["score"]
    result = calculate(
        product,
        annual_rate_pct=annual_rate,
        tenure_months=tenure_months,
        requested_amount=amount,
        true_monthly_income=float(profile["true_monthly_income"]),
        income_volatility=float(profile["income_volatility"]),
        total_emi=float(profile["total_emi"]),
        months_history=int(profile["months_history"]),
        confidence_band=profile["confidence_band"],
        investable_surplus=float(profile["investable_surplus"]),
        prospect_score=float(score["p_good_prospect"]) if score else None,
    )
    return {
        "customer_id": profile["customer_id"],
        "name": profile["name"],
        "confidence_band": profile["confidence_band"],
        **result,
        "disclaimer": DISCLAIMER,
    }
