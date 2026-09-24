from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any

from intelgraph.core.notification.channels import CHANNEL_DISPATCH
from intelgraph.core.notification.models import (
    NotificationChannel,
    NotificationEvent,
    NotificationHistoryEntry,
    NotificationSeverity,
    NotificationStatus,
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAYS = [1.0, 5.0, 15.0]  # exponential backoff


class NotificationManager:
    def __init__(self, state_path: str = ""):
        self._channels: dict[str, NotificationChannel] = {}
        self._history: list[NotificationHistoryEntry] = []
        self._history_max = 200
        self._lock = threading.Lock()
        self._state_path = state_path or os.environ.get(
            "INTELGRAPH_NOTIFICATION_STATE",
            "/tmp/opencode/notification_state.json",
        )
        self._load()

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def add_channel(self, channel: NotificationChannel) -> None:
        with self._lock:
            self._channels[channel.channel_id] = channel
            self._save()

    def remove_channel(self, channel_id: str) -> bool:
        with self._lock:
            if channel_id in self._channels:
                del self._channels[channel_id]
                self._save()
                return True
            return False

    def get_channel(self, channel_id: str) -> NotificationChannel | None:
        with self._lock:
            return self._channels.get(channel_id)

    def list_channels(self) -> list[NotificationChannel]:
        with self._lock:
            return list(self._channels.values())

    # ------------------------------------------------------------------
    # Event dispatch
    # ------------------------------------------------------------------

    def send_event(self, event: NotificationEvent) -> list[NotificationHistoryEntry]:
        entries: list[NotificationHistoryEntry] = []
        for channel in self._list_enabled_channels(event.severity):
            entry = self._dispatch_with_retry(channel, event)
            with self._lock:
                self._history.append(entry)
                if len(self._history) > self._history_max:
                    self._history = self._history[-self._history_max :]
                self._save()
            entries.append(entry)
            if entry.status == NotificationStatus.SENT.value:
                logger.info(
                    "Notification sent: %s -> %s (%s)",
                    event.event_id,
                    channel.channel_id,
                    channel.channel_type,
                )
            else:
                logger.warning(
                    "Notification failed: %s -> %s: %s",
                    event.event_id,
                    channel.channel_id,
                    entry.error,
                )
        return entries

    def send_event_async(self, event: NotificationEvent) -> None:
        t = threading.Thread(target=self.send_event, args=(event,), daemon=True)
        t.start()

    def _dispatch_with_retry(
        self, channel: NotificationChannel, event: NotificationEvent
    ) -> NotificationHistoryEntry:
        last_error = ""
        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                delay = RETRY_DELAYS[min(attempt - 2, len(RETRY_DELAYS) - 1)]
                logger.info(
                    "Retry %d/%d for %s in %.1fs", attempt, MAX_RETRIES, channel.channel_id, delay
                )
                time.sleep(delay)

            send_fn = CHANNEL_DISPATCH.get(channel.channel_type)
            if not send_fn:
                return NotificationHistoryEntry(
                    event_id=event.event_id,
                    channel_id=channel.channel_id,
                    status=NotificationStatus.FAILED.value,
                    error=f"unknown channel_type: {channel.channel_type}",
                    attempt=attempt,
                )

            try:
                err = send_fn(event, channel)
            except Exception as e:
                err = str(e)

            if err is None:
                return NotificationHistoryEntry(
                    event_id=event.event_id,
                    channel_id=channel.channel_id,
                    status=NotificationStatus.SENT.value,
                    attempt=attempt,
                )
            last_error = err

        return NotificationHistoryEntry(
            event_id=event.event_id,
            channel_id=channel.channel_id,
            status=NotificationStatus.FAILED.value,
            error=last_error,
            attempt=MAX_RETRIES,
        )

    def _list_enabled_channels(self, severity: str) -> list[NotificationChannel]:
        try:
            sev = NotificationSeverity(severity)
        except ValueError:
            sev = NotificationSeverity.MEDIUM
        result: list[NotificationChannel] = []
        with self._lock:
            for ch in self._channels.values():
                if not ch.enabled:
                    continue
                try:
                    ch_min = NotificationSeverity(ch.min_severity)
                except ValueError:
                    ch_min = NotificationSeverity.MEDIUM
                if sev >= ch_min:
                    result.append(ch)
        return result

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def get_history(self, limit: int = 50) -> list[NotificationHistoryEntry]:
        with self._lock:
            return list(reversed(self._history))[:limit]

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()
            self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            data = {
                "channels": [ch.to_dict() for ch in self._channels.values()],
                "history": [h.to_dict() for h in self._history],
            }
            with open(self._state_path, "w") as f:
                json.dump(data, f, default=str)
        except Exception as e:
            logger.error("Failed to save notification state: %s", e)

    def _load(self) -> None:
        try:
            if not os.path.exists(self._state_path):
                return
            with open(self._state_path) as f:
                data = json.load(f)
            for ch_data in data.get("channels", []):
                ch = NotificationChannel.from_dict(ch_data)
                self._channels[ch.channel_id] = ch
            for h_data in data.get("history", []):
                self._history.append(NotificationHistoryEntry.from_dict(h_data))
        except Exception as e:
            logger.error("Failed to load notification state: %s", e)

    @staticmethod
    def build_event(
        event_type: str,
        severity: str,
        title: str,
        body: str,
        entity_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> NotificationEvent:
        return NotificationEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            severity=severity,
            title=title,
            body=body,
            entity_id=entity_id,
            metadata=metadata or {},
        )
