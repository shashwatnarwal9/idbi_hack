"""Idempotent schema migration for the serving store.

Creates the tables the API depends on that the data loader does not own, reusing
the same DDL the app creates lazily at runtime (no duplicated schema):

  review_status                 analyst review marks (aayai.serving.reviews)
  share_log                     customer-summary share audit (aayai.serving.shares)
  upload_batches / _profiles /
  _streams / _transactions      uploaded-batch staging (aayai.uploads.store)
  merge_log                     merge/revert audit for merged batches
  customer_profiles.source/     provenance columns, added only if the table
  batch_id/merged_at            already exists (the loader creates them otherwise)

Not covered here, by design:
  * The core gold tables (customer_profiles, prospect_scores, spending_breakdown,
    income_streams, key_transactions, income_by_month) are created AND populated
    by the loader (aayai.serving.load), which drops and rebuilds them each run.
  * Loan eligibility is derived at query time from gold fields — there is no
    eligibility table to migrate.
  * Airflow run state is read live from Airflow, so there is no pipeline_runs
    table.

Runs against whatever the environment points at (SERVING_DB_DSN or AAYAI_PG_*):
    python -m aayai.serving.migrate
"""

from __future__ import annotations

from aayai.serving.db import connect
from aayai.serving.reviews import ensure_table as ensure_reviews
from aayai.serving.shares import ensure_table as ensure_shares
from aayai.uploads.store import ensure_main_source_columns
from aayai.uploads.store import ensure_tables as ensure_upload_tables


def migrate(conn) -> None:
    """Create/verify every serving table the loader does not create (idempotent)."""
    ensure_reviews(conn)
    ensure_shares(conn)
    ensure_upload_tables(conn)
    ensure_main_source_columns(conn)


def main() -> None:
    """Apply the migration and print the resulting public-schema tables."""
    conn = connect()
    migrate(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        tables = [r[0] for r in cur.fetchall()]
    print(f"[migrate] serving schema ready ({len(tables)} tables):")
    for table in tables:
        print(f"  {table}")
    conn.close()


if __name__ == "__main__":
    main()
