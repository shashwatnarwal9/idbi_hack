"""Read-side queries shared by consumers of the serving store."""

from __future__ import annotations

from aayai.gold.loan_products import PRODUCTS, evaluate_all
from aayai.serving.reviews import get_review
from aayai.serving.shares import last_share


def loan_eligibility_for(profile: dict) -> list[dict]:
    """Per-product loan eligibility from an already-fetched gold profile row.

    Uses only derived gold fields (no duplicate fetch, no ground truth). Shared
    by the profile endpoint and the loan-assessment queries so eligibility is
    computed one way everywhere.
    """
    return evaluate_all(
        true_monthly_income=float(profile["true_monthly_income"]),
        income_volatility=float(profile["income_volatility"]),
        total_emi=float(profile["total_emi"]),
        months_history=int(profile["months_history"]),
        confidence_band=profile["confidence_band"],
        investable_surplus=float(profile["investable_surplus"]),
    )


def portfolio_summary(conn) -> dict:
    """Book-level aggregates for dashboard headers.

    Args:
        conn: open psycopg2 connection to the serving store.

    Returns:
        Dict with customers, avg_reconstructed, avg_declared, median_surplus
        and per-band counts. Aggregates are None when the table is empty —
        consumers must render those as "unavailable", never as fake numbers.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT count(*),
                   avg(true_monthly_income),
                   avg(declared_monthly_income),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY investable_surplus),
                   count(*) FILTER (WHERE confidence_band = 'high'),
                   count(*) FILTER (WHERE confidence_band = 'medium'),
                   count(*) FILTER (WHERE confidence_band = 'low')
            FROM customer_profiles
            """)
        n, avg_rec, avg_dec, med_sur, high, medium, low = cur.fetchone()
    return {
        "customers": n,
        "avg_reconstructed": float(avg_rec) if avg_rec is not None else None,
        "avg_declared": float(avg_dec) if avg_dec is not None else None,
        "median_surplus": float(med_sur) if med_sur is not None else None,
        "bands": {"high": high, "medium": medium, "low": low},
    }


def income_by_month(conn) -> list[dict]:
    """Average income-classified inflows per customer for every month on file."""
    with conn.cursor() as cur:
        cur.execute("SELECT month, avg_income FROM income_by_month ORDER BY month")
        return [{"month": m, "avg_income": float(v)} for m, v in cur.fetchall()]


def ranked_prospects(
    conn, bands: list[str] | None = None, ascending: bool = False
) -> list[dict]:
    """Every customer ranked by prospect score.

    Args:
        conn: open psycopg2 connection to the serving store.
        bands: confidence bands to include; None means all bands.
        ascending: rank worst-first when True (default best-first).

    Returns:
        List of dicts with rank, customer_id, name, score, band, reviewed and
        the stored SHAP reason codes (customer_id breaks score ties).
    """
    where = ""
    params: tuple = ()
    if bands is not None:
        where = "WHERE p.confidence_band = ANY(%s)"
        params = (list(bands),)
    direction = "ASC" if ascending else "DESC"
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT p.customer_id, p.name, s.p_good_prospect,
                   p.confidence_band, s.reasons, COALESCE(r.reviewed, false),
                   COALESCE(p.source, 'seeded')
            FROM customer_profiles p
            JOIN prospect_scores s USING (customer_id)
            LEFT JOIN review_status r USING (customer_id)
            {where}
            ORDER BY s.p_good_prospect {direction}, p.customer_id
            """,
            params,
        )
        rows = cur.fetchall()
    return [
        {
            "rank": i,
            "customer_id": cid,
            "name": name,
            "score": float(score),
            "band": band,
            "reasons": reasons,
            "reviewed": reviewed,
            "source": source,
        }
        for i, (cid, name, score, band, reasons, reviewed, source) in enumerate(rows, 1)
    ]


def search_customers(conn, q: str, limit: int = 10) -> list[dict]:
    """Match customers by partial id or name (case-insensitive)."""
    pattern = f"%{q}%"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.customer_id, p.name, p.confidence_band,
                   COALESCE(r.reviewed, false)
            FROM customer_profiles p
            LEFT JOIN review_status r USING (customer_id)
            WHERE p.customer_id ILIKE %s OR p.name ILIKE %s
            ORDER BY p.customer_id
            LIMIT %s
            """,
            (pattern, pattern, limit),
        )
        return [
            {"customer_id": cid, "name": name, "band": band, "reviewed": reviewed}
            for cid, name, band, reviewed in cur.fetchall()
        ]


