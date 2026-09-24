from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from intelgraph.core.export.stix import graph_to_bundle_json

router = APIRouter(prefix="/taxii", tags=["TAXII"])

_TAXII_MEDIA_TYPE = "application/taxii+json;version=2.1"

_GRAPHS = {
    "intelgraph": {
        "id": "intelgraph--default",
        "title": "IntelGraph Knowledge Base",
        "description": "Threat intelligence graph from multi-source pipeline",
    },
}

_COLLECTIONS = {
    "collection--intelgraph": {
        "id": "collection--intelgraph",
        "title": "IntelGraph Objects",
        "description": "All entities, relationships, and indicators from the IntelGraph pipeline",
        "can_read": True,
        "can_write": False,
        "media_types": [_TAXII_MEDIA_TYPE],
    },
}


def _get_graph() -> Any:
    """Return reconstructed IntelligenceGraph from container backend."""
    from intelgraph.core.kernel.execution import build_graph_from_container

    return build_graph_from_container()


@router.get(
    "",
    summary="TAXII 2.1 Discovery",
    description="Returns TAXII 2.1 server discovery information.",
    response_class=JSONResponse,
)
def discovery():
    return JSONResponse(
        content={
            "title": "IntelGraph TAXII 2.1 Server",
            "description": "TAXII 2.1 server for IntelGraph threat intelligence export",
            "contact": "admin@intelgraph.local",
            "default": "http://localhost:9090",
            "api_roots": ["http://localhost:9090/taxii/"],
        },
        media_type=_TAXII_MEDIA_TYPE,
        headers={"X-TAXII-Content-Type": "application/vnd.oasis.taxii+json; version=2.1"},
    )


@router.get(
    "/collections/",
    summary="TAXII 2.1 Collections",
    description="List available TAXII 2.1 collections.",
    response_class=JSONResponse,
)
def list_collections():
    graph = _get_graph()
    collections = []
    for cid, col in _COLLECTIONS.items():
        collections.append(
            {
                "id": cid,
                "title": col["title"],
                "description": col["description"],
                "can_read": col["can_read"],
                "can_write": col["can_write"],
                "media_types": col["media_types"],
                "objects_count": len(graph.nodes),
            }
        )
    return JSONResponse(
        content={"collections": collections},
        media_type=_TAXII_MEDIA_TYPE,
    )


@router.get(
    "/collections/{collection_id}/objects/",
    summary="TAXII 2.1 Get Objects",
    description=(
        "Returns STIX 2.1 objects from the specified collection. "
        "Supports temporal filter with added_after, type filter with match[type], "
        "and pagination via limit and next parameters."
    ),
    response_class=JSONResponse,
)
def get_objects(
    collection_id: str,
    added_after: str | None = Query(
        None, description="Only return objects added after this timestamp (ISO 8601)"
    ),
    match_type: str | None = Query(
        None, alias="match[type]", description="Filter by STIX object type"
    ),
    limit: int = Query(100, description="Maximum number of objects to return", ge=1, le=1000),
    next_cursor: str | None = Query(None, alias="next", description="Cursor for pagination"),
):
    if collection_id not in _COLLECTIONS:
        raise HTTPException(
            status_code=404,
            detail={
                "title": "Collection not found",
                "description": f"Collection {collection_id} does not exist",
                "http_status": "404",
            },
        )

    since = None
    if added_after:
        try:
            since = datetime.fromisoformat(added_after.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400,
                detail={
                    "title": "Invalid timestamp",
                    "description": f"Could not parse added_after: {added_after}",
                    "http_status": "400",
                },
            )

    graph = _get_graph()

    if match_type == "relationship":
        stix_json = graph_to_bundle_json(graph, since=since, filter_type="relationship")
    elif match_type:
        stix_json = graph_to_bundle_json(graph, since=since, filter_type=match_type)
    else:
        stix_json = graph_to_bundle_json(graph, since=since)

    import json

    bundle = json.loads(stix_json)

    objects = bundle.get("objects", [])

    # Pagination
    total = len(objects)
    offset = int(next_cursor) if next_cursor else 0
    page = objects[offset : offset + limit]

    response_data: dict[str, Any] = {
        "objects": page,
    }
    if offset + limit < total:
        response_data["next"] = str(offset + limit)

    return JSONResponse(
        content=response_data,
        media_type=_TAXII_MEDIA_TYPE,
    )


@router.get(
    "/collections/{collection_id}/objects/{object_id}/",
    summary="TAXII 2.1 Get Object by ID",
    description="Returns a single STIX 2.1 object by ID.",
    response_class=JSONResponse,
)
def get_object_by_id(collection_id: str, object_id: str):
    if collection_id not in _COLLECTIONS:
        raise HTTPException(status_code=404, detail="Collection not found")

    graph = _get_graph()
    stix_json = graph_to_bundle_json(graph)
    import json

    bundle = json.loads(stix_json)

    for obj in bundle.get("objects", []):
        if obj.get("id") == object_id:
            return JSONResponse(
                content={"objects": [obj]},
                media_type=_TAXII_MEDIA_TYPE,
            )

    raise HTTPException(status_code=404, detail=f"Object {object_id} not found")
