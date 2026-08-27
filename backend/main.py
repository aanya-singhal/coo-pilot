"""CoO-PILOT backend - FastAPI application.

Run locally:

    uvicorn backend.main:app --reload

Interactive API docs for the frontend: http://localhost:8000/docs
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.models import HealthResponse, RootResponse
from backend.routes import claims, console, documents, pipeline

logging.basicConfig(level=logging.INFO)

VERSION = "0.1.0"

settings = get_settings()

app = FastAPI(
    title="CoO-PILOT Backend",
    description="Backend API for Certificate of Origin verification.",
    version=VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(claims.router)
app.include_router(documents.router)
app.include_router(pipeline.router)
app.include_router(console.router)


@app.get("/", response_model=RootResponse, tags=["meta"])
def root() -> RootResponse:
    return RootResponse(service="CoO-PILOT Backend", version=VERSION, docs="/docs")


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok", supabase_configured=get_settings().supabase_configured
    )
