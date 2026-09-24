"""Tests for SOC integration endpoints (Phase 42):

- IOC enrichment (/enrichment/{ioc_type}/{ioc_value})
- STIX export (/export/stix)
- API key authentication (X-API-Key header)
"""
from __future__ import annotations

import pytest


class TestEnrichmentEndpoint:
    def test_enrich_unknown_indicator(self, auth_client):
        resp = auth_client.get("/enrichment/ip_address/192.0.2.99")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False
        assert data["ioc_type"] == "ip_address"
        assert data["ioc_value"] == "192.0.2.99"

    def test_enrich_unsupported_type(self, auth_client):
        resp = auth_client.get("/enrichment/bogus_type/something")
        assert resp.status_code == 400
        assert "Unsupported" in resp.json()["detail"]

    def test_enrich_found_entity(self, auth_client):
        # Create an entity first via the entities API.
        resp = auth_client.post(
            "/entities",
            json={
                "entity_type": "ipaddress",
                "attributes": {
                    "ip": "203.0.113.5",
                    "confidence_score": 80,
                    "trust_score": 70,
                },
            },
        )
        assert resp.status_code == 200
        entity_id = resp.json().get("id") or resp.json().get("entity_id")

        resp = auth_client.get("/enrichment/ip_address/203.0.113.5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["ioc_type"] == "ip_address"
        assert data["ioc_value"] == "203.0.113.5"
        assert data["entity"]["identifier"] == "203.0.113.5"
        assert data["entity"]["confidence_score"] >= 80
        assert "related_entities" in data
        assert "related_count" in data

    def test_enrich_case_insensitive(self, auth_client):
        auth_client.post(
            "/entities",
            json={
                "entity_type": "domain",
                "attributes": {
                    "domain_name": "Example.Org",
                    "confidence_score": 60,
                },
            },
        )
        resp = auth_client.get("/enrichment/domain/example.org")
        assert resp.status_code == 200
        assert resp.json()["found"] is True

    def test_enrich_max_neighbors_param(self, auth_client):
        auth_client.post(
            "/entities",
            json={
                "entity_type": "ipaddress",
                "attributes": {"ip": "198.51.100.1", "confidence_score": 50},
            },
        )
        resp = auth_client.get("/enrichment/ip_address/198.51.100.1?max_neighbors=5")
        assert resp.status_code == 200
        assert resp.json()["related_count"] <= 5

    def test_enrich_invalid_max_neighbors(self, auth_client):
        resp = auth_client.get("/enrichment/ip_address/1.2.3.4?max_neighbors=999")
        assert resp.status_code == 422  # FastAPI validation


class TestStixExportEndpoint:
    def test_stix_empty_graph(self, auth_client):
        resp = auth_client.get("/export/stix")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "empty"

    def test_stix_bundle_exported(self, auth_client):
        auth_client.post(
            "/entities",
            json={
                "entity_type": "ipaddress",
                "attributes": {"ip": "203.0.113.10", "confidence_score": 70},
            },
        )
        resp = auth_client.get("/export/stix")
        assert resp.status_code == 200
        bundle = resp.json()
        assert bundle["type"] == "bundle"
        assert bundle["id"].startswith("bundle--")
        assert len(bundle["objects"]) >= 1

    def test_stix_since_invalid(self, auth_client):
        # Need at least one entity so we get past the empty-graph early return.
        auth_client.post(
            "/entities",
            json={
                "entity_type": "domain",
                "attributes": {"domain_name": "probe.example.com", "confidence_score": 50},
            },
        )
        resp = auth_client.get("/export/stix?since=not-a-date")
        assert resp.status_code == 400

    def test_stix_headers(self, auth_client):
        auth_client.post(
            "/entities",
            json={
                "entity_type": "domain",
                "attributes": {"domain_name": "test.example.com", "confidence_score": 65},
            },
        )
        resp = auth_client.get("/export/stix")
        assert resp.status_code == 200
        assert resp.headers.get("X-STIX-Version") == "2.1"
        assert int(resp.headers.get("X-Export-Object-Count", "0")) >= 1


class TestApiKeyAuth:
    def test_x_api_key_header_accepted_in_schema(self, auth_client):
        # The OpenAPI spec should mention X-API-Key somewhere — at least
        # via the middleware description.
        schema = auth_client.get("/openapi.json").json()
        desc = schema["info"]["description"]
        assert "X-API-Key" in desc

    def test_write_endpoints_reject_no_auth(self, client):
        # POST to write endpoint without any auth header should 401.
        # Note: this works because /investigations is not in public prefixes.
        resp = client.post(
            "/investigations",
            json={
                "name": "should fail",
                "seed_ioc": "1.1.1.1",
                "seed_ioc_type": "ip_address",
            },
        )
        assert resp.status_code == 401

    def test_invalid_api_key_treated_as_unauthenticated(self, client):
        # Invalid X-API-Key should not grant access.
        resp = client.post(
            "/investigations",
            json={
                "name": "should fail",
                "seed_ioc": "1.1.1.1",
                "seed_ioc_type": "ip_address",
            },
            headers={"X-API-Key": "igt_invalid_key_12345"},
        )
        # Invalid key should still 401 (no resolved uid).
        assert resp.status_code == 401