"""API tests: shell, ranking, review persistence, profile, pipeline state."""

import pytest
from fastapi.testclient import TestClient

from aayai.api.main import app

client = TestClient(app)

try:
    from aayai.serving.db import connect

    _conn = connect()
except Exception:
    _conn = None

needs_store = pytest.mark.skipif(
    _conn is None, reason="serving postgres not reachable; start it via docker compose"
)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok" and "env" in body


def test_cors_allows_only_react_dev_origin():
    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    other = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


@needs_store
def test_ranked_matches_db_order():
    rows = client.get("/customers/ranked").json()
    with _conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM prospect_scores")
        assert len(rows) == cur.fetchone()[0]
        cur.execute(
            "SELECT customer_id FROM prospect_scores "
            "ORDER BY p_good_prospect DESC, customer_id LIMIT 10"
        )
        assert [r["customer_id"] for r in rows[:10]] == [x[0] for x in cur.fetchall()]
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    assert all("reviewed" in r and "name" in r for r in rows)


@needs_store
def test_ranked_confidence_filter_and_validation():
    rows = client.get("/customers/ranked", params={"confidence": ["high"]}).json()
    assert rows and all(r["band"] == "high" for r in rows)
    bad = client.get("/customers/ranked", params={"confidence": ["bogus"]})
    assert bad.status_code == 422


@needs_store
def test_review_roundtrip_persists():
    cid = client.get("/customers/ranked").json()[0]["customer_id"]
    on = client.post(
        f"/customers/{cid}/review", json={"reviewed": True, "reviewed_by": "pytest"}
    ).json()
    assert on["reviewed"] is True and on["reviewed_by"] == "pytest"
    # visible in ranked (server state, not client state)
    rows = client.get("/customers/ranked").json()
    assert next(r for r in rows if r["customer_id"] == cid)["reviewed"] is True
    off = client.post(
        f"/customers/{cid}/review", json={"reviewed": False, "reviewed_by": "pytest"}
    ).json()
    assert off["reviewed"] is False


@needs_store
def test_profile_full_shape_and_404():
    cid = client.get("/customers/ranked").json()[0]["customer_id"]
    res = client.get(f"/customers/{cid}")
    assert res.status_code == 200
    body = res.json()
    assert body["profile"]["customer_id"] == cid
    assert body["score"] and 0 <= body["score"]["p_good_prospect"] <= 1
    sb = body["surplus_breakdown"]
    assert (
        abs(sb["income"] - sb["essentials"] - sb["emis"] - sb["buffer"] - sb["surplus"])
        < 0.02
    )
    assert body["income_streams"] and body["key_transactions"]
    assert "reviewed" in body["review"]

    missing = client.get("/customers/CUST99999")
    assert missing.status_code == 404
    assert "not found" in missing.json()["detail"]


@needs_store
def test_search_partial():
    rows = client.get("/customers/search", params={"q": "0001"}).json()
    assert rows and all("0001" in r["customer_id"] for r in rows)


def test_pipeline_state_is_honest():
    body = client.get("/pipeline/state").json()
    assert "available" in body and "ui_url" in body
    if body["available"] and body.get("run"):
        assert body["run"]["state"] in {"success", "running", "failed", "queued"}
        assert all("task_id" in t and "state" in t for t in body["tasks"])
    else:
        assert body.get("reason") or body.get("run") is None


_VALID_TXN = (
    "account_id,txn_date,amt,dr_cr,description,balance\n"
    "UPX1,2026-01-01,90000,CR,NEFT-HDFC0001-ACME PVT LTD-SALARY CREDIT-N1,90000\n"
    "UPX1,2026-01-05,18000,DR,UPI/12345/LANDLORD/l@okhdfc/RENT,72000\n"
    "UPX1,2026-02-01,90000,CR,NEFT-HDFC0001-ACME PVT LTD-SALARY CREDIT-N2,162000\n"
    "UPX1,2026-02-06,7000,DR,UPI/P2M/9/DMART/dmart@ybl/PAYMENT,155000\n"
    "UPX2,2026-01-03,5000,CR,IMPS/P2A/22/SWIGGY PARTNER PAYOUT/N7,5000\n"
    "UPX2,2026-02-03,5200,CR,IMPS/P2A/22/SWIGGY PARTNER PAYOUT/N8,10200\n"
)
_VALID_CUST = (
    "account_id,customer_name,monthly_income,occupation,city\n"
    "UPX1,Test One,70000,SERVICE,Pune\n"
    "UPX2,Test Two,12000,SELF EMPLOYED,Chennai\n"
)


