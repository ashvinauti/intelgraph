from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from intelgraph.api.models import EntityCreate, EntityUpdate
from intelgraph.core.storage.audit import AuditEntry

router = APIRouter(prefix="/entities", tags=["entities"])


def _get_backend() -> Any:
    from intelgraph.api.main import _container

    return _container.backend


_ENTITY_CLASSES: dict[str, type] = {}


def _get_entity_class(entity_type: str) -> type | None:
    if not _ENTITY_CLASSES:
        from intelgraph.core.entity import (
            Certificate,
            Company,
            CveEntity,
            Domain,
            Email,
            IPAddress,
            Person,
            Technology,
            Username,
        )

        for cls in (
            Person,
            Company,
            Domain,
            Email,
            Username,
            IPAddress,
            Technology,
            Certificate,
            CveEntity,
        ):
            _ENTITY_CLASSES[cls.__name__.lower()] = cls
            _ENTITY_CLASSES[cls.__name__] = cls
    return _ENTITY_CLASSES.get(entity_type.lower()) or _ENTITY_CLASSES.get(entity_type)


@router.get(
    "/{entity_id}",
    summary="Get entity by ID",
    description="Retrieve a single entity by its unique identifier.",
)
def get_entity(entity_id: str, backend: Any = Depends(_get_backend)):
    record = backend.get_entity(entity_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    return record


def _get_audit() -> Any:
    from intelgraph.api.main import _container

    return _container.audit


def _get_actor(request: Request) -> str:
    uid = getattr(request.state, "user_id", "")
    return uid or "anonymous"


@router.post(
    "",
    summary="Create entity",
    description="Create a new entity with a given type and attributes.",
)
def create_entity(
    body: EntityCreate, backend: Any = Depends(_get_backend), request: Request = None
):

    cls = _get_entity_class(body.entity_type)
    if cls is None:
        raise HTTPException(status_code=400, detail=f"Unknown entity type: {body.entity_type}")
    entity = cls(**body.attributes)
    backend.put_entity(entity)
    _get_audit().log(
        AuditEntry(
            entity_id=entity.id,
            entity_type=body.entity_type,
            operation="CREATE",
            new_data=body.attributes,
            actor=_get_actor(request),
        )
    )
    return {"id": entity.id, "entity_type": body.entity_type}


@router.put(
    "/{entity_id}",
    summary="Update entity",
    description="Update an existing entity's attributes.",
)
def update_entity(
    entity_id: str,
    body: EntityUpdate,
    backend: Any = Depends(_get_backend),
    request: Request = None,
):
    existing = backend.get_entity(entity_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    cls = type(existing)
    merged = {}
    for f in getattr(cls, "__dataclass_fields__", {}):
        merged[f] = getattr(existing, f, None)
    merged.update(body.attributes)
    merged["id"] = entity_id
    merged["version"] = existing.version + 1
    for skip in ("entity_type",):
        merged.pop(skip, None)
    entity = cls(**merged)
    backend.put_entity(entity, operation="UPDATE")
    etype = getattr(existing, "entity_type", None)
    _get_audit().log(
        AuditEntry(
            entity_id=entity_id,
            entity_type=etype.type_name if etype else "unknown",
            operation="UPDATE",
            old_data={"name": getattr(existing, "name", "")},
            new_data=body.attributes,
            actor=_get_actor(request),
        )
    )
    return {"id": entity_id, "updated": True}


@router.delete(
    "/{entity_id}",
    summary="Delete entity",
    description="Delete an entity by its unique identifier.",
)
def delete_entity(entity_id: str, backend: Any = Depends(_get_backend), request: Request = None):
    existing = backend.get_entity(entity_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    backend.delete_entity(entity_id)
    etype = getattr(existing, "entity_type", None)
    _get_audit().log(
        AuditEntry(
            entity_id=entity_id,
            entity_type=etype.type_name if etype else "unknown",
            operation="DELETE",
            old_data={"name": getattr(existing, "name", "")},
            actor=_get_actor(request),
        )
    )
    return {"id": entity_id, "deleted": True}
