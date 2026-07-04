"""Isolated storage for uploaded batches.

Every table is keyed by batch_id and is entirely separate from the seeded book
(customer_profiles, prospect_scores, ...). Seeded dashboard queries never read
these tables, and these queries never read the seeded tables, so uploaded data
can never pollute the demo metrics. A batch is fully removable via delete_batch.
"""

from __future__ import annotations

import pandas as pd
from psycopg2.extras import Json, execute_values

from aayai.serving.db import connect
from aayai.serving.queries import loan_eligibility_for

PROFILE_COLS = [
    "customer_id",
    "name",
    "region",
    "income_type",
    "true_monthly_income",
    "declared_monthly_income",
    "income_volatility",
    "avg_monthly_essentials",
    "total_emi",
    "total_sip",
    "investable_surplus",
    "surplus_stability",
    "savings_rate",
    "risk_capacity",
    "months_history",
    "pct_categorized",
    "occupation_declared",
    "confidence_band",
    "p_good_prospect",
    "reasons",
]

DDL = """
CREATE TABLE IF NOT EXISTS upload_batches (
    batch_id           TEXT PRIMARY KEY,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    n_customers        INTEGER,
    n_transactions     INTEGER,
    note               TEXT,
    uploaded_by        TEXT,
    status             TEXT NOT NULL DEFAULT 'analyzed',
    gates              JSONB,
    min_history_months INTEGER,
    merged_at          TIMESTAMPTZ
);
-- migrate pre-existing tables to the gated-ingestion columns (idempotent)
ALTER TABLE upload_batches ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'analyzed';
ALTER TABLE upload_batches ADD COLUMN IF NOT EXISTS gates JSONB;
ALTER TABLE upload_batches ADD COLUMN IF NOT EXISTS min_history_months INTEGER;
ALTER TABLE upload_batches ADD COLUMN IF NOT EXISTS merged_at TIMESTAMPTZ;
ALTER TABLE upload_batches ADD COLUMN IF NOT EXISTS uploaded_by TEXT;
-- append-only audit of merges and reverts of uploaded batches
CREATE TABLE IF NOT EXISTS merge_log (
    id          BIGSERIAL PRIMARY KEY,
    batch_id    TEXT NOT NULL,
    action      TEXT NOT NULL,
    n_customers INTEGER,
    actor       TEXT,
    at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS upload_profiles (
    batch_id                TEXT NOT NULL,
    customer_id             TEXT NOT NULL,
    name                    TEXT,
    region                  TEXT,
    income_type             TEXT,
    true_monthly_income     DOUBLE PRECISION,
    declared_monthly_income DOUBLE PRECISION,
    income_volatility       DOUBLE PRECISION,
    avg_monthly_essentials  DOUBLE PRECISION,
    total_emi               DOUBLE PRECISION,
    total_sip               DOUBLE PRECISION,
    investable_surplus      DOUBLE PRECISION,
    surplus_stability       DOUBLE PRECISION,
    savings_rate            DOUBLE PRECISION,
    risk_capacity           TEXT,
    months_history          INTEGER,
    pct_categorized         DOUBLE PRECISION,
    occupation_declared     TEXT,
    confidence_band         TEXT,
    p_good_prospect         DOUBLE PRECISION,
    reasons                 JSONB,
    PRIMARY KEY (batch_id, customer_id)
);
CREATE TABLE IF NOT EXISTS upload_streams (
    batch_id    TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    category    TEXT,
    avg_monthly DOUBLE PRECISION,
    share       DOUBLE PRECISION,
    months_seen INTEGER
);
CREATE TABLE IF NOT EXISTS upload_transactions (
    batch_id    TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    txn_id      TEXT,
    ts          DATE,
    label       TEXT,
    channel     TEXT,
    category    TEXT,
    direction   TEXT,
    amount      DOUBLE PRECISION
);
"""


# idempotent migration adding the source/provenance columns to the MAIN book so
# merged uploaded customers stay identifiable and accuracy can stay seeded-only
MAIN_SOURCE_DDL = """
ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'seeded';
ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS batch_id TEXT;
ALTER TABLE customer_profiles ADD COLUMN IF NOT EXISTS merged_at TIMESTAMPTZ;
"""


