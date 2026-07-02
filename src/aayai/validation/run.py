"""Great Expectations validation: hard gates plus the confidence_band feature.

Two roles:
  1. GATES (pass/fail): hard floors on silver transactions and gold profiles.
     A gate failure exits non-zero so orchestration can stop the pipeline.
  2. FEATURE: the confidence suite re-checks gold at two stricter tiers and the
     per-customer unexpected lists from the GE run become a confidence_band
     column (high/medium/low) written back onto customer_profiles.parquet —
     "we know how much we can trust each estimate".

confidence_band derives ONLY from months_history and pct_categorized (both
derived fields — the ground-truth firewall holds):
  high   : months_history >= 12 AND pct_categorized >= 0.90
  medium : months_history >=  6 AND pct_categorized >= 0.85
  low    : anything weaker (thin file or poorly parsed narrations)
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("GX_ANALYTICS_ENABLED", "false")  # keep everything local

import duckdb
import great_expectations as gx
import pandas as pd

from aayai.gold.build import PROFILES_FILE, PROFILES_READ
from aayai.silver.evaluate import SILVER_CATEGORIES
from aayai.silver.transform import TXN_READ as SILVER_READ

# gate floors (hard, batch-level)
GATE_MIN_MONTHS = 6
GATE_MIN_PCT = 0.60
SURPLUS_BOUNDS = (-200_000, 1_000_000)  # plausible for this income range

# band tiers (per-customer). Key = band the tier guards.
BAND_RULES = {"high": {"months": 12, "pct": 0.90}, "medium": {"months": 6, "pct": 0.85}}

GOLD_KEY_FIELDS = [
    "customer_id",
    "income_type",
    "true_monthly_income",
    "investable_surplus",
    "risk_capacity",
    "region",
    "months_history",
    "pct_categorized",
]

E = gx.expectations


def build_context():
    """Ephemeral GX context: in-memory stores, no progress-bar noise."""
    from great_expectations.data_context.types.base import (
        DataContextConfig,
        InMemoryStoreBackendDefaults,
        ProgressBarsConfig,
    )

    config = DataContextConfig(
        store_backend_defaults=InMemoryStoreBackendDefaults(),
        progress_bars=ProgressBarsConfig(globally=False),
    )
    return gx.get_context(project_config=config, mode="ephemeral")


def silver_gate_suite() -> gx.ExpectationSuite:
    """Hard floors on silver transactions: nulls, ranges and value domains."""
    suite = gx.ExpectationSuite(name="silver_gate")
    for col in (
        "txn_id",
        "customer_id",
        "category",
        "direction",
        "amount",
        "is_income",
        "parse_confidence",
    ):
        suite.add_expectation(E.ExpectColumnValuesToNotBeNull(column=col))
    suite.add_expectation(
        E.ExpectColumnValuesToBeBetween(
            column="parse_confidence", min_value=0.0, max_value=1.0
        )
    )
    suite.add_expectation(
        E.ExpectColumnValuesToBeBetween(column="amount", min_value=0.0, strict_min=True)
    )
    suite.add_expectation(
        E.ExpectColumnValuesToBeInSet(column="direction", value_set=["credit", "debit"])
    )
    suite.add_expectation(
        E.ExpectColumnValuesToBeInSet(column="category", value_set=SILVER_CATEGORIES)
    )
    return suite


def gold_gate_suite() -> gx.ExpectationSuite:
    """Hard floors on gold profiles: keys, history, income and surplus bounds."""
    suite = gx.ExpectationSuite(name="gold_gate")
    for col in GOLD_KEY_FIELDS:
        suite.add_expectation(E.ExpectColumnValuesToNotBeNull(column=col))
    suite.add_expectation(E.ExpectColumnValuesToBeUnique(column="customer_id"))
    suite.add_expectation(
        E.ExpectColumnValuesToBeBetween(
            column="months_history", min_value=GATE_MIN_MONTHS
        )
    )
    suite.add_expectation(
        E.ExpectColumnValuesToBeBetween(
            column="pct_categorized", min_value=GATE_MIN_PCT
        )
    )
    suite.add_expectation(
        E.ExpectColumnValuesToBeBetween(  # no negative income
            column="true_monthly_income", min_value=0.0, strict_min=True
        )
    )
    suite.add_expectation(
        E.ExpectColumnValuesToBeBetween(
            column="investable_surplus",
            min_value=SURPLUS_BOUNDS[0],
            max_value=SURPLUS_BOUNDS[1],
        )
    )
    return suite


def confidence_suite() -> gx.ExpectationSuite:
    """Tiered trust checks; per-customer failures become the band feature."""
    suite = gx.ExpectationSuite(name="gold_confidence")
    for band, rule in BAND_RULES.items():
        suite.add_expectation(
            E.ExpectColumnValuesToBeBetween(
                column="months_history",
                min_value=rule["months"],
                meta={"tier": band, "reason": f"months_history >= {rule['months']}"},
            )
        )
        suite.add_expectation(
            E.ExpectColumnValuesToBeBetween(
                column="pct_categorized",
                min_value=rule["pct"],
                meta={"tier": band, "reason": f"pct_categorized >= {rule['pct']}"},
            )
        )
    return suite


def run_suite(
    context,
    name: str,
    suite: gx.ExpectationSuite,
    df: pd.DataFrame,
    complete: bool = False,
):
    """Validate a dataframe against a suite.

    Args:
        context: GX data context.
        name: unique name for the datasource/asset/validation objects.
        suite: expectation suite to run.
        df: dataframe to validate.
        complete: when True, request COMPLETE results with per-customer
            unexpected lists (needed to build the confidence_band feature).

    Returns:
        The GX validation result.
    """
    asset = context.data_sources.add_pandas(f"ds_{name}").add_dataframe_asset(name=name)
    batch_def = asset.add_batch_definition_whole_dataframe(f"{name}_batch")
    vd = context.validation_definitions.add(
        gx.ValidationDefinition(
            data=batch_def, suite=context.suites.add(suite), name=f"{name}_validation"
        )
    )
    result_format: dict | str = "SUMMARY"
    if complete:
        result_format = {
            "result_format": "COMPLETE",
            "unexpected_index_column_names": ["customer_id"],
        }
    return vd.run(batch_parameters={"dataframe": df}, result_format=result_format)


def print_gate(name: str, result) -> bool:
    """Print a gate summary and return whether the whole suite passed."""
    ok = sum(1 for r in result.results if r.success)
    print(
        f"[validation] {name}: {'PASS' if result.success else 'FAIL'} "
        f"({ok}/{len(result.results)} expectations)"
    )
    for r in result.results:
        if not r.success:
            cfg = r.expectation_config
            print(
                f"  FAILED {cfg.type}({cfg.kwargs.get('column')}): "
                f"{r.result.get('unexpected_count')} unexpected rows"
            )
    return bool(result.success)


def derive_bands(result, gold_df: pd.DataFrame) -> tuple[dict, dict]:
    """Turn GE per-customer unexpected lists into the band feature.

    Args:
        result: COMPLETE-format validation result of the confidence suite.
        gold_df: gold profiles (for the values quoted in the reasons).

    Returns:
        (bands, reasons): customer_id -> band, customer_id -> reason strings.
    """
    failed: dict[str, dict[str, list[str]]] = {}  # cid -> tier -> reasons
    for r in result.results:
        tier = (r.expectation_config.meta or {}).get("tier")
        if tier is None or r.success:
            continue
        reason = r.expectation_config.meta["reason"]
        for row in r.result.get("unexpected_index_list", []):
            cid = row["customer_id"]
            failed.setdefault(cid, {}).setdefault(tier, []).append(reason)

    bands, reasons = {}, {}
    for cid, months, pct in zip(
        gold_df["customer_id"], gold_df["months_history"], gold_df["pct_categorized"]
    ):
        tiers = failed.get(cid, {})
        if "medium" in tiers:  # fails even the medium bar -> low
            bands[cid] = "low"
            reasons[cid] = [f"FAILS {t}" for t in tiers["medium"]]
        elif "high" in tiers:  # fails only the high bar -> medium
            bands[cid] = "medium"
            reasons[cid] = [f"FAILS {t}" for t in tiers["high"]]
        else:
            bands[cid] = "high"
            reasons[cid] = []
        reasons[cid].append(f"months_history={months}, pct_categorized={pct:.3f}")
    return bands, reasons


def write_bands(con: duckdb.DuckDBPyConnection, bands: dict) -> None:
    """Rejoin the band column onto the gold parquet file (idempotent)."""
    band_df = pd.DataFrame(
        {"customer_id": list(bands), "confidence_band": list(bands.values())}
    )
    con.register("band_map", band_df)
    cols = [
        r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {PROFILES_READ}").fetchall()
    ]
    exclude = " EXCLUDE (confidence_band)" if "confidence_band" in cols else ""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE gold_banded AS
        SELECT g.*{exclude}, b.confidence_band
        FROM {PROFILES_READ} g JOIN band_map b USING (customer_id)""")
    n_gold = con.execute(f"SELECT count(*) FROM {PROFILES_READ}").fetchone()[0]
    n_banded = con.execute("SELECT count(*) FROM gold_banded").fetchone()[0]
    assert n_gold == n_banded, "band write-back would drop rows"
    con.execute(f"COPY gold_banded TO '{PROFILES_FILE.as_posix()}' (FORMAT PARQUET)")


