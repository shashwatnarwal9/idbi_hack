"""आय·AI Silver transform runner.

bronze transactions -> data/silver/transactions/year=YYYY/month=MM/*.parquet
with parsed narration fields (channel, direction, counterparty, ref) and the
DERIVED category / is_income / parse_confidence. All logic lives in
sql/silver_transactions.sql; this module only wires paths and prints a summary.
"""
from __future__ import annotations

import shutil
from string import Template

import duckdb

from aayai.bronze.ingest import TXN_GLOB as BRONZE_GLOB
from aayai.paths import SILVER_DIR, SQL_DIR

TXN_DIR = SILVER_DIR / "transactions"
TXN_GLOB = TXN_DIR.as_posix() + "/*/*/*.parquet"
TXN_READ = f"read_parquet('{TXN_GLOB}', hive_partitioning=1, hive_types_autocast=0)"


def transform(con: duckdb.DuckDBPyConnection) -> None:
    if TXN_DIR.exists():
        shutil.rmtree(TXN_DIR)  # silver is fully rebuilt from bronze on every run
    TXN_DIR.parent.mkdir(parents=True, exist_ok=True)
    sql = Template((SQL_DIR / "silver_transactions.sql").read_text(encoding="utf-8"))
    # safe_substitute: regex '$' anchors in the SQL must not look like placeholders
    con.execute(sql.safe_substitute(bronze_glob=BRONZE_GLOB, out_dir=TXN_DIR.as_posix()))


def verify(con: duckdb.DuckDBPyConnection) -> None:
    """Printed sanity check: row parity with bronze + derived-field profile."""
    n_bronze = con.execute(
        f"SELECT count(*) FROM read_parquet('{BRONZE_GLOB}', hive_partitioning=1)"
    ).fetchone()[0]
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
        f"SELECT channel, count(*) FROM {TXN_READ} GROUP BY 1 ORDER BY 2 DESC").fetchall()
    print("[silver] channels: " + ", ".join(f"{c}={n:,}" for c, n in channels))
    low = con.execute(
        f"SELECT count(*) FROM {TXN_READ} WHERE parse_confidence < 0.8").fetchone()[0]
    print(f"[silver] rows on weak/fallback rules (confidence < 0.8): "
          f"{low:,} ({100.0 * low / n_silver:.1f}%)")


def main() -> None:
    con = duckdb.connect()
    transform(con)
    verify(con)


if __name__ == "__main__":
    main()
