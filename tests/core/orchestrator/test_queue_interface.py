from intelgraph.core.orchestrator.queue import InMemoryTaskQueue
from intelgraph.core.orchestrator.queue_interface import TaskQueue
from intelgraph.core.orchestrator.task import Task


class TestQueueInterface:
    def test_in_memory_implements_interface(self):
        q: TaskQueue = InMemoryTaskQueue()
        assert isinstance(q, TaskQueue)

    def test_enqueue_dequeue(self):
        q: TaskQueue = InMemoryTaskQueue()
        t = Task()
        q.enqueue(t)
        pulled = q.dequeue()
        assert pulled is not None
        assert pulled.id == t.id

    def test_complete(self):
        q: TaskQueue = InMemoryTaskQueue()
        t = Task()
        q.enqueue(t)
        q.dequeue()
        q.complete(t.id)
        assert q.get(t.id).status.value == "completed"

    def test_fail(self):
        q: TaskQueue = InMemoryTaskQueue()
        t = Task()
        q.enqueue(t)
        q.dequeue()
        q.fail(t.id, "error")
        assert q.get(t.id).status.value == "failed"
        assert q.get(t.id).error == "error"

    def test_retry(self):
        q: TaskQueue = InMemoryTaskQueue()
        t = Task()
        q.enqueue(t)
        q.dequeue()
        q.retry(t)
        assert q.get(t.id).status.value == "pending"

    def test_get_nonexistent(self):
        q: TaskQueue = InMemoryTaskQueue()
        assert q.get("nonexistent") is None

    def test_list(self):
        q: TaskQueue = InMemoryTaskQueue()
        q.enqueue(Task())
        assert len(q.list()) == 1

    def test_metrics(self):
        q: TaskQueue = InMemoryTaskQueue()
        m = q.metrics()
        assert "queue_pending" in m
        assert "queue_running" in m
        assert "queue_completed" in m
        assert "queue_failed" in m
