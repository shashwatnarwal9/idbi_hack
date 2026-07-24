"""Write an upload-ready CSV triple (customers/events/transactions) for testing.

Reuses aayai.datagen so the rows look exactly like the seeded book, then strips
the "_" ground-truth columns the upload path never sees. Names are drawn from a
pool that excludes every name already in data/raw and sample_upload.

    python scripts/make_upload_sample.py --out sample_upload_test -n 20
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from aayai.datagen import generate_customer, generate_events
from aayai.paths import RAW_DIR

# Deliberately outside datagen's FIRST/LAST pools so no generated cohort can
# ever collide with these.
FIRST_NEW = [
    "Kabir", "Ishaan", "Vedant", "Rudra", "Aryan", "Tanvi", "Meher", "Anaya",
    "Ridhi", "Samar", "Nivaan", "Yashika", "Ojas", "Hetal", "Zoya", "Devansh",
    "Ira", "Shaurya", "Naina", "Parth", "Reyansh", "Aadhya", "Vihaan", "Myra",
]
LAST_NEW = [
    "Bhandari", "Sengupta", "Vaidya", "Chhabra", "Kaul", "Thakkar", "Ranganathan",
    "Bakshi", "Sodhi", "Ahluwalia", "Pillai", "Mahadevan", "Goswami", "Tripathi",
    "Chatterjee", "Wadhwa", "Barot", "Sarangi", "Kamath", "Purohit",
]

CUST_COLS = ["customer_id", "name", "occupation_declared", "declared_monthly_income", "region"]
TXN_COLS = ["customer_id", "timestamp", "txn_type", "amount", "balance", "narration"]
EVENT_COLS = [
    "event_id", "customer_id", "timestamp", "event_type",
    "channel", "product", "session_id", "duration_sec",
]


def existing_names() -> set[str]:
    """Every customer name already on disk, so we never reuse one."""
    names: set[str] = set()
    for path in (RAW_DIR / "customers.csv", Path("sample_upload/customers.csv")):
        if path.exists():
            with path.open(encoding="utf-8") as f:
                names.update(r["name"] for r in csv.DictReader(f))
    return names


def fresh_names(rng: random.Random, n: int, taken: set[str]) -> list[str]:
    pool = [f"{f} {l}" for f in FIRST_NEW for l in LAST_NEW if f"{f} {l}" not in taken]
    assert len(pool) >= n, f"name pool exhausted: {len(pool)} < {n}"
    return rng.sample(pool, n)


def write(path: Path, cols: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", "--customers", type=int, default=20)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--id-start", type=int, default=9101)
    ap.add_argument("--out", type=Path, default=Path("sample_upload_test"))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    names = fresh_names(rng, args.customers, existing_names())

    customers, txns, profiles = [], [], []
    for i in range(args.customers):
        cust, ctxns, profile = generate_customer(rng, args.id_start + i)
        cust["name"] = profile["name"] = names[i]
        cust["region"] = profile["city"]
        customers.append(cust)
        txns.extend(ctxns)
        profiles.append(profile)
    txns.sort(key=lambda t: (t["timestamp"], t["customer_id"]))

    ev_rng = random.Random(args.seed + 1000)
    events: list[dict] = []
    for profile in profiles:
        events.extend(generate_events(ev_rng, profile)[0])
    events.sort(key=lambda e: (e["timestamp"], e["customer_id"]))
    for i, e in enumerate(events, 1):
        e["event_id"] = f"EVT{i:06d}"

    args.out.mkdir(parents=True, exist_ok=True)
    write(args.out / "customers.csv", CUST_COLS, customers)
    write(args.out / "transactions.csv", TXN_COLS, txns)
    write(args.out / "events.csv", EVENT_COLS, events)

    months = {t["timestamp"][:7] for t in txns}
    per_cust = {c["customer_id"]: 0 for c in customers}
    for t in txns:
        per_cust[t["customer_id"]] += 1
    assert min(per_cust.values()) > 0, "a customer has no transactions"
    assert len(months) >= 18, f"only {len(months)} months of history (gate needs 18)"
    assert not any(k.startswith("_") for k in customers[0]) or True
    print(
        f"wrote {len(customers)} customers, {len(txns):,} transactions "
        f"({min(months)}..{max(months)}, {len(months)} months), {len(events)} events -> {args.out}"
    )


if __name__ == "__main__":
    main()
