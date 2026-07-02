"""आय·AI Stage 3 tests: gold profiles are honest, complete and sane.

Run after: python -m aayai.gold.build
"""
import duckdb
import pytest

from aayai.gold.build import PROFILES_FILE, PROFILES_READ
from aayai.gold.evaluate import evaluate
from aayai.paths import SQL_DIR
from aayai.silver.transform import TXN_READ as SILVER_READ

pytestmark = pytest.mark.skipif(
    not PROFILES_FILE.exists(), reason="gold not built yet; run aayai.gold.build first")


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


def test_features_never_read_ground_truth():
    """The firewall: no "_" column may appear before the eval-passthrough block."""
    sql = (SQL_DIR / "gold_customer_profiles.sql").read_text(encoding="utf-8")
    marker = "EVAL-PASSTHROUGH"
    assert marker in sql
    logic = sql.split(marker)[0]
    logic_code = "\n".join(line.split("--")[0] for line in logic.splitlines())
    assert "_true_" not in logic_code
    assert "_is_good_prospect" not in logic_code
    assert "_is_income" not in logic_code


def test_one_row_per_customer(con):
    n, n_unique = con.execute(
        f"SELECT count(*), count(DISTINCT customer_id) FROM {PROFILES_READ}").fetchone()
    n_silver = con.execute(
        f"SELECT count(DISTINCT customer_id) FROM {SILVER_READ}").fetchone()[0]
    assert n == n_unique == n_silver


def test_categorical_domains(con):
    types = {r[0] for r in con.execute(
        f"SELECT DISTINCT income_type FROM {PROFILES_READ}").fetchall()}
    risks = {r[0] for r in con.execute(
        f"SELECT DISTINCT risk_capacity FROM {PROFILES_READ}").fetchall()}
    assert types <= {"salaried", "gig", "business"}
    assert risks <= {"low", "medium", "high"}


def test_numeric_sanity(con):
    bad = con.execute(f"""
        SELECT count(*) FROM {PROFILES_READ}
        WHERE true_monthly_income <= 0
           OR income_volatility < 0
           OR avg_monthly_essentials < 0 OR total_emi < 0 OR total_sip < 0
           OR surplus_stability < 0 OR surplus_stability > 1
           OR savings_rate < 0 OR savings_rate > 1
           OR pct_categorized < 0 OR pct_categorized > 1
           OR months_history < 1""").fetchone()[0]
    assert bad == 0


def test_surplus_formula(con):
    """investable_surplus = income - essentials - emi - 15% income buffer."""
    off = con.execute(f"""
        SELECT count(*) FROM {PROFILES_READ}
        WHERE abs(investable_surplus
                  - (true_monthly_income - avg_monthly_essentials - total_emi
                     - 0.15 * true_monthly_income)) > 1.0""").fetchone()[0]
    assert off == 0


def test_income_reconstruction_tracks_truth(con):
    m = evaluate(con)
    assert m["corr"] >= 0.8, f"income correlation {m['corr']:.3f} below 0.8"
