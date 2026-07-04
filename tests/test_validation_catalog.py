"""The static validation catalog must never drift from the live GE suites.

Builds each real suite and asserts its expectation count matches the catalog the
API serves to the Validation page, so a check added/removed in run.py without
updating catalog.py (or vice-versa) fails CI.
"""

from aayai.validation.catalog import suite_catalog
from aayai.validation.run import (
    bronze_structural_suite,
    build_context,
    confidence_suite,
    gold_gate_suite,
    silver_gate_suite,
)


def _live_counts() -> dict[str, int]:
    build_context()  # suites need an active GX context to be assembled
    suites = {
        "bronze_structural": bronze_structural_suite(),
        "silver_gate": silver_gate_suite(),
        "gold_gate": gold_gate_suite(),
        "gold_confidence": confidence_suite(),
    }
    return {name: len(list(s.expectations)) for name, s in suites.items()}


def test_catalog_counts_match_live_suites():
    live = _live_counts()
    catalog = {e["suite"]: e["n_expectations"] for e in suite_catalog()}
    assert catalog == live


def test_catalog_covers_all_layers_and_roles():
    entries = suite_catalog()
    layers = {e["layer"] for e in entries}
    assert layers == {"Bronze", "Silver", "Gold"}
    # exactly one soft feature suite (the confidence tiers); the rest are gates
    roles = [e["role"] for e in entries]
    assert roles.count("feature") == 1
    assert roles.count("gate") == 3


def test_no_ground_truth_column_is_validated():
    # firewall: no "_"-prefixed (ground-truth) column may appear in any check
    for entry in suite_catalog():
        for check in entry["checks"]:
            assert "`_" not in check["detail"], check
