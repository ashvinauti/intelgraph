class TestReasoningAPI:
    def _populate_graph(self, client):
        from intelgraph.api.main import _container

        backend = _container.backend
        from intelgraph.core.entity.person import Person
        from intelgraph.core.relationship import Relationship
        from intelgraph.core.relationship.types import RelationshipType

        for i in range(6):
            p = Person(
                id=f"p{i}",
                name=f"Person {i}",
                confidence_score=min(50 + i * 5, 95),
                trust_score=min(40 + i * 5, 90),
            )
            backend.put_entity(p)
        rels_data = [
            ("p0", "p1", 80),
            ("p0", "p2", 60),
            ("p1", "p3", 90),
            ("p1", "p4", 50),
            ("p2", "p5", 70),
            ("p3", "p4", 75),
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

    # --- Root cause ---

    def test_root_cause(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post(
            "/graph/reasoning/root-cause", json={"anomaly_node": "p3", "max_depth": 4}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("found") is True
        assert "trace_id" in data
        assert "root_causes" in data
        assert "graph_version" in data

    def test_root_cause_missing_param(self, auth_client):
        resp = auth_client.post("/graph/reasoning/root-cause", json={})
        assert resp.status_code == 400

    def test_root_cause_not_found(self, auth_client):
        resp = auth_client.post("/graph/reasoning/root-cause", json={"anomaly_node": "nonexistent"})
        assert resp.status_code == 404

    # --- Causal path ---

    def test_causal_path(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post(
            "/graph/reasoning/causal-path", json={"source": "p0", "target": "p3", "max_depth": 4}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "trace_id" in data

    def test_causal_path_missing_params(self, auth_client):
        resp = auth_client.post("/graph/reasoning/causal-path", json={"source": "p0"})
        assert resp.status_code == 400

    # --- Explain ---

    def test_explain(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/reasoning/explain/p0")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("found") is True
        assert "direct_causes" in data
        assert "direct_effects" in data
        assert "causal_graph" in data
        assert "trace_id" in data

    def test_explain_not_found(self, auth_client):
        resp = auth_client.get("/graph/reasoning/explain/nonexistent")
        assert resp.status_code == 404

    # --- Chains ---

    def test_chains(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/reasoning/chains/p0")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("found") is True
        assert "cause_chains" in data
        assert "effect_chains" in data

    def test_chains_not_found(self, auth_client):
        resp = auth_client.get("/graph/reasoning/chains/nonexistent")
        assert resp.status_code == 404

    # --- Causal graph ---

    def test_causal_graph(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/reasoning/causal-graph")
        assert resp.status_code == 200
        data = resp.json()
        assert "causal_graph" in data
        assert "trace_id" in data
        assert data["causal_graph"]["node_count"] > 0

    # --- Top causes ---

    def test_top_causes(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get(
            "/graph/reasoning/top-causes/p3", params={"max_depth": 4, "top_n": 5}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("found") is True
        assert "root_causes" in data
        assert "cross_community_propagation" in data

    def test_top_causes_not_found(self, auth_client):
        resp = auth_client.get("/graph/reasoning/top-causes/nonexistent")
        assert resp.status_code == 404

    def test_top_causes_invalid_top_n(self, auth_client):
        resp = auth_client.get("/graph/reasoning/top-causes/p0", params={"top_n": 0})
        assert resp.status_code == 400

    # --- Metrics ---

    def test_metrics_recorded(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post(
            "/graph/reasoning/root-cause", json={"anomaly_node": "p3", "max_depth": 3}
        )
        assert resp.status_code == 200
        metrics_resp = auth_client.get("/metrics")
        assert metrics_resp.status_code == 200
        body = metrics_resp.text
        assert "causal_root_cause_duration_ms" in body
        assert "causal_graph_size_nodes" in body
