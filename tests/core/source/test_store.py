import pytest

from intelgraph.core.source.connector import ConnectorConfig
from intelgraph.core.source.store import DataSourceStore


@pytest.fixture
def store():
    s = DataSourceStore(":memory:")
    s.connect()
    yield s
    s.close()


class TestDataSourceStore:
    def test_register_and_get(self, store):
        cfg = ConnectorConfig(
            id="src1", name="Test Source", connector_type="http", endpoint_url="https://example.com"
        )
        store.register_source(cfg)
        src = store.get_source("src1")
        assert src is not None
        assert src["name"] == "Test Source"
        assert src["connector_type"] == "http"

    def test_list_sources(self, store):
        store.register_source(ConnectorConfig(id="a", name="A", connector_type="http"))
        store.register_source(
            ConnectorConfig(id="b", name="B", connector_type="file", file_path="/tmp/x.json")
        )
        sources = store.list_sources()
        assert len(sources) == 2

    def test_delete_source(self, store):
        store.register_source(ConnectorConfig(id="x", name="X", connector_type="http"))
        assert store.delete_source("x") is True
        assert store.delete_source("nonexistent") is False

    def test_record_poll(self, store):
        store.register_source(ConnectorConfig(id="p1", name="Poll Test", connector_type="http"))
        poll = store.record_poll("p1", "success", duration_ms=100.0, nodes_ingested=5)
        assert poll["status"] == "success"
        history = store.get_poll_history("p1")
        assert len(history) == 1
        assert history[0]["nodes_ingested"] == 5

    def test_record_poll_failure(self, store):
        store.register_source(ConnectorConfig(id="p2", name="Fail Test", connector_type="http"))
        poll = store.record_poll("p2", "failure", error_message="timeout")
        assert poll["status"] == "failure"
        src = store.get_source("p2")
        assert src["last_poll_status"] == "failure"

    def test_get_source_status(self, store):
        store.register_source(ConnectorConfig(id="s1", name="Status Test", connector_type="http"))
        status = store.get_source_status("s1")
        assert status["name"] == "Status Test"
        assert status["status"] == "active"

    def test_get_source_status_not_found(self, store):
        status = store.get_source_status("nonexistent")
        assert "error" in status

    def test_save_and_get_feed_schema(self, store):
        store.register_source(ConnectorConfig(id="f1", name="Schema Test", connector_type="http"))
        schema = {"required_fields": ["name"]}
        result = store.save_feed_schema("f1", schema, version=1)
        assert result["version"] == 1
        schemas = store.get_feed_schemas("f1")
        assert len(schemas) == 1
        assert schemas[0]["schema_definition"]["required_fields"] == ["name"]

    def test_record_and_get_resolution(self, store):
        res_id = store.record_resolution(
            source_entity_id="e1",
            target_entity_id="e2",
            data_source_id="ds1",
            merge_strategy="priority",
            merged_fields={"name": "Alice"},
            confidence=0.95,
        )
        assert res_id is not None
        history = store.get_resolution_history(entity_id="e1")
        assert len(history) == 1
        assert history[0]["merge_strategy"] == "priority"

    def test_update_source_status(self, store):
        store.register_source(ConnectorConfig(id="u1", name="Update Test", connector_type="http"))
        store.update_source_status("u1", "error", consecutive_failures=3)
        src = store.get_source("u1")
        assert src["status"] == "error"
        assert src["consecutive_failures"] == 3

    def test_poll_history_limit(self, store):
        store.register_source(ConnectorConfig(id="h1", name="History Test", connector_type="http"))
        for _ in range(5):
            store.record_poll("h1", "success")
        history = store.get_poll_history("h1", limit=3)
        assert len(history) <= 3