def _assessment_rows(conn) -> list[dict]:
    """Every operational customer with score/review/source and all-product loan
    eligibility computed once (reusing the Part A rules, not a second rule set).

    Includes seeded and merged uploaded customers; soft-deleted (reverted)
    customers are already gone from customer_profiles.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.customer_id, p.name, p.confidence_band,
                   COALESCE(p.source, 'seeded'), p.true_monthly_income,
                   p.income_volatility, p.total_emi, p.months_history,
                   p.investable_surplus, s.p_good_prospect,
                   COALESCE(r.reviewed, false)
            FROM customer_profiles p
            JOIN prospect_scores s USING (customer_id)
            LEFT JOIN review_status r USING (customer_id)
            """)
        rows = cur.fetchall()
    out = []
    for (
        cid,
        name,
        band,
        source,
        income,
        vol,
        emi,
        months,
        surplus,
        score,
        reviewed,
    ) in rows:
        eligibility = {
            e["product"]: e
            for e in evaluate_all(
                true_monthly_income=float(income),
                income_volatility=float(vol),
                total_emi=float(emi),
                months_history=int(months),
                confidence_band=band,
                investable_surplus=float(surplus),
            )
        }
        out.append(
            {
                "customer_id": cid,
                "name": name,
                "confidence_band": band,
                "source": source,
                "score": float(score),
                "reviewed": reviewed,
                "eligibility": eligibility,
            }
        )
    return out


def loan_assessment(conn, product: str, status: str = "all") -> list[dict]:
    """Customers assessed for one product, eligible-first by prospect score.

    Args:
        conn: open serving-store connection.
        product: product key (personal/auto/home/mortgage).
        status: 'eligible', 'not_eligible' or 'all'.

    Returns:
        Rows with customer_id, name, source, prospect score, confidence_band,
        reviewed, plus this product's status/reason/suggested_amount.
    """
    rows = []
    for r in _assessment_rows(conn):
        e = r["eligibility"][product]
        if status != "all" and e["status"] != status:
            continue
        rows.append(
            {
                "customer_id": r["customer_id"],
                "name": r["name"],
                "source": r["source"],
                "score": r["score"],
                "confidence_band": r["confidence_band"],
                "reviewed": r["reviewed"],
                "status": e["status"],
                "reason": e["reason"],
                "suggested_amount": e["suggested_amount"],
            }
        )
    rows.sort(key=lambda x: (x["status"] != "eligible", -x["score"]))
    return rows


def loan_assessment_summary(conn) -> dict:
    """Per-product eligible/not-eligible counts across the operational book."""
    rows = _assessment_rows(conn)
    products = []
    for product in PRODUCTS:
        eligible = sum(
            1 for r in rows if r["eligibility"][product.key]["status"] == "eligible"
        )
        products.append(
            {
                "product": product.key,
                "label": product.label,
                "eligible": eligible,
                "not_eligible": len(rows) - eligible,
            }
        )
    return {"customers": len(rows), "products": products}


def customer_profile(conn, customer_id: str) -> dict | None:
    """Full single-customer analysis for the profile view.

    Returns None when the customer does not exist. The surplus breakdown uses
    the gold identity income - essentials - emi - buffer = surplus, so the
    buffer is derived from stored values rather than re-stating a constant.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM customer_profiles WHERE customer_id = %s", (customer_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        profile = dict(zip([d[0] for d in cur.description], row))

        cur.execute(
            "SELECT p_good_prospect, reasons FROM prospect_scores "
            "WHERE customer_id = %s",
            (customer_id,),
        )
        score_row = cur.fetchone()

        cur.execute(
            "SELECT category, avg_monthly, share, months_seen FROM income_streams "
            "WHERE customer_id = %s ORDER BY share DESC",
            (customer_id,),
        )
        streams = [
            {
                "category": c,
                "avg_monthly": float(a),
                "share": float(s),
                "months_seen": m,
            }
            for c, a, s, m in cur.fetchall()
        ]

        cur.execute(
            "SELECT txn_id, ts, label, channel, category, direction, amount "
            "FROM key_transactions WHERE customer_id = %s ORDER BY ts DESC",
            (customer_id,),
        )
        transactions = [
            {
                "txn_id": t,
                "date": ts.isoformat(),
                "label": label,
                "channel": channel,
                "category": category,
                "direction": direction,
                "amount": float(amount),
            }
            for t, ts, label, channel, category, direction, amount in cur.fetchall()
        ]

    income = float(profile["true_monthly_income"])
    essentials = float(profile["avg_monthly_essentials"])
    emis = float(profile["total_emi"])
    surplus = float(profile["investable_surplus"])
    open_date = profile.get("account_open_date")
    profile["account_open_date"] = open_date.isoformat() if open_date else None
    for key, value in profile.items():
        if hasattr(value, "quantize"):  # Decimal -> float for JSON
            profile[key] = float(value)
        elif (
            hasattr(value, "isoformat") and key != "account_open_date"
        ):  # date/datetime
            profile[key] = value.isoformat()

    return {
        "profile": profile,
        "score": (
            {
                "p_good_prospect": float(score_row[0]),
                "reasons": score_row[1],
            }
            if score_row
            else None
        ),
        "surplus_breakdown": {
            "income": income,
            "essentials": essentials,
            "emis": emis,
            "buffer": round(income - essentials - emis - surplus, 2),
            "surplus": surplus,
        },
        "income_streams": streams,
        "key_transactions": transactions,
        "review": get_review(conn, customer_id),
        "last_share": last_share(conn, customer_id),
        "loan_eligibility": loan_eligibility_for(profile),
    }
