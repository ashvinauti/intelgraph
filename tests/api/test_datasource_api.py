class TestDatasourceAPI:
    def test_list_empty(self, client):
        resp = client.get("/data-sources")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_register_invalid_type(self, auth_client):
        resp = auth_client.post(
            "/data-sources/register",
            json={
                "source_id": "src1",
                "source_name": "Bad",
                "connector_type": "invalid",
            },
        )
        assert resp.status_code == 422

    def test_register_http_source(self, auth_client):
        resp = auth_client.post(
            "/data-sources/register",
            json={
                "source_id": "http1",
                "source_name": "HTTP Feed",
                "connector_type": "http",
                "endpoint_url": "https://example.com/feed",
                "polling_interval": 3600,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "http1"
        assert data["connector_type"] == "http"

    def test_register_file_source(self, auth_client):
        resp = auth_client.post(
            "/data-sources/register",
            json={
                "source_id": "file1",
                "source_name": "Local File",
                "connector_type": "file",
                "file_path": "/tmp/data.json",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "file1"

    def test_list_after_register(self, client):
        resp = client.get("/data-sources")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 2

    def test_get_source(self, client):
        resp = client.get("/data-sources/http1")
        assert resp.status_code == 200
        assert resp.json()["id"] == "http1"

    def test_get_source_not_found(self, client):
        resp = client.get("/data-sources/nonexistent")
        assert resp.status_code == 404

    def test_delete_source(self, auth_client):
        resp = auth_client.delete("/data-sources/file1")
        assert resp.status_code == 200

    def test_delete_not_found(self, auth_client):
        resp = auth_client.delete("/data-sources/nonexistent")
        assert resp.status_code == 404

    def test_poll_source(self, auth_client):
        resp = auth_client.post("/data-sources/http1/poll")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data

    def test_poll_nonexistent(self, auth_client):
        resp = auth_client.post("/data-sources/nonexistent/poll")
        assert resp.status_code == 404

    def test_get_source_status(self, client):
        resp = client.get("/data-sources/http1/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active" or data["status"] == "error"

    def test_get_source_status_not_found(self, client):
        resp = client.get("/data-sources/nonexistent/status")
        assert resp.status_code == 404

    def test_bulk_poll(self, auth_client):
        auth_client.post(
            "/data-sources/register",
            json={
                "source_id": "bp1",
                "source_name": "Bulk1",
                "connector_type": "http",
                "endpoint_url": "https://example.com/a",
            },
        )
        auth_client.post(
            "/data-sources/register",
            json={
                "source_id": "bp2",
                "source_name": "Bulk2",
                "connector_type": "file",
                "file_path": "/nonexistent.json",
            },
        )
        resp = auth_client.post("/data-sources/bulk-poll", json=["bp1", "bp2"])
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2

    def test_poll_history(self, client):
        resp = client.get("/data-sources/http1/poll-history")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_unauthenticated_write_rejected(self, client):
        resp = client.post(
            "/data-sources/register",
            json={
                "source_id": "unauth",
                "source_name": "Unauth",
                "connector_type": "http",
            },
        )
        assert resp.status_code == 401
