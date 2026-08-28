"""Adapter around Person 2's Rules Engine.

TODO(Person 2): the rules engine does not exist in the repo yet.

When it lands, either name it so one of ``CANDIDATE_MODULES`` matches, or add
its import path to that list. The expected contract is a single callable:

    def evaluate(extraction: dict) -> dict

``extraction`` is ``{"<doc_type>": {<extracted fields>}, ...}`` - for example
``{"invoice": {...}, "packing_list": {...}}`` - built from the results Person
1's extractor returned for the claim's documents.

The return value should be a dict; these keys are read if present, and
anything else is preserved verbatim under ``raw``::

    {
      "reconciliation": {...},
      "rules": {...},
      "risk": {...},
      "decision": "APPROVED" | "REJECTED" | "PENDING_REVIEW"
    }

Until then this adapter returns a clearly-marked placeholder. The backend
does not reconcile, score risk, or decide anything on its own.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: Module paths checked, in order, for Person 2's engine.
CANDIDATE_MODULES: tuple[str, ...] = (
    "rules.engine",
    "rules.rules_engine",
    "rules_engine",
    "logic.rules_engine",
)

#: Function names checked, in order, inside a matched module.
CANDIDATE_FUNCTIONS: tuple[str, ...] = (
    "evaluate",
    "run_rules",
    "apply_rules",
    "reconcile_and_verdict",
)

#: Neutral fallback - "a human should look at this", not a computed verdict.
DEFAULT_DECISION = "PENDING_REVIEW"


def _load_rules_engine() -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    """Return Person 2's entry point, or ``None`` if it is not present yet."""
    for module_path in CANDIDATE_MODULES:
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            continue
        for name in CANDIDATE_FUNCTIONS:
            func = getattr(module, name, None)
            if callable(func):
                logger.info("Using rules engine %s.%s", module_path, name)
                return func
    return None


def _placeholder() -> dict[str, Any]:
    return {
        "reconciliation": None,
        "rules": None,
        "risk": None,
        "decision": DEFAULT_DECISION,
        "raw": {
            "status": "NOT_IMPLEMENTED",
            "detail": (
                "Rules engine not found. Backend stored extraction results only. "
                "See backend/services/rules_adapter.py for the expected interface."
            ),
        },
    }


def _normalise(result: Any) -> dict[str, Any]:
    """Shape Person 2's return value without interpreting it."""
    if not isinstance(result, dict):
        return {
            "reconciliation": None,
            "rules": None,
            "risk": None,
            "decision": DEFAULT_DECISION,
            "raw": {"error": f"Rules engine returned {type(result).__name__}"},
        }

    known = {"reconciliation", "rules", "risk", "decision"}
    extra = {k: v for k, v in result.items() if k not in known}

    return {
        "reconciliation": result.get("reconciliation"),
        "rules": result.get("rules"),
        "risk": result.get("risk"),
        "decision": result.get("decision") or DEFAULT_DECISION,
        "raw": extra or None,
    }


def run_rules(extraction: dict[str, Any]) -> dict[str, Any]:
    """Call Person 2's engine over ``extraction`` and normalise the result."""
    engine = _load_rules_engine()
    if engine is None:
        logger.warning("Rules engine not available - returning placeholder result")
        return _placeholder()

    try:
        return _normalise(engine(extraction))
    except Exception as exc:
        logger.exception("Rules engine raised")
        return {
            "reconciliation": None,
            "rules": None,
            "risk": None,
            "decision": DEFAULT_DECISION,
            "raw": {"error": f"Rules engine failed: {exc}"},
        }
