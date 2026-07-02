"""Gold layer: one profile row per customer.

Joins silver transactions with bronze customers and writes
data/gold/customer_profiles.parquet: reconstructed income, essentials, EMI/SIP
load, investable surplus, stability measures and risk capacity. All feature
logic lives in sql/gold_customer_profiles.sql.
"""

from __future__ import annotations

import duckdb

from aayai.bronze.ingest import CUSTOMERS_FILE
from aayai.paths import GOLD_DIR
from aayai.silver.transform import TXN_READ as SILVER_READ
from aayai.util import run_sql_file

PROFILES_FILE = GOLD_DIR / "customer_profiles.parquet"
PROFILES_READ = f"read_parquet('{PROFILES_FILE.as_posix()}')"


def build(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild gold customer profiles from silver and bronze customers."""
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_FILE.unlink(missing_ok=True)  # gold is fully rebuilt from silver
    run_sql_file(
        con,
        "gold_customer_profiles.sql",
        silver_read=SILVER_READ,
        customers_file=CUSTOMERS_FILE.as_posix(),
        out_file=PROFILES_FILE.as_posix(),
    )


def verify(con: duckdb.DuckDBPyConnection) -> None:
    """Print row uniqueness and the distribution of the key derived fields."""
    n, n_unique = con.execute(
        f"SELECT count(*), count(DISTINCT customer_id) FROM {PROFILES_READ}"
    ).fetchone()
    status = "OK" if n == n_unique else "DUPLICATES"
    print(f"[gold] customer_profiles: {n} rows, {n_unique} unique customers [{status}]")

    for label in ("income_type", "risk_capacity"):
        dist = con.execute(
            f"SELECT {label}, count(*) FROM {PROFILES_READ} GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        print(f"[gold] {label}: " + ", ".join(f"{v}={c}" for v, c in dist))

    inc, sur, neg = con.execute(f"""
        SELECT round(avg(true_monthly_income)), round(avg(investable_surplus)),
               sum(CASE WHEN investable_surplus < 0 THEN 1 ELSE 0 END)
        FROM {PROFILES_READ}""").fetchone()
    print(
        f"[gold] avg reconstructed income: Rs {inc:,.0f}/mo | "
        f"avg investable surplus: Rs {sur:,.0f}/mo | negative-surplus customers: {neg}"
    )


def main() -> None:
    """Run the build, then print the verification summary."""
    con = duckdb.connect()
    build(con)
    verify(con)


if __name__ == "__main__":
    main()
