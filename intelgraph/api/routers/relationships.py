from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from intelgraph.api.models import RelationshipCreate
from intelgraph.core.storage.audit import AuditEntry

router = APIRouter(prefix="/relationships", tags=["relationships"])


def _get_backend() -> Any:
    from intelgraph.api.main import _container

    return _container.backend


@router.get(
    "/{relationship_id}",
    summary="Get relationship by ID",
    description="Retrieve a single relationship by its unique identifier.",
)
def get_relationship(relationship_id: str, backend: Any = Depends(_get_backend)):
    record = backend.get_relationship(relationship_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Relationship {relationship_id} not found")
    return record


def _get_audit() -> Any:
    from intelgraph.api.main import _container

    return _container.audit


def _get_actor(request: Any) -> str:
    uid = getattr(request.state, "user_id", "")
    return uid or "anonymous"


@router.post(
    "",
    summary="Create relationship",
    description="Create a new relationship between two entities.",
)
def create_relationship(
    body: RelationshipCreate, backend: Any = Depends(_get_backend), request: Request = None
):
    from intelgraph.core.relationship import Relationship
    from intelgraph.core.relationship.types import RelationshipType

    try:
        rtype = RelationshipType[body.type.upper().replace(" ", "_")]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown relationship type: {body.type}")
    rel = Relationship(
        type=rtype,
        source_id=body.source_id,
        target_id=body.target_id,
        confidence_score=body.confidence_score,
        trust_weight=body.trust_weight,
    )
    backend.put_relationship(rel)
    if request:
        _get_audit().log(
            AuditEntry(
                entity_id=rel.id,
                entity_type="relationship",
                operation="CREATE",
                new_data={
                    "type": body.type,
                    "source_id": body.source_id,
                    "target_id": body.target_id,
                },
                actor=_get_actor(request),
            )
        )
    return {"id": rel.id}


@router.delete(
    "/{relationship_id}",
    summary="Delete relationship",
    description="Delete a relationship by its unique identifier.",
)
def delete_relationship(
    relationship_id: str, backend: Any = Depends(_get_backend), request: Request = None
):
    existing = backend.get_relationship(relationship_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Relationship {relationship_id} not found")
    backend.delete_relationship(relationship_id)
    if request:
        _get_audit().log(
            AuditEntry(
                entity_id=relationship_id,
                entity_type="relationship",
                operation="DELETE",
                old_data={"id": relationship_id},
                actor=_get_actor(request),
            )
        )
    return {"id": relationship_id, "deleted": True}
