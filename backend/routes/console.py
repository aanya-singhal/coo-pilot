"""Compatibility endpoint for Person 4's ``console.html``.

The console calls ``POST /process`` with a case id and a list of sample
filenames from ``extraction/``, and expects ``{invoice, packing_list,
verdict}`` back (the shapes in the root ``schema.py``).

This route adapts that contract onto the real backend flow - it creates a
claim, uploads each sample file to storage, and runs the normal pipeline -
then reshapes the output. It does not reimplement anything: extraction is
Person 1's module and the verdict comes from Person 2's engine via the rules
adapter.

When the rules engine is absent the verdict is reported as ``PENDING_REVIEW``
rather than a fabricated GREEN/YELLOW. The console renders anything that is
not ``GREEN`` as amber, so this degrades honestly.
"""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.config import ALLOWED_EXTENSIONS
from backend.database import Database, get_database
from backend.models import DocumentType
from backend.services import claims as claims_service, pipeline as pipeline_service
from backend.services.storage import Storage, get_storage

logger = logging.getLogger(__name__)

router = APIRouter(tags=["console"])

#: Sample documents shipped by Person 1 live here.
SAMPLES_DIR = Path(__file__).resolve().parents[2] / "extraction"

#: The console colours on GREEN and treats everything else as amber, so the
#: backend's decision is mapped to its vocabulary rather than the reverse.
_DECISION_COLOURS = {
    "APPROVED": "GREEN",
    "REJECTED": "RED",
    "PENDING_REVIEW": "YELLOW",
}

_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class ConsoleProcessRequest(BaseModel):
    case_id: str = Field(max_length=200)
    files: list[str] = Field(min_length=1, max_length=10)


def _resolve_sample(filename: str) -> Path:
    """Resolve a sample filename to a path inside ``extraction/``.

    Only bare filenames are accepted, so a caller cannot walk out of the
    samples directory.
    """
    if PurePosixPath(filename).name != filename or filename in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail=f"Invalid filename '{filename}'")

    suffix = PurePosixPath(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"Unsupported file type '{filename}'"
        )

    path = (SAMPLES_DIR / filename).resolve()
    if not path.is_relative_to(SAMPLES_DIR.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Sample '{filename}' not found")
    return path


def _infer_doc_type(filename: str) -> DocumentType:
    lowered = filename.lower()
    if "packing" in lowered:
        return DocumentType.PACKING_LIST
    if "invoice" in lowered:
        return DocumentType.INVOICE
    raise HTTPException(
        status_code=400,
        detail=(
            f"Cannot tell the document type of '{filename}'. Name it so it "
            "contains 'invoice' or 'packing'."
        ),
    )


@router.post("/process")
def process_console_case(
    payload: ConsoleProcessRequest,
    db: Annotated[Database, Depends(get_database)],
    storage: Annotated[Storage, Depends(get_storage)],
) -> dict[str, Any]:
    """Run the pipeline over sample files and answer in the console's shape."""
    resolved = [(name, _resolve_sample(name)) for name in payload.files]

    claim = claims_service.create_claim(
        db, reference=payload.case_id, metadata={"source": "console.html"}
    )
    claim_id = claim["id"]

    for name, path in resolved:
        claims_service.add_document(
            db,
            storage,
            claim_id=claim_id,
            filename=name,
            content=path.read_bytes(),
            content_type=_CONTENT_TYPES[PurePosixPath(name).suffix.lower()],
            doc_type=_infer_doc_type(name),
        )

    pipeline_service.process_claim(db, storage, claim_id)
    result = pipeline_service.get_result(db, claim_id)
    extraction = result.get("extraction") or {}

    # If extraction did not produce usable documents, fail loudly. The console
    # already falls back to its recorded case on a non-OK response, which is
    # far better than rendering half-empty fields.
    errors = {
        doc_type: data.get("error")
        for doc_type, data in extraction.items()
        if isinstance(data, dict) and data.get("error")
    }
    if errors or not extraction:
        raise HTTPException(
            status_code=502,
            detail={"message": "Extraction did not return usable data", "errors": errors},
        )

    rules = result.get("rules") or {}
    decision = result.get("decision") or "PENDING_REVIEW"
    engine_missing = result.get("reconciliation") is None and not rules

    return {
        "case_id": payload.case_id,
        "claim_id": claim_id,
        "invoice": extraction.get("invoice"),
        "packing_list": extraction.get("packing_list"),
        "verdict": {
            "case_id": payload.case_id,
            "verdict": _DECISION_COLOURS.get(decision, "YELLOW"),
            "decision": decision,
            "reason": (
                "Documents extracted successfully. Awaiting the rules engine "
                "for a reconciliation verdict."
                if engine_missing
                else rules.get("reason", "")
            ),
            "rule_applied": rules.get("rule_applied", "Rules engine not integrated"),
            "rule_satisfied": bool(rules.get("rule_satisfied", False)),
        },
        # Full detail for a dashboard that wants to show the working.
        "reconciliation": result.get("reconciliation"),
        "rules": rules,
        "risk": result.get("risk"),
    }
