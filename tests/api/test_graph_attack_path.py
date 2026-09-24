class TestAttackPathAPI:
    def _populate_graph(self, client):
        from intelgraph.api.main import _container

        backend = _container.backend
        from intelgraph.core.entity.person import Person
        from intelgraph.core.relationship import Relationship
        from intelgraph.core.relationship.types import RelationshipType

        entities = []
        for i in range(8):
            p = Person(
                id=f"p{i}",
                name=f"Person {i}",
                confidence_score=min(50 + i * 5, 95),
                trust_score=min(40 + i * 5, 90),
            )
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
            ("p4", "p0", 75),
            ("p5", "p6", 65),
            ("p6", "p7", 55),
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

    # --- Find shortest path ---

    def test_find_shortest_path(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post("/graph/attack-path/find", json={"source": "p0", "target": "p7"})
        assert resp.status_code == 200
        data = resp.json()
        assert "found" in data
        assert "graph_version" in data

    def test_find_shortest_path_missing_params(self, auth_client):
        resp = auth_client.post("/graph/attack-path/find", json={"source": "p0"})
        assert resp.status_code == 400

    def test_find_shortest_path_empty(self, auth_client):
        resp = auth_client.post(
            "/graph/attack-path/find", json={"source": "p0", "target": "nonexistent"}
        )
        assert resp.status_code == 200
        assert resp.json()["found"] is False

    # --- Find all paths ---

    def test_find_all_paths(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post("/graph/attack-path/all", json={"source": "p0", "max_depth": 4})
        assert resp.status_code == 200
        data = resp.json()
        assert "paths" in data

    def test_find_all_paths_missing_source(self, auth_client):
        resp = auth_client.post("/graph/attack-path/all", json={})
        assert resp.status_code == 400

    def test_find_all_paths_invalid_depth(self, auth_client):
        resp = auth_client.post("/graph/attack-path/all", json={"source": "p0", "max_depth": 20})
        assert resp.status_code == 400

    def test_find_all_paths_to_target(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post(
            "/graph/attack-path/all", json={"source": "p0", "target": "p7", "max_depth": 4}
        )
        assert resp.status_code == 200
        data = resp.json()
        if data.get("found"):
            for p in data["paths"]:
                assert p["node_ids"][-1] == "p7"

    # --- Get path by ID ---

    def test_get_path_by_id_not_found(self, auth_client):
        resp = auth_client.get("/graph/attack-path/nonexistent")
        assert resp.status_code == 404

    def test_get_path_by_id_from_result(self, auth_client):
        self._populate_graph(auth_client)
        all_resp = auth_client.post("/graph/attack-path/all", json={"source": "p0", "max_depth": 3})
        all_data = all_resp.json()
        if all_data.get("paths"):
            path_id = all_data["paths"][0]["path_id"]
            resp = auth_client.get(f"/graph/attack-path/{path_id}")
            # Path ID is ephemeral, won't exist in a new graph build, so 404 is expected
            assert resp.status_code == 404

    # --- Critical nodes ---

    def test_critical_nodes(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/attack-path/critical-nodes", params={"max_depth": 4})
        assert resp.status_code == 200
        data = resp.json()
        assert "critical_nodes" in data
        assert "analytics" in data

    def test_critical_nodes_invalid_depth(self, auth_client):
        resp = auth_client.get("/graph/attack-path/critical-nodes", params={"max_depth": 20})
        assert resp.status_code == 400

    def test_critical_nodes_empty(self, auth_client):
        resp = auth_client.get("/graph/attack-path/critical-nodes")
        assert resp.status_code == 200

    # --- Attack surface ---

    def test_attack_surface(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/attack-path/surface/p0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert "surface_size" in data
        assert "surface_by_type" in data

    def test_attack_surface_not_found(self, auth_client):
        resp = auth_client.get("/graph/attack-path/surface/nonexistent")
        assert resp.status_code == 404

    def test_attack_surface_invalid_depth(self, auth_client):
        resp = auth_client.get("/graph/attack-path/surface/p0", params={"max_depth": 20})
        assert resp.status_code == 400

    # --- Explain path ---

    def test_explain_path_with_data(self, auth_client):
        self._populate_graph(auth_client)
        all_resp = auth_client.post("/graph/attack-path/all", json={"source": "p0", "max_depth": 3})
        all_data = all_resp.json()
        if all_data.get("paths"):
            path_id = all_data["paths"][0]["path_id"]
            resp = auth_client.post(f"/graph/attack-path/explain/{path_id}", json=all_data)
            assert resp.status_code == 200
            data = resp.json()
            if data.get("found"):
                assert "segment_breakdown" in data

    def test_explain_path_not_found(self, auth_client):
        resp = auth_client.post("/graph/attack-path/explain/nonexistent", json={})
        assert resp.status_code == 404

    # --- Metrics ---

    def test_metrics_recorded(self, auth_client):
        self._populate_graph(auth_client)
        auth_client.post("/graph/attack-path/find", json={"source": "p0", "target": "p7"})
        metrics_resp = auth_client.get("/metrics")
        assert metrics_resp.status_code == 200
        body = metrics_resp.text
        assert "attack_path_find_shortest_duration_ms" in body
