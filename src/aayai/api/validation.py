"""Validation endpoints: the real Great Expectations structure for the UI.

Serves the static suite catalog (bronze structural, silver_gate, gold_gate,
gold_confidence) plus the live confidence-band distribution, so the Validation
page shows complete, accurate check counts instead of hardcoded numbers. The
catalog is plain data (no Great Expectations import), kept in lock-step with the
live suites by tests/test_validation_catalog.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from aayai.api.deps import get_conn
from aayai.serving.queries import portfolio_summary
from aayai.validation.catalog import GROUND_TRUTH_PREFIX, suite_catalog

router = APIRouter(prefix="/validation", tags=["validation"])

_FIREWALL = (
    'Ground-truth firewall: bronze carries the evaluation-only "'
    f'{GROUND_TRUTH_PREFIX}"-prefixed columns unchanged, but no suite ever '
    "asserts on or reads them. Validation is a transform like any other and "
    "treats ground truth as if absent, so no label can leak into a decision."
)


@router.get("/structure")
def structure(conn=Depends(get_conn)) -> dict:
    """Complete validation structure + live confidence-band distribution."""
    suites = suite_catalog()
    gate_suites = [s for s in suites if s["role"] == "gate"]
    total_expectations = sum(s["n_expectations"] for s in suites)
    summary = portfolio_summary(conn)
    return {
        "suites": suites,
        "totals": {
            "suites": len(suites),
            "gates": len(gate_suites),
            "expectations": total_expectations,
            "gate_expectations": sum(s["n_expectations"] for s in gate_suites),
        },
        "bands": summary.get("bands", {"high": 0, "medium": 0, "low": 0}),
        "customers": summary.get("customers", 0),
        "firewall": _FIREWALL,
    }
