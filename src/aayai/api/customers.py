"""Customer endpoints: ranking, search, full profile and review state."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from aayai.api.customer_pdf import build_customer_summary
from aayai.api.deps import get_conn
from aayai.serving.queries import customer_profile, ranked_prospects, search_customers
from aayai.serving.reviews import set_review
from aayai.serving.shares import log_share

router = APIRouter(prefix="/customers", tags=["customers"])

BANDS = {"high", "medium", "low"}


@router.get("/ranked")
def ranked(
    order: str = Query("desc", pattern="^(asc|desc)$"),
    confidence: list[str] | None = Query(None),
    conn=Depends(get_conn),
) -> list[dict]:
    """All customers ranked by real prospect score, straight from the store."""
    if confidence is not None:
        unknown = set(confidence) - BANDS
        if unknown:
            raise HTTPException(422, f"unknown confidence bands: {sorted(unknown)}")
    return ranked_prospects(conn, bands=confidence, ascending=order == "asc")


@router.get("/search")
def search(q: str = Query(min_length=1), conn=Depends(get_conn)) -> list[dict]:
    """Partial id/name match, at most 10 rows."""
    return search_customers(conn, q)


@router.get("/{customer_id}")
def profile(customer_id: str, conn=Depends(get_conn)) -> dict:
    """Full analysis for one customer; 404 with a clear message when unknown."""
    result = customer_profile(conn, customer_id)
    if result is None:
        raise HTTPException(404, f"customer '{customer_id}' not found")
    return result


class ReviewRequest(BaseModel):
    reviewed: bool
    reviewed_by: str = Field(min_length=1, max_length=100)


@router.post("/{customer_id}/review")
def review(customer_id: str, body: ReviewRequest, conn=Depends(get_conn)) -> dict:
    """Upsert the analyst review mark and return the stored state."""
    if customer_profile(conn, customer_id) is None:
        raise HTTPException(404, f"customer '{customer_id}' not found")
    state = set_review(conn, customer_id, body.reviewed, body.reviewed_by)
    return {"customer_id": customer_id, **state}


@router.post("/{customer_id}/share")
def share(
    customer_id: str, shared_by: str = Query("analyst"), conn=Depends(get_conn)
) -> Response:
    """Generate the clean customer-facing PDF, log the share, return it for download.

    The PDF is a plain-language summary only, it never contains the prospect
    score, SHAP impactors or any model mechanics. Logging is append-only and
    the file is offered as a download; nothing is emailed or sent anywhere.
    """
    analysis = customer_profile(conn, customer_id)
    if analysis is None:
        raise HTTPException(404, f"customer '{customer_id}' not found")
    pdf = build_customer_summary(analysis["profile"], analysis["surplus_breakdown"])
    event = log_share(conn, customer_id, shared_by)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{customer_id}-summary.pdf"',
            "X-Shared-At": event["shared_at"],
        },
    )
