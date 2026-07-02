"""Gold evaluation: reconstructed income against ground truth.

Prints three archetype profiles side by side, then how well the reconstructed
true_monthly_income tracks _true_monthly_income: Pearson r, MAE, bias
(derived - truth) and MAPE, overall and per archetype. Evaluation code is the
only part of the pipeline permitted to read "_" columns.
"""

from __future__ import annotations

import duckdb

from aayai.gold.build import PROFILES_READ

SHOW_FIELDS = [
    "customer_id",
    "region",
    "occupation_declared",
    "declared_monthly_income",
    "income_type",
    "true_monthly_income",
    "_true_monthly_income",
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
]


def evaluate(con: duckdb.DuckDBPyConnection | None = None) -> dict:
    """Compare reconstructed income with ground truth.

    Args:
        con: optional open DuckDB connection; a fresh one is created if omitted.

    Returns:
        Dict with corr, mae, bias, mape, n and per-archetype rows
        (occupation, n, mae, bias, mape).
    """
    con = con or duckdb.connect()
    corr, mae, bias, mape, n = con.execute(f"""
        SELECT corr(true_monthly_income, _true_monthly_income),
               avg(abs(true_monthly_income - _true_monthly_income)),
               avg(true_monthly_income - _true_monthly_income),
               avg(abs(true_monthly_income - _true_monthly_income)
                   / NULLIF(_true_monthly_income, 0)),
               count(*)
        FROM {PROFILES_READ}""").fetchone()
    by_archetype = con.execute(f"""
        SELECT _true_occupation, count(*),
               avg(abs(true_monthly_income - _true_monthly_income)),
               avg(true_monthly_income - _true_monthly_income),
               avg(abs(true_monthly_income - _true_monthly_income)
                   / NULLIF(_true_monthly_income, 0))
        FROM {PROFILES_READ} GROUP BY 1 ORDER BY 1""").fetchall()
    return {
        "corr": corr,
        "mae": mae,
        "bias": bias,
        "mape": mape,
        "n": n,
        "by_archetype": by_archetype,
    }


def print_samples(con: duckdb.DuckDBPyConnection) -> None:
    """Print one full profile per archetype, transposed for comparison."""
    print("[gold eval] sample profiles (one per archetype):")
    rows, headers = [], []
    for occ in ("SALARIED", "GIG", "BUSINESS"):
        cur = con.execute(
            f"SELECT * FROM {PROFILES_READ} WHERE _true_occupation = ? "
            f"ORDER BY customer_id LIMIT 1",
            [occ],
        )
        cols = [d[0] for d in cur.description]
        row = cur.fetchone()
        if row:
            rows.append(dict(zip(cols, row)))
            headers.append(occ)
    print(f"  {'field':<26}" + "".join(f"{h:>22}" for h in headers))
    for field in SHOW_FIELDS:
        vals = []
        for r in rows:
            v = r[field]
            vals.append(f"{v:,.2f}" if isinstance(v, float) else str(v))
        print(f"  {field:<26}" + "".join(f"{v:>22}" for v in vals))


def main() -> None:
    """Print sample profiles and the income-reconstruction accuracy report."""
    con = duckdb.connect()
    print_samples(con)
    m = evaluate(con)
    print(f"[gold eval] derived vs ground-truth monthly income (n={m['n']}):")
    print(
        f"  pearson r = {m['corr']:.4f}   MAE = Rs {m['mae']:,.0f}   "
        f"bias = Rs {m['bias']:+,.0f}   MAPE = {m['mape']:.1%}"
    )
    print(f"  {'archetype':<16} {'n':>4} {'MAE':>12} {'bias':>12} {'MAPE':>8}")
    for occ, n, mae, bias, mape in m["by_archetype"]:
        print(f"  {occ:<16} {n:>4} {mae:>12,.0f} {bias:>+12,.0f} {mape:>8.1%}")
    print(
        "[gold eval] notes: gig/business use a p25 floor (conservative by "
        "design, negative bias expected); SALARIED_PLUS undershoots because "
        "rent credits are excluded from is_income by the Stage-2 taxonomy."
    )


if __name__ == "__main__":
    main()