def ensure_tables(conn) -> None:
    """Create the isolated upload tables when missing (idempotent)."""
    with conn, conn.cursor() as cur:
        cur.execute(DDL)


def ensure_main_source_columns(conn) -> None:
    """Add source/batch_id/merged_at to customer_profiles if absent.

    Checks information_schema first and only runs ALTER when a column is missing,
    so the common (already-migrated) path is a cheap SELECT that takes no lock —
    an unconditional ALTER on every request would serialise behind open
    transactions and stall the API.
    """
    with conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.customer_profiles')")
        if cur.fetchone()[0] is None:
            return  # loader creates the table with these columns already
        cur.execute(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'customer_profiles' "
            "AND column_name IN ('source', 'batch_id', 'merged_at')"
        )
        if cur.fetchone()[0] < 3:
            cur.execute(MAIN_SOURCE_DDL)


def save_batch(
    batch_id: str,
    note: str,
    gold: pd.DataFrame,
    names: dict,
    scores: dict | None,
    streams: list[tuple],
    transactions: list[tuple],
    n_transactions: int,
    status: str = "analyzed",
    gates: dict | None = None,
    min_history_months: int | None = None,
    uploaded_by: str | None = None,
) -> None:
    """Persist one analysed batch across the isolated upload tables."""
    conn = connect()
    ensure_tables(conn)
    scores = scores or {}
    profile_rows = []
    for _, r in gold.iterrows():
        cid = str(r["customer_id"])
        proba, reasons = scores.get(cid, (None, []))
        profile_rows.append(
            (
                batch_id,
                cid,
                names.get(cid, cid),
                r.get("region"),
                r["income_type"],
                float(r["true_monthly_income"]),
                (
                    None
                    if pd.isna(r["declared_monthly_income"])
                    else float(r["declared_monthly_income"])
                ),
                float(r["income_volatility"]),
                float(r["avg_monthly_essentials"]),
                float(r["total_emi"]),
                float(r["total_sip"]),
                float(r["investable_surplus"]),
                float(r["surplus_stability"]),
                float(r["savings_rate"]),
                r["risk_capacity"],
                int(r["months_history"]),
                float(r["pct_categorized"]),
                r.get("occupation_declared"),
                r["confidence_band"],
                None if proba is None else float(proba),
                Json(reasons),
            )
        )
    with conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO upload_batches (batch_id, n_customers, n_transactions, "
            "note, uploaded_by, status, gates, min_history_months) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                batch_id,
                len(gold),
                n_transactions,
                note,
                uploaded_by,
                status,
                Json(gates) if gates is not None else None,
                min_history_months,
            ),
        )
        execute_values(
            cur,
            f"INSERT INTO upload_profiles (batch_id, {', '.join(PROFILE_COLS)}) VALUES %s",
            profile_rows,
        )
        execute_values(
            cur,
            "INSERT INTO upload_streams "
            "(batch_id, customer_id, category, avg_monthly, share, months_seen) VALUES %s",
            [(batch_id, *s) for s in streams],
        )
        execute_values(
            cur,
            "INSERT INTO upload_transactions "
            "(batch_id, customer_id, txn_id, ts, label, channel, category, direction, amount) "
            "VALUES %s",
            [
                (batch_id, cid, tid, ts, label, ch, cat, d, amt)
                for (tid, cid, ts, label, ch, cat, d, amt) in transactions
            ],
        )
    conn.close()


