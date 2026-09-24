from __future__ import annotations

import os
import platform
import threading
import time
import uuid
from typing import Any


class WorkerRegistry:
    def __init__(self, heartbeat_interval: float = 30.0) -> None:
        self._lock = threading.Lock()
        self._workers: dict[str, dict[str, Any]] = {}
        self._heartbeat_interval = heartbeat_interval
        self._local_id: str | None = None

    @property
    def local_id(self) -> str:
        if self._local_id is None:
            self._local_id = str(uuid.uuid4())
        return self._local_id

    def register(self, worker_id: str | None = None) -> str:
        wid = worker_id or self.local_id
        now = time.time()
        with self._lock:
            self._workers[wid] = {
                "worker_id": wid,
                "hostname": platform.node(),
                "pid": os.getpid(),
                "registered_at": now,
                "last_heartbeat": now,
                "status": "alive",
            }
        return wid

    def heartbeat(self, worker_id: str | None = None) -> None:
        wid = worker_id or self._local_id
        if wid is None:
            return
        now = time.time()
        with self._lock:
            w = self._workers.get(wid)
            if w is not None:
                w["last_heartbeat"] = now
                w["status"] = "alive"

    def unregister(self, worker_id: str | None = None) -> None:
        wid = worker_id or self._local_id
        if wid is None:
            return
        with self._lock:
            self._workers.pop(wid, None)

    def list_workers(self) -> list[dict[str, Any]]:
        now = time.time()
        timeout = self._heartbeat_interval * 2
        with self._lock:
            workers = list(self._workers.values())
        for w in workers:
            if w["status"] == "alive" and (now - w["last_heartbeat"]) > timeout:
                w["status"] = "dead"
        return sorted(workers, key=lambda x: x["registered_at"])

    def get_worker(self, worker_id: str) -> dict[str, Any] | None:
        with self._lock:
            w = self._workers.get(worker_id)
            if w is None:
                return None
            w = dict(w)
        now = time.time()
        timeout = self._heartbeat_interval * 2
        if w["status"] == "alive" and (now - w["last_heartbeat"]) > timeout:
            w["status"] = "dead"
        return w

    def metrics(self) -> dict[str, int]:
        workers = self.list_workers()
        alive = sum(1 for w in workers if w["status"] == "alive")
        dead = sum(1 for w in workers if w["status"] == "dead")
        return {
            "workers_total": len(workers),
            "workers_alive": alive,
            "workers_dead": dead,
        }
