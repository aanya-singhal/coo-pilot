"""CoO-PILOT backend - FastAPI application.

Run locally:

    uvicorn backend.main:app --reload

Interactive API docs for the frontend: http://localhost:8000/docs
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.models import HealthResponse, RootResponse
from backend.routes import claims, console, dashboard, documents, pipeline, review

logging.basicConfig(level=logging.INFO)

VERSION = "0.1.0"

settings = get_settings()

class UTF8JSONResponse(JSONResponse):
    """JSON with an explicit charset.

    Responses carry non-ASCII text (the origin criteria use "≥"). Without
    the charset a browser opening an endpoint directly falls back to a
    legacy encoding and renders it as mojibake.
    """

    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="CoO-PILOT Backend",
    description="Backend API for Certificate of Origin verification.",
    version=VERSION,
    default_response_class=UTF8JSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# review is included first so that GET /claims/review matches the literal
# path instead of being captured by GET /claims/{claim_id}.
app.include_router(review.router)
app.include_router(claims.router)
app.include_router(documents.router)
app.include_router(pipeline.router)
app.include_router(dashboard.router)
app.include_router(console.router)


@app.get("/", response_model=RootResponse, tags=["meta"])
def root() -> RootResponse:
    return RootResponse(service="CoO-PILOT Backend", version=VERSION, docs="/docs")


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok", supabase_configured=get_settings().supabase_configured
    )
