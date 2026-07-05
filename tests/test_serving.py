"""Serving tests: the store is complete, keyed and ground-truth-free.

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
    _conn is None, reason="serving postgres not reachable; start it via docker compose"
)


@pytest.fixture(scope="module")
def cur():
    with _conn.cursor() as c:
        yield c
    _conn.rollback()


def test_row_counts(cur):
    # scope to the seeded book: merged uploaded batches legitimately add rows
    # (tagged source='uploaded') without touching the seeded 200
    cur.execute(
        "SELECT count(*) FROM customer_profiles "
        "WHERE COALESCE(source, 'seeded') = 'seeded'"
    )
    n = cur.fetchone()[0]
    assert n == 200
    cur.execute(
        "SELECT count(*) FROM prospect_scores s "
        "JOIN customer_profiles p USING (customer_id) "
        "WHERE COALESCE(p.source, 'seeded') = 'seeded'"
    )
    assert cur.fetchone()[0] == n
    # spending_breakdown is seeded-only (merges never write it)
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
    cur.execute(
        "SELECT count(*) FROM prospect_scores "
        "WHERE p_good_prospect < 0 OR p_good_prospect > 1"
    )
    assert cur.fetchone()[0] == 0


def test_portfolio_summary_matches_table(cur):
    from aayai.serving.queries import portfolio_summary

    s = portfolio_summary(_conn)
    cur.execute("SELECT count(*) FROM customer_profiles")
    assert s["customers"] == cur.fetchone()[0]
    assert sum(s["bands"].values()) == s["customers"]
    cur.execute("SELECT avg(true_monthly_income) FROM customer_profiles")
    assert abs(s["avg_reconstructed"] - float(cur.fetchone()[0])) < 1e-6
    assert s["median_surplus"] is not None


def test_ranked_prospects_order_matches_db(cur):
    from aayai.serving.queries import ranked_prospects

    rows = ranked_prospects(_conn)
    cur.execute("SELECT count(*) FROM prospect_scores")
    assert len(rows) == cur.fetchone()[0]
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    cur.execute(
        "SELECT customer_id FROM prospect_scores "
        "ORDER BY p_good_prospect DESC, customer_id LIMIT 10"
    )
    assert [r["customer_id"] for r in rows[:10]] == [x[0] for x in cur.fetchall()]
    assert all(r["name"] for r in rows)


def test_ranked_prospects_band_filter(cur):
    from aayai.serving.queries import ranked_prospects

    rows = ranked_prospects(_conn, ["high"])
    assert rows and all(r["band"] == "high" for r in rows)
    cur.execute("SELECT count(*) FROM customer_profiles WHERE confidence_band = 'high'")
    assert len(rows) == cur.fetchone()[0]
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))


def test_breakdown_categories_are_debit_side(cur):
    cur.execute("SELECT DISTINCT category FROM spending_breakdown")
    cats = {r[0] for r in cur.fetchall()}
    assert cats <= {
        "rent",
        "emi",
        "sip",
        "utility",
        "groceries",
        "food",
        "fuel",
        "shopping",
        "entertainment",
        "p2p_out",
        "atm",
    }
