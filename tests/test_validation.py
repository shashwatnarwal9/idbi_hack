"""Validation tests: GE gates hold and confidence_band is consistent.

Run after: python -m aayai.validation.run
"""

from pathlib import Path

import duckdb
import pytest

from aayai.gold.build import PROFILES_FILE, PROFILES_READ
from aayai.validation.run import BAND_RULES

pytestmark = pytest.mark.skipif(not PROFILES_FILE.exists(), reason="gold not built yet")


@pytest.fixture(scope="module")
def con():
    return duckdb.connect()


def _has_band(con) -> bool:
    cols = [
        r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {PROFILES_READ}").fetchall()
    ]
    return "confidence_band" in cols


def test_confidence_band_written(con):
    assert _has_band(con), "run aayai.validation.run to write confidence_band"
    nulls = con.execute(
        f"SELECT count(*) FROM {PROFILES_READ} WHERE confidence_band IS NULL"
    ).fetchone()[0]
    assert nulls == 0


def test_confidence_band_domain(con):
    if not _has_band(con):
        pytest.skip("confidence_band not written yet")
    bands = {
        r[0]
        for r in con.execute(
            f"SELECT DISTINCT confidence_band FROM {PROFILES_READ}"
        ).fetchall()
    }
    assert bands <= {"high", "medium", "low"}


def test_confidence_band_matches_rules(con):
    """Band must equal what the documented thresholds imply, GE and the
    written feature can never drift apart."""
    if not _has_band(con):
        pytest.skip("confidence_band not written yet")
    hi, med = BAND_RULES["high"], BAND_RULES["medium"]
    mismatches = con.execute(f"""
        SELECT count(*) FROM {PROFILES_READ}
        WHERE confidence_band != CASE
            WHEN months_history >= {hi['months']} AND pct_categorized >= {hi['pct']}
                THEN 'high'
            WHEN months_history >= {med['months']} AND pct_categorized >= {med['pct']}
                THEN 'medium'
            ELSE 'low' END""").fetchone()[0]
    assert mismatches == 0


def test_band_uses_only_derived_inputs():
    """Firewall: the band logic must reference no ground-truth column."""
    src = (
        Path(__file__).parents[1] / "src" / "aayai" / "validation" / "run.py"
    ).read_text(encoding="utf-8")
    assert "_true_" not in src
    assert "_is_good_prospect" not in src


def test_gates_pass_on_current_data(con):
    from aayai.validation.run import build_context, gold_gate_suite, run_suite

    gold_df = con.execute(f"SELECT * FROM {PROFILES_READ}").df()
    context = build_context()
    result = run_suite(context, "gold_test", gold_gate_suite(), gold_df)
    assert result.success
