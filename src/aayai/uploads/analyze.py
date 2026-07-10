"""Run an uploaded CSV pair through the existing pipeline in an isolated batch.

The uploaded data is written to a private temp directory as bronze/customers
Parquet with the "_" ground-truth columns present but NULL, so the EXACT silver
and gold SQL used for the seeded book runs unchanged. Bands reuse the
validation stage's BAND_RULES; scoring reuses the trained model + SHAP. No
accuracy is computed (uploads have no ground truth). Results are written to the
isolated upload_* tables; the temp Parquet (raw transactions) is deleted after.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path

import duckdb

from aayai.model.train import MODEL_FILE, encode_features
from aayai.serving.load import load_income_streams, load_key_transactions, score_frame
from aayai.uploads import store
from aayai.uploads.schema import (
    CREDIT_TOKENS,
    CUSTOMER_FIELDS,
    DEBIT_TOKENS,
    TRANSACTION_FIELDS,
    resolve_mapping,
)
from aayai.util import run_sql_file


class UploadValidationError(Exception):
    """Fatal validation problem; carries a list of human-readable errors."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


class HistoryGateError(UploadValidationError):
    """Rejected before the pipeline: one or more customers have < min months."""

    def __init__(self, min_months: int, failures: list[dict]):
        listed = ", ".join(f"{f['customer_id']} ({f['months']}mo)" for f in failures)
        super().__init__(
            [
                f"{len(failures)} customer(s) have less than the required "
                f"{min_months} months of history: {listed}."
            ]
        )
        self.min_months = min_months
        self.failures = failures


def _history_report(duck: duckdb.DuckDBPyConnection) -> list[dict]:
    """Per-customer transaction history length, derived from the date span."""
    rows = duck.execute("""
        SELECT customer_id,
               (year(max(ts)) - year(min(ts))) * 12
                   + (month(max(ts)) - month(min(ts))) + 1 AS span_months,
               count(DISTINCT (year(ts) * 100 + month(ts)))  AS active_months
        FROM typed_txn
        WHERE customer_id IS NOT NULL AND customer_id <> '' AND ts IS NOT NULL
        GROUP BY 1 ORDER BY 2
    """).fetchall()
    return [
        {"customer_id": c, "months": int(span), "active_months": int(active)}
        for c, span, active in rows
    ]


def _run_hard_gates(silver_df, gold_df) -> dict:
    """Run the pipeline's GE hard gates on the uploaded batch (same suites).

    Reuses aayai.validation.run's silver_gate and gold_gate suites, the exact
    gates that stop the seeded pipeline before scoring on failure.
    """
    from aayai.validation.run import (
        build_context,
        gold_gate_suite,
        run_suite,
        silver_gate_suite,
    )

    context = build_context()
    suites = []
    all_passed = True
    for name, suite, df in (
        ("silver_gate", silver_gate_suite(), silver_df),
        ("gold_gate", gold_gate_suite(), gold_df),
    ):
        result = run_suite(context, f"ingest_{name}", suite, df)
        failed = [r.expectation_config.type for r in result.results if not r.success]
        suites.append(
            {
                "suite": name,
                "passed": bool(result.success),
                "checks": len(result.results),
                "failed": failed,
            }
        )
        all_passed = all_passed and bool(result.success)
    return {"passed": all_passed, "suites": suites}


def _hive_read(directory: Path) -> str:
    return (
        f"read_parquet('{directory.as_posix()}/*/*/*.parquet', "
        "hive_partitioning=1, hive_types_autocast=0)"
    )


