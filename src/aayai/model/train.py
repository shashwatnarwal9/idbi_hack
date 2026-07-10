"""XGBoost prospect model.

Predicts _is_good_prospect from gold-derived features only. _is_good_prospect
is the training target (y): the single permitted use of a "_" column outside
evaluation. No "_" column, and no region, is ever a feature.

Also runs the fairness audit: a throwaway variant trained WITH region, so SHAP
can show the model gains nothing from it.

Artifacts (model/):
  aayai_model.ubj    XGBoost native model
  feature_meta.json  feature order + categorical encodings (serving needs this)
  train_report.json  metrics + fairness + SHAP summary (tests assert on this)
"""

from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from aayai.gold.build import PROFILES_READ
from aayai.paths import MODEL_DIR

MODEL_FILE = MODEL_DIR / "aayai_model.ubj"
META_FILE = MODEL_DIR / "feature_meta.json"
REPORT_FILE = MODEL_DIR / "train_report.json"

ORDINAL = {
    "risk_capacity": {"low": 0, "medium": 1, "high": 2},
    "confidence_band": {"low": 0, "medium": 1, "high": 2},
}
INCOME_TYPES = ["salaried", "gig", "business"]

NUMERIC_FEATURES = [
    "true_monthly_income",
    "income_volatility",
    "avg_monthly_essentials",
    "total_emi",
    "total_sip",
    "investable_surplus",
    "surplus_stability",
    "savings_rate",
    "months_history",
    "pct_categorized",
]
FEATURES = (
    NUMERIC_FEATURES
    + ["risk_capacity_ord", "confidence_band_ord"]
    + [f"income_type_{t}" for t in INCOME_TYPES]
)

SEED = 42


def encode_features(df: pd.DataFrame) -> pd.DataFrame:
    """Encode a gold-profile dataframe into the model feature matrix.

    Shared by training, seeded scoring and uploaded-batch scoring, so every
    code path builds features identically. Requires the gold columns plus a
    confidence_band column (assigned by the validation stage).
    """
    X = df[NUMERIC_FEATURES].astype(float).copy()
    for col, mapping in ORDINAL.items():
        X[f"{col}_ord"] = df[col].map(mapping).astype(int)
    for t in INCOME_TYPES:
        X[f"income_type_{t}"] = (df["income_type"] == t).astype(int)
    X = X[FEATURES]

    # the firewall, checked at runtime: features contain no "_" column & no region
    assert not any(c.startswith("_") for c in X.columns)
    assert "region" not in X.columns
    return X


def load_features() -> tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """Build the model matrix from gold profiles.

    Returns:
        (X, y, ids, region): features only, target, customer ids, and region,
        which is returned separately for the fairness audit and is never in X.
    """
    df = duckdb.connect().execute(f"SELECT * FROM {PROFILES_READ}").df()
    X = encode_features(df)
    y = df["_is_good_prospect"].astype(int)  # TARGET: permitted use
    return X, y, df["customer_id"], df["region"]


def fit(X_train: pd.DataFrame, y_train: pd.Series) -> xgb.XGBClassifier:
    """Train the classifier with fixed, seeded hyperparameters."""
    clf = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        eval_metric="logloss",
        tree_method="hist",
        random_state=SEED,
    )
    clf.fit(X_train, y_train)
    return clf


def metrics_report(clf, X_test, y_test) -> dict:
    """Compute test-set accuracy, precision, recall, ROC-AUC and the confusion matrix."""
    pred = clf.predict(X_test)
    proba = clf.predict_proba(X_test)[:, 1]
    cm = confusion_matrix(y_test, pred)
    return {
        "accuracy": float(accuracy_score(y_test, pred)),
        "precision": float(precision_score(y_test, pred)),
        "recall": float(recall_score(y_test, pred)),
        "roc_auc": float(roc_auc_score(y_test, proba)),
        "confusion_matrix": cm.tolist(),
        "n_test": int(len(y_test)),
    }


def shap_summary(clf, X: pd.DataFrame) -> list[tuple[str, float]]:
    """(feature, mean |SHAP|) ranked; SHAP values are in log-odds units."""
    sv = shap.TreeExplainer(clf).shap_values(X)
    mean_abs = np.abs(sv).mean(axis=0)
    order = np.argsort(mean_abs)[::-1]
    return [(X.columns[i], float(mean_abs[i])) for i in order]


