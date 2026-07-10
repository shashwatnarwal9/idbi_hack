"""Load behaviour/engagement signals and compute intent + lead scores to Postgres.

Reads the gold behaviour + engagement parquet (built by aayai.gold.behaviour /
engagement), joins the serving profiles + prospect scores already in Postgres,
and fuses them with aayai.gold.intent / leads into four point-lookup tables:
behaviour_signals, engagement_summary, intent_scores, lead_scores.

Firewall: no "_" ground-truth column is read, and the analyst workflow tables
(review_status, lead_contacts) are never touched, this loader only refreshes
derived data. Run it AFTER aayai.serving.load has populated customer_profiles
and prospect_scores.
"""

from __future__ import annotations

import json

import duckdb
from psycopg2.extras import Json, execute_values

from aayai.gold import intent, leads
from aayai.gold.behaviour import BEHAVIOUR_FILE, BEHAVIOUR_READ
from aayai.gold.engagement import ENGAGEMENT_FILE, ENGAGEMENT_READ
from aayai.serving.contacts import ensure_table as ensure_contacts_table
from aayai.serving.db import connect

DDL = """
DROP TABLE IF EXISTS behaviour_signals;
CREATE TABLE behaviour_signals (
    customer_id    TEXT PRIMARY KEY,
    emi_regularity DOUBLE PRECISION,
    emi_ending     BOOLEAN,
    ending_stream  TEXT,
    is_renter      BOOLEAN,
    rent_months    INTEGER,
    rent_avg       DOUBLE PRECISION,
    sip_discipline DOUBLE PRECISION,
    surplus_trend  DOUBLE PRECISION,
    income_growth  DOUBLE PRECISION,
    months_history INTEGER
);
DROP TABLE IF EXISTS engagement_summary;
CREATE TABLE engagement_summary (
    customer_id                TEXT PRIMARY KEY,
    sessions_90d               INTEGER,
    recency                    DOUBLE PRECISION,
    frequency                  DOUBLE PRECISION,
    strongest_tier             DOUBLE PRECISION,
    offer_click_rate           DOUBLE PRECISION,
    product_affinity           JSONB,
    days_since_last_loan_event INTEGER,
    days_since_strong_event    INTEGER,
    last_event_type            TEXT,
    last_event_at              TIMESTAMPTZ,
    strongest_action           TEXT
);
DROP TABLE IF EXISTS intent_scores;
CREATE TABLE intent_scores (
    customer_id           TEXT PRIMARY KEY,
    intent                DOUBLE PRECISION,
    behavioral_score      DOUBLE PRECISION,
    engagement_score      DOUBLE PRECISION,
    engagement_used       BOOLEAN,
    best_fit_product      TEXT,
    best_fit_reason       TEXT,
    best_repayable_amount DOUBLE PRECISION,
    quadrant              TEXT,
    intent_decile         INTEGER,
    per_product           JSONB,
    composition           JSONB
);
DROP TABLE IF EXISTS lead_scores;
CREATE TABLE lead_scores (
    customer_id           TEXT NOT NULL,
    product               TEXT NOT NULL,
    lead_score            DOUBLE PRECISION,
    product_intent        DOUBLE PRECISION,
    eligible              BOOLEAN,
    quadrant              TEXT,
    urgency               BOOLEAN,
    best_repayable_amount DOUBLE PRECISION,
    trigger               TEXT,
    PRIMARY KEY (customer_id, product)
);
"""

PRODUCTS = ("personal", "auto", "home", "mortgage")


def _trigger(product: str, b: dict) -> str:
    """A short human reason this product suits the customer, from behaviour."""
    if product == "home" and b.get("is_renter"):
        return "Pays rent every month with no home loan on file"
    if product == "personal" and b.get("emi_ending"):
        return "An existing EMI is ending, repayment capacity is freeing up"
    if product == "mortgage" and (b.get("sip_discipline") or 0) >= 0.5:
        return "Consistent SIP discipline suits a long-horizon loan"
    if product == "auto" and (b.get("emi_regularity") or 0) >= 0.5:
        return "Clean EMI record and steady cash flow"
    return "Eligible with repayment capacity for this product"


