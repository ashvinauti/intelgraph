from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(
    prefix="/entities/{entity_id}/evidence",
    tags=["evidence"],
)


def _get_chain() -> Any:
    from intelgraph.api.main import _container

    return _container.chain


@router.get(
    "",
    summary="Get evidence chain",
    description="Retrieve the evidence chain for a given entity.",
)
def get_evidence(entity_id: str, chain: Any = Depends(_get_chain)):
    chain_data = chain.get_chain_by_entity(entity_id)
    if chain_data is None:
        raise HTTPException(status_code=404, detail=f"No evidence chain for entity {entity_id}")
    return chain_data.to_dict()
