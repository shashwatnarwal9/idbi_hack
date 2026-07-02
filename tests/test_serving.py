"""आय·AI Stage 7 tests: serving store is complete, keyed and ground-truth-free.

Requires the serving-postgres container: docker compose up -d serving-postgres
then python -m aayai.serving.load. Skips cleanly when Postgres is unreachable.
"""
import pytest

from aayai.serving.db import connect

try:
    _conn = connect()
except Exception:
    _conn = None

pytestmark = pytest.mark.skipif(
    _conn is None, reason="serving postgres not reachable; start it via docker compose")


@pytest.fixture(scope="module")
def cur():
    with _conn.cursor() as c:
        yield c
    _conn.rollback()


def test_row_counts(cur):
    cur.execute("SELECT count(*) FROM customer_profiles")
    n = cur.fetchone()[0]
    assert n == 200
    cur.execute("SELECT count(*) FROM prospect_scores")
    assert cur.fetchone()[0] == n
    cur.execute("SELECT count(DISTINCT customer_id) FROM spending_breakdown")
    assert cur.fetchone()[0] == n


def test_no_ground_truth_in_serving(cur):
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'customer_profiles'""")
    cols = {r[0] for r in cur.fetchall()}
    assert not any(c.startswith("_") for c in cols)


def test_point_lookup_by_key(cur):
    cur.execute("""
        SELECT p.true_monthly_income, p.confidence_band, s.p_good_prospect, s.reasons
        FROM customer_profiles p JOIN prospect_scores s USING (customer_id)
        WHERE customer_id = 'CUST00001'""")
    rows = cur.fetchall()
    assert len(rows) == 1
    income, band, score, reasons = rows[0]
    assert income > 0
    assert band in ("high", "medium", "low")
    assert 0.0 <= score <= 1.0
    assert len(reasons) >= 3 and {"feature", "value", "shap"} <= set(reasons[0])


def test_scores_in_range(cur):
    cur.execute("SELECT count(*) FROM prospect_scores "
                "WHERE p_good_prospect < 0 OR p_good_prospect > 1")
    assert cur.fetchone()[0] == 0


def test_breakdown_categories_are_debit_side(cur):
    cur.execute("SELECT DISTINCT category FROM spending_breakdown")
    cats = {r[0] for r in cur.fetchall()}
    assert cats <= {"rent", "emi", "sip", "utility", "groceries", "food", "fuel",
                    "shopping", "entertainment", "p2p_out", "atm"}
