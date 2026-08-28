"""Persistence layer for the backend.

Two implementations of the same small interface:

* ``SupabaseDatabase`` - talks to Supabase PostgreSQL (production).
* ``InMemoryDatabase`` - keeps everything in dicts (tests, and local runs
  where ``SUPABASE_URL`` / ``SUPABASE_KEY`` are not set).

Keeping the interface narrow means routes and services never touch the
Supabase client directly, and unit tests never need real credentials.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from backend.config import Settings, get_settings

logger = logging.getLogger(__name__)

Row = dict[str, Any]


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database(ABC):
    """Narrow persistence interface used by the backend services."""

    # --- claims -------------------------------------------------------
    @abstractmethod
    def create_claim(
        self,
        *,
        claim_number: str,
        reference: str | None,
        exporter: str | None,
        metadata: dict[str, Any],
    ) -> Row: ...

    @abstractmethod
    def get_claim(self, claim_id: str) -> Row | None: ...

    @abstractmethod
    def list_claims(
        self, *, limit: int = 50, statuses: list[str] | None = None
    ) -> list[Row]: ...

    @abstractmethod
    def update_claim_status(self, claim_id: str, status: str) -> Row | None: ...

    @abstractmethod
    def count_claims_by_status(self) -> dict[str, int]: ...

    # --- human review decisions ---------------------------------------
    @abstractmethod
    def create_decision(
        self, *, claim_id: str, decision: str, reviewer: str, comments: str | None
    ) -> Row: ...

    @abstractmethod
    def list_decisions(self, claim_id: str) -> list[Row]: ...

    # --- documents ----------------------------------------------------
    @abstractmethod
    def create_document(
        self,
        *,
        document_id: str,
        claim_id: str,
        filename: str,
        doc_type: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
    ) -> Row: ...

    @abstractmethod
    def get_document(self, document_id: str) -> Row | None: ...

    @abstractmethod
    def list_documents(self, claim_id: str) -> list[Row]: ...

    # --- extraction results (owned by Person 1's module) --------------
    @abstractmethod
    def save_extracted_data(
        self,
        *,
        claim_id: str,
        document_id: str,
        data: dict[str, Any],
        extraction_status: str,
    ) -> Row: ...

    @abstractmethod
    def list_extracted_data(self, claim_id: str) -> list[Row]: ...

    # --- origin declaration (cost statement, CAROTAR 2020 Form I) -----
    @abstractmethod
    def save_origin_declaration(
        self, *, claim_id: str, declaration: dict[str, Any]
    ) -> Row: ...

    @abstractmethod
    def get_origin_declaration(self, claim_id: str) -> Row | None: ...

    # --- verification results (owned by Person 2's module) ------------
    @abstractmethod
    def save_verification_result(
        self, *, claim_id: str, result: dict[str, Any], decision: str
    ) -> Row: ...

    @abstractmethod
    def get_verification_result(self, claim_id: str) -> Row | None: ...

    # --- audit --------------------------------------------------------
    @abstractmethod
    def write_audit_log(
        self, *, claim_id: str | None, action: str, details: dict[str, Any]
    ) -> Row: ...

    @abstractmethod
    def list_audit_logs(self, claim_id: str) -> list[Row]: ...


class InMemoryDatabase(Database):
    """Dict-backed database used for tests and credential-free local runs."""

    def __init__(self) -> None:
        self.claims: dict[str, Row] = {}
        self.documents: dict[str, Row] = {}
        self.extracted: list[Row] = []
        self.decisions: list[Row] = []
        self.declarations: dict[str, Row] = {}
        self.verifications: dict[str, Row] = {}
        self.audit: list[Row] = []

    # --- claims -------------------------------------------------------
    def create_claim(
        self,
        *,
        claim_number: str,
        reference: str | None,
        exporter: str | None,
        metadata: dict[str, Any],
    ) -> Row:
        now = _now()
        row: Row = {
            "id": _new_id(),
            "claim_number": claim_number,
            "reference": reference,
            "exporter": exporter,
            "status": "CREATED",
            "metadata": metadata,
            "created_at": now,
            "updated_at": now,
        }
        self.claims[row["id"]] = row
        return dict(row)

    def get_claim(self, claim_id: str) -> Row | None:
        row = self.claims.get(claim_id)
        return dict(row) if row else None

    def list_claims(
        self, *, limit: int = 50, statuses: list[str] | None = None
    ) -> list[Row]:
        rows = sorted(self.claims.values(), key=lambda r: r["created_at"], reverse=True)
        if statuses:
            rows = [r for r in rows if r["status"] in statuses]
        return [dict(r) for r in rows[:limit]]

    def update_claim_status(self, claim_id: str, status: str) -> Row | None:
        row = self.claims.get(claim_id)
        if row is None:
            return None
        row["status"] = status
        row["updated_at"] = _now()
        return dict(row)

    def count_claims_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.claims.values():
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return counts

    # --- decisions ----------------------------------------------------
    def create_decision(
        self, *, claim_id: str, decision: str, reviewer: str, comments: str | None
    ) -> Row:
        row: Row = {
            "id": _new_id(),
            "claim_id": claim_id,
            "decision": decision,
            "reviewer": reviewer,
            "comments": comments,
            "created_at": _now(),
        }
        self.decisions.append(row)
        return dict(row)

    def list_decisions(self, claim_id: str) -> list[Row]:
        rows = [r for r in self.decisions if r["claim_id"] == claim_id]
        rows.sort(key=lambda r: r["created_at"])
        return [dict(r) for r in rows]

    # --- documents ----------------------------------------------------
    def create_document(
        self,
        *,
        document_id: str,
        claim_id: str,
        filename: str,
        doc_type: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
    ) -> Row:
        row: Row = {
            "id": document_id,
            "claim_id": claim_id,
            "filename": filename,
            "doc_type": doc_type,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "storage_path": storage_path,
            "created_at": _now(),
        }
        self.documents[row["id"]] = row
        return dict(row)

    def get_document(self, document_id: str) -> Row | None:
        row = self.documents.get(document_id)
        return dict(row) if row else None

    def list_documents(self, claim_id: str) -> list[Row]:
        rows = [r for r in self.documents.values() if r["claim_id"] == claim_id]
        rows.sort(key=lambda r: r["created_at"])
        return [dict(r) for r in rows]

    # --- extraction ---------------------------------------------------
    def save_extracted_data(
        self,
        *,
        claim_id: str,
        document_id: str,
        data: dict[str, Any],
        extraction_status: str,
    ) -> Row:
        row: Row = {
            "id": _new_id(),
            "claim_id": claim_id,
            "document_id": document_id,
            "data": data,
            "extraction_status": extraction_status,
            "created_at": _now(),
        }
        # One row per document: re-extracting replaces the previous result.
        self.extracted = [
            r for r in self.extracted if r["document_id"] != document_id
        ]
        self.extracted.append(row)
        return dict(row)

    def list_extracted_data(self, claim_id: str) -> list[Row]:
        return [dict(r) for r in self.extracted if r["claim_id"] == claim_id]

    # --- origin declaration -------------------------------------------
    def save_origin_declaration(
        self, *, claim_id: str, declaration: dict[str, Any]
    ) -> Row:
        row: Row = {
            "id": _new_id(),
            "claim_id": claim_id,
            "declaration": declaration,
            "created_at": _now(),
        }
        self.declarations[claim_id] = row
        return dict(row)

    def get_origin_declaration(self, claim_id: str) -> Row | None:
        row = self.declarations.get(claim_id)
        return dict(row) if row else None

    # --- verification -------------------------------------------------
    def save_verification_result(
        self, *, claim_id: str, result: dict[str, Any], decision: str
    ) -> Row:
        row: Row = {
            "id": _new_id(),
            "claim_id": claim_id,
            "result": result,
            "decision": decision,
            "created_at": _now(),
        }
        self.verifications[claim_id] = row
        return dict(row)

    def get_verification_result(self, claim_id: str) -> Row | None:
        row = self.verifications.get(claim_id)
        return dict(row) if row else None

    # --- audit --------------------------------------------------------
    def write_audit_log(
        self, *, claim_id: str | None, action: str, details: dict[str, Any]
    ) -> Row:
        row: Row = {
            "id": _new_id(),
            "claim_id": claim_id,
            "action": action,
            "details": details,
            "created_at": _now(),
        }
        self.audit.append(row)
        return dict(row)

    def list_audit_logs(self, claim_id: str) -> list[Row]:
        return [dict(r) for r in self.audit if r["claim_id"] == claim_id]


class SupabaseDatabase(Database):
    """Supabase PostgreSQL implementation."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def _rows(self, response: Any) -> list[Row]:
        return list(getattr(response, "data", None) or [])

    def _one(self, response: Any) -> Row | None:
        rows = self._rows(response)
        return rows[0] if rows else None

    # --- claims -------------------------------------------------------
    def create_claim(
        self,
        *,
        claim_number: str,
        reference: str | None,
        exporter: str | None,
        metadata: dict[str, Any],
    ) -> Row:
        payload = {
            "claim_number": claim_number,
            "reference": reference,
            "exporter": exporter,
            "status": "CREATED",
            "metadata": metadata,
        }
        response = self._client.table("claims").insert(payload).execute()
        row = self._one(response)
        if row is None:
            raise RuntimeError("Supabase did not return the inserted claim")
        return row

    def get_claim(self, claim_id: str) -> Row | None:
        response = (
            self._client.table("claims").select("*").eq("id", claim_id).limit(1).execute()
        )
        return self._one(response)

    def list_claims(
        self, *, limit: int = 50, statuses: list[str] | None = None
    ) -> list[Row]:
        query = self._client.table("claims").select("*")
        if statuses:
            query = query.in_("status", statuses)
        response = query.order("created_at", desc=True).limit(limit).execute()
        return self._rows(response)

    def count_claims_by_status(self) -> dict[str, int]:
        response = self._client.table("claims").select("status").execute()
        counts: dict[str, int] = {}
        for row in self._rows(response):
            status = row.get("status")
            if status:
                counts[status] = counts.get(status, 0) + 1
        return counts

    # --- decisions ----------------------------------------------------
    def create_decision(
        self, *, claim_id: str, decision: str, reviewer: str, comments: str | None
    ) -> Row:
        payload = {
            "claim_id": claim_id,
            "decision": decision,
            "reviewer": reviewer,
            "comments": comments,
        }
        response = self._client.table("decisions").insert(payload).execute()
        row = self._one(response)
        if row is None:
            raise RuntimeError("Supabase did not return the inserted decision")
        return row

    def list_decisions(self, claim_id: str) -> list[Row]:
        response = (
            self._client.table("decisions")
            .select("*")
            .eq("claim_id", claim_id)
            .order("created_at")
            .execute()
        )
        return self._rows(response)

    def update_claim_status(self, claim_id: str, status: str) -> Row | None:
        payload = {"status": status, "updated_at": _now()}
        response = (
            self._client.table("claims").update(payload).eq("id", claim_id).execute()
        )
        return self._one(response)

    # --- documents ----------------------------------------------------
    def create_document(
        self,
        *,
        document_id: str,
        claim_id: str,
        filename: str,
        doc_type: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
    ) -> Row:
        payload = {
            "id": document_id,
            "claim_id": claim_id,
            "filename": filename,
            "doc_type": doc_type,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "storage_path": storage_path,
        }
        response = self._client.table("documents").insert(payload).execute()
        row = self._one(response)
        if row is None:
            raise RuntimeError("Supabase did not return the inserted document")
        return row

    def get_document(self, document_id: str) -> Row | None:
        response = (
            self._client.table("documents")
            .select("*")
            .eq("id", document_id)
            .limit(1)
            .execute()
        )
        return self._one(response)

    def list_documents(self, claim_id: str) -> list[Row]:
        response = (
            self._client.table("documents")
            .select("*")
            .eq("claim_id", claim_id)
            .order("created_at")
            .execute()
        )
        return self._rows(response)

    # --- extraction ---------------------------------------------------
    def save_extracted_data(
        self,
        *,
        claim_id: str,
        document_id: str,
        data: dict[str, Any],
        extraction_status: str,
    ) -> Row:
        payload = {
            "claim_id": claim_id,
            "document_id": document_id,
            "data": data,
            "extraction_status": extraction_status,
        }
        response = (
            self._client.table("extracted_data")
            .upsert(payload, on_conflict="document_id")
            .execute()
        )
        row = self._one(response)
        if row is None:
            raise RuntimeError("Supabase did not return the inserted extracted_data row")
        return row

    def list_extracted_data(self, claim_id: str) -> list[Row]:
        response = (
            self._client.table("extracted_data")
            .select("*")
            .eq("claim_id", claim_id)
            .order("created_at")
            .execute()
        )
        return self._rows(response)

    # --- origin declaration -------------------------------------------
    def save_origin_declaration(
        self, *, claim_id: str, declaration: dict[str, Any]
    ) -> Row:
        payload = {"claim_id": claim_id, "declaration": declaration}
        response = (
            self._client.table("origin_declarations")
            .upsert(payload, on_conflict="claim_id")
            .execute()
        )
        row = self._one(response)
        if row is None:
            raise RuntimeError("Supabase did not return the origin declaration")
        return row

    def get_origin_declaration(self, claim_id: str) -> Row | None:
        response = (
            self._client.table("origin_declarations")
            .select("*")
            .eq("claim_id", claim_id)
            .limit(1)
            .execute()
        )
        return self._one(response)

    # --- verification -------------------------------------------------
    def save_verification_result(
        self, *, claim_id: str, result: dict[str, Any], decision: str
    ) -> Row:
        payload = {"claim_id": claim_id, "result": result, "decision": decision}
        response = self._client.table("verification_results").insert(payload).execute()
        row = self._one(response)
        if row is None:
            raise RuntimeError("Supabase did not return the inserted verification result")
        return row

    def get_verification_result(self, claim_id: str) -> Row | None:
        response = (
            self._client.table("verification_results")
            .select("*")
            .eq("claim_id", claim_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        return self._one(response)

    # --- audit --------------------------------------------------------
    def write_audit_log(
        self, *, claim_id: str | None, action: str, details: dict[str, Any]
    ) -> Row:
        payload = {"claim_id": claim_id, "action": action, "details": details}
        response = self._client.table("audit_logs").insert(payload).execute()
        row = self._one(response)
        if row is None:
            raise RuntimeError("Supabase did not return the inserted audit log")
        return row

    def list_audit_logs(self, claim_id: str) -> list[Row]:
        response = (
            self._client.table("audit_logs")
            .select("*")
            .eq("claim_id", claim_id)
            .order("created_at")
            .execute()
        )
        return self._rows(response)


_supabase_client: Any = None
_database: Database | None = None


def get_supabase_client(settings: Settings | None = None) -> Any:
    """Return a cached Supabase client, or ``None`` if not configured."""
    global _supabase_client

    settings = settings or get_settings()
    if not settings.supabase_configured:
        return None
    if _supabase_client is None:
        from supabase import create_client

        _supabase_client = create_client(settings.supabase_url, settings.supabase_key)
    return _supabase_client


def get_database() -> Database:
    """FastAPI dependency returning the active database.

    Tests override this with an :class:`InMemoryDatabase`.
    """
    global _database

    if _database is None:
        client = get_supabase_client()
        if client is None:
            logger.warning(
                "SUPABASE_URL/SUPABASE_KEY not set - using in-memory database. "
                "Data will be lost when the process exits."
            )
            _database = InMemoryDatabase()
        else:
            _database = SupabaseDatabase(client)
    return _database