def batch_exists(conn, batch_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM upload_batches WHERE batch_id = %s", (batch_id,))
        return cur.fetchone() is not None


# Internal status vocabulary -> the phase shown in the "Past Batches" list.
# analyzed/passed batches stay isolated previews until an explicit merge; only a
# merged batch is part of the operational book; a failed gate is terminal.
_PHASE_BY_STATUS = {
    "analyzed": "isolated_preview",
    "passed": "isolated_preview",
    "merged": "validated_merged",
    "failed": "failed_gate",
    "reverted": "reverted",
}


def _auto_name(batch_id: str, created_at) -> str:
    """Human-friendly fallback name when the analyst left the note blank."""
    return f"Batch {batch_id[:8]} · {created_at:%Y-%m-%d %H:%M}"


def _gate_failures(gates: dict | None) -> list[dict]:
    """Flatten a failed batch's GE gate result into failure-card rows.

    The gate JSON is {passed, suites: [{suite, checks, failed: [type, ...]}]};
    each failed expectation type becomes one row matching the shared
    ValidationFailuresCard shape ({expectation_name, layer, detail, severity}).
    Returns [] for a passing/preview batch.
    """
    if not gates:
        return []
    out: list[dict] = []
    for suite in gates.get("suites", []) or []:
        layer = suite.get("suite", "")
        for exp in suite.get("failed", []) or []:
            out.append(
                {
                    "expectation_name": exp,
                    "layer": layer,
                    "detail": f"Hard {layer} expectation failed on the uploaded batch.",
                    "severity": "hard",
                }
            )
    return out


def _batch_row(row) -> dict:
    b, ts, nc, nt, note, uploaded_by, status, gates, mhm, merged = row
    return {
        "batch_id": b,
        "created_at": ts.isoformat(),
        "n_customers": nc,
        "n_transactions": nt,
        "note": note,
        "name": note or _auto_name(b, ts),
        "uploaded_by": uploaded_by,
        "status": status,
        "phase": _PHASE_BY_STATUS.get(status, status),
        "gates": gates,
        "failure_reasons": _gate_failures(gates) if status == "failed" else [],
        "min_history_months": mhm,
        "merged_at": merged.isoformat() if merged else None,
    }


_BATCH_COLS = (
    "batch_id, created_at, n_customers, n_transactions, note, uploaded_by, "
    "status, gates, min_history_months, merged_at"
)


def list_batches(conn) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_BATCH_COLS} FROM upload_batches ORDER BY created_at DESC"
        )
        return [_batch_row(r) for r in cur.fetchall()]


def get_batch(conn, batch_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_BATCH_COLS} FROM upload_batches WHERE batch_id = %s", (batch_id,)
        )
        row = cur.fetchone()
    return _batch_row(row) if row else None


def summary(conn, batch_id: str) -> dict:
    """Batch-level aggregates (no accuracy — uploads have no ground truth)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*), avg(true_monthly_income),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY investable_surplus),
                   count(*) FILTER (WHERE confidence_band = 'high'),
                   count(*) FILTER (WHERE confidence_band = 'medium'),
                   count(*) FILTER (WHERE confidence_band = 'low'),
                   count(*) FILTER (WHERE p_good_prospect >= 0.5)
            FROM upload_profiles WHERE batch_id = %s
            """,
            (batch_id,),
        )
        n, inc, sur, high, med, low, prospects = cur.fetchone()
    return {
        "customers": n,
        "avg_reconstructed": float(inc) if inc is not None else None,
        "median_surplus": float(sur) if sur is not None else None,
        "bands": {"high": high, "medium": med, "low": low},
        "high_prospects": prospects,
    }


