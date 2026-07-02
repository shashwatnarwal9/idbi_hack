"""आय·AI Stage 2 tests: silver parses narrations and derives labels honestly.

Run after: python -m aayai.silver.transform
"""
import duckdb
import pytest

from aayai.paths import SQL_DIR
from aayai.silver.evaluate import SILVER_CATEGORIES, evaluate
from aayai.silver.transform import BRONZE_GLOB, TXN_DIR, TXN_READ

pytestmark = pytest.mark.skipif(
    not TXN_DIR.exists(), reason="silver not built yet; run aayai.silver.transform first")

INCOME_CATEGORIES = ("salary", "gig_income", "business_income", "interest")


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


def test_rules_never_read_ground_truth():
    """The firewall: no "_" column may appear before the eval-passthrough join."""
    sql = (SQL_DIR / "silver_transactions.sql").read_text(encoding="utf-8")
    marker = "EVAL-PASSTHROUGH"
    assert marker in sql
    logic = sql.split(marker)[0]
    # strip comments, then check no ground-truth identifier is referenced
    logic_code = "\n".join(line.split("--")[0] for line in logic.splitlines())
    assert "_true_category" not in logic_code
    assert "_is_income" not in logic_code
    assert "_true_" not in logic_code


def test_row_count_preserved(con):
    n_bronze = con.execute(
        f"SELECT count(*) FROM read_parquet('{BRONZE_GLOB}', hive_partitioning=1)"
    ).fetchone()[0]
    n_silver = con.execute(f"SELECT count(*) FROM {TXN_READ}").fetchone()[0]
    assert n_bronze == n_silver


def test_category_domain(con):
    derived = {r[0] for r in con.execute(
        f"SELECT DISTINCT category FROM {TXN_READ}").fetchall()}
    assert derived <= set(SILVER_CATEGORIES)


def test_channel_domain(con):
    channels = {r[0] for r in con.execute(
        f"SELECT DISTINCT channel FROM {TXN_READ}").fetchall()}
    assert channels <= {"UPI", "NEFT", "IMPS", "ACH", "BIL", "ATW", "OTHER"}


def test_parse_confidence_range(con):
    lo, hi, nulls = con.execute(
        f"SELECT min(parse_confidence), max(parse_confidence), "
        f"count(*) - count(parse_confidence) FROM {TXN_READ}").fetchone()
    assert nulls == 0
    assert 0.0 <= lo <= hi <= 1.0


def test_is_income_matches_category_definition(con):
    cats = ", ".join(f"'{c}'" for c in INCOME_CATEGORIES)
    mismatched = con.execute(
        f"SELECT count(*) FROM {TXN_READ} "
        f"WHERE is_income != (category IN ({cats}))").fetchone()[0]
    assert mismatched == 0


def test_partition_layout_matches_bronze(con):
    silver_parts = {tuple(r) for r in con.execute(
        f"SELECT DISTINCT year, month FROM {TXN_READ}").fetchall()}
    bronze_parts = {tuple(r) for r in con.execute(
        f"SELECT DISTINCT year, month FROM read_parquet('{BRONZE_GLOB}', "
        f"hive_partitioning=1, hive_types_autocast=0)").fetchall()}
    assert silver_parts == bronze_parts


def test_overall_accuracy_headline(con):
    m = evaluate(con)
    assert m["overall"] >= 0.85, f"category accuracy {m['overall']:.2%} below 85%"
