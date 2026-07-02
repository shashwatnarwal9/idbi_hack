"""आय·AI Bronze ingestion.

data/raw/transactions.csv -> data/bronze/transactions/year=YYYY/month=MM/*.parquet
data/raw/customers.csv    -> data/bronze/customers.parquet

Bronze is the replayable source of truth: explicit types, no cleaning, no new
columns except the year/month partition keys. Re-running rebuilds bronze from
raw, so the layer stays a pure function of the raw CSVs.
"""
from __future__ import annotations

import shutil
from string import Template

import duckdb

from aayai.paths import BRONZE_DIR, RAW_DIR, SQL_DIR

TXN_DIR = BRONZE_DIR / "transactions"
CUSTOMERS_FILE = BRONZE_DIR / "customers.parquet"
# read_parquet glob for the hive layout; hive_partitioning exposes year/month.
# hive_types_autocast=0 keeps both partition keys VARCHAR ('2025', '01') instead
# of DuckDB guessing BIGINT for year — stable schema for every downstream reader.
TXN_GLOB = TXN_DIR.as_posix() + "/*/*/*.parquet"
TXN_READ = f"read_parquet('{TXN_GLOB}', hive_partitioning=1, hive_types_autocast=0)"


def _run_sql(con: duckdb.DuckDBPyConnection, sql_file: str, **params: str) -> None:
    sql = Template((SQL_DIR / sql_file).read_text(encoding="utf-8"))
    con.execute(sql.substitute(params))


def ingest_transactions(con: duckdb.DuckDBPyConnection) -> None:
    if TXN_DIR.exists():
        shutil.rmtree(TXN_DIR)  # full replay from raw; bronze is never edited in place
    TXN_DIR.parent.mkdir(parents=True, exist_ok=True)
    _run_sql(con, "bronze_transactions.sql",
             raw_csv=(RAW_DIR / "transactions.csv").as_posix(),
             out_dir=TXN_DIR.as_posix())


def ingest_customers(con: duckdb.DuckDBPyConnection) -> None:
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOMERS_FILE.unlink(missing_ok=True)
    _run_sql(con, "bronze_customers.sql",
             raw_csv=(RAW_DIR / "customers.csv").as_posix(),
             out_file=CUSTOMERS_FILE.as_posix())


def verify(con: duckdb.DuckDBPyConnection) -> None:
    """Printed sanity check: row counts, partition folders, read-back dtypes."""
    for name, raw, bronze in (
        ("transactions", (RAW_DIR / "transactions.csv").as_posix(), TXN_READ),
        ("customers", (RAW_DIR / "customers.csv").as_posix(),
         f"read_parquet('{CUSTOMERS_FILE.as_posix()}')"),
    ):
        n_raw = con.execute(f"SELECT count(*) FROM read_csv_auto('{raw}')").fetchone()[0]
        n_bronze = con.execute(f"SELECT count(*) FROM {bronze}").fetchone()[0]
        status = "OK" if n_raw == n_bronze else "MISMATCH"
        print(f"[bronze] {name}: raw={n_raw:,} bronze={n_bronze:,} [{status}]")

    parts = sorted(p.relative_to(TXN_DIR).as_posix()
                   for p in TXN_DIR.glob("year=*/month=*"))
    print(f"[bronze] {len(parts)} partitions under {TXN_DIR.as_posix()}:")
    for part in parts:
        print(f"  {part}")

    print("[bronze] transactions schema read back from Parquet:")
    for col, dtype in con.execute(
            f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM {TXN_READ})"
    ).fetchall():
        print(f"  {col:<16} {dtype}")


def main() -> None:
    con = duckdb.connect()
    ingest_transactions(con)
    ingest_customers(con)
    verify(con)


if __name__ == "__main__":
    main()