@needs_store
def test_upload_analyze_isolation_and_discard():
    from aayai.serving.queries import portfolio_summary

    before = portfolio_summary(_conn)["customers"]
    res = client.post(
        "/uploads/analyze",
        files={
            "transactions": ("t.csv", _VALID_TXN, "text/csv"),
            "customers": ("c.csv", _VALID_CUST, "text/csv"),
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    batch_id = body["batch_id"]
    assert body["customers"] == 2 and body["transactions_used"] == 6

    ranked = client.get(f"/uploads/{batch_id}/ranked").json()
    assert [r["rank"] for r in ranked] == [1, 2]
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)
    assert {r["customer_id"] for r in ranked} == {"UPX1", "UPX2"}

    summ = client.get(f"/uploads/{batch_id}/summary").json()
    assert summ["customers"] == 2 and summ["avg_reconstructed"] > 0

    prof = client.get(f"/uploads/{batch_id}/customers/UPX1").json()
    assert prof["profile"]["true_monthly_income"] > 0
    assert prof["score"] and 0 <= prof["score"]["p_good_prospect"] <= 1
    assert prof["income_streams"] and prof["review"] is None

    # the seeded book is untouched by the upload
    assert portfolio_summary(_conn)["customers"] == before

    assert client.delete(f"/uploads/{batch_id}").json()["discarded"] is True
    assert client.get(f"/uploads/{batch_id}/summary").status_code == 404


@needs_store
def test_share_generates_pdf_and_logs():
    cid = client.get("/customers/ranked").json()[0]["customer_id"]
    res = client.post(f"/customers/{cid}/share")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:5] == b"%PDF-"
    # the customer PDF must not leak internal model mechanics
    body = res.content.lower()
    assert b"shap" not in body and b"impactor" not in body
    assert b"prospect score" not in body

    # an append-only share_log row was written and surfaces on the profile
    with _conn.cursor() as cur:
        cur.execute(
            "SELECT document_type FROM share_log WHERE customer_id = %s "
            "ORDER BY shared_at DESC LIMIT 1",
            (cid,),
        )
        row = cur.fetchone()
    assert row and row[0] == "customer_summary"
    _conn.rollback()
    prof = client.get(f"/customers/{cid}").json()
    assert (
        prof["last_share"] and prof["last_share"]["document_type"] == "customer_summary"
    )

    missing = client.post("/customers/CUST99999/share")
    assert missing.status_code == 404


@needs_store
def test_loan_assessment_summary_and_product():
    from aayai.gold.loan_products import PRODUCTS

    summ = client.get("/loan-assessment/summary").json()
    assert summ["customers"] > 0
    assert {p["product"] for p in summ["products"]} == {p.key for p in PRODUCTS}

    rows = client.get("/loan-assessment/personal").json()
    assert len(rows) == summ["customers"]
    # eligible-first, then by score descending
    keys = [(r["status"] != "eligible", -r["score"]) for r in rows]
    assert keys == sorted(keys)
    personal = next(p for p in summ["products"] if p["product"] == "personal")
    assert sum(1 for r in rows if r["status"] == "eligible") == personal["eligible"]

    only = client.get("/loan-assessment/home", params={"status": "eligible"}).json()
    assert all(r["status"] == "eligible" and r["suggested_amount"] for r in only)

    assert client.get("/loan-assessment/bogus").status_code == 404
    assert (
        client.get("/loan-assessment/personal", params={"status": "x"}).status_code
        == 422
    )


def _book(customer_ids, months):
    """Build an 18-month-capable transactions CSV for the given customers."""
    ym = [
        (y, m) for y in (2025, 2026) for m in range(1, 13) if not (y == 2026 and m > 6)
    ]
    header = "account_id,txn_date,amt,dr_cr,description,balance\n"
    rows = []
    for cid in customer_ids:
        for y, m in ym[-months:]:
            rows.append(
                f"{cid},{y}-{m:02d}-01 10:00:00,90000,CR,"
                f"NEFT-HDFC0001-GLOBEX PVT LTD-SALARY CREDIT-N1,90000"
            )
            rows.append(
                f"{cid},{y}-{m:02d}-05 10:00:00,20000,DR,"
                f"UPI/1/RAO/r@okhdfc/RENT,70000"
            )
    return header + "\n".join(rows) + "\n"


