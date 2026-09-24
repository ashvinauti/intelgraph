import time

from intelgraph.core.orchestrator.worker_registry import WorkerRegistry


class TestWorkerRegistry:
    def test_register_creates_worker(self):
        r = WorkerRegistry(heartbeat_interval=30)
        wid = r.register()
        workers = r.list_workers()
        assert len(workers) == 1
        assert workers[0]["worker_id"] == wid
        assert workers[0]["status"] == "alive"

    def test_register_with_custom_id(self):
        r = WorkerRegistry()
        r.register("custom-123")
        w = r.get_worker("custom-123")
        assert w is not None
        assert w["worker_id"] == "custom-123"

    def test_heartbeat_updates_timestamp(self):
        r = WorkerRegistry(heartbeat_interval=30)
        wid = r.register()
        old_hb = r.get_worker(wid)["last_heartbeat"]
        time.sleep(0.01)
        r.heartbeat(wid)
        new_hb = r.get_worker(wid)["last_heartbeat"]
        assert new_hb > old_hb

    def test_unregister_removes_worker(self):
        r = WorkerRegistry()
        wid = r.register()
        assert len(r.list_workers()) == 1
        r.unregister(wid)
        assert len(r.list_workers()) == 0

    def test_local_id_is_persistent(self):
        r = WorkerRegistry()
        first = r.local_id
        second = r.local_id
        assert first == second

    def test_metrics(self):
        r = WorkerRegistry(heartbeat_interval=30)
        r.register()
        m = r.metrics()
        assert m["workers_total"] >= 1
        assert m["workers_alive"] >= 1
        assert "workers_dead" in m

    def test_get_nonexistent(self):
        r = WorkerRegistry()
        assert r.get_worker("nonexistent") is None

    def test_list_empty(self):
        r = WorkerRegistry()
        assert r.list_workers() == []
