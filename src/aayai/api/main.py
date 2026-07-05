"""आय·AI API application.

Run locally:  uvicorn aayai.api.main:app --port 8000 --reload
Every endpoint reads live from the serving store, model artifacts or Airflow
state; nothing is fabricated. Missing sources return an honest "unavailable".
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aayai.api.config import AAYAI_ENV, CORS_ORIGINS
from aayai.api.customers import router as customers_router
from aayai.api.loan_assessment import router as loan_assessment_router
from aayai.api.loan_calc import router as loan_calc_router
from aayai.api.overview import router as overview_router
from aayai.api.pipeline import router as pipeline_router
from aayai.api.uploads import router as uploads_router
from aayai.api.validation import router as validation_router

app = FastAPI(title="AayAI API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Shared-At"],  # so the browser can read the share timestamp
)

app.include_router(overview_router)
app.include_router(customers_router)
app.include_router(pipeline_router)
app.include_router(uploads_router)
app.include_router(loan_assessment_router)
app.include_router(loan_calc_router)
app.include_router(validation_router)


@app.get("/health")
def health() -> dict:
    """Liveness probe for the API process itself, tagged with the deploy env."""
    return {"status": "ok", "env": AAYAI_ENV}
