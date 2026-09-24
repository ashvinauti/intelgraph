class TestAnomalyAPI:
    def _populate_graph(self, client):
        from intelgraph.api.main import _container

        backend = _container.backend
        from intelgraph.core.entity.person import Person
        from intelgraph.core.relationship import Relationship
        from intelgraph.core.relationship.types import RelationshipType

        entities = []
        for i in range(10):
            p = Person(id=f"p{i}", name=f"Person {i}", confidence_score=50, trust_score=50)
            backend.put_entity(p)
            entities.append(p)
        rels_data = [
            ("p0", "p1", 80),
            ("p0", "p2", 60),
            ("p1", "p3", 90),
            ("p1", "p4", 50),
            ("p2", "p5", 70),
            ("p2", "p6", 40),
            ("p3", "p7", 85),
            ("p4", "p8", 75),
            ("p5", "p9", 65),
            ("p6", "p7", 55),
            ("p7", "p8", 45),
            ("p8", "p9", 95),
        ]
        for idx, (src, tgt, conf) in enumerate(rels_data):
            r = Relationship(
                id=f"r{idx}",
                source_id=src,
                target_id=tgt,
                type=RelationshipType.RELATED_TO,
                confidence_score=conf,
                trust_weight=conf,
            )
            backend.put_relationship(r)

    # --- Detect ---

    def test_detect(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post("/graph/anomaly/detect")
        assert resp.status_code == 200
        data = resp.json()
        assert "detections" in data
        assert data["total_nodes_analyzed"] == 10
        assert data["graph_node_count"] == 10
        assert "graph_version" in data
        assert "execution_time_ms" in data

    def test_detect_empty_graph(self, auth_client):
        resp = auth_client.post("/graph/anomaly/detect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_nodes_analyzed"] == 0
        assert data["detections"]["high"] == 0

    # --- Nodes ---

    def test_get_node_anomaly(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/anomaly/nodes/p0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["node_id"] == "p0"
        assert "anomaly_score" in data
        assert "confidence" in data
        assert "signals" in data
        assert "feature_contributions" in data

    def test_get_node_anomaly_not_found(self, auth_client):
        resp = auth_client.get("/graph/anomaly/nodes/nonexistent")
        assert resp.status_code == 404

    # --- Timeline ---

    def test_timeline(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/anomaly/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert "timeline" in data
        assert data["entry_count"] == 10

    def test_timeline_empty(self, auth_client):
        resp = auth_client.get("/graph/anomaly/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entry_count"] == 0

    # --- Top-N ---

    def test_top_n(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/anomaly/top-n/5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 5
        assert len(data["top_nodes"]) == 5

    def test_top_n_invalid_n(self, auth_client):
        resp = auth_client.get("/graph/anomaly/top-n/0")
        assert resp.status_code == 400

    def test_top_n_large_n(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/anomaly/top-n/100")
        assert resp.status_code == 200

    def test_top_n_empty(self, auth_client):
        resp = auth_client.get("/graph/anomaly/top-n/5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0

    # --- Explain ---

    def test_explain(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/anomaly/explain/p0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["schema_version"] == "1.0"
        assert "overall_score" in data
        assert "confidence" in data
        assert "severity" in data
        assert "signals" in data
        assert "top_contributors" in data
        assert "entity_type" in data

    def test_explain_not_found(self, auth_client):
        resp = auth_client.get("/graph/anomaly/explain/nonexistent")
        assert resp.status_code == 404

    def test_explain_detail(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/anomaly/explain/detail/p0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert "feature_values" in data
        assert "network_context" in data

    def test_explain_detail_not_found(self, auth_client):
        resp = auth_client.get("/graph/anomaly/explain/detail/nonexistent")
        assert resp.status_code == 404

    # --- Metrics recorded ---

    def test_metrics_recorded(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post("/graph/anomaly/detect")
        assert resp.status_code == 200
        metrics_resp = auth_client.get("/metrics")
        assert metrics_resp.status_code == 200
        body = metrics_resp.text
        assert "anomaly_detect_duration_ms" in body
        assert "anomaly_high_count" in body
        assert "anomaly_mean_score" in body
