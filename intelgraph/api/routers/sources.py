from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/sources", tags=["sources"])


def _get_sr() -> Any:
    from intelgraph.api.main import _container

    return _container.source_registry


@router.get(
    "",
    summary="List sources",
    description="List all registered intelligence sources.",
)
def list_sources(sr: Any = Depends(_get_sr)):
    return sr.list_sources()


@router.get(
    "/{source_id}",
    summary="Get source by ID",
    description="Retrieve a single source by its unique identifier.",
)
def get_source(source_id: str, sr: Any = Depends(_get_sr)):
    record = sr.get_source(source_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    return record
