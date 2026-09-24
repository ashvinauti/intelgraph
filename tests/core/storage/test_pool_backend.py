import pytest

from intelgraph.core.storage.postgres_backend import HAS_PSYCOPG2, PostgresBackend


class TestPostgresPoolBackend:
    def test_pool_import(self):
        assert HAS_PSYCOPG2 is True

    def test_pool_stats_before_connect(self):
        if not HAS_PSYCOPG2:
            pytest.skip("psycopg2 not available")
        be = PostgresBackend(pool_size=10)
        stats = be.pool_stats()
        assert stats["pool_active"] == 0
        assert stats["pool_idle"] == 0

    def test_connect_sets_pool(self):
        if not HAS_PSYCOPG2:
            pytest.skip("psycopg2 not available")
        be = PostgresBackend(pool_size=5)
        assert be._pool is None
        with pytest.raises(RuntimeError, match="not connected"):
            be._require()

    def test_disconnect_when_not_connected(self):
        if not HAS_PSYCOPG2:
            pytest.skip("psycopg2 not available")
        be = PostgresBackend()
        be.disconnect()

    def test_pool_size_config(self):
        if not HAS_PSYCOPG2:
            pytest.skip("psycopg2 not available")
        be = PostgresBackend(pool_size=20)
        assert be._pool_size == 20
