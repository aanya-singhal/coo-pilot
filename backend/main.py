"""CoO-PILOT backend - FastAPI application.

Run locally:

    uvicorn backend.main:app --reload

Interactive API docs for the frontend: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.database import get_database
from backend.services import rule_store
from backend.models import HealthResponse, RootResponse
from backend.routes import (
    claims,
    console,
    dashboard,
    documents,
    pipeline,
    review,
    rules,
)

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


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Restore amended rule versions before serving any request.

    The registry holds version 1 of each agreement from code. Anything
    amended since lives in storage, and has to be back in the registry
    before a claim is evaluated, or a decision would silently be judged
    under a superseded rule.
    """
    try:
        restored = rule_store.restore(get_database())
        if restored:
            logger.info("Restored %d amended rule version(s)", restored)
    except Exception:  # noqa: BLE001 - never block startup on this
        logger.exception("Could not restore rule versions; using code defaults")
    yield


app = FastAPI(
    lifespan=lifespan,
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
app.include_router(rules.router)


@app.get("/", response_model=RootResponse, tags=["meta"])
def root() -> RootResponse:
    return RootResponse(service="CoO-PILOT Backend", version=VERSION, docs="/docs")


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok", supabase_configured=get_settings().supabase_configured
    )