_ING_CUST = (
    "account_id,customer_name,monthly_income,occupation,city\n"
    "INGA,Ingest A,70000,SERVICE,Pune\n"
    "INGB,Ingest B,80000,SERVICE,Mumbai\n"
)


@needs_store
def test_gated_ingest_merge_firewall_and_revert():
    from aayai.gold.evaluate import evaluate as gold_eval
    from aayai.serving.queries import portfolio_summary

    acc_before = round(gold_eval()["corr"], 6)
    seeded_before = portfolio_summary(_conn)["customers"]

    res = client.post(
        "/uploads/ingest",
        files={
            "transactions": ("t.csv", _book(["INGA", "INGB"], 18), "text/csv"),
            "customers": ("c.csv", _ING_CUST, "text/csv"),
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "passed" and body["gates"]["passed"] is True
    assert min(h["months"] for h in body["history"]) >= 18
    batch_id = body["batch_id"]

    # merge requires explicit confirm
    assert (
        client.post(f"/uploads/{batch_id}/merge", json={"confirm": False}).status_code
        == 422
    )
    merged = client.post(f"/uploads/{batch_id}/merge", json={"confirm": True}).json()
    assert merged["merged"] == 2 and merged["status"] == "merged"

    # merged customers are operational and tagged 'uploaded' (the book may also
    # hold other legitimately merged batches, so subset — not equality)
    ranked = client.get("/customers/ranked").json()
    uploaded = {r["customer_id"] for r in ranked if r["source"] == "uploaded"}
    assert {"INGA", "INGB"}.issubset(uploaded)

    # accuracy firewall: seeded-only metrics unchanged, operational count grew
    assert round(gold_eval()["corr"], 6) == acc_before
    after = portfolio_summary(_conn)
    assert after["customers"] == seeded_before + 2

    # audit + reversibility
    status = client.get(f"/uploads/{batch_id}").json()
    assert status["status"] == "merged"
    assert any(h["action"] == "merge" for h in status["merge_history"])
    reverted = client.post(f"/uploads/{batch_id}/revert", json={}).json()
    assert reverted["removed"] == 2
    assert portfolio_summary(_conn)["customers"] == seeded_before
    client.delete(f"/uploads/{batch_id}")


@needs_store
def test_gated_ingest_rejects_short_history():
    # INGB has only 6 months -> rejected before the pipeline
    txn = _book(["INGA"], 18) + _book(["INGB"], 6).split("\n", 1)[1]
    res = client.post(
        "/uploads/ingest",
        files={
            "transactions": ("t.csv", txn, "text/csv"),
            "customers": ("c.csv", _ING_CUST, "text/csv"),
        },
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert detail["min_history_months"] == 18
    failures = {f["customer_id"]: f["months"] for f in detail["history_failures"]}
    assert failures == {"INGB": 6}


@needs_store
def test_upload_missing_columns_is_rejected():
    bad = "account_id,txn_date,amt,balance\nUPX1,2026-01-01,1000,50000\n"
    res = client.post(
        "/uploads/analyze",
        files={"transactions": ("bad.csv", bad, "text/csv")},
    )
    assert res.status_code == 422
    errors = res.json()["detail"]["errors"]
    assert any("missing required column" in e for e in errors)
    assert any("type" in e and "narration" in e for e in errors)


@needs_store
def test_loan_calc_endpoint():
    top = client.get("/customers/ranked").json()[0]["customer_id"]
    res = client.get(
        f"/customers/{top}/loan-calc",
        params={"product": "personal", "annual_rate": 11, "amount": 300000},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["affordability"]["max_loan_amount"] >= 0
    assert "requested" in body
    assert "disclaimer" in body
    assert (
        client.get(
            f"/customers/{top}/loan-calc",
            params={"product": "bogus", "annual_rate": 11},
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/customers/{top}/loan-calc",
            params={"product": "personal", "annual_rate": 99},
        ).status_code
        == 422
    )
