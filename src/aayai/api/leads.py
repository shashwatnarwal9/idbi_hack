"""Leads endpoints: ranked per-product lead lists, summary, and mark-contacted.

The ranked list joins the precomputed lead_scores with the customer's display
fields and the contacted workflow flag. STRICT firewall: the mark-contacted
action writes only to lead_contacts and changes NO score, the list re-reads the
same lead_score it had before.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from aayai.api.deps import get_conn
from aayai.gold.loan_products import PRODUCTS_BY_KEY
from aayai.serving.contacts import set_contacted

router = APIRouter(prefix="/leads", tags=["leads"])

BANDS = {"high", "medium", "low"}
QUADRANTS = {"act_now", "nurture", "downsell", "exclude"}


@router.get("/summary")
def summary(conn=Depends(get_conn)) -> dict:
    """Per-product eligible pool, act-now count and total best-repayable."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT product,
                   count(*) FILTER (WHERE eligible) AS eligible_pool,
                   count(*) FILTER (WHERE quadrant = 'act_now' AND eligible) AS act_now,
                   COALESCE(sum(best_repayable_amount) FILTER (WHERE eligible), 0) AS repayable
            FROM lead_scores GROUP BY product
            """)
        cols = [d[0] for d in cur.description]
        by_product = {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}
    products = [
        {
            "product": key,
            "label": PRODUCTS_BY_KEY[key].label,
            "eligible_pool": int(by_product.get(key, {}).get("eligible_pool", 0)),
            "act_now": int(by_product.get(key, {}).get("act_now", 0)),
            "total_repayable": float(by_product.get(key, {}).get("repayable", 0.0)),
        }
        for key in PRODUCTS_BY_KEY
    ]
    return {"products": products, "disclaimer": "illustrative, not an offer"}


@router.get("/{product}")
def by_product(
    product: str,
    quadrant: str | None = Query(None),
    band: str | None = Query(None),
    source: str | None = Query(None),
    min_decile: int = Query(0, ge=0, le=9),
    conn=Depends(get_conn),
) -> list[dict]:
    """Ranked leads for a product (best lead_score first), with display fields."""
    if product not in PRODUCTS_BY_KEY:
        raise HTTPException(404, f"unknown loan product '{product}'")
    if quadrant is not None and quadrant not in QUADRANTS:
        raise HTTPException(422, f"quadrant must be one of {sorted(QUADRANTS)}")
    if band is not None and band not in BANDS:
        raise HTTPException(422, f"band must be one of {sorted(BANDS)}")

    where = ["l.product = %s", "i.intent_decile >= %s"]
    params: list = [product, min_decile]
    if quadrant:
        where.append("l.quadrant = %s")
        params.append(quadrant)
    if band:
        where.append("p.confidence_band = %s")
        params.append(band)
    if source:
        where.append("COALESCE(p.source, 'seeded') = %s")
        params.append(source)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT l.customer_id, p.name, p.confidence_band,
                   COALESCE(p.source, 'seeded') AS source,
                   l.lead_score, l.product_intent, l.quadrant, l.urgency,
                   l.best_repayable_amount, l.trigger, l.eligible,
                   i.intent_decile, s.p_good_prospect,
                   COALESCE(c.contacted, false) AS contacted
            FROM lead_scores l
            JOIN customer_profiles p USING (customer_id)
            JOIN intent_scores i USING (customer_id)
            LEFT JOIN prospect_scores s USING (customer_id)
            LEFT JOIN lead_contacts c
                   ON c.customer_id = l.customer_id AND c.product = l.product
            WHERE {' AND '.join(where)}
            ORDER BY l.lead_score DESC, l.customer_id
            """,
            params,
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["prospect_score"] = (
            float(r.pop("p_good_prospect"))
            if r["p_good_prospect"] is not None
            else None
        )
    return rows


class ContactRequest(BaseModel):
    contacted: bool = True
    contacted_by: str = "analyst"


@router.post("/{product}/{customer_id}/contacted")
def mark_contacted(
    product: str, customer_id: str, body: ContactRequest, conn=Depends(get_conn)
) -> dict:
    """Record (or clear) the contacted mark. Workflow only, changes no score."""
    if product not in PRODUCTS_BY_KEY:
        raise HTTPException(404, f"unknown loan product '{product}'")
    return set_contacted(conn, customer_id, product, body.contacted, body.contacted_by)
