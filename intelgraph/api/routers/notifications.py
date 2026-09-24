from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request

from intelgraph.core.notification.manager import NotificationManager
from intelgraph.core.notification.models import NotificationChannel

router = APIRouter(prefix="/notifications", tags=["notifications"])

_notifier = NotificationManager()


def _get_notifier() -> NotificationManager:
    return _notifier


@router.post("/channels")
def create_channel(body: dict[str, Any], request: Request) -> dict[str, Any]:
    nt = _get_notifier()
    channel_id = body.get("channel_id", f"ch_{uuid.uuid4().hex[:12]}")
    ch = NotificationChannel(
        channel_id=channel_id,
        channel_type=body.get("channel_type", "webhook"),
        config=body.get("config", {}),
        enabled=body.get("enabled", True),
        min_severity=body.get("min_severity", "medium"),
    )
    nt.add_channel(ch)
    return {"status": "ok", "channel_id": channel_id}


@router.get("/channels")
def list_channels(request: Request) -> dict[str, Any]:
    nt = _get_notifier()
    return {"channels": [ch.to_dict() for ch in nt.list_channels()]}


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: str, request: Request) -> dict[str, Any]:
    nt = _get_notifier()
    ok = nt.remove_channel(channel_id)
    return {"status": "ok" if ok else "not_found"}


@router.get("/history")
def get_history(request: Request, limit: int = 50) -> dict[str, Any]:
    nt = _get_notifier()
    return {"history": [h.to_dict() for h in nt.get_history(limit=limit)]}


@router.post("/test")
def test_notification(body: dict[str, Any], request: Request) -> dict[str, Any]:
    nt = _get_notifier()
    event = nt.build_event(
        event_type=body.get("event_type", "test"),
        severity=body.get("severity", "low"),
        title=body.get("title", "Test notification"),
        body=body.get("body", "This is a test notification from IntelGraph"),
        entity_id=body.get("entity_id", ""),
        metadata=body.get("metadata", {}),
    )
    entries = nt.send_event(event)
    return {
        "status": "ok",
        "event_id": event.event_id,
        "results": [e.to_dict() for e in entries],
    }
