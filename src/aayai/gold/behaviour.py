"""Gold behavioural signals — one row per customer from silver transactions only.

Six signals feed the behavioural (B) half of intent, all normalised to 0-1
across the book (RFM-style decile ranking via percent_rank):
  * emi_regularity  — coverage × amount stability of the dominant EMI stream
  * emi_ending      — a regular EMI stream absent in the most recent 2 months
  * is_renter       — recurring rent debits
  * sip_discipline  — SIP months present / months of history
  * surplus_trend   — mean monthly net, last 3 months vs the prior 3
  * income_growth   — income_net, last 3 months vs the prior 3

Ground-truth firewall: the SQL reads no "_"-prefixed column — only the derived
category / is_income / counterparty and the amount/timestamp. See
tests/test_behaviour_firewall.py.
"""

from __future__ import annotations

import duckdb

from aayai.paths import GOLD_DIR
from aayai.silver.transform import TXN_READ as SILVER_READ
from aayai.util import run_sql_file

BEHAVIOUR_FILE = GOLD_DIR / "behaviour_signals.parquet"
BEHAVIOUR_READ = f"read_parquet('{BEHAVIOUR_FILE.as_posix()}')"

# The signals consumed by intent.behavioral_score / per_product_behavioral.
SIGNAL_COLUMNS = (
    "emi_regularity",
    "emi_ending",
    "is_renter",
    "sip_discipline",
    "surplus_trend",
    "income_growth",
)


def build(con: duckdb.DuckDBPyConnection) -> None:
    """Rebuild behavioural signals from silver transactions."""
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    BEHAVIOUR_FILE.unlink(missing_ok=True)
    run_sql_file(
        con,
        "gold_behaviour.sql",
        silver_read=SILVER_READ,
        out_file=BEHAVIOUR_FILE.as_posix(),
    )


def verify(con: duckdb.DuckDBPyConnection) -> None:
    """Print row uniqueness and a profile of the derived behavioural signals."""
    n, n_unique = con.execute(
        f"SELECT count(*), count(DISTINCT customer_id) FROM {BEHAVIOUR_READ}"
    ).fetchone()
    status = "OK" if n == n_unique else "DUPLICATES"
    print(f"[behaviour] {n} rows, {n_unique} unique customers [{status}]")
    renters, ending = con.execute(
        f"SELECT sum(is_renter), sum(emi_ending) FROM {BEHAVIOUR_READ}"
    ).fetchone()
    print(f"[behaviour] renters: {renters} | emi-ending customers: {ending}")
    for col in SIGNAL_COLUMNS:
        lo, avg, hi = con.execute(
            f"SELECT min({col}), round(avg({col}), 3), max({col}) FROM {BEHAVIOUR_READ}"
        ).fetchone()
        print(f"[behaviour] {col:<16} min={lo} avg={avg} max={hi}")


def main() -> None:
    """Run the build, then print the verification summary."""
    con = duckdb.connect()
    build(con)
    verify(con)


if __name__ == "__main__":
    main()
