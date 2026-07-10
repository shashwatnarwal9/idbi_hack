"""Repeatable hard reset for the demo cohort.

Wipes every generated artifact, the raw CSVs, the bronze/silver/gold Parquet
lake, and the Postgres serving + workflow tables, then regenerates a brand-new
synthetic cohort (fresh ids via --id-start, fresh people via --seed) and re-runs
the whole pipeline end to end so the new customers are scored and served.

    python -m aayai.reset                       # 320 customers, ids from CUST01001
    python -m aayai.reset --customers 300 --seed 7 --id-start 2001
    python -m aayai.reset --no-run              # wipe + regenerate only

Safe to run repeatedly; every step drops-and-rebuilds rather than appending.
"""

from __future__ import annotations

import argparse
import shutil

from aayai.paths import BRONZE_DIR, GOLD_DIR, RAW_DIR, SILVER_DIR

# Every app-owned serving table; dropped so no stale customer survives a reset.
DROP_TABLES = [
    # intent / lead layer
    "lead_scores",
    "intent_scores",
    "engagement_summary",
    "behaviour_signals",
    # analyst workflow (old marks point at customers that no longer exist)
    "interactions",
    "lead_contacts",
    "review_status",
    "share_log",
    # core serving
    "key_transactions",
    "income_streams",
    "spending_breakdown",
    "income_by_month",
    "prospect_scores",
    "customer_profiles",
    # uploaded-batch staging
    "merge_log",
    "upload_transactions",
    "upload_streams",
    "upload_profiles",
    "upload_batches",
]


def wipe_files() -> None:
    """Delete the raw CSVs and every medallion Parquet output."""
    for path in (RAW_DIR, BRONZE_DIR, SILVER_DIR, GOLD_DIR):
        if path.exists():
            shutil.rmtree(path)
            print(f"[reset] removed {path}")


def wipe_db() -> None:
    """Drop every app-owned serving table (idempotent; skips if DB unreachable)."""
    from aayai.serving.db import connect

    try:
        conn = connect()
    except Exception as exc:  # noqa: BLE001 - reset should not hard-fail on no DB
        print(
            f"[reset] serving DB unreachable ({exc.__class__.__name__}); skipped DB wipe"
        )
        return
    with conn, conn.cursor() as cur:
        for table in DROP_TABLES:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    conn.close()
    print(f"[reset] dropped {len(DROP_TABLES)} serving tables")


def run_pipeline() -> None:
    """Run every stage main() in dependency order for the new cohort."""
    from aayai.bronze.ingest import main as bronze
    from aayai.gold.behaviour import main as behaviour
    from aayai.gold.build import main as gold
    from aayai.gold.engagement import main as engagement
    from aayai.model.train import main as train
    from aayai.serving.intent_load import main as intent_load
    from aayai.serving.load import main as serve_load
    from aayai.silver.transform import main as silver
    from aayai.validation.run import main as validation

    bronze()
    silver()
    gold()
    behaviour()
    engagement()
    try:
        validation()  # writes confidence_band onto gold; exits non-zero on gate fail
    except SystemExit as exc:
        if exc.code:
            raise RuntimeError("GE gates failed on the generated cohort") from exc
    train()
    serve_load()
    intent_load()


def main() -> None:
    ap = argparse.ArgumentParser(description="Wipe + regenerate + rerun the pipeline")
    ap.add_argument("--customers", type=int, default=320)
    ap.add_argument("--seed", type=int, default=20250107)
    ap.add_argument(
        "--id-start", type=int, default=1001, help="first customer index (new ids)"
    )
    ap.add_argument("--no-run", action="store_true", help="wipe + regenerate only")
    args = ap.parse_args()

    print("[reset] wiping generated data and serving tables …")
    wipe_files()
    wipe_db()

    from aayai.datagen import generate

    generate(args.customers, args.seed, events=True, id_start=args.id_start)

    if not args.no_run:
        run_pipeline()
    print("[reset] done.")


if __name__ == "__main__":
    main()
