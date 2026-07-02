"""आय·AI Gold builder.

silver transactions + bronze customers -> data/gold/customer_profiles.parquet
(one row per customer). All logic lives in sql/gold_customer_profiles.sql.
"""
from __future__ import annotations

from string import Template

import duckdb

from aayai.bronze.ingest import CUSTOMERS_FILE
from aayai.paths import GOLD_DIR, SQL_DIR
from aayai.silver.transform import TXN_GLOB as SILVER_GLOB

PROFILES_FILE = GOLD_DIR / "customer_profiles.parquet"
PROFILES_READ = f"read_parquet('{PROFILES_FILE.as_posix()}')"


def build(con: duckdb.DuckDBPyConnection) -> None:
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_FILE.unlink(missing_ok=True)  # gold is fully rebuilt from silver
    sql = Template((SQL_DIR / "gold_customer_profiles.sql").read_text(encoding="utf-8"))
    con.execute(sql.safe_substitute(
        silver_glob=SILVER_GLOB,
        customers_file=CUSTOMERS_FILE.as_posix(),
        out_file=PROFILES_FILE.as_posix(),
    ))


def verify(con: duckdb.DuckDBPyConnection) -> None:
    """Printed sanity check: one row per customer + distribution of key fields."""
    n, n_unique = con.execute(
        f"SELECT count(*), count(DISTINCT customer_id) FROM {PROFILES_READ}").fetchone()
    status = "OK" if n == n_unique else "DUPLICATES"
    print(f"[gold] customer_profiles: {n} rows, {n_unique} unique customers [{status}]")

    for label, col in (("income_type", "income_type"), ("risk_capacity", "risk_capacity")):
        dist = con.execute(
            f"SELECT {col}, count(*) FROM {PROFILES_READ} GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
        print(f"[gold] {label}: " + ", ".join(f"{v}={c}" for v, c in dist))

    inc, sur, neg = con.execute(f"""
        SELECT round(avg(true_monthly_income)), round(avg(investable_surplus)),
               sum(CASE WHEN investable_surplus < 0 THEN 1 ELSE 0 END)
        FROM {PROFILES_READ}""").fetchone()
    print(f"[gold] avg reconstructed income: Rs {inc:,.0f}/mo | "
          f"avg investable surplus: Rs {sur:,.0f}/mo | negative-surplus customers: {neg}")


def main() -> None:
    con = duckdb.connect()
    build(con)
    verify(con)


if __name__ == "__main__":
    main()
