from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(
    prefix="/entities/{entity_id}/verification",
    tags=["verification"],
)


def _get_verification() -> Any:
    from intelgraph.api.main import _container

    return _container.verification


@router.get(
    "",
    summary="Get verification record",
    description="Retrieve the verification record for a given entity.",
)
def get_verification(entity_id: str, vm: Any = Depends(_get_verification)):
    record = vm.get_verification(entity_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail=f"No verification record for entity {entity_id}"
        )
    return record.to_dict()
