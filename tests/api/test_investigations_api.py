"""API tests for the Investigation Workspace endpoints (Phase 41)."""
from __future__ import annotations

import pytest


@pytest.fixture
def investigation(auth_client):
    resp = auth_client.post(
        "/investigations",
        json={
            "name": "API test investigation",
            "seed_ioc": "107.172.135.60",
            "seed_ioc_type": "ip_address",
            "created_by": "tester",
            "tags": ["c2", "mirai"],
        },
    )
    assert resp.status_code == 200
    return resp.json()


class TestInvestigationsCRUD:
    def test_create_and_get(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        assert investigation["name"] == "API test investigation"
        assert investigation["seed_ioc"] == "107.172.135.60"
        assert investigation["seed_ioc_type"] == "ip_address"
        assert investigation["status"] == "open"
        assert investigation["tags"] == ["c2", "mirai"]

        resp = auth_client.get(f"/investigations/{inv_id}")
        assert resp.status_code == 200
        assert resp.json()["investigation_id"] == inv_id

    def test_list(self, auth_client, investigation):
        resp = auth_client.get("/investigations")
        assert resp.status_code == 200
        data = resp.json()
        assert "investigations" in data
        assert len(data["investigations"]) >= 1
        ids = [inv["investigation_id"] for inv in data["investigations"]]
        assert investigation["investigation_id"] in ids

    def test_delete(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.delete(f"/investigations/{inv_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        resp = auth_client.get(f"/investigations/{inv_id}")
        assert resp.status_code == 404

    def test_get_not_found(self, auth_client):
        resp = auth_client.get("/investigations/inv_nonexistent")
        assert resp.status_code == 404

    def test_create_missing_fields(self, auth_client):
        resp = auth_client.post("/investigations", json={"name": "missing"})
        assert resp.status_code == 400


class TestStatusUpdate:
    def test_status_closed(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.patch(
            f"/investigations/{inv_id}/status",
            json={"status": "closed"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "closed"

    def test_status_invalid(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.patch(
            f"/investigations/{inv_id}/status",
            json={"status": "bogus"},
        )
        assert resp.status_code == 404


class TestNotes:
    def test_add_note(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.post(
            f"/investigations/{inv_id}/notes",
            json={"author": "alice", "content": "This looks like C2 infra"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "This looks like C2 infra"
        assert data["pinned"] is False

    def test_add_pinned_note(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.post(
            f"/investigations/{inv_id}/notes",
            json={"author": "bob", "content": "Critical", "pinned": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pinned"] is True

    def test_list_notes(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        auth_client.post(
            f"/investigations/{inv_id}/notes",
            json={"author": "a", "content": "first"},
        )
        auth_client.post(
            f"/investigations/{inv_id}/notes",
            json={"author": "b", "content": "pinned", "pinned": True},
        )
        resp = auth_client.get(f"/investigations/{inv_id}/notes")
        assert resp.status_code == 200
        data = resp.json()["notes"]
        assert len(data) == 2
        assert data[0]["pinned"] is True

    def test_delete_note(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        add = auth_client.post(
            f"/investigations/{inv_id}/notes",
            json={"author": "x", "content": "to be deleted"},
        )
        note_id = add.json()["note_id"]
        resp = auth_client.delete(f"/investigations/{inv_id}/notes/{note_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_add_note_missing_content(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.post(
            f"/investigations/{inv_id}/notes",
            json={"author": "x", "content": ""},
        )
        assert resp.status_code == 400


class TestTimeline:
    def test_get_timeline(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.get(f"/investigations/{inv_id}/timeline")
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert any(e["event_type"] == "creation" for e in events)

    def test_add_timeline_event(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.post(
            f"/investigations/{inv_id}/timeline",
            json={
                "event_type": "escalation",
                "title": "Escalated",
                "description": "Escalated to tier 2",
                "source": "analyst1",
                "metadata": {"tier": 2},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_type"] == "escalation"
        assert data["metadata"]["tier"] == 2

    def test_add_timeline_no_title(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.post(
            f"/investigations/{inv_id}/timeline",
            json={"event_type": "x", "title": "", "description": ""},
        )
        assert resp.status_code == 400


class TestFindingsAndPivot:
    def test_list_findings_empty(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.get(f"/investigations/{inv_id}/findings")
        assert resp.status_code == 200
        assert resp.json()["findings"] == []

    def test_add_finding(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.post(
            f"/investigations/{inv_id}/findings",
            json={
                "ioc_value": "evil.example.com",
                "ioc_type": "domain",
                "finding_type": "manual",
                "confidence": 85,
                "evidence_summary": "Resolves to seed IP",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["finding_count"] >= 1
        latest = data["findings"][-1]
        assert latest["ioc_value"] == "evil.example.com"

    def test_pivot_empty_graph(self, auth_client, investigation):
        inv_id = investigation["investigation_id"]
        resp = auth_client.post(
            f"/investigations/{inv_id}/pivot",
            json={"max_depth": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_findings"] == 0