"""Intent endpoints: fused per-customer intent, composition and the book view.

Reads the precomputed intent_scores (fused 90% behavioural / 10% engagement)
plus the engagement strip for the customer detail. Analyst/app activity never
influences these, they are pure derived data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from aayai.api.deps import get_conn
from aayai.gold.intent import best_repayable

router = APIRouter(prefix="/intent", tags=["intent"])

QUADRANTS = {"act_now", "nurture", "downsell", "exclude"}


@router.get("/search")
def search(
    q: str = Query(min_length=1),
    limit: int = Query(10, ge=1, le=50),
    conn=Depends(get_conn),
) -> list[dict]:
    """Resolve a customer by NAME (partial, case-insensitive) or by cust id."""
    like = f"%{q.strip()}%"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.customer_id, p.name, i.intent, i.quadrant
            FROM intent_scores i
            JOIN customer_profiles p USING (customer_id)
            WHERE p.name ILIKE %s OR i.customer_id ILIKE %s
            ORDER BY (i.customer_id ILIKE %s) DESC, i.intent DESC
            LIMIT %s
            """,
            (like, like, q.strip(), limit),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


@router.get("/quadrant/{quadrant}")
def by_quadrant(quadrant: str, conn=Depends(get_conn)) -> list[dict]:
    """Every customer in one capacity×intent quadrant (for the Overview lists)."""
    if quadrant not in QUADRANTS:
        raise HTTPException(422, f"quadrant must be one of {sorted(QUADRANTS)}")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.customer_id, p.name, p.confidence_band, i.intent,
                   i.intent_decile, i.best_fit_product, s.p_good_prospect
            FROM intent_scores i
            JOIN customer_profiles p USING (customer_id)
            LEFT JOIN prospect_scores s USING (customer_id)
            WHERE i.quadrant = %s
            ORDER BY i.intent DESC, i.customer_id
            """,
            (quadrant,),
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        r["prospect_score"] = (
            float(r.pop("p_good_prospect"))
            if r["p_good_prospect"] is not None
            else None
        )
    return rows


@router.get("/book")
def book(conn=Depends(get_conn)) -> dict:
    """Capacity × intent scatter, intent-decile histogram and quadrant counts."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT i.customer_id, p.name, i.intent, i.intent_decile, i.quadrant,
                   i.engagement_used, s.p_good_prospect
            FROM intent_scores i
            JOIN customer_profiles p USING (customer_id)
            LEFT JOIN prospect_scores s USING (customer_id)
            ORDER BY i.intent DESC
            """)
        cols = [d[0] for d in cur.description]
        points = [dict(zip(cols, r)) for r in cur.fetchall()]
    deciles = [0] * 10
    quadrants: dict[str, int] = {}
    for pt in points:
        d = pt["intent_decile"] if pt["intent_decile"] is not None else 0
        deciles[max(0, min(9, d))] += 1
        quadrants[pt["quadrant"]] = quadrants.get(pt["quadrant"], 0) + 1
        pt["capacity"] = (
            float(pt["p_good_prospect"]) if pt["p_good_prospect"] is not None else None
        )
    return {
        "points": points,
        "deciles": [{"decile": i, "count": c} for i, c in enumerate(deciles)],
        "quadrants": quadrants,
        "customers": len(points),
    }


@router.get("/{customer_id}")
def customer_intent(customer_id: str, conn=Depends(get_conn)) -> dict:
    """Fused intent + composition + per-product + best-fit / best-repayable."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.intent, i.behavioral_score, i.engagement_score, i.engagement_used,
                   i.best_fit_product, i.best_fit_reason, i.best_repayable_amount,
                   i.quadrant, i.intent_decile, i.per_product, i.composition,
                   p.name, p.confidence_band, s.p_good_prospect,
                   p.true_monthly_income, p.total_emi, p.investable_surplus
            FROM intent_scores i
            JOIN customer_profiles p USING (customer_id)
            LEFT JOIN prospect_scores s USING (customer_id)
            WHERE i.customer_id = %s
            """,
            (customer_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, f"no intent score for '{customer_id}'")
        cols = [d[0] for d in cur.description]
        data = dict(zip(cols, row))

        cur.execute(
            """
            SELECT sessions_90d, recency, frequency, strongest_tier, offer_click_rate,
                   product_affinity, days_since_last_loan_event, days_since_strong_event,
                   last_event_type, last_event_at, strongest_action
            FROM engagement_summary WHERE customer_id = %s
            """,
            (customer_id,),
        )
        eng_row = cur.fetchone()
        engagement = None
        if eng_row is not None:
            engagement = dict(zip([d[0] for d in cur.description], eng_row))
            if engagement.get("last_event_at") is not None:
                engagement["last_event_at"] = engagement["last_event_at"].isoformat()

    repayable = None
    if data["best_fit_product"]:
        repayable = best_repayable(
            data["best_fit_product"],
            true_monthly_income=float(data["true_monthly_income"]),
            total_emi=float(data["total_emi"]),
            investable_surplus=float(data["investable_surplus"]),
        )

    return {
        "customer_id": customer_id,
        "name": data["name"],
        "confidence_band": data["confidence_band"],
        "prospect_score": (
            float(data["p_good_prospect"])
            if data["p_good_prospect"] is not None
            else None
        ),
        "intent": data["intent"],
        "behavioral_score": data["behavioral_score"],
        "engagement_score": data["engagement_score"],
        "engagement_used": data["engagement_used"],
        "quadrant": data["quadrant"],
        "intent_decile": data["intent_decile"],
        "per_product_intent": data["per_product"],
        "composition": data["composition"],
        "best_fit_product": data["best_fit_product"],
        "best_fit_reason": data["best_fit_reason"],
        "best_repayable_amount": data["best_repayable_amount"],
        "best_repayable": repayable,
        "engagement": engagement,
        "disclaimer": "illustrative, not an offer",
    }