def _headers(duck: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [d[0] for d in duck.execute(f"SELECT * FROM {table} LIMIT 0").description]


def _sql_set(tokens: set[str]) -> str:
    return ", ".join(f"'{t}'" for t in sorted(tokens))


def _write_bronze(
    duck, txn_csv: Path, mapping: dict, bronze_dir: Path, batch_id: str
) -> dict:
    """Type/validate transactions and write partitioned bronze Parquet.

    Returns an issue report; raises UploadValidationError if nothing is usable.
    """
    cust = mapping["customer_id"]
    ts = mapping["timestamp"]
    amt = mapping["amount"]
    typ = mapping["type"]
    narr = mapping["narration"]
    bal = mapping.get("balance_after")
    bal_expr = f'TRY_CAST("{bal}" AS DOUBLE)' if bal else "CAST(NULL AS DOUBLE)"

    duck.execute(f"""
        CREATE OR REPLACE TEMP TABLE typed_txn AS
        SELECT
            trim("{cust}")                       AS customer_id,
            TRY_CAST("{ts}" AS TIMESTAMP)        AS ts,
            TRY_CAST("{amt}" AS DOUBLE)          AS amount,
            CASE
                WHEN upper(trim("{typ}")) IN ({_sql_set(CREDIT_TOKENS)}) THEN 'CREDIT'
                WHEN upper(trim("{typ}")) IN ({_sql_set(DEBIT_TOKENS)})  THEN 'DEBIT'
                ELSE NULL END                    AS txn_type,
            "{narr}"                             AS narration,
            {bal_expr}                           AS balance
        FROM raw_txn
    """)

    total, bad_cust, bad_date, bad_amt, bad_type, valid = duck.execute("""
        SELECT count(*),
               count(*) FILTER (WHERE customer_id IS NULL OR customer_id = ''),
               count(*) FILTER (WHERE ts IS NULL),
               count(*) FILTER (WHERE amount IS NULL OR amount <= 0),
               count(*) FILTER (WHERE txn_type IS NULL),
               count(*) FILTER (WHERE customer_id IS NOT NULL AND customer_id <> ''
                    AND ts IS NOT NULL AND amount IS NOT NULL AND amount > 0
                    AND txn_type IS NOT NULL)
        FROM typed_txn
    """).fetchone()

    if valid == 0:
        raise UploadValidationError(
            [
                f"No usable transactions after validation "
                f"({total} rows read; all failed date/amount/type checks)."
            ]
        )

    if bronze_dir.exists():
        shutil.rmtree(bronze_dir)
    duck.execute(f"""
        COPY (
            SELECT
                '{batch_id}-' || CAST(row_number() OVER () AS VARCHAR) AS txn_id,
                customer_id, ts AS "timestamp", txn_type, amount,
                COALESCE(balance, 0.0) AS balance, narration,
                CAST(year(ts) AS VARCHAR)                    AS year,
                lpad(CAST(month(ts) AS VARCHAR), 2, '0')     AS month,
                CAST(NULL AS VARCHAR)  AS _true_category,
                CAST(NULL AS BOOLEAN)  AS _is_income
            FROM typed_txn
            WHERE customer_id IS NOT NULL AND customer_id <> ''
              AND ts IS NOT NULL AND amount IS NOT NULL AND amount > 0
              AND txn_type IS NOT NULL
        ) TO '{bronze_dir.as_posix()}' (FORMAT PARQUET, PARTITION_BY (year, month))
    """)

    issues = []
    skipped = total - valid
    if skipped:
        parts = []
        if bad_date:
            parts.append(f"{bad_date} unparseable dates")
        if bad_amt:
            parts.append(f"{bad_amt} non-positive/invalid amounts")
        if bad_type:
            parts.append(f"{bad_type} unrecognised CR/DR values")
        if bad_cust:
            parts.append(f"{bad_cust} missing customer ids")
        issues.append(
            f"{skipped} of {total} transaction rows skipped ({', '.join(parts)})."
        )
    return {"issues": issues, "rows_total": total, "rows_valid": valid}


def _write_customers(
    duck, cust_csv: Path | None, mapping: dict, customers_file: Path
) -> dict:
    """Write customers Parquet, auto-filling customers seen only in transactions."""
    if cust_csv is not None:
        cid = mapping["customer_id"]
        name = f'"{mapping["name"]}"' if "name" in mapping else "customer_id"
        inc = (
            f'TRY_CAST("{mapping["declared_monthly_income"]}" AS DOUBLE)'
            if "declared_monthly_income" in mapping
            else "CAST(NULL AS DOUBLE)"
        )
        occ = (
            f'"{mapping["occupation_declared"]}"'
            if "occupation_declared" in mapping
            else "CAST(NULL AS VARCHAR)"
        )
        region = (
            f'"{mapping["region"]}"' if "region" in mapping else "CAST(NULL AS VARCHAR)"
        )
        duck.execute(f"""
            CREATE OR REPLACE TEMP TABLE uploaded_customers AS
            SELECT trim("{cid}") AS customer_id, {name} AS name, {inc} AS declared_monthly_income,
                   {occ} AS occupation_declared, {region} AS region
            FROM raw_cust WHERE trim("{cid}") IS NOT NULL AND trim("{cid}") <> ''
        """)
    else:
        duck.execute("""
            CREATE OR REPLACE TEMP TABLE uploaded_customers AS
            SELECT CAST(NULL AS VARCHAR) AS customer_id, CAST(NULL AS VARCHAR) AS name,
                   CAST(NULL AS DOUBLE) AS declared_monthly_income,
                   CAST(NULL AS VARCHAR) AS occupation_declared,
                   CAST(NULL AS VARCHAR) AS region
            WHERE false
        """)

    # customers that appear in transactions but not in the customers file
    auto = duck.execute("""
        SELECT count(DISTINCT t.customer_id)
        FROM (SELECT DISTINCT customer_id FROM typed_txn
              WHERE customer_id IS NOT NULL AND customer_id <> '') t
        LEFT JOIN uploaded_customers c USING (customer_id)
        WHERE c.customer_id IS NULL
    """).fetchone()[0]

    customers_file.unlink(missing_ok=True)
    duck.execute(f"""
        COPY (
            WITH declared AS (
                SELECT customer_id, max(name) AS name,
                       max(declared_monthly_income) AS declared_monthly_income,
                       max(occupation_declared) AS occupation_declared,
                       max(region) AS region
                FROM uploaded_customers GROUP BY 1
            ),
            txn_ids AS (
                SELECT DISTINCT customer_id FROM typed_txn
                WHERE customer_id IS NOT NULL AND customer_id <> ''
            )
            SELECT
                x.customer_id,
                COALESCE(d.name, x.customer_id)   AS name,
                d.region                          AS city,
                d.occupation_declared             AS occupation_declared,
                d.declared_monthly_income         AS declared_monthly_income,
                CAST(NULL AS VARCHAR) AS _true_occupation,
                CAST(NULL AS DOUBLE)  AS _true_monthly_income,
                CAST(NULL AS BOOLEAN) AS _is_good_prospect
            FROM txn_ids x
            LEFT JOIN declared d USING (customer_id)
        ) TO '{customers_file.as_posix()}' (FORMAT PARQUET)
    """)
    issues = []
    if auto:
        issues.append(
            f"{auto} customer id(s) appeared in transactions but not the customers "
            "file; analysed with declared income unavailable."
        )
    return {"issues": issues}


def _band(months: int, pct: float) -> str:
    from aayai.validation.run import BAND_RULES

    hi, med = BAND_RULES["high"], BAND_RULES["medium"]
    if months >= hi["months"] and pct >= hi["pct"]:
        return "high"
    if months >= med["months"] and pct >= med["pct"]:
        return "medium"
    return "low"


def analyze_upload(
    transactions_path: Path,
    customers_path: Path | None,
    txn_override: dict | None = None,
    cust_override: dict | None = None,
    note: str = "",
    min_history_months: int | None = None,
    run_gates: bool = False,
    uploaded_by: str | None = None,
) -> dict:
    """Validate, run the pipeline in isolation, persist the batch, return summary.

    Args:
        min_history_months: when set, every customer must have at least this many
            months of history or the whole upload is rejected before the pipeline
            (raises HistoryGateError with a per-customer report).
        run_gates: when True, run the pipeline's GE hard gates on the batch and
            only score/pass it if they succeed (mirrors the DAG stopping before
            scoring on gate failure). Gated batches are mergeable; preview batches
            (run_gates=False) are isolated-only.

    Raises UploadValidationError on fatal schema/type problems (missing required
    columns, nothing usable), so the caller can return a clean 422.
    """
    duck = duckdb.connect()
    duck.execute(
        f"CREATE TEMP TABLE raw_txn AS "
        f"SELECT * FROM read_csv_auto('{transactions_path.as_posix()}', all_varchar=true)"
    )
    txn_map, txn_missing = resolve_mapping(
        _headers(duck, "raw_txn"), TRANSACTION_FIELDS, txn_override
    )
    if txn_missing:
        raise UploadValidationError(
            [
                f"Transactions CSV is missing required column(s): {', '.join(txn_missing)}. "
                f"Detected headers: {', '.join(_headers(duck, 'raw_txn'))}."
            ]
        )

    cust_map: dict = {}
    if customers_path is not None:
        duck.execute(
            f"CREATE TEMP TABLE raw_cust AS "
            f"SELECT * FROM read_csv_auto('{customers_path.as_posix()}', all_varchar=true)"
        )
        cust_map, cust_missing = resolve_mapping(
            _headers(duck, "raw_cust"), CUSTOMER_FIELDS, cust_override
        )
        if cust_missing:
            raise UploadValidationError(
                [
                    f"Customers CSV is missing required column(s): {', '.join(cust_missing)}. "
                    f"Detected headers: {', '.join(_headers(duck, 'raw_cust'))}."
                ]
            )

    batch_id = f"BATCH-{uuid.uuid4().hex[:10]}"
    work = Path(tempfile.mkdtemp(prefix="aayai-upload-"))
    try:
        bronze_dir = work / "bronze"
        customers_file = work / "customers.parquet"
        silver_dir = work / "silver"
        gold_file = work / "gold.parquet"

        report = _write_bronze(duck, transactions_path, txn_map, bronze_dir, batch_id)

        # STEP 1, mandatory history gate, BEFORE the pipeline runs
        history = _history_report(duck)
        if min_history_months is not None:
            failures = [h for h in history if h["months"] < min_history_months]
            if failures:
                raise HistoryGateError(min_history_months, failures)

        report_c = _write_customers(
            duck, customers_path if customers_path else None, cust_map, customers_file
        )

        # identical silver + gold SQL as the seeded book
        run_sql_file(
            duck,
            "silver_transactions.sql",
            bronze_read=_hive_read(bronze_dir),
            out_dir=silver_dir.as_posix(),
        )
        silver_read = _hive_read(silver_dir)
        run_sql_file(
            duck,
            "gold_customer_profiles.sql",
            silver_read=silver_read,
            customers_file=customers_file.as_posix(),
            out_file=gold_file.as_posix(),
        )

        gold = duck.execute(
            f"SELECT * FROM read_parquet('{gold_file.as_posix()}')"
        ).df()
        if gold.empty:
            raise UploadValidationError(
                ["Pipeline produced no customer profiles from the uploaded data."]
            )
        gold["confidence_band"] = [
            _band(int(m), float(p))
            for m, p in zip(gold["months_history"], gold["pct_categorized"])
        ]

        # STEP 2, GE hard gates (the pipeline's quality gate)
        gates = None
        if run_gates:
            silver_df = duck.execute(
                f"SELECT txn_id, customer_id, category, direction, amount, "
                f"is_income, parse_confidence FROM {silver_read}"
            ).df()
            gates = _run_hard_gates(silver_df, gold)
        gates_ok = gates is None or gates["passed"]

        # Score only when the gates pass (matches the DAG: no scoring on gate
        # fail). The trained model is a build artifact that may be absent in a
        # cloud deployment; if so, still deliver profiles/bands/eligibility and
        # note that the prospect score is unavailable rather than crashing.
        scores = None
        if gates_ok and MODEL_FILE.exists():
            X = encode_features(gold)
            scores = {
                cid: (proba, reasons)
                for cid, proba, reasons in score_frame(X, gold["customer_id"])
            }
        elif gates_ok:
            report["issues"].append(
                "Prospect scoring model is not available in this deployment; "
                "profiles, confidence bands and loan eligibility are shown, "
                "prospect score is unavailable."
            )

        names = dict(
            duck.execute(
                f"SELECT customer_id, name FROM read_parquet('{customers_file.as_posix()}')"
            ).fetchall()
        )
        streams = load_income_streams(duck, txn_read=silver_read)
        txns = load_key_transactions(duck, txn_read=silver_read)

        status = "analyzed" if not run_gates else ("passed" if gates_ok else "failed")
        store.save_batch(
            batch_id=batch_id,
            note=note,
            gold=gold,
            names=names,
            scores=scores,
            streams=streams,
            transactions=txns,
            n_transactions=report["rows_valid"],
            status=status,
            gates=gates,
            min_history_months=min_history_months,
            uploaded_by=uploaded_by,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)  # raw uploaded txns not persisted

    issues = report["issues"] + report_c["issues"]
    return {
        "batch_id": batch_id,
        "customers": int(len(gold)),
        "transactions_used": report["rows_valid"],
        "issues": issues,
        "status": status,
        "gates": gates,
        "history": history,
        "min_history_months": min_history_months,
    }