def main() -> None:
    """Run both gates and the confidence suite; exit non-zero on gate failure."""
    con = duckdb.connect()
    silver_df = con.execute(
        f"SELECT txn_id, customer_id, category, direction, amount, "
        f"is_income, parse_confidence FROM {SILVER_READ}"
    ).df()
    gold_df = con.execute(f"SELECT * FROM {PROFILES_READ}").df()
    context = build_context()

    gates_ok = print_gate(
        "silver gate", run_suite(context, "silver", silver_gate_suite(), silver_df)
    )
    gates_ok &= print_gate(
        "gold gate", run_suite(context, "gold", gold_gate_suite(), gold_df)
    )

    conf_result = run_suite(
        context, "confidence", confidence_suite(), gold_df, complete=True
    )
    bands, reasons = derive_bands(conf_result, gold_df)
    write_bands(con, bands)
    print(f"[validation] wrote confidence_band onto {PROFILES_FILE.as_posix()}")

    dist = pd.Series(bands).value_counts()
    print(
        "[validation] confidence_band distribution: "
        + ", ".join(f"{b}={dist.get(b, 0)}" for b in ("high", "medium", "low"))
    )
    for target in ("high", "low"):
        cid = next((c for c, b in bands.items() if b == target), None)
        if cid is None:
            print(f"[validation] example {target.upper()}: none in this run")
            continue
        print(
            f"[validation] example {target.upper()}: {cid} -- "
            + "; ".join(reasons[cid])
        )

    if not gates_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