def ranked(conn, batch_id: str, bands: list[str] | None = None) -> list[dict]:
    where = "WHERE batch_id = %s"
    params: list = [batch_id]
    if bands is not None:
        where += " AND confidence_band = ANY(%s)"
        params.append(list(bands))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT customer_id, name, p_good_prospect, confidence_band, reasons
            FROM upload_profiles {where}
            ORDER BY p_good_prospect DESC NULLS LAST, customer_id
            """,
            params,
        )
        rows = cur.fetchall()
    return [
        {
            "rank": i,
            "customer_id": cid,
            "name": name,
            "score": float(score) if score is not None else 0.0,
            "band": band,
            "reasons": reasons,
            "reviewed": False,
        }
        for i, (cid, name, score, band, reasons) in enumerate(rows, 1)
    ]


def profile(conn, batch_id: str, customer_id: str) -> dict | None:
    """Full analysis for one uploaded customer, same shape as the seeded view."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM upload_profiles WHERE batch_id = %s AND customer_id = %s",
            (batch_id, customer_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        p = dict(zip([d[0] for d in cur.description], row))

        cur.execute(
            "SELECT category, avg_monthly, share, months_seen FROM upload_streams "
            "WHERE batch_id = %s AND customer_id = %s ORDER BY share DESC",
            (batch_id, customer_id),
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
            "FROM upload_transactions WHERE batch_id = %s AND customer_id = %s ORDER BY ts DESC",
            (batch_id, customer_id),
        )
        transactions = [
            {
                "txn_id": t,
                "date": ts.isoformat(),
                "label": label,
                "channel": ch,
                "category": cat,
                "direction": d,
                "amount": float(amt),
            }
            for t, ts, label, ch, cat, d, amt in cur.fetchall()
        ]

    income = float(p["true_monthly_income"])
    essentials = float(p["avg_monthly_essentials"])
    emis = float(p["total_emi"])
    surplus = float(p["investable_surplus"])
    declared = p["declared_monthly_income"]
    profile_out = {
        "customer_id": p["customer_id"],
        "name": p["name"],
        "region": p["region"],
        "income_type": p["income_type"],
        "true_monthly_income": income,
        "declared_monthly_income": float(declared) if declared is not None else None,
        "income_volatility": float(p["income_volatility"]),
        "avg_monthly_essentials": essentials,
        "total_emi": emis,
        "total_sip": float(p["total_sip"]),
        "investable_surplus": surplus,
        "surplus_stability": float(p["surplus_stability"]),
        "savings_rate": float(p["savings_rate"]),
        "risk_capacity": p["risk_capacity"],
        "months_history": p["months_history"],
        "pct_categorized": float(p["pct_categorized"]),
        "occupation_declared": p["occupation_declared"],
        "confidence_band": p["confidence_band"],
        "account_open_date": None,
    }
    return {
        "profile": profile_out,
        "score": (
            {"p_good_prospect": float(p["p_good_prospect"]), "reasons": p["reasons"]}
            if p["p_good_prospect"] is not None
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
        "review": None,
        "loan_eligibility": loan_eligibility_for(
            profile_out,
            float(p["p_good_prospect"]) if p["p_good_prospect"] is not None else None,
        ),
    }


def rename_batch(conn, batch_id: str, name: str) -> bool:
    """Set the editable display name (stored in `note`) for a batch."""
    with conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE upload_batches SET note = %s WHERE batch_id = %s",
            (name, batch_id),
        )
        return cur.rowcount > 0


def delete_batch(conn, batch_id: str) -> bool:
    """Discard a staged batch entirely from every upload table."""
    with conn, conn.cursor() as cur:
        cur.execute("DELETE FROM upload_profiles WHERE batch_id = %s", (batch_id,))
        cur.execute("DELETE FROM upload_streams WHERE batch_id = %s", (batch_id,))
        cur.execute("DELETE FROM upload_transactions WHERE batch_id = %s", (batch_id,))
        cur.execute("DELETE FROM upload_batches WHERE batch_id = %s", (batch_id,))
        return cur.rowcount > 0


# columns copied from upload_profiles into the main customer_profiles on merge
_MERGE_PROFILE_COLS = [
    "customer_id",
    "name",
    "region",
    "income_type",
    "true_monthly_income",
    "income_volatility",
    "avg_monthly_essentials",
    "total_emi",
    "total_sip",
    "investable_surplus",
    "surplus_stability",
    "savings_rate",
    "risk_capacity",
    "months_history",
    "pct_categorized",
    "occupation_declared",
    "declared_monthly_income",
    "confidence_band",
]


def merge_batch(conn, batch_id: str, merged_by: str) -> dict:
    """Permanently merge a PASSED batch into the main book, tagged source='uploaded'.

    Only batches whose GE gates passed may be merged. Merged customers carry
    source/batch_id/merged_at so they stay identifiable, and enter every
    operational view — but never the seeded-only accuracy metrics. Append-only
    logged. Returns per-table insert counts.
    """
    ensure_main_source_columns(conn)
    batch = get_batch(conn, batch_id)
    if batch is None:
        raise ValueError(f"batch '{batch_id}' not found")
    if batch["status"] != "passed":
        raise ValueError(
            f"batch '{batch_id}' has status '{batch['status']}'; only 'passed' "
            "batches (GE gates cleared) can be merged"
        )

    cols = ", ".join(_MERGE_PROFILE_COLS)
    with conn, conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO customer_profiles
                ({cols}, account_open_date, source, batch_id, merged_at)
            SELECT {cols}, NULL, 'uploaded', %s, now()
            FROM upload_profiles WHERE batch_id = %s
            ON CONFLICT (customer_id) DO NOTHING
            """,
            (batch_id, batch_id),
        )
        merged = cur.rowcount
        cur.execute(
            """
            INSERT INTO prospect_scores (customer_id, p_good_prospect, reasons)
            SELECT customer_id, p_good_prospect, reasons
            FROM upload_profiles WHERE batch_id = %s
            ON CONFLICT (customer_id) DO NOTHING
            """,
            (batch_id,),
        )
        cur.execute(
            """
            INSERT INTO income_streams (customer_id, category, avg_monthly, share, months_seen)
            SELECT customer_id, category, avg_monthly, share, months_seen
            FROM upload_streams WHERE batch_id = %s
            ON CONFLICT (customer_id, category) DO NOTHING
            """,
            (batch_id,),
        )
        cur.execute(
            """
            INSERT INTO key_transactions
                (txn_id, customer_id, ts, label, channel, category, direction, amount)
            SELECT txn_id, customer_id, ts, label, channel, category, direction, amount
            FROM upload_transactions WHERE batch_id = %s
            ON CONFLICT (txn_id) DO NOTHING
            """,
            (batch_id,),
        )
        cur.execute(
            "UPDATE upload_batches SET status = 'merged', merged_at = now() "
            "WHERE batch_id = %s",
            (batch_id,),
        )
        cur.execute(
            "INSERT INTO merge_log (batch_id, action, n_customers, actor) "
            "VALUES (%s, 'merge', %s, %s)",
            (batch_id, merged, merged_by),
        )
    skipped = batch["n_customers"] - merged
    return {
        "batch_id": batch_id,
        "merged": merged,
        "skipped_duplicates": skipped,
        "status": "merged",
    }


def revert_batch(conn, batch_id: str, reverted_by: str) -> dict:
    """Soft-delete a merged batch from the main book by batch_id (roll back)."""
    ensure_main_source_columns(conn)
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT customer_id FROM customer_profiles "
            "WHERE batch_id = %s AND source = 'uploaded'",
            (batch_id,),
        )
        ids = [r[0] for r in cur.fetchall()]
        if ids:
            cur.execute(
                "DELETE FROM key_transactions WHERE customer_id = ANY(%s)", (ids,)
            )
            cur.execute(
                "DELETE FROM income_streams WHERE customer_id = ANY(%s)", (ids,)
            )
            cur.execute(
                "DELETE FROM prospect_scores WHERE customer_id = ANY(%s)", (ids,)
            )
            cur.execute(
                "DELETE FROM customer_profiles WHERE batch_id = %s AND source = 'uploaded'",
                (batch_id,),
            )
        cur.execute(
            "UPDATE upload_batches SET status = 'reverted' WHERE batch_id = %s",
            (batch_id,),
        )
        cur.execute(
            "INSERT INTO merge_log (batch_id, action, n_customers, actor) "
            "VALUES (%s, 'revert', %s, %s)",
            (batch_id, len(ids), reverted_by),
        )
    return {"batch_id": batch_id, "removed": len(ids), "status": "reverted"}


def merge_history(conn, batch_id: str) -> list[dict]:
    """Append-only merge/revert audit rows for a batch."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT action, n_customers, actor, at FROM merge_log "
            "WHERE batch_id = %s ORDER BY at",
            (batch_id,),
        )
        return [
            {"action": a, "n_customers": n, "actor": actor, "at": at.isoformat()}
            for a, n, actor, at in cur.fetchall()
        ]
