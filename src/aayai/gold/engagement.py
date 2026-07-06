"""Gold engagement signals — one row per customer from marketing EVENTS only.

Feeds the engagement (E) half of intent, which is worth exactly 10% of the
fused score. A customer with no events gets no row here; the intent layer then
sets has_events=False and uses behaviour alone — engagement is never fabricated.

Firewall: reads only the event's own fields (type/product/session/timestamp),
never the carried intent-propensity ground-truth column, and nothing about
analyst or app activity on the customer's account.
"""

from __future__ import annotations

import json
import math
from datetime import datetime

import duckdb

from aayai.bronze.ingest import EVENTS_READ
from aayai.paths import GOLD_DIR

ENGAGEMENT_FILE = GOLD_DIR / "engagement_summary.parquet"
ENGAGEMENT_READ = f"read_parquet('{ENGAGEMENT_FILE.as_posix()}')"

PRODUCTS = ("personal", "auto", "home", "mortgage")

# Funnel tier weight per event type (0-1) — deeper intent scores higher.
TIER_WEIGHTS: dict[str, float] = {
    "app_open": 0.2,
    "login": 0.2,
    "product_page_view": 0.4,
    "emi_calculator_use": 0.7,
    "eligibility_check": 0.8,
    "offer_email_sent": 0.3,
    "offer_email_open": 0.4,
    "offer_email_click": 0.6,
    "enquiry_submitted": 1.0,
    "document_upload": 1.0,
    "application_started": 1.0,
    "branch_visit": 0.9,
    "call_center_inbound": 0.7,
}

# Events that signal genuine loan interest (drive the recency signal).
LOAN_EVENTS = frozenset(
    {
        "product_page_view",
        "emi_calculator_use",
        "eligibility_check",
        "enquiry_submitted",
        "document_upload",
        "application_started",
        "offer_email_click",
        "branch_visit",
    }
)
# Strong recent actions that also drive lead urgency.
STRONG_EVENTS = frozenset({"enquiry_submitted", "eligibility_check"})

RECENCY_HALFLIFE_DAYS = 30.0  # recency decays by half every 30 days
SESSION_WINDOW_DAYS = 90  # "sessions_90d" window
FREQ_SATURATION = 8.0  # sessions at which the frequency signal saturates to 1.0


def recency_decay(days: float | None) -> float:
    """0-1 recency: 1.0 today, halving every RECENCY_HALFLIFE_DAYS. None -> 0."""
    if days is None or days < 0:
        return 0.0
    return round(0.5 ** (days / RECENCY_HALFLIFE_DAYS), 4)


def summarize_events(events: list[dict], now: datetime) -> dict:
    """Engagement signals for ONE customer's events. Pure and reusable.

    Each event is a dict with `timestamp` (datetime), `event_type` (str) and
    optional `product` (str). Returns the 0-1 signals intent.engagement_score
    consumes plus display fields; has_events is False for an empty list.
    """
    if not events:
        return {"has_events": False}

    sessions_90d = {
        e.get("session_id")
        for e in events
        if e.get("session_id") and (now - e["timestamp"]).days <= SESSION_WINDOW_DAYS
    }
    strongest_tier = max(TIER_WEIGHTS.get(e["event_type"], 0.2) for e in events)

    loan_events = [e for e in events if e["event_type"] in LOAN_EVENTS]
    last_loan = max((e["timestamp"] for e in loan_events), default=None)
    days_since_loan = (now - last_loan).days if last_loan else None

    strong = [e for e in events if e["event_type"] in STRONG_EVENTS]
    last_strong = max((e["timestamp"] for e in strong), default=None)
    days_since_strong = (now - last_strong).days if last_strong else None

    # per-product affinity: share of product-referencing events per product
    product_counts = {p: 0 for p in PRODUCTS}
    for e in events:
        prod = (e.get("product") or "").strip()
        if prod in product_counts:
            product_counts[prod] += 1
    total_prod = sum(product_counts.values())
    affinity = {
        p: round(product_counts[p] / total_prod, 4) if total_prod else 0.0
        for p in PRODUCTS
    }

    sends = sum(1 for e in events if e["event_type"] == "offer_email_sent")
    clicks = sum(1 for e in events if e["event_type"] == "offer_email_click")
    offer_click_rate = round(clicks / sends, 4) if sends else 0.0

    last_event = max(events, key=lambda e: e["timestamp"])
    strongest_action = max(events, key=lambda e: TIER_WEIGHTS.get(e["event_type"], 0.2))

    return {
        "has_events": True,
        "sessions_90d": len(sessions_90d),
        "recency": recency_decay(days_since_loan),
        "frequency": round(min(len(sessions_90d) / FREQ_SATURATION, 1.0), 4),
        "strongest_tier": round(strongest_tier, 4),
        "offer_click_rate": offer_click_rate,
        "product_affinity": affinity,
        "days_since_last_loan_event": days_since_loan,
        "days_since_strong_event": days_since_strong,
        "last_event_type": last_event["event_type"],
        "last_event_at": last_event["timestamp"].isoformat(),
        "strongest_action": strongest_action["event_type"],
    }