def fairness_audit(
    X_train, X_test, y_train, y_test, region_train, region_test, main_auc: float
) -> dict:
    """Train a throwaway variant WITH region; show SHAP gives it ~no weight."""
    region_cols = sorted(set(region_train) | set(region_test))

    def with_region(X, region):
        Xr = X.copy()
        for city in region_cols:
            Xr[f"region_{city}"] = (region.values == city).astype(int)
        return Xr

    Xr_train, Xr_test = with_region(X_train, region_train), with_region(
        X_test, region_test
    )
    clf_r = fit(Xr_train, y_train)
    auc_r = float(roc_auc_score(y_test, clf_r.predict_proba(Xr_test)[:, 1]))
    ranked = shap_summary(clf_r, Xr_test)
    total = sum(v for _, v in ranked) or 1.0
    region_share = sum(v for f, v in ranked if f.startswith("region_")) / total
    top_region = next(
        ((f, v) for f, v in ranked if f.startswith("region_")), ("region_*", 0.0)
    )
    return {
        "auc_without_region": main_auc,
        "auc_with_region": auc_r,
        "auc_delta": auc_r - main_auc,
        "region_shap_share": float(region_share),
        "strongest_region_feature": {
            "name": top_region[0],
            "mean_abs_shap": top_region[1],
        },
    }


def reason_codes(
    clf, X_test: pd.DataFrame, ids_test: pd.Series, k: int = 3
) -> list[dict]:
    """Per-customer top SHAP drivers for 3 examples: strong yes / borderline / strong no."""
    proba = clf.predict_proba(X_test)[:, 1]
    sv = shap.TreeExplainer(clf).shap_values(X_test)
    picks = {
        "strong yes": int(np.argmax(proba)),
        "borderline": int(np.argmin(np.abs(proba - 0.5))),
        "strong no": int(np.argmin(proba)),
    }
    out = []
    for label, i in picks.items():
        order = np.argsort(np.abs(sv[i]))[::-1][:k]
        out.append(
            {
                "customer_id": str(ids_test.iloc[i]),
                "kind": label,
                "p_good_prospect": float(proba[i]),
                "reasons": [
                    {
                        "feature": X_test.columns[j],
                        "value": float(X_test.iloc[i, j]),
                        "shap": float(sv[i][j]),
                    }
                    for j in order
                ],
            }
        )
    return out


def main() -> None:
    """Train, evaluate, audit and save the model plus its reports."""
    X, y, ids, region = load_features()
    print(f"[model] features ({len(FEATURES)}): {', '.join(FEATURES)}")
    print(
        f"[model] 'region' among features: {'region' in FEATURES} | "
        f"'_' columns among features: {any(c.startswith('_') for c in FEATURES)}"
    )

    X_train, X_test, y_train, y_test, ids_train, ids_test, reg_train, reg_test = (
        train_test_split(
            X, y, ids, region, test_size=0.25, stratify=y, random_state=SEED
        )
    )
    clf = fit(X_train, y_train)

    m = metrics_report(clf, X_test, y_test)
    (tn, fp), (fn, tp) = m["confusion_matrix"]
    print(
        f"[model] test metrics (n={m['n_test']}, stratified 75/25 split): "
        f"accuracy={m['accuracy']:.3f} precision={m['precision']:.3f} "
        f"recall={m['recall']:.3f} ROC-AUC={m['roc_auc']:.3f}"
    )
    print(f"[model] confusion matrix [test]: TN={tn} FP={fp} / FN={fn} TP={tp}")

    ranked = shap_summary(clf, X_test)
    print("[model] SHAP top features (mean |log-odds| on test):")
    for f, v in ranked[:8]:
        print(f"  {f:<24} {v:.3f}")

    fair = fairness_audit(
        X_train, X_test, y_train, y_test, reg_train, reg_test, m["roc_auc"]
    )
    print(
        f"[model] fairness audit: AUC without region={fair['auc_without_region']:.3f} "
        f"vs with region={fair['auc_with_region']:.3f} "
        f"(delta={fair['auc_delta']:+.3f})"
    )
    print(
        f"[model] region SHAP share in the with-region variant: "
        f"{fair['region_shap_share']:.1%} "
        f"(strongest: {fair['strongest_region_feature']['name']} "
        f"at {fair['strongest_region_feature']['mean_abs_shap']:.4f}) "
        f"-> region does not drive the score"
    )

    examples = reason_codes(clf, X_test, ids_test)
    print("[model] reason codes (top SHAP drivers, log-odds):")
    for e in examples:
        parts = [
            f"{r['feature']}={r['value']:,.2f} ({r['shap']:+.2f})" for r in e["reasons"]
        ]
        print(
            f"  {e['customer_id']} [{e['kind']}] "
            f"P(good)={e['p_good_prospect']:.2f}: " + "; ".join(parts)
        )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    clf.get_booster().save_model(MODEL_FILE.as_posix())
    META_FILE.write_text(
        json.dumps(
            {
                "features": FEATURES,
                "ordinal_encodings": ORDINAL,
                "income_types": INCOME_TYPES,
                "seed": SEED,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    REPORT_FILE.write_text(
        json.dumps(
            {
                "metrics": m,
                "fairness": fair,
                "shap_top": [{"feature": f, "mean_abs_shap": v} for f, v in ranked],
                "examples": examples,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"[model] saved {MODEL_FILE.as_posix()}, feature_meta.json, train_report.json"
    )


if __name__ == "__main__":
    main()
