#!/usr/bin/env python
"""Repeatable performance benchmark for the आय·AI prototype.

Measures the deterministic local stack and writes benchmarks/results.json:
  * dataset scale, model quality (classifier + income reconstruction + silver),
  * DB point-lookup and API latency (p50/p95), model inference throughput,
  * data-quality gate counts, and (with --pipeline) per-stage rebuild timings.

    python scripts/benchmark.py                 # read-only (safe, fast)
    python scripts/benchmark.py --pipeline      # + times a full rebuild

Every section is isolated: a failure records an "error" string instead of
sinking the whole run. Nothing external is invented, accuracy comes from the
existing evaluate modules and the trained model report.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "benchmarks" / "results.json"
API_BASE = os.environ.get("AAYAI_API_BASE", "http://localhost:8000")


def _pct(values: list[float], p: float) -> float:
    """Linear-interpolated percentile (p in [0, 100])."""
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _summ(times_ms: list[float]) -> dict:
    return {
        "n": len(times_ms),
        "p50_ms": round(_pct(times_ms, 50), 3),
        "p95_ms": round(_pct(times_ms, 95), 3),
        "mean_ms": round(statistics.mean(times_ms), 3),
        "min_ms": round(min(times_ms), 3),
        "max_ms": round(max(times_ms), 3),
    }


def environment() -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }


def dataset_scale() -> dict:
    import duckdb

    from aayai.bronze.ingest import CUSTOMERS_FILE, EVENTS_DIR, EVENTS_READ
    from aayai.bronze.ingest import TXN_READ as BRONZE_TXN
    from aayai.paths import RAW_DIR

    con = duckdb.connect()
    out: dict = {}
    out["customers"] = con.execute(
        f"SELECT count(*) FROM read_parquet('{CUSTOMERS_FILE.as_posix()}')"
    ).fetchone()[0]
    out["transactions"] = con.execute(f"SELECT count(*) FROM {BRONZE_TXN}").fetchone()[
        0
    ]
    out["events"] = (
        con.execute(f"SELECT count(*) FROM {EVENTS_READ}").fetchone()[0]
        if EVENTS_DIR.exists()
        else 0
    )
    out["raw_csv_bytes"] = {
        name: (RAW_DIR / name).stat().st_size if (RAW_DIR / name).exists() else None
        for name in ("transactions.csv", "customers.csv", "events.csv")
    }
    return out


def model_quality() -> dict:
    out: dict = {}
    # classifier metrics from the trained-model report
    try:
        from aayai.model.train import MODEL_DIR

        report = json.loads((MODEL_DIR / "train_report.json").read_text("utf-8"))
        out["classifier"] = {**report["metrics"], "fairness": report["fairness"]}
    except Exception as exc:  # noqa: BLE001
        out["classifier"] = {"error": f"{exc.__class__.__name__}: {exc}"}
    # income reconstruction vs ground truth
    try:
        from aayai.gold.evaluate import evaluate as gold_eval

        g = gold_eval()
        out["income_reconstruction"] = {
            "pearson_r": round(g["corr"], 4),
            "mae": round(g["mae"], 2),
            "bias": round(g["bias"], 2),
            "mape": round(g["mape"], 4),
            "n": g["n"],
        }
    except Exception as exc:  # noqa: BLE001
        out["income_reconstruction"] = {"error": f"{exc.__class__.__name__}: {exc}"}
    # silver category accuracy
    try:
        from aayai.silver.evaluate import evaluate as silver_eval

        s = silver_eval()
        out["silver_category"] = {
            "overall_accuracy": round(s["overall"], 4),
            "is_income_accuracy": round(s["is_income_acc"], 4),
            "rows": s["total"],
        }
    except Exception as exc:  # noqa: BLE001
        out["silver_category"] = {"error": f"{exc.__class__.__name__}: {exc}"}
    return out


def db_latency(reps: int) -> dict:
    try:
        from aayai.serving.db import connect
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{exc.__class__.__name__}: {exc}"}
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT min(customer_id) FROM customer_profiles")
            cid = cur.fetchone()[0]
            if cid is None:
                return {"error": "no customers in serving store"}
            times = []
            for _ in range(reps):
                t0 = time.perf_counter()
                cur.execute(
                    """
                    SELECT p.true_monthly_income, p.confidence_band, s.p_good_prospect
                    FROM customer_profiles p
                    JOIN prospect_scores s USING (customer_id)
                    WHERE p.customer_id = %s
                    """,
                    (cid,),
                )
                cur.fetchone()
                times.append((time.perf_counter() - t0) * 1000)
        return {"query": "profile point lookup (join)", **_summ(times)}
    finally:
        conn.close()


def api_latency(reps: int) -> dict:
    import httpx

    # resolve a real customer id via the API (or in-process TestClient fallback)
    def _endpoints(cid: str) -> list[str]:
        return [
            "/overview/summary",
            f"/customers/{cid}",
            f"/intent/{cid}",
            "/leads/personal",
            "/outreach/queue",
        ]

    # try the live server first
    try:
        r = httpx.get(f"{API_BASE}/customers/ranked", timeout=5)
        r.raise_for_status()
        cid = r.json()[0]["customer_id"]
        mode, get = "live", lambda p: httpx.get(f"{API_BASE}{p}", timeout=10)
    except Exception:
        from fastapi.testclient import TestClient

        from aayai.api.main import app

        client = TestClient(app)
        cid = client.get("/customers/ranked").json()[0]["customer_id"]
        mode, get = "in-process (TestClient)", client.get

    out: dict = {"mode": mode, "endpoints": {}}
    for path in _endpoints(cid):
        try:
            get(path)  # warm
            times = []
            for _ in range(reps):
                t0 = time.perf_counter()
                resp = get(path)
                _ = resp.status_code
                times.append((time.perf_counter() - t0) * 1000)
            out["endpoints"][path.replace(cid, "{id}")] = _summ(times)
        except Exception as exc:  # noqa: BLE001
            out["endpoints"][path] = {"error": f"{exc.__class__.__name__}: {exc}"}
    return out


def model_inference() -> dict:
    try:
        from aayai.model.train import load_features
        from aayai.serving.load import score_frame

        X, _y, ids, _region = load_features()
        t0 = time.perf_counter()
        rows = score_frame(X, ids)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        n = len(rows)
        return {
            "customers_scored": n,
            "total_ms": round(elapsed_ms, 2),
            "per_customer_us": round(elapsed_ms * 1000 / n, 2) if n else None,
            "note": "XGBoost predict + SHAP reason codes for the whole book",
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{exc.__class__.__name__}: {exc}"}


def data_quality_gates() -> dict:
    try:
        from aayai.validation.catalog import suite_catalog

        suites = suite_catalog()
        return {
            "suites": len(suites),
            "gate_suites": sum(1 for s in suites if s["role"] == "gate"),
            "total_expectations": sum(s["n_expectations"] for s in suites),
            "by_suite": {s["suite"]: s["n_expectations"] for s in suites},
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{exc.__class__.__name__}: {exc}"}


def pipeline_timings() -> dict:
    """Time each stage main() rebuilding from the CURRENT raw CSVs (same cohort)."""
    stages: list[tuple[str, str]] = [
        ("bronze", "aayai.bronze.ingest"),
        ("silver", "aayai.silver.transform"),
        ("gold_build", "aayai.gold.build"),
        ("gold_behaviour", "aayai.gold.behaviour"),
        ("gold_engagement", "aayai.gold.engagement"),
        ("validation", "aayai.validation.run"),
        ("model_train", "aayai.model.train"),
        ("serving_load", "aayai.serving.load"),
        ("intent_load", "aayai.serving.intent_load"),
    ]
    import importlib

    timings: dict = {}
    for name, module_path in stages:
        module = importlib.import_module(module_path)
        t0 = time.perf_counter()
        try:
            module.main()
            timings[name] = round(time.perf_counter() - t0, 2)
        except SystemExit as exc:  # validation exits non-zero only on gate failure
            timings[name] = {
                "seconds": round(time.perf_counter() - t0, 2),
                "exit_code": exc.code,
            }
        except Exception as exc:  # noqa: BLE001
            timings[name] = {"error": f"{exc.__class__.__name__}: {exc}"}
    timings["total_seconds"] = round(
        sum(v for v in timings.values() if isinstance(v, (int, float))), 2
    )
    return timings


def main() -> None:
    ap = argparse.ArgumentParser(description="AayAI prototype benchmark")
    ap.add_argument("--pipeline", action="store_true", help="also time a full rebuild")
    ap.add_argument("--db-reps", type=int, default=200)
    ap.add_argument("--api-reps", type=int, default=30)
    args = ap.parse_args()

    results: dict = {"environment": environment()}
    print("[bench] environment:", results["environment"]["platform"])

    if args.pipeline:
        print("[bench] timing full pipeline rebuild (this reloads the same cohort)…")
        results["pipeline_stage_seconds"] = pipeline_timings()

    print("[bench] dataset scale…")
    results["dataset"] = dataset_scale()
    print("[bench] model quality (accuracy)…")
    results["model_quality"] = model_quality()
    print(f"[bench] db point-lookup latency (x{args.db_reps})…")
    results["db_point_lookup"] = db_latency(args.db_reps)
    print(f"[bench] api latency (x{args.api_reps}/endpoint)…")
    results["api_latency"] = api_latency(args.api_reps)
    print("[bench] model inference throughput…")
    results["model_inference"] = model_inference()
    print("[bench] data-quality gates…")
    results["data_quality_gates"] = data_quality_gates()

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n[bench] wrote {RESULTS}")
    print(json.dumps(_summary(results), indent=2))


def _summary(r: dict) -> dict:
    """A compact human summary for the console."""
    db = r.get("db_point_lookup", {})
    inf = r.get("model_inference", {})
    mq = r.get("model_quality", {})
    return {
        "customers": r.get("dataset", {}).get("customers"),
        "transactions": r.get("dataset", {}).get("transactions"),
        "events": r.get("dataset", {}).get("events"),
        "roc_auc": mq.get("classifier", {}).get("roc_auc"),
        "income_pearson_r": mq.get("income_reconstruction", {}).get("pearson_r"),
        "silver_accuracy": mq.get("silver_category", {}).get("overall_accuracy"),
        "db_p50_ms": db.get("p50_ms"),
        "db_p95_ms": db.get("p95_ms"),
        "inference_per_customer_us": inf.get("per_customer_us"),
        "gate_expectations": r.get("data_quality_gates", {}).get("total_expectations"),
    }


if __name__ == "__main__":
    sys.exit(main())
