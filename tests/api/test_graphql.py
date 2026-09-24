from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from intelgraph.api.main import create_app


@pytest.fixture
def client():
    app = create_app({"storage": {"path": ":memory:"}})
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    resp = client.post(
        "/auth/register",
        json={"username": "admin", "password": "admin123", "role": "admin"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


def _gql(client, query: str, variables: dict | None = None):
    resp = client.post("/graphql", json={"query": query, "variables": variables or {}})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "errors" not in body, body
    return body["data"]


class TestGraphQLAuth:
    def test_mutation_requires_auth(self, client):
        mutation = """
        mutation {
          createEntity(input: {entityType: "domain", attributes: "{}"}) { id }
        }
        """
        resp = client.post("/graphql", json={"query": mutation})
        assert resp.status_code == 401


class TestGraphQLEntities:
    def test_create_and_fetch_entity(self, auth_client):
        mutation = """
        mutation($attrs: JSON!) {
          createEntity(input: {entityType: "domain", attributes: $attrs}) {
            id
            entityType
            attributes
          }
        }
        """
        data = _gql(
            auth_client, mutation, {"attrs": {"domain_name": "evil.example"}}
        )
        entity_id = data["createEntity"]["id"]
        assert data["createEntity"]["entityType"] == "domain"
        assert data["createEntity"]["attributes"]["domain_name"] == "evil.example"

        query = """
        query($id: String!) {
          entity(id: $id) { id entityType attributes }
        }
        """
        data = _gql(auth_client, query, {"id": entity_id})
        assert data["entity"]["id"] == entity_id
        assert data["entity"]["attributes"]["domain_name"] == "evil.example"

    def test_entity_not_found_returns_null(self, auth_client):
        query = 'query { entity(id: "does-not-exist") { id } }'
        data = _gql(auth_client, query)
        assert data["entity"] is None

    def test_list_entities_filtered_by_type(self, auth_client):
        mutation = """
        mutation($attrs: JSON!) {
          createEntity(input: {entityType: "domain", attributes: $attrs}) { id }
        }
        """
        _gql(auth_client, mutation, {"attrs": {"domain_name": "one.example"}})
        _gql(auth_client, mutation, {"attrs": {"domain_name": "two.example"}})

        query = 'query { entities(entityType: "domain") { id entityType } }'
        data = _gql(auth_client, query)
        assert len(data["entities"]) >= 2
        assert all(e["entityType"] == "domain" for e in data["entities"])

    def test_search_finds_created_entity(self, auth_client):
        mutation = """
        mutation($attrs: JSON!) {
          createEntity(input: {entityType: "domain", attributes: $attrs}) { id }
        }
        """
        _gql(auth_client, mutation, {"attrs": {"domain_name": "findme.example"}})

        query = 'query { search(query: "findme") { nodeId entityIdentifier relevance } }'
        data = _gql(auth_client, query)
        assert any(h["entityIdentifier"] == "findme.example" for h in data["search"])

    def test_create_entity_unknown_type_errors(self, auth_client):
        mutation = """
        mutation($attrs: JSON!) {
          createEntity(input: {entityType: "not_a_type", attributes: $attrs}) { id }
        }
        """
        resp = auth_client.post(
            "/graphql", json={"query": mutation, "variables": {"attrs": {}}}
        )
        assert resp.status_code == 200
        assert "errors" in resp.json()


class TestGraphQLRelationships:
    def test_create_relationship_between_entities(self, auth_client):
        create_entity = """
        mutation($attrs: JSON!) {
          createEntity(input: {entityType: "domain", attributes: $attrs}) { id }
        }
        """
        source = _gql(
            auth_client, create_entity, {"attrs": {"domain_name": "src.example"}}
        )["createEntity"]["id"]
        target = _gql(
            auth_client, create_entity, {"attrs": {"domain_name": "dst.example"}}
        )["createEntity"]["id"]

        create_rel = """
        mutation($input: RelationshipCreateInput!) {
          createRelationship(input: $input) {
            id
            type
            sourceId
            targetId
          }
        }
        """
        data = _gql(
            auth_client,
            create_rel,
            {
                "input": {
                    "type": "related_to",
                    "sourceId": source,
                    "targetId": target,
                }
            },
        )
        rel_id = data["createRelationship"]["id"]
        assert data["createRelationship"]["sourceId"] == source
        assert data["createRelationship"]["targetId"] == target

        query = """
        query($id: String!) {
          relationship(id: $id) { id sourceId targetId }
        }
        """
        data = _gql(auth_client, query, {"id": rel_id})
        assert data["relationship"]["id"] == rel_id

        list_query = """
        query($sourceId: String!) {
          relationships(sourceId: $sourceId) { id sourceId }
        }
        """
        data = _gql(auth_client, list_query, {"sourceId": source})
        assert any(r["id"] == rel_id for r in data["relationships"])

    def test_create_relationship_unknown_type_errors(self, auth_client):
        create_entity = """
        mutation($attrs: JSON!) {
          createEntity(input: {entityType: "domain", attributes: $attrs}) { id }
        }
        """
        source = _gql(auth_client, create_entity, {"attrs": {"domain_name": "a.example"}})[
            "createEntity"
        ]["id"]
        target = _gql(auth_client, create_entity, {"attrs": {"domain_name": "b.example"}})[
            "createEntity"
        ]["id"]

        create_rel = """
        mutation($input: RelationshipCreateInput!) {
          createRelationship(input: $input) { id }
        }
        """
        resp = auth_client.post(
            "/graphql",
            json={
                "query": create_rel,
                "variables": {
                    "input": {
                        "type": "not_a_real_type",
                        "sourceId": source,
                        "targetId": target,
                    }
                },
            },
        )
        assert resp.status_code == 200
        assert "errors" in resp.json()
