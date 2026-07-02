"""Bronze layer tests: a typed, partitioned, lossless copy of raw.

Run after: python -m aayai.datagen && python -m aayai.bronze.ingest
"""

import duckdb
import pytest

from aayai.bronze.ingest import CUSTOMERS_FILE, TXN_DIR, TXN_READ
from aayai.paths import RAW_DIR

pytestmark = pytest.mark.skipif(
    not TXN_DIR.exists(), reason="bronze not built yet; run aayai.bronze.ingest first"
)


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


def _csv(name: str) -> str:
    return f"read_csv_auto('{(RAW_DIR / name).as_posix()}')"


BRONZE_TXN = TXN_READ


def test_no_rows_lost(con):
    assert (
        con.execute(f"SELECT count(*) FROM {_csv('transactions.csv')}").fetchone()[0]
        == con.execute(f"SELECT count(*) FROM {BRONZE_TXN}").fetchone()[0]
    )
    assert (
        con.execute(f"SELECT count(*) FROM {_csv('customers.csv')}").fetchone()[0]
        == con.execute(
            f"SELECT count(*) FROM read_parquet('{CUSTOMERS_FILE.as_posix()}')"
        ).fetchone()[0]
    )


def test_transaction_dtypes(con):
    dtypes = dict(
        con.execute(
            f"SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM {BRONZE_TXN})"
        ).fetchall()
    )
    assert dtypes["timestamp"] == "TIMESTAMP"
    assert dtypes["amount"] == "DOUBLE"
    assert dtypes["balance"] == "DOUBLE"
    assert dtypes["_is_income"] == "BOOLEAN"
    assert dtypes["year"] == "VARCHAR" and dtypes["month"] == "VARCHAR"


def test_bronze_adds_only_partition_keys(con):
    raw_cols = {
        r[0]
        for r in con.execute(
            f"SELECT column_name FROM (DESCRIBE SELECT * FROM {_csv('transactions.csv')})"
        ).fetchall()
    }
    bronze_cols = {
        r[0]
        for r in con.execute(
            f"SELECT column_name FROM (DESCRIBE SELECT * FROM {BRONZE_TXN})"
        ).fetchall()
    }
    assert bronze_cols - raw_cols == {"year", "month"}
    assert raw_cols - bronze_cols == set()


def test_partition_layout_matches_data(con):
    on_disk = {
        p.relative_to(TXN_DIR).as_posix() for p in TXN_DIR.glob("year=*/month=*")
    }
    expected = {
        f"year={y}/month={m}"
        for y, m in con.execute(
            f'SELECT DISTINCT CAST(year("timestamp") AS VARCHAR), '
            f"lpad(CAST(month(\"timestamp\") AS VARCHAR), 2, '0') FROM {_csv('transactions.csv')}"
        ).fetchall()
    }
    assert on_disk == expected


def test_ground_truth_carried_unchanged(con):
    raw_income = con.execute(
        f"SELECT count(*) FROM {_csv('transactions.csv')} WHERE _is_income"
    ).fetchone()[0]
    bronze_income = con.execute(
        f"SELECT count(*) FROM {BRONZE_TXN} WHERE _is_income"
    ).fetchone()[0]
    assert raw_income == bronze_income
    raw_cats = con.execute(
        f"SELECT count(DISTINCT _true_category) FROM {_csv('transactions.csv')}"
    ).fetchone()[0]
    bronze_cats = con.execute(
        f"SELECT count(DISTINCT _true_category) FROM {BRONZE_TXN}"
    ).fetchone()[0]
    assert raw_cats == bronze_cats
