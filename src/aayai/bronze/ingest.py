"""Bronze layer: raw CSVs to typed, partitioned Parquet.

data/raw/transactions.csv -> data/bronze/transactions/year=YYYY/month=MM/*.parquet
data/raw/customers.csv    -> data/bronze/customers.parquet

Bronze is the replayable source of truth: explicit types, no cleaning, and no
derived columns except the year/month partition keys. Re-running rebuilds the
layer from raw, so it stays a pure function of the input CSVs.
"""

from __future__ import annotations

import shutil

import duckdb

from aayai.paths import BRONZE_DIR, RAW_DIR
from aayai.util import hive_read, run_sql_file

TXN_DIR = BRONZE_DIR / "transactions"
CUSTOMERS_FILE = BRONZE_DIR / "customers.parquet"
EVENTS_DIR = BRONZE_DIR / "events"
TXN_READ = hive_read(TXN_DIR)
EVENTS_READ = hive_read(EVENTS_DIR)


def ingest_transactions(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild the partitioned transactions table from the raw CSV."""
    if TXN_DIR.exists():
        shutil.rmtree(TXN_DIR)  # full replay; bronze is never edited in place
    TXN_DIR.parent.mkdir(parents=True, exist_ok=True)
    run_sql_file(
        con,
        "bronze_transactions.sql",
        raw_csv=(RAW_DIR / "transactions.csv").as_posix(),
        out_dir=TXN_DIR.as_posix(),
    )


def ingest_customers(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild the single-file customers table from the raw CSV."""
    BRONZE_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOMERS_FILE.unlink(missing_ok=True)
    run_sql_file(
        con,
        "bronze_customers.sql",
        raw_csv=(RAW_DIR / "customers.csv").as_posix(),
        out_file=CUSTOMERS_FILE.as_posix(),
    )


def ingest_events(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild the partitioned events table from raw CSV, if events.csv is present.

    Events are optional; when data/raw/events.csv is absent this is a no-op so
    the pipeline still runs on a transactions-only book.
    """
    raw = RAW_DIR / "events.csv"
    if not raw.exists():
        print("[bronze] events: no data/raw/events.csv, skipping (optional source)")
        return
    if EVENTS_DIR.exists():
        shutil.rmtree(EVENTS_DIR)  # full replay; bronze is never edited in place
    EVENTS_DIR.parent.mkdir(parents=True, exist_ok=True)
    run_sql_file(
        con,
        "bronze_events.sql",
        raw_csv=raw.as_posix(),
        out_dir=EVENTS_DIR.as_posix(),
    )


def verify(con: duckdb.DuckDBPyConnection) -> None:
    """Print row-count parity with raw, partition folders and read-back dtypes."""
    for name, raw, bronze in (
        ("transactions", (RAW_DIR / "transactions.csv").as_posix(), TXN_READ),
        (
            "customers",
            (RAW_DIR / "customers.csv").as_posix(),
            f"read_parquet('{CUSTOMERS_FILE.as_posix()}')",
        ),
    ):
        n_raw = con.execute(f"SELECT count(*) FROM read_csv_auto('{raw}')").fetchone()[
            0
        ]
        n_bronze = con.execute(f"SELECT count(*) FROM {bronze}").fetchone()[0]
        status = "OK" if n_raw == n_bronze else "MISMATCH"
        print(f"[bronze] {name}: raw={n_raw:,} bronze={n_bronze:,} [{status}]")

    parts = sorted(
        p.relative_to(TXN_DIR).as_posix() for p in TXN_DIR.glob("year=*/month=*")
    )
    print(f"[bronze] {len(parts)} partitions under {TXN_DIR.as_posix()}:")
    for part in parts:
        print(f"  {part}")

    print("[bronze] transactions schema read back from Parquet:")
    for col, dtype in con.execute(
        f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM {TXN_READ})"
    ).fetchall():
        print(f"  {col:<16} {dtype}")


def main() -> None:
    """Ingest both tables, then print the verification summary."""
    con = duckdb.connect()
    ingest_transactions(con)
    ingest_customers(con)
    ingest_events(con)
    verify(con)


if __name__ == "__main__":
    main()
