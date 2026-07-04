"""Required schema the pipeline needs from uploaded CSVs, plus header mapping.

The canonical field names below are what silver/gold consume. Uploaded files
may use different headers; :func:`resolve_mapping` matches them by synonym so
the analyst usually needs no manual mapping, and reports exactly which required
fields are missing when it cannot.

region is optional and only ever displayed (fairness context); it is never a
model input. Uploaded files carry no "_" ground-truth columns, so accuracy is
never measured on them — results only.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    required: bool
    description: str
    synonyms: tuple[str, ...]


TRANSACTION_FIELDS: tuple[Field, ...] = (
    Field(
        "customer_id",
        True,
        "Account/customer identifier",
        ("customer_id", "customerid", "cust_id", "account_id", "acct_id", "account"),
    ),
    Field(
        "timestamp",
        True,
        "Transaction date/time (parseable)",
        (
            "timestamp",
            "date",
            "txn_date",
            "transaction_date",
            "value_date",
            "posted_at",
        ),
    ),
    Field(
        "amount",
        True,
        "Transaction amount (numeric, positive)",
        ("amount", "amt", "transaction_amount", "txn_amount", "value"),
    ),
    Field(
        "type",
        True,
        "Credit/debit indicator (CR/DR)",
        ("type", "txn_type", "cr_dr", "drcr", "dr_cr", "direction", "transaction_type"),
    ),
    Field(
        "narration",
        True,
        "Free-text narration / description",
        ("narration", "description", "particulars", "remarks", "details", "text"),
    ),
    Field(
        "balance_after",
        False,
        "Running balance after the transaction",
        ("balance_after", "balance", "running_balance", "closing_balance"),
    ),
)

CUSTOMER_FIELDS: tuple[Field, ...] = (
    Field(
        "customer_id",
        True,
        "Account/customer identifier",
        ("customer_id", "customerid", "cust_id", "account_id", "acct_id", "account"),
    ),
    Field(
        "name",
        False,
        "Display name",
        ("name", "customer_name", "full_name", "account_name"),
    ),
    Field(
        "declared_monthly_income",
        False,
        "Self-declared monthly income",
        (
            "declared_monthly_income",
            "declared_income",
            "monthly_income",
            "income",
            "stated_income",
        ),
    ),
    Field(
        "occupation_declared",
        False,
        "Declared occupation",
        ("occupation_declared", "occupation", "profession", "job"),
    ),
    Field(
        "region",
        False,
        "City/region (display only, never a model input)",
        ("region", "city", "location", "branch_city", "branch"),
    ),
)

CREDIT_TOKENS = {"CR", "CREDIT", "C", "CRDT", "DEPOSIT", "CREDITED"}
DEBIT_TOKENS = {"DR", "DEBIT", "D", "DBT", "WITHDRAWAL", "DEBITED"}

# Minimum months of transaction history every customer must have before an
# uploaded book may be ingested into the main database. A short-history book is
# rejected before the pipeline runs. Named constant, never a magic number.
MIN_HISTORY_MONTHS = 18


def _norm(header: str) -> str:
    return header.strip().lower().replace(" ", "_").replace("-", "_")


def resolve_mapping(
    headers: list[str],
    fields: tuple[Field, ...],
    override: dict[str, str] | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Map canonical field -> source header.

    Args:
        headers: the uploaded file's column headers.
        fields: the field spec (TRANSACTION_FIELDS or CUSTOMER_FIELDS).
        override: analyst-supplied field -> header choices, taking precedence.

    Returns:
        (mapping, missing_required): mapping only contains fields that were
        matched; missing_required lists required fields with no match.
    """
    override = override or {}
    by_norm = {_norm(h): h for h in headers}
    mapping: dict[str, str] = {}
    missing: list[str] = []
    for field in fields:
        chosen = override.get(field.name)
        if chosen and chosen in headers:
            mapping[field.name] = chosen
            continue
        match = next(
            (by_norm[_norm(s)] for s in field.synonyms if _norm(s) in by_norm), None
        )
        if match:
            mapping[field.name] = match
        elif field.required:
            missing.append(field.name)
    return mapping, missing


def schema_doc() -> dict:
    """Machine-readable schema for the upload UI."""
    return {
        "transactions": [
            {"field": f.name, "required": f.required, "description": f.description}
            for f in TRANSACTION_FIELDS
        ],
        "customers": [
            {"field": f.name, "required": f.required, "description": f.description}
            for f in CUSTOMER_FIELDS
        ],
    }
