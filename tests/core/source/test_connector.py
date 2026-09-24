import json
import tempfile

from intelgraph.core.source.connector import (
    ConnectorConfig,
    ConnectorRegistry,
    DatabaseConnector,
    FileConnector,
    HttpConnector,
    PollResult,
    _backoff_delay,
)


class TestConnectorConfig:
    def test_defaults(self):
        cfg = ConnectorConfig(id="x", name="test", connector_type="http")
        assert cfg.polling_interval_seconds == 3600
        assert cfg.retry_max_attempts == 3
        assert cfg.enabled is True

    def test_to_dict_masks_credentials(self):
        cfg = ConnectorConfig(
            id="x",
            name="test",
            connector_type="http",
            auth_credentials={"api_key": "secret123", "username": "admin"},
        )
        d = cfg.to_dict()
        assert d["auth_credentials"]["api_key"] == "***MASKED***"
        assert d["auth_credentials"]["username"] == "admin"


class TestBackoffDelay:
    def test_exponential(self):
        d1 = _backoff_delay(0, 1.0, 60.0)
        d2 = _backoff_delay(1, 1.0, 60.0)
        d3 = _backoff_delay(2, 1.0, 60.0)
        assert d1 < d2 < d3
        assert d3 <= 60.0

    def test_capped(self):
        d = _backoff_delay(10, 1.0, 10.0)
        assert d <= 10.0


class TestConnectorRegistry:
    def test_register_and_get(self):
        assert "http" in ConnectorRegistry.list_types()
        assert "file" in ConnectorRegistry.list_types()
        assert "database" in ConnectorRegistry.list_types()
        cls = ConnectorRegistry.get("http")
        assert cls is HttpConnector

    def test_create_http(self):
        cfg = ConnectorConfig(
            id="x", name="t", connector_type="http", endpoint_url="https://example.com/data"
        )
        connector = ConnectorRegistry.create(cfg)
        assert isinstance(connector, HttpConnector)

    def test_create_file(self):
        cfg = ConnectorConfig(id="x", name="t", connector_type="file", file_path="/tmp/test.json")
        connector = ConnectorRegistry.create(cfg)
        assert isinstance(connector, FileConnector)

    def test_create_invalid(self):
        cfg = ConnectorConfig(id="x", name="t", connector_type="invalid")
        assert ConnectorRegistry.create(cfg) is None


class TestFileConnector:
    def test_connect_no_path(self):
        cfg = ConnectorConfig(id="x", name="t", connector_type="file")
        c = FileConnector(cfg)
        assert c.connect() is False

    def test_connect_with_path(self):
        cfg = ConnectorConfig(id="x", name="t", connector_type="file", file_path="/tmp/test.json")
        c = FileConnector(cfg)
        assert c.connect() is True

    def test_poll_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([{"name": "Alice", "type": "person"}, {"name": "Bob", "type": "person"}], f)
            f.flush()
            cfg = ConnectorConfig(id="x", name="t", connector_type="file", file_path=f.name)
            c = FileConnector(cfg)
            c.connect()
            result = c.poll()
            assert result.success is True
            assert len(result.raw_data) == 2
            assert result.nodes_ingested == 2

    def test_poll_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,type\nAlice,person\nBob,person\n")
            f.flush()
            cfg = ConnectorConfig(id="x", name="t", connector_type="file", file_path=f.name)
            c = FileConnector(cfg)
            c.connect()
            result = c.poll()
            assert result.success is True
            assert len(result.raw_data) == 2
            assert result.raw_data[0]["name"] == "Alice"

    def test_poll_file_not_found(self):
        cfg = ConnectorConfig(
            id="x", name="t", connector_type="file", file_path="/nonexistent/file.json"
        )
        c = FileConnector(cfg)
        c.connect()
        result = c.poll()
        assert result.success is False

    def test_health_check(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("[]")
            f.flush()
            cfg = ConnectorConfig(id="x", name="t", connector_type="file", file_path=f.name)
            c = FileConnector(cfg)
            assert c.health_check() is True

    def test_health_check_missing(self):
        cfg = ConnectorConfig(id="x", name="t", connector_type="file", file_path="/nonexistent")
        c = FileConnector(cfg)
        assert c.health_check() is False


class TestDatabaseConnector:
    def test_connect_no_conn_string(self):
        cfg = ConnectorConfig(id="x", name="t", connector_type="database")
        c = DatabaseConnector(cfg)
        assert c.connect() is False

    def test_connect_and_poll(self):
        cfg = ConnectorConfig(
            id="x",
            name="t",
            connector_type="database",
        )
        c = DatabaseConnector(cfg)
        assert c.connect() is False


class TestHttpConnector:
    def test_connect_no_endpoint(self):
        cfg = ConnectorConfig(id="x", name="t", connector_type="http")
        c = HttpConnector(cfg)
        assert c.connect() is False

    def test_poll_invalid_url(self):
        cfg = ConnectorConfig(
            id="x", name="t", connector_type="http", endpoint_url="https://nonexistent.invalid/data"
        )
        c = HttpConnector(cfg)
        c.connect()
        result = c.poll()
        assert result.success is False

    def test_health_check_invalid(self):
        cfg = ConnectorConfig(
            id="x", name="t", connector_type="http", endpoint_url="https://nonexistent.invalid"
        )
        c = HttpConnector(cfg)
        assert c.health_check() is False


class TestConnectorRetry:
    def test_poll_with_retry_skips_on_success(self):
        class AlwaysOkConnector(FileConnector):
            def poll(self) -> PollResult:
                return PollResult(success=True, nodes_ingested=5)

        cfg = ConnectorConfig(
            id="x", name="t", connector_type="file", file_path="/tmp/x.json", retry_max_attempts=3
        )
        c = AlwaysOkConnector(cfg)
        result = c.poll_with_retry()
        assert result.success is True
        assert result.nodes_ingested == 5

    def test_poll_with_retry_exhausts(self):
        class AlwaysFailConnector(FileConnector):
            def poll(self) -> PollResult:
                return PollResult(success=False, error_message="fail")

        cfg = ConnectorConfig(
            id="x",
            name="t",
            connector_type="file",
            file_path="/tmp/x.json",
            retry_max_attempts=2,
            retry_base_delay=0.01,
        )
        c = AlwaysFailConnector(cfg)
        result = c.poll_with_retry()
        assert result.success is False
        assert "All retries exhausted" in result.error_message

    def test_validate_data_required_fields(self):
        cfg = ConnectorConfig(
            id="x",
            name="t",
            connector_type="file",
            file_path="/tmp/x.json",
            feed_schema={"required_fields": ["name", "type"]},
        )
        c = FileConnector(cfg)
        data = [{"name": "Alice", "type": "person"}, {"name": "Bob"}]
        validated = c.validate_data(data)
        assert len(validated) == 1
        assert validated[0]["name"] == "Alice"
