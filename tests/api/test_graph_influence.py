class TestInfluenceAPI:
    def _populate_graph(self, client):
        from intelgraph.api.main import _container

        backend = _container.backend
        from intelgraph.core.entity.person import Person
        from intelgraph.core.relationship import Relationship
        from intelgraph.core.relationship.types import RelationshipType

        p1 = Person(id="p1", name="Alice", confidence_score=80)
        p2 = Person(id="p2", name="Bob", confidence_score=70)
        p3 = Person(id="p3", name="Charlie", confidence_score=90)
        backend.put_entity(p1)
        backend.put_entity(p2)
        backend.put_entity(p3)
        r1 = Relationship(
            id="r1",
            source_id="p1",
            target_id="p2",
            type=RelationshipType.ASSOCIATED_WITH,
            confidence_score=80,
            trust_weight=80,
        )
        r2 = Relationship(
            id="r2",
            source_id="p2",
            target_id="p3",
            type=RelationshipType.ASSOCIATED_WITH,
            confidence_score=70,
            trust_weight=70,
        )
        r3 = Relationship(
            id="r3",
            source_id="p1",
            target_id="p3",
            type=RelationshipType.RELATED_TO,
            confidence_score=90,
            trust_weight=90,
        )
        backend.put_relationship(r1)
        backend.put_relationship(r2)
        backend.put_relationship(r3)

    def test_pagerank(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post("/graph/algorithms/pagerank", params={"damping": 0.85})
        assert resp.status_code == 200
        data = resp.json()
        assert "scores" in data
        assert len(data["scores"]) == 3
        assert data["converged"] is True

    def test_pagerank_empty_graph(self, auth_client):
        resp = auth_client.post("/graph/algorithms/pagerank")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scores"] == {}

    def test_weighted_pagerank(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post("/graph/algorithms/weighted-pagerank", params={"damping": 0.85})
        assert resp.status_code == 200
        data = resp.json()
        assert "scores" in data
        assert len(data["scores"]) == 3
        assert data["converged"] is True

    def test_influence_propagation(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post(
            "/graph/algorithms/influence-propagation",
            json={
                "seed_nodes": {"p1": 1.0},
                "threshold": 0.3,
                "decay_factor": 0.5,
                "max_depth": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "influence" in data
        assert data["seed_count"] == 1
        assert data["nodes_activated"] >= 1

    def test_influence_propagation_no_seeds(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post(
            "/graph/algorithms/influence-propagation",
            json={
                "seed_nodes": {},
            },
        )
        assert resp.status_code == 400

    def test_influence_propagation_invalid_threshold(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post(
            "/graph/algorithms/influence-propagation",
            json={
                "seed_nodes": {"p1": 1.0},
                "threshold": 2.0,
            },
        )
        assert resp.status_code == 400

    def test_influence_propagation_invalid_depth(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post(
            "/graph/algorithms/influence-propagation",
            json={
                "seed_nodes": {"p1": 1.0},
                "max_depth": 200,
            },
        )
        assert resp.status_code == 400

    def test_influence_scores(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.post("/graph/algorithms/influence-scores")
        assert resp.status_code == 200
        data = resp.json()
        assert "scores" in data
        assert len(data["scores"]) == 3
        assert "components" in data

    def test_top_influence(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/influence/top-n/2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["top_nodes"]) == 2

    def test_top_influence_invalid_n(self, auth_client):
        resp = auth_client.get("/graph/influence/top-n/0")
        assert resp.status_code == 400

    def test_top_influence_large_n(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/influence/top-n/100")
        assert resp.status_code == 200

    def test_influence_chain(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/influence/chain/p1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["node_id"] == "p1"
        assert len(data["chain"]) >= 1

    def test_influence_chain_not_found(self, auth_client):
        resp = auth_client.get("/graph/influence/chain/nonexistent")
        assert resp.status_code == 404

    def test_influence_chain_invalid_depth(self, auth_client):
        self._populate_graph(auth_client)
        resp = auth_client.get("/graph/influence/chain/p1", params={"max_depth": 200})
        assert resp.status_code == 400

    def test_metrics_recorded(self, auth_client):
        self._populate_graph(auth_client)
        auth_client.post("/graph/algorithms/pagerank")
        resp = auth_client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "influence_page_rank_duration_ms" in body