def engagement_rows(con: duckdb.DuckDBPyConnection, events_read: str, now: datetime):
    """Summarize every customer's events into engagement rows (one per engaged cid)."""
    rows = con.execute(f"""
        SELECT customer_id, "timestamp", event_type, product, session_id
        FROM {events_read} ORDER BY customer_id, "timestamp"
        """).fetchall()
    by_customer: dict[str, list[dict]] = {}
    for cid, ts, etype, product, session in rows:
        by_customer.setdefault(cid, []).append(
            {
                "timestamp": ts,
                "event_type": etype,
                "product": product,
                "session_id": session,
            }
        )
    out = []
    for cid, events in by_customer.items():
        summary = summarize_events(events, now)
        summary["customer_id"] = cid
        out.append(summary)
    return out


def _data_now(con: duckdb.DuckDBPyConnection, events_read: str) -> datetime:
    """Recency is measured against the latest event in the book (the data horizon)."""
    return con.execute(f'SELECT max("timestamp") FROM {events_read}').fetchone()[0]


def build(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild engagement signals from events bronze, if events are present."""
    from aayai.bronze.ingest import EVENTS_DIR

    if not EVENTS_DIR.exists():
        print("[engagement] no events bronze — skipping (optional source)")
        return
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    ENGAGEMENT_FILE.unlink(missing_ok=True)
    now = _data_now(con, EVENTS_READ)
    rows = engagement_rows(con, EVENTS_READ, now)
    records = [
        {
            "customer_id": r["customer_id"],
            "sessions_90d": r["sessions_90d"],
            "recency": r["recency"],
            "frequency": r["frequency"],
            "strongest_tier": r["strongest_tier"],
            "offer_click_rate": r["offer_click_rate"],
            "product_affinity_json": json.dumps(r["product_affinity"]),
            "days_since_last_loan_event": r["days_since_last_loan_event"],
            "days_since_strong_event": r["days_since_strong_event"],
            "last_event_type": r["last_event_type"],
            "last_event_at": r["last_event_at"],
            "strongest_action": r["strongest_action"],
        }
        for r in rows
    ]
    con.register("_engagement_df", _as_relation(con, records))
    con.execute(
        f"COPY (SELECT * FROM _engagement_df) TO '{ENGAGEMENT_FILE.as_posix()}' (FORMAT PARQUET)"
    )
    con.unregister("_engagement_df")


def _as_relation(con: duckdb.DuckDBPyConnection, records: list[dict]):
    import pandas as pd

    return pd.DataFrame(records)


def verify(con: duckdb.DuckDBPyConnection) -> None:
    """Print engagement coverage and a couple of aggregate signals."""
    if not ENGAGEMENT_FILE.exists():
        print("[engagement] no engagement_summary.parquet")
        return
    n, sess, rec = con.execute(
        f"SELECT count(*), round(avg(sessions_90d),1), round(avg(recency),3) "
        f"FROM {ENGAGEMENT_READ}"
    ).fetchone()
    print(
        f"[engagement] {n} engaged customers | avg sessions_90d={sess} avg recency={rec}"
    )


def main() -> None:
    con = duckdb.connect()
    build(con)
    verify(con)


if __name__ == "__main__":
    main()
