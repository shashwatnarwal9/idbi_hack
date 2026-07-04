"""Loan assessment endpoints: browse Part A's per-product eligibility.

Reads the eligibility computed by the loan-product rules (no separate rule set);
covers seeded and merged uploaded customers, tagged by source.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from aayai.api.deps import get_conn
from aayai.gold.loan_products import PRODUCTS_BY_KEY
from aayai.serving.queries import loan_assessment, loan_assessment_summary

router = APIRouter(prefix="/loan-assessment", tags=["loan-assessment"])

STATUSES = {"eligible", "not_eligible", "all"}


@router.get("/summary")
def summary(conn=Depends(get_conn)) -> dict:
    """Eligible-customer counts per product across the operational book."""
    return loan_assessment_summary(conn)


@router.get("/{product}")
def by_product(
    product: str,
    status: str = Query("all"),
    conn=Depends(get_conn),
) -> list[dict]:
    """Customers assessed for one product, eligible-first by prospect score."""
    if product not in PRODUCTS_BY_KEY:
        raise HTTPException(404, f"unknown loan product '{product}'")
    if status not in STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(STATUSES)}")
    return loan_assessment(conn, product, status)
