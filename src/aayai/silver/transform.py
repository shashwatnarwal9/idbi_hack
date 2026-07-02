"""Silver layer: parsed narrations plus a derived category and is_income.

Reads bronze transactions and writes
data/silver/transactions/year=YYYY/month=MM/*.parquet with each narration
cracked into channel, direction, counterparty and ref, plus the rule-derived
category / is_income / parse_confidence. All transform logic lives in
sql/silver_transactions.sql; this module wires paths and prints a summary.
"""

from __future__ import annotations

import shutil

import duckdb

from aayai.bronze.ingest import TXN_READ as BRONZE_READ
from aayai.paths import SILVER_DIR
from aayai.util import hive_read, run_sql_file

TXN_DIR = SILVER_DIR / "transactions"
TXN_READ = hive_read(TXN_DIR)


def transform(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild silver transactions from bronze."""
    if TXN_DIR.exists():
        shutil.rmtree(TXN_DIR)  # silver is fully rebuilt from bronze on every run
    TXN_DIR.parent.mkdir(parents=True, exist_ok=True)
    run_sql_file(
        con,
        "silver_transactions.sql",
        bronze_read=BRONZE_READ,
        out_dir=TXN_DIR.as_posix(),
    )


def verify(con: duckdb.DuckDBPyConnection) -> None:
    """Print row parity with bronze and a profile of the derived fields."""
    n_bronze = con.execute(f"SELECT count(*) FROM {BRONZE_READ}").fetchone()[0]
    n_silver = con.execute(f"SELECT count(*) FROM {TXN_READ}").fetchone()[0]
    status = "OK" if n_bronze == n_silver else "MISMATCH"
    print(f"[silver] rows: bronze={n_bronze:,} silver={n_silver:,} [{status}]")

    print("[silver] derived categories (count / avg confidence / % with counterparty):")
    for cat, n, conf, cp in con.execute(f"""
        SELECT category, count(*), round(avg(parse_confidence), 3),
               round(100.0 * count(counterparty_raw) / count(*), 1)
        FROM {TXN_READ} GROUP BY 1 ORDER BY 2 DESC""").fetchall():
        print(f"  {cat:<16} {n:>7,}   conf={conf:<5}  counterparty={cp}%")

    channels = con.execute(
        f"SELECT channel, count(*) FROM {TXN_READ} GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    print("[silver] channels: " + ", ".join(f"{c}={n:,}" for c, n in channels))
    low = con.execute(
        f"SELECT count(*) FROM {TXN_READ} WHERE parse_confidence < 0.8"
    ).fetchone()[0]
    print(
        f"[silver] rows on weak/fallback rules (confidence < 0.8): "
        f"{low:,} ({100.0 * low / n_silver:.1f}%)"
    )


def main() -> None:
    """Run the transform, then print the verification summary."""
    con = duckdb.connect()
    transform(con)
    verify(con)


if __name__ == "__main__":
    main()
