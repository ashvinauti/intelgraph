from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from intelgraph.core.playbook import DEFAULT_PLAYBOOKS, PlaybookEngine

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


def _get_engine() -> PlaybookEngine:
    from intelgraph.api.routers.dashboard import dashboard_state

    engine = PlaybookEngine()
    r = dashboard_state.result
    if r and hasattr(r, "playbook_statuses") and r.playbook_statuses:
        engine.restore_from_dicts(r.playbook_statuses)
    return engine


@router.get("")
def list_playbooks() -> list[dict[str, Any]]:
    return [
        {
            "playbook_id": pb.playbook_id,
            "name": pb.name,
            "description": pb.description,
            "severity_level": pb.severity_level,
            "entity_types": pb.entity_types,
            "step_count": len(pb.steps),
            "steps": [
                {
                    "step_id": s.step_id,
                    "action_type": s.action_type.name.lower(),
                    "description": s.description,
                    "automated": s.automated,
                    "required": s.required,
                    "order": s.order,
                }
                for s in pb.steps
            ],
        }
        for pb in DEFAULT_PLAYBOOKS
    ]


@router.get("/engine/status")
def engine_status() -> dict[str, Any]:
    engine = _get_engine()
    statuses = engine.to_dicts()
    return {
        "active_playbooks": len(statuses),
        "statuses": statuses,
    }
