import pytest

from intelgraph.core.source.connector import ConnectorConfig
from intelgraph.core.source.manager import DataSourceManager


@pytest.fixture
def manager():
    m = DataSourceManager(":memory:")
    yield m
    m.close()


class TestDataSourceManager:
    def test_register_connector(self, manager):
        result = manager.register_connector(
            source_id="src1",
            source_name="Test HTTP Source",
            connector_type="http",
            config_overrides={"endpoint_url": "https://example.com/data"},
        )
        assert result["id"] == "src1"
        assert result["connector_type"] == "http"

    def test_register_invalid_type(self, manager):
        result = manager.register_connector(
            source_id="src1",
            source_name="Bad",
            connector_type="invalid",
        )
        assert "error" in result

    def test_list_sources(self, manager):
        manager.register_connector("a", "A", "http")
        manager.register_connector("b", "B", "file", {"file_path": "/tmp/x.json"})
        sources = manager.list_sources()
        assert len(sources) == 2

    def test_get_source(self, manager):
        manager.register_connector(
            "g1", "Get Test", "http", {"endpoint_url": "https://example.com"}
        )
        src = manager.get_source("g1")
        assert src["id"] == "g1"

    def test_get_source_not_found(self, manager):
        src = manager.get_source("nonexistent")
        assert "error" in src

    def test_delete_source(self, manager):
        manager.register_connector("d1", "Delete Test", "http")
        assert manager.delete_source("d1") is True
        assert manager.delete_source("d1") is False

    def test_poll_source(self, manager):
        manager.register_connector(
            "p1", "Poll Test", "http", {"endpoint_url": "https://example.com/data"}
        )
        result = manager.poll_source("p1")
        assert result["status"] == "error"
        assert "error" in result

    def test_poll_nonexistent(self, manager):
        result = manager.poll_source("nonexistent")
        assert "error" in result

    def test_disabled_source_skips_poll(self, manager):
        cfg = ConnectorConfig(id="dp1", name="Disabled", connector_type="http", enabled=False)
        manager.store.register_source(cfg)
        result = manager.poll_source("dp1")
        assert result["status"] == "skipped"

    def test_bulk_poll(self, manager):
        manager.register_connector("bp1", "BP1", "http", {"endpoint_url": "https://example.com/a"})
        manager.register_connector("bp2", "BP2", "file", {"file_path": "/nonexistent.json"})
        results = manager.bulk_poll(["bp1", "bp2"])
        assert len(results) == 2

    def test_run_scheduled_poll(self, manager):
        from intelgraph.core.source.connector import ConnectorConfig

        cfg1 = ConnectorConfig(
            id="r1",
            name="R1",
            connector_type="http",
            endpoint_url="https://x.com",
            enabled=True,
            polling_interval_seconds=0,
        )
        cfg2 = ConnectorConfig(
            id="r2", name="R2", connector_type="http", endpoint_url="https://y.com", enabled=False
        )
        manager.store.register_source(cfg1)
        manager.store.register_source(cfg2)
        results = manager.run_scheduled_poll()
        assert len(results) == 1

    def test_get_poll_history(self, manager):
        manager.register_connector("h1", "History", "http")
        manager.store.record_poll("h1", "success")
        history = manager.get_poll_history("h1")
        assert len(history) == 1
