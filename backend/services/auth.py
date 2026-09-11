"""API-key authentication and role-based access control.

Static API keys mapped to a label and a role (`officer` or `admin`) - not a
full identity provider, which is an honest scope for a prototype. What this
gives, for real: every rule amendment and every review decision is
attributed to a named actor, and that attribution is written into the audit
log alongside the action.

With no API_KEYS configured, the backend runs open (every actor is
"anonymous") so it still starts with zero setup for local/dev work. Setting
API_KEYS turns enforcement on - same pattern as SUPABASE_URL gating real
persistence vs. the in-memory fallback.

API_KEYS format: comma-separated key:label:role triples, e.g.
    API_KEYS="k-officer-1:Reviewing Officer A:officer,k-admin-1:Chief:admin"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from backend.config import get_settings

ROLE_OFFICER = "officer"
ROLE_ADMIN = "admin"
ANONYMOUS_LABEL = "anonymous"
ANONYMOUS_ROLE = "anonymous"


@dataclass(frozen=True)
class Actor:
    """Who performed an action, for attribution in the audit log."""

    label: str
    role: str

    def audit_fields(self) -> dict[str, str]:
        return {"actor": self.label, "actor_role": self.role}


ANONYMOUS = Actor(label=ANONYMOUS_LABEL, role=ANONYMOUS_ROLE)


def _load_api_keys() -> dict[str, Actor]:
    raw = get_settings().api_keys_raw
    keys: dict[str, Actor] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":", 2)
        if len(parts) != 3:
            continue
        key, label, role = (p.strip() for p in parts)
        if key and label and role:
            keys[key] = Actor(label=label, role=role)
    return keys


def get_actor(authorization: Annotated[str | None, Header()] = None) -> Actor:
    keys = _load_api_keys()
    if not keys:
        return ANONYMOUS

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Expected 'Bearer <api-key>'.",
        )

    token = authorization.removeprefix("Bearer ").strip()
    actor = keys.get(token)
    if actor is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
    return actor


def require_role(*allowed_roles: str):
    def _dependency(actor: Annotated[Actor, Depends(get_actor)]) -> Actor:
        if not _load_api_keys():
            return actor
        if actor.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{actor.role}' is not permitted to perform this "
                    f"action; requires one of {sorted(allowed_roles)}."
                ),
            )
        return actor

    return _dependency
