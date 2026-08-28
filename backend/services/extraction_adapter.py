"""Adapter around Person 1's extraction module.

The backend does NOT implement extraction. This module only:

1. materialises the stored document bytes as a temp file, because
   ``extraction/extractor.py`` takes a file path; and
2. calls ``extract_document(file_path, doc_type)`` and returns its dict.

Person 1's code is imported lazily so that the backend (and the tests) can
start without ``GEMINI_API_KEY`` being set - ``extraction/extractor.py``
builds its Gemini client at import time.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Document types Person 1's extractor currently understands.
SUPPORTED_DOC_TYPES: frozenset[str] = frozenset({"invoice", "packing_list"})


def _load_extract_document() -> Callable[[str, str], dict[str, Any]]:
    """Import Person 1's ``extract_document`` without modifying their code."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from extraction.extractor import extract_document

    return extract_document


def extract_document_bytes(
    *, content: bytes, filename: str, doc_type: str
) -> dict[str, Any]:
    """Run Person 1's extractor over ``content``.

    Returns whatever their module returns - a data dict on success, or a dict
    with an ``error`` key on failure. The backend stores the result verbatim
    and never interprets it.

    NOTE for Person 1: ``extractor.py`` hardcodes ``mime_type="image/png"``,
    so PDF and JPEG uploads are currently sent to Gemini labelled as PNG.
    The backend accepts and stores all four file types; making the extractor
    mime-aware is an extraction-side change, not a backend one.
    """
    if doc_type not in SUPPORTED_DOC_TYPES:
        return {
            "skipped": True,
            "reason": f"doc_type '{doc_type}' is not handled by the extraction module",
            "supported_doc_types": sorted(SUPPORTED_DOC_TYPES),
        }

    try:
        extract_document = _load_extract_document()
    except Exception as exc:
        logger.exception("Extraction module unavailable")
        return {"error": f"Extraction module unavailable: {exc}"}

    suffix = PurePosixPath(filename).suffix.lower() or ".png"
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        result = extract_document(tmp_path, doc_type)
    except Exception as exc:
        logger.exception("Extraction failed for %s", filename)
        return {"error": f"Extraction call failed: {exc}"}
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)

    if not isinstance(result, dict):
        return {"error": f"Extractor returned {type(result).__name__}, expected dict"}
    return result
