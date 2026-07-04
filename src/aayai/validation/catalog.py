"""Static catalog of the आय·AI validation structure.

Single source of truth for WHICH expectations each Great Expectations suite
runs, importable without loading Great Expectations (so the API can serve the
Validation page cheaply). `run.py` builds the live suites from the SAME column
lists defined here, and `tests/test_validation_catalog.py` asserts the built
suites match these counts — so the catalog can never silently drift from code.

Ground-truth firewall
---------------------
Bronze carries the evaluation-only "_"-prefixed columns (`_true_category`,
`_is_income`) through UNCHANGED, but NO suite ever asserts on them or reads them
as an input. Validation is a transform like any other: it treats ground truth as
if absent, so a label can never leak into a pipeline decision. The bronze
structural suite deliberately checks only the non-"_" analytic columns.
"""

from __future__ import annotations

GROUND_TRUTH_PREFIX = "_"

# ── Bronze (structural): schema intact + non-derived keys present, pre-cleaning ─
BRONZE_STRUCT_COLUMNS = [
    "txn_id",
    "customer_id",
    "timestamp",
    "txn_type",
    "amount",
    "balance",
    "narration",
]
BRONZE_NOT_NULL = ["txn_id", "customer_id", "timestamp", "txn_type", "amount"]

# ── Silver (gate): nulls, ranges and value domains on cleaned transactions ─────
SILVER_NOT_NULL = [
    "txn_id",
    "customer_id",
    "category",
    "direction",
    "amount",
    "is_income",
    "parse_confidence",
]

# ── Gold (gate): keys, history, income and surplus bounds on profiles ──────────
GOLD_KEY_FIELDS = [
    "customer_id",
    "income_type",
    "true_monthly_income",
    "investable_surplus",
    "risk_capacity",
    "region",
    "months_history",
    "pct_categorized",
]

# ── Gold (feature): tiered trust checks that become the confidence_band ────────
# Key = the band the tier guards; each tier contributes 2 expectations.
BAND_RULES = {
    "high": {"months": 12, "pct": 0.90},
    "medium": {"months": 6, "pct": 0.85},
}

# hard gate floors (kept here so the catalog descriptions and run.py agree)
GATE_MIN_MONTHS = 6
GATE_MIN_PCT = 0.60
SURPLUS_BOUNDS = (-200_000, 1_000_000)


def _checks(*items: tuple[str, str]) -> list[dict]:
    return [{"expectation": e, "detail": d} for e, d in items]


def _bronze_checks() -> list[dict]:
    out = [
        {"expectation": "expect_column_to_exist", "detail": f"column `{c}` present"}
        for c in BRONZE_STRUCT_COLUMNS
    ]
    out += [
        {
            "expectation": "expect_column_values_to_not_be_null",
            "detail": f"`{c}` not null",
        }
        for c in BRONZE_NOT_NULL
    ]
    out.append(
        {
            "expectation": "expect_column_values_to_be_unique",
            "detail": "`txn_id` unique",
        }
    )
    return out


def _silver_checks() -> list[dict]:
    out = [
        {
            "expectation": "expect_column_values_to_not_be_null",
            "detail": f"`{c}` not null",
        }
        for c in SILVER_NOT_NULL
    ]
    out += _checks(
        ("expect_column_values_to_be_between", "`parse_confidence` in [0, 1]"),
        ("expect_column_values_to_be_between", "`amount` > 0"),
        ("expect_column_values_to_be_in_set", "`direction` in {credit, debit}"),
        ("expect_column_values_to_be_in_set", "`category` in the silver category set"),
    )
    return out


def _gold_checks() -> list[dict]:
    out = [
        {
            "expectation": "expect_column_values_to_not_be_null",
            "detail": f"`{c}` not null",
        }
        for c in GOLD_KEY_FIELDS
    ]
    out += _checks(
        ("expect_column_values_to_be_unique", "`customer_id` unique"),
        (
            "expect_column_values_to_be_between",
            f"`months_history` >= {GATE_MIN_MONTHS}",
        ),
        ("expect_column_values_to_be_between", f"`pct_categorized` >= {GATE_MIN_PCT}"),
        ("expect_column_values_to_be_between", "`true_monthly_income` > 0"),
        (
            "expect_column_values_to_be_between",
            f"`investable_surplus` in [{SURPLUS_BOUNDS[0]:,}, {SURPLUS_BOUNDS[1]:,}]",
        ),
    )
    return out


def _confidence_checks() -> list[dict]:
    out: list[dict] = []
    for band, rule in BAND_RULES.items():
        out.append(
            {
                "expectation": "expect_column_values_to_be_between",
                "detail": f"[{band} tier] months_history >= {rule['months']}",
            }
        )
        out.append(
            {
                "expectation": "expect_column_values_to_be_between",
                "detail": f"[{band} tier] pct_categorized >= {rule['pct']}",
            }
        )
    return out


def suite_catalog() -> list[dict]:
    """Every suite with its layer, role, purpose and full expectation list."""
    entries = [
        {
            "suite": "bronze_structural",
            "layer": "Bronze",
            "role": "gate",
            "purpose": (
                "Structural floor on raw bronze transactions: the schema is intact "
                "and the non-derived key fields are present, before any cleaning."
            ),
            "checks": _bronze_checks(),
        },
        {
            "suite": "silver_gate",
            "layer": "Silver",
            "role": "gate",
            "purpose": (
                "Hard floor on cleaned transactions: nulls, numeric ranges and "
                "value domains (direction, category)."
            ),
            "checks": _silver_checks(),
        },
        {
            "suite": "gold_gate",
            "layer": "Gold",
            "role": "gate",
            "purpose": (
                "Hard floor on customer profiles: unique keys, minimum history, "
                "positive income and plausible surplus bounds."
            ),
            "checks": _gold_checks(),
        },
        {
            "suite": "gold_confidence",
            "layer": "Gold",
            "role": "feature",
            "purpose": (
                "Soft, per-customer trust tiers (NOT a hard gate): failures "
                "downgrade a customer's confidence_band so a weak estimate is "
                "never shown as high-trust."
            ),
            "checks": _confidence_checks(),
        },
    ]
    for e in entries:
        e["n_expectations"] = len(e["checks"])
    return entries
