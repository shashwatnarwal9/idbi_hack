"""Overview endpoints: book-level aggregates for the dashboard home."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from aayai.api.deps import get_conn
from aayai.serving.queries import income_by_month, portfolio_summary

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("/summary")
def summary(conn=Depends(get_conn)) -> dict:
    """Portfolio aggregates plus the monthly income series, all live."""
    return {
        **portfolio_summary(conn),
        "income_by_month": income_by_month(conn),
    }
