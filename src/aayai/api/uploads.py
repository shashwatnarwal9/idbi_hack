"""Upload & Analyze endpoints: run analyst CSVs through the pipeline in isolation.

Results live in the isolated upload_* tables (never the seeded book). Uploaded
CSVs have no ground truth, so responses carry results only, never accuracy.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from aayai.api.deps import get_conn
from aayai.uploads import store
from aayai.uploads.analyze import (
    HistoryGateError,
    UploadValidationError,
    analyze_upload,
)
from aayai.uploads.schema import MIN_HISTORY_MONTHS, schema_doc

router = APIRouter(prefix="/uploads", tags=["uploads"])

BANDS = {"high", "medium", "low"}


@router.get("/schema")
def schema() -> dict:
    """The required/optional columns the pipeline needs from uploaded CSVs."""
    return schema_doc()


@router.get("")
def batches(conn=Depends(get_conn)) -> list[dict]:
    """List analysed batches (isolated from the seeded book)."""
    store.ensure_tables(conn)
    return store.list_batches(conn)


def _parse_mapping(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(422, f"invalid mapping JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise HTTPException(422, "mapping must be a JSON object")
    return value


async def _run(
    transactions: UploadFile,
    customers: UploadFile | None,
    transactions_mapping: str | None,
    customers_mapping: str | None,
    note: str,
    uploaded_by: str,
    *,
    min_history_months: int | None,
    run_gates: bool,
) -> dict:
    """Save the uploaded files to a temp dir and drive analyze_upload."""
    work = Path(tempfile.mkdtemp(prefix="aayai-upload-in-"))
    try:
        txn_path = work / "transactions.csv"
        with txn_path.open("wb") as f:
            shutil.copyfileobj(transactions.file, f)
        cust_path = None
        if customers is not None:
            cust_path = work / "customers.csv"
            with cust_path.open("wb") as f:
                shutil.copyfileobj(customers.file, f)
        try:
            return analyze_upload(
                transactions_path=txn_path,
                customers_path=cust_path,
                txn_override=_parse_mapping(transactions_mapping),
                cust_override=_parse_mapping(customers_mapping),
                note=note,
                min_history_months=min_history_months,
                run_gates=run_gates,
                uploaded_by=uploaded_by,
            )
        except HistoryGateError as exc:
            raise HTTPException(
                422,
                detail={
                    "errors": exc.errors,
                    "history_failures": exc.failures,
                    "min_history_months": exc.min_months,
                },
            ) from exc
        except UploadValidationError as exc:
            raise HTTPException(422, detail={"errors": exc.errors}) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)


@router.post("/analyze")
async def analyze(
    transactions: UploadFile = File(...),
    customers: UploadFile | None = File(None),
    transactions_mapping: str | None = Form(None),
    customers_mapping: str | None = Form(None),
    note: str = Form(""),
    uploaded_by: str = Form("analyst"),
) -> dict:
    """Isolated preview: analyse a CSV pair without gates or merge (no history gate)."""
    return await _run(
        transactions,
        customers,
        transactions_mapping,
        customers_mapping,
        note,
        uploaded_by,
        min_history_months=None,
        run_gates=False,
    )


@router.post("/ingest")
async def ingest(
    transactions: UploadFile = File(...),
    customers: UploadFile | None = File(None),
    transactions_mapping: str | None = Form(None),
    customers_mapping: str | None = Form(None),
    note: str = Form(""),
    uploaded_by: str = Form("analyst"),
) -> dict:
    """Gated ingestion: enforce the 18-month history gate, then run the pipeline's
    GE hard gates. A short-history book is rejected (422) before the pipeline; a
    gate failure yields status='failed' (not mergeable). Only status='passed'
    batches can be merged into the main database."""
    return await _run(
        transactions,
        customers,
        transactions_mapping,
        customers_mapping,
        note,
        uploaded_by,
        min_history_months=MIN_HISTORY_MONTHS,
        run_gates=True,
    )


def _require_batch(conn, batch_id: str) -> None:
    store.ensure_tables(conn)
    if not store.batch_exists(conn, batch_id):
        raise HTTPException(404, f"batch '{batch_id}' not found")


@router.get("/{batch_id}")
def batch_status(batch_id: str, conn=Depends(get_conn)) -> dict:
    """Batch metadata: status, gate results, history config, merge audit trail."""
    _require_batch(conn, batch_id)
    batch = store.get_batch(conn, batch_id)
    return {**batch, "merge_history": store.merge_history(conn, batch_id)}


@router.get("/{batch_id}/summary")
def batch_summary(batch_id: str, conn=Depends(get_conn)) -> dict:
    _require_batch(conn, batch_id)
    return store.summary(conn, batch_id)


@router.get("/{batch_id}/ranked")
def batch_ranked(
    batch_id: str, confidence: list[str] | None = None, conn=Depends(get_conn)
) -> list[dict]:
    _require_batch(conn, batch_id)
    if confidence is not None:
        unknown = set(confidence) - BANDS
        if unknown:
            raise HTTPException(422, f"unknown confidence bands: {sorted(unknown)}")
    return store.ranked(conn, batch_id, bands=confidence)


@router.get("/{batch_id}/customers/{customer_id}")
def batch_profile(batch_id: str, customer_id: str, conn=Depends(get_conn)) -> dict:
    _require_batch(conn, batch_id)
    result = store.profile(conn, batch_id, customer_id)
    if result is None:
        raise HTTPException(404, f"customer '{customer_id}' not found in batch")
    return result


class MergeRequest(BaseModel):
    merged_by: str = "analyst"
    confirm: bool = False


@router.post("/{batch_id}/merge")
def merge(batch_id: str, body: MergeRequest, conn=Depends(get_conn)) -> dict:
    """Permanently merge a PASSED batch into the main book (explicit confirm required)."""
    _require_batch(conn, batch_id)
    if not body.confirm:
        raise HTTPException(
            422, "explicit confirm required to merge into the main database"
        )
    try:
        return store.merge_batch(conn, batch_id, body.merged_by)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{batch_id}/revert")
def revert(batch_id: str, body: MergeRequest, conn=Depends(get_conn)) -> dict:
    """Roll back a merged batch from the main book by batch_id (soft-delete)."""
    _require_batch(conn, batch_id)
    return store.revert_batch(conn, batch_id, body.merged_by)


class RenameRequest(BaseModel):
    name: str


@router.patch("/{batch_id}")
def rename(batch_id: str, body: RenameRequest, conn=Depends(get_conn)) -> dict:
    """Rename a batch's editable display name (does not touch its data)."""
    _require_batch(conn, batch_id)
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name cannot be empty")
    store.rename_batch(conn, batch_id, name)
    return store.get_batch(conn, batch_id)


@router.delete("/{batch_id}")
def discard_batch(batch_id: str, conn=Depends(get_conn)) -> dict:
    """Discard a staged (un-merged) batch from the isolated upload tables."""
    _require_batch(conn, batch_id)
    store.delete_batch(conn, batch_id)
    return {"batch_id": batch_id, "discarded": True}
