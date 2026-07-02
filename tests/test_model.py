"""Model tests: honest features, sufficient skill, and no reliance on region.

Run after: python -m aayai.model.train
"""

import json

import pytest

from aayai.model.train import (
    FEATURES,
    META_FILE,
    MODEL_FILE,
    REPORT_FILE,
    load_features,
)

pytestmark = pytest.mark.skipif(
    not MODEL_FILE.exists(), reason="model not trained yet; run aayai.model.train"
)


def test_feature_firewall():
    assert not any(c.startswith("_") for c in FEATURES)
    assert "region" not in FEATURES
    assert "customer_id" not in FEATURES
    meta = json.loads(META_FILE.read_text(encoding="utf-8"))
    assert meta["features"] == FEATURES


def test_model_loads_and_scores():
    import xgboost as xgb

    X = load_features()[0]
    booster = xgb.Booster()
    booster.load_model(MODEL_FILE.as_posix())
    proba = booster.inplace_predict(X[FEATURES])
    assert len(proba) == len(X)
    assert ((proba >= 0) & (proba <= 1)).all()


def test_test_set_skill():
    report = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    assert report["metrics"]["roc_auc"] >= 0.85
    assert report["metrics"]["recall"] >= 0.7


def test_region_does_not_drive_the_score():
    report = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    fair = report["fairness"]
    assert (
        fair["region_shap_share"] < 0.10
    ), f"region contributes {fair['region_shap_share']:.1%} of SHAP mass"
    assert abs(fair["auc_delta"]) < 0.10
