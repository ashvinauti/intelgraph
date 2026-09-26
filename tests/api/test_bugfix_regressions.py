"""Regression tests for bugs that previously crashed or silently misbehaved."""

from __future__ import annotations

import pytest

from intelgraph.api.routers.dashboard import DashboardState, dashboard_state


class TestEnrichmentThreatScore:
    def test_threat_score_is_computed(self, auth_client):
        resp = auth_client.post(
            "/entities",
            json={
                "entity_type": "ipaddress",
                "attributes": {"ip": "203.0.113.77", "confidence_score": 80},
            },
        )
        assert resp.status_code == 200

        resp = auth_client.get("/enrichment/ip_address/203.0.113.77")
        assert resp.status_code == 200
        # ThreatScorer used to be constructed with a stray argument, the
        # TypeError was swallowed and threat_score was always null.
        assert isinstance(resp.json()["threat_score"], float)


class TestTechnologyEntityUpdate:
    def test_update_technology_increments_revision(self, auth_client):
        resp = auth_client.post(
            "/entities",
            json={
                "entity_type": "technology",
                "attributes": {"name": "nginx", "product_version": "1.25"},
            },
        )
        assert resp.status_code == 200
        entity_id = resp.json().get("id") or resp.json().get("entity_id")

        # Technology.version used to shadow the integer record revision, so
        # the update did `"" + 1` and returned a 500.
        resp = auth_client.put(
            f"/entities/{entity_id}", json={"attributes": {"category": "web"}}
        )
        assert resp.status_code == 200


class TestDashboardGraphSinceFilter:
    @pytest.fixture(autouse=True)
    def _seed(self):
        saved = dict(dashboard_state._results)
        dashboard_state._results[""] = {
            "graph_nodes_summary": [
                {"id": "old", "last_seen": "2020-01-01T00:00:00"},
                {"id": "new", "last_seen": "2099-01-01T00:00:00"},
            ],
            "graph_edges_summary": [],
        }
        yield
        dashboard_state._results.clear()
        dashboard_state._results.update(saved)

    def test_naive_iso_date(self, auth_client):
        resp = auth_client.get("/dashboard/graph", params={"since": "2025-01-01"})
        assert resp.status_code == 200
        assert len(resp.json()["nodes"]) == 1

    def test_malformed_day_suffix(self, auth_client):
        resp = auth_client.get("/dashboard/graph", params={"since": "xd"})
        assert resp.status_code == 200


def test_dashboard_state_default_tenant_lookup():
    state = DashboardState()
    state._results[""] = {"ok": True}
    assert state._get_result("") == {"ok": True}
