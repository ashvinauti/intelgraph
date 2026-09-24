import time

import pytest

from intelgraph.core.orchestrator import Task, TaskManager, TaskStatus, TaskType
from intelgraph.core.orchestrator.dispatcher import TaskDispatcher
from intelgraph.core.orchestrator.queue import InMemoryTaskQueue
from intelgraph.core.orchestrator.worker import TaskWorker


class TestTaskModel:
    def test_task_defaults(self):
        t = Task()
        assert t.status == TaskStatus.PENDING
        assert t.retry_count == 0
        assert t.max_retries == 3

    def test_transition_pending_to_running(self):
        t = Task()
        t.transition(TaskStatus.RUNNING)
        assert t.status == TaskStatus.RUNNING

    def test_transition_running_to_completed(self):
        t = Task()
        t.transition(TaskStatus.RUNNING)
        t.transition(TaskStatus.COMPLETED)
        assert t.status == TaskStatus.COMPLETED

    def test_transition_running_to_failed(self):
        t = Task()
        t.transition(TaskStatus.RUNNING)
        t.transition(TaskStatus.FAILED)
        assert t.status == TaskStatus.FAILED

    def test_invalid_transition(self):
        t = Task()
        with pytest.raises(ValueError, match="Invalid transition"):
            t.transition(TaskStatus.COMPLETED)

    def test_invalid_transition_from_completed(self):
        t = Task()
        t.transition(TaskStatus.RUNNING)
        t.transition(TaskStatus.COMPLETED)
        with pytest.raises(ValueError, match="Invalid transition"):
            t.transition(TaskStatus.RUNNING)

    def test_to_dict(self):
        t = Task(type=TaskType.VERIFY_ENTITY, payload=b"hello")
        d = t.to_dict()
        assert d["id"] == t.id
        assert d["type"] == "verify_entity"
        assert d["status"] == "pending"
        assert "payload" not in d


class TestTaskQueue:
    def test_enqueue_dequeue(self):
        q = InMemoryTaskQueue()
        t = Task()
        q.enqueue(t)
        pulled = q.dequeue()
        assert pulled is not None
        assert pulled.id == t.id
        assert pulled.status == TaskStatus.RUNNING

    def test_dequeue_empty(self):
        q = InMemoryTaskQueue()
        assert q.dequeue() is None

    def test_dequeue_only_pending(self):
        q = InMemoryTaskQueue()
        t = Task()
        t.transition(TaskStatus.RUNNING)
        q.enqueue(t)
        assert q.dequeue() is None

    def test_complete(self):
        q = InMemoryTaskQueue()
        t = Task()
        q.enqueue(t)
        q.dequeue()
        q.complete(t.id)
        assert q.get(t.id).status == TaskStatus.COMPLETED

    def test_fail(self):
        q = InMemoryTaskQueue()
        t = Task()
        q.enqueue(t)
        q.dequeue()
        q.fail(t.id, "oops")
        finished = q.get(t.id)
        assert finished.status == TaskStatus.FAILED
        assert finished.error == "oops"

    def test_get_nonexistent(self):
        q = InMemoryTaskQueue()
        assert q.get("nonexistent") is None

    def test_list_all(self):
        q = InMemoryTaskQueue()
        q.enqueue(Task())
        q.enqueue(Task())
        assert len(q.list()) == 2

    def test_list_filtered(self):
        q = InMemoryTaskQueue()
        t = Task()
        q.enqueue(t)
        assert len(q.list(status="pending")) == 1
        assert len(q.list(status="running")) == 0


class TestTaskDispatcher:
    def test_register_and_dispatch(self):
        d = TaskDispatcher()
        results = []
        d.register(TaskType.COLLECT_ENTITY, lambda t: results.append("called"))
        task = Task(type=TaskType.COLLECT_ENTITY)
        d.dispatch(task)
        assert results == ["called"]

    def test_dispatch_unregistered(self):
        d = TaskDispatcher()
        task = Task(type=TaskType.VERIFY_ENTITY)
        with pytest.raises(ValueError, match="No handler registered"):
            d.dispatch(task)


class TestTaskWorker:
    def test_worker_processes_task(self):
        q = InMemoryTaskQueue()
        d = TaskDispatcher()
        results = []
        d.register(TaskType.COLLECT_ENTITY, lambda t: results.append("done"))
        worker = TaskWorker(q, d)
        task = Task(type=TaskType.COLLECT_ENTITY)
        q.enqueue(task)
        worker.start()
        time.sleep(0.3)
        worker.stop()
        assert results == ["done"]
        assert q.get(task.id).status == TaskStatus.COMPLETED

    def test_worker_fails_after_max_retries(self):
        q = InMemoryTaskQueue()
        d = TaskDispatcher()
        call_count = 0

        def flaky(_):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("boom")

        d.register(TaskType.COLLECT_ENTITY, flaky)
        worker = TaskWorker(q, d)
        task = Task(type=TaskType.COLLECT_ENTITY, max_retries=1)
        q.enqueue(task)
        worker.start()
        time.sleep(1.0)
        worker.stop()
        assert q.get(task.id).status == TaskStatus.FAILED
        assert q.get(task.id).error == "boom"
        assert call_count >= 2


class TestTaskManager:
    def test_enqueue_and_get(self):
        tm = TaskManager()
        tm.initialize()
        task = tm.enqueue("collect_entity", payload=b"test")
        assert task.status == TaskStatus.PENDING
        pulled = tm.get_task(task.id)
        assert pulled is not None
        assert pulled["type"] == "collect_entity"
        tm.shutdown()

    def test_enqueue_invalid_type(self):
        tm = TaskManager()
        with pytest.raises(ValueError, match="Unknown task type"):
            tm.enqueue("invalid_type")

    def test_get_nonexistent(self):
        tm = TaskManager()
        assert tm.get_task("nonexistent") is None

    def test_list_tasks(self):
        tm = TaskManager()
        tm.enqueue("collect_entity")
        tm.enqueue("verify_entity")
        tasks = tm.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_filtered(self):
        tm = TaskManager()
        tm.enqueue("collect_entity")
        assert len(tm.list_tasks(status="pending")) == 1
        assert len(tm.list_tasks(status="running")) == 0