def _read_parquet_rows(duck, read_expr: str) -> dict[str, dict]:
    cols = [
        c[0] for c in duck.execute(f"DESCRIBE SELECT * FROM {read_expr}").fetchall()
    ]
    out: dict[str, dict] = {}
    for row in duck.execute(f"SELECT * FROM {read_expr}").fetchall():
        rec = dict(zip(cols, row))
        out[rec["customer_id"]] = rec
    return out


def _profiles(pg) -> dict[str, dict]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT p.customer_id, p.true_monthly_income, p.income_volatility,
                   p.total_emi, p.months_history, p.confidence_band,
                   p.investable_surplus, s.p_good_prospect
            FROM customer_profiles p
            LEFT JOIN prospect_scores s USING (customer_id)
            """)
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}


def compute(duck, pg) -> tuple[list, list, list, list]:
    """Return (behaviour_rows, engagement_rows, intent_rows, lead_rows) for load."""
    behaviour = _read_parquet_rows(duck, BEHAVIOUR_READ)
    engagement = (
        _read_parquet_rows(duck, ENGAGEMENT_READ) if ENGAGEMENT_FILE.exists() else {}
    )
    profiles = _profiles(pg)

    behaviour_rows, engagement_rows = [], []
    intent_records: dict[str, dict] = {}
    # first pass: intent + per-product amounts (for cross-book normalisation)
    raw_amounts: list[float] = []
    per_customer_products: dict[str, dict] = {}

    for cid, prof in profiles.items():
        b = behaviour.get(cid, {})
        beh_signals = {
            "emi_regularity": b.get("emi_regularity") or 0.0,
            "surplus_trend": b.get("surplus_trend") or 0.0,
            "is_renter": 1.0 if b.get("is_renter") else 0.0,
            "sip_discipline": b.get("sip_discipline") or 0.0,
            "emi_ending": 1.0 if b.get("emi_ending") else 0.0,
            "income_growth": b.get("income_growth") or 0.0,
        }
        eng = engagement.get(cid)
        has_events = eng is not None
        eng_signals = None
        if has_events:
            affinity = json.loads(eng.get("product_affinity_json") or "{}")
            eng_signals = {
                "recency": eng.get("recency") or 0.0,
                "frequency": eng.get("frequency") or 0.0,
                "strongest_tier": eng.get("strongest_tier") or 0.0,
                "offer_click_rate": eng.get("offer_click_rate") or 0.0,
                "product_affinity": affinity,
            }
        prospect = prof.get("p_good_prospect")
        result = intent.score_customer(
            behavioural_signals=beh_signals,
            engagement_signals=eng_signals,
            has_events=has_events,
            true_monthly_income=float(prof["true_monthly_income"]),
            income_volatility=float(prof["income_volatility"]),
            total_emi=float(prof["total_emi"]),
            months_history=int(prof["months_history"]),
            confidence_band=prof["confidence_band"],
            investable_surplus=float(prof["investable_surplus"]),
            prospect_score=float(prospect) if prospect is not None else None,
        )
        intent_records[cid] = {"result": result, "b": b, "eng": eng, "prof": prof}

        amounts = {}
        for p in PRODUCTS:
            amt = intent.best_repayable(
                p,
                true_monthly_income=float(prof["true_monthly_income"]),
                total_emi=float(prof["total_emi"]),
                investable_surplus=float(prof["investable_surplus"]),
            )["max_principal"]
            amounts[p] = amt
            raw_amounts.append(amt)
        per_customer_products[cid] = amounts

        # collect raw behaviour/engagement table rows
        if b:
            behaviour_rows.append(
                (
                    cid,
                    b.get("emi_regularity"),
                    bool(b.get("emi_ending")),
                    b.get("ending_stream"),
                    bool(b.get("is_renter")),
                    b.get("rent_months"),
                    b.get("rent_avg"),
                    b.get("sip_discipline"),
                    b.get("surplus_trend"),
                    b.get("income_growth"),
                    b.get("months_history"),
                )
            )
        if eng:
            engagement_rows.append(
                (
                    cid,
                    eng.get("sessions_90d"),
                    eng.get("recency"),
                    eng.get("frequency"),
                    eng.get("strongest_tier"),
                    eng.get("offer_click_rate"),
                    Json(json.loads(eng.get("product_affinity_json") or "{}")),
                    eng.get("days_since_last_loan_event"),
                    eng.get("days_since_strong_event"),
                    eng.get("last_event_type"),
                    eng.get("last_event_at"),
                    eng.get("strongest_action"),
                )
            )

    max_amount = max(raw_amounts) if raw_amounts else 1.0
    max_amount = max_amount or 1.0

    # intent deciles across the book
    intents_sorted = sorted(
        (rec["result"]["intent"] for rec in intent_records.values())
    )

    def _decile(value: float) -> int:
        if not intents_sorted:
            return 0
        # position of value in the sorted list -> decile 0..9
        below = sum(1 for x in intents_sorted if x <= value)
        return min(9, int((below - 1) * 10 / len(intents_sorted)))

    intent_rows, lead_rows = [], []
    for cid, rec in intent_records.items():
        result = rec["result"]
        b, eng, prof = rec["b"], rec["eng"], rec["prof"]
        prospect = prof.get("p_good_prospect")
        band = prof["confidence_band"]
        best_amt = (
            result["best_repayable"]["max_principal"]
            if result["best_repayable"]
            else 0.0
        )
        intent_rows.append(
            (
                cid,
                result["intent"],
                result["behavioral_score"],
                result["engagement_score"],
                result["engagement_used"],
                result["best_fit_product"],
                result["best_fit_reason"],
                best_amt,
                leads.quadrant(prospect, result["intent"]),
                _decile(result["intent"]),
                Json(result["per_product_intent"]),
                Json(result["composition"]),
            )
        )
        days_strong = eng.get("days_since_strong_event") if eng else None
        for p in PRODUCTS:
            eligible = p in result["eligible_products"]
            amt = per_customer_products[cid][p]
            lead = leads.lead_score(
                eligible=eligible,
                product_intent=result["per_product_intent"][p],
                prospect_score=float(prospect) if prospect is not None else None,
                suggested_amount_norm=amt / max_amount,
                confidence_band=band,
                emi_ending=bool(b.get("emi_ending")),
                days_since_strong_event=days_strong,
            )
            lead_rows.append(
                (
                    cid,
                    p,
                    lead["lead_score"],
                    result["per_product_intent"][p],
                    eligible,
                    lead["quadrant"],
                    lead["urgency"],
                    amt,
                    _trigger(p, b),
                )
            )
    return behaviour_rows, engagement_rows, intent_rows, lead_rows


def main() -> None:
    """Rebuild the intent/lead serving tables from gold signals."""
    duck = duckdb.connect()
    pg = connect()
    behaviour_rows, engagement_rows, intent_rows, lead_rows = compute(duck, pg)
    with pg, pg.cursor() as cur:
        cur.execute(DDL)
        if behaviour_rows:
            execute_values(
                cur,
                "INSERT INTO behaviour_signals (customer_id, emi_regularity, "
                "emi_ending, ending_stream, is_renter, rent_months, rent_avg, "
                "sip_discipline, surplus_trend, income_growth, months_history) VALUES %s",
                behaviour_rows,
            )
        if engagement_rows:
            execute_values(
                cur,
                "INSERT INTO engagement_summary (customer_id, sessions_90d, recency, "
                "frequency, strongest_tier, offer_click_rate, product_affinity, "
                "days_since_last_loan_event, days_since_strong_event, last_event_type, "
                "last_event_at, strongest_action) VALUES %s",
                engagement_rows,
            )
        execute_values(
            cur,
            "INSERT INTO intent_scores (customer_id, intent, behavioral_score, "
            "engagement_score, engagement_used, best_fit_product, best_fit_reason, "
            "best_repayable_amount, quadrant, intent_decile, per_product, composition) "
            "VALUES %s",
            intent_rows,
        )
        execute_values(
            cur,
            "INSERT INTO lead_scores (customer_id, product, lead_score, product_intent, "
            "eligible, quadrant, urgency, best_repayable_amount, trigger) VALUES %s",
            lead_rows,
        )
    ensure_contacts_table(pg)
    with pg, pg.cursor() as cur:
        for table in (
            "behaviour_signals",
            "engagement_summary",
            "intent_scores",
            "lead_scores",
        ):
            cur.execute(f"SELECT count(*) FROM {table}")
            print(f"[intent-load] {table}: {cur.fetchone()[0]:,} rows")
    pg.close()


if __name__ == "__main__":
    main()
