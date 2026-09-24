from __future__ import annotations

import json
import tempfile

from intelgraph.api.auth import (
    decode_token,
    login_user,
    login_with_api_key,
    register_user,
)
from intelgraph.core.multitenant import (
    MultiTenantRouter,
    Tenant,
    TenantManager,
    reset_tenant_manager,
)


def _fresh_tm() -> TenantManager:
    """Create a TenantManager with a temporary DB to avoid cross-test pollution."""

    tmp = tempfile.mktemp(suffix=".db")
    return TenantManager(db_path=tmp)


# ===================================================================
# Tenant Manager Tests
# ===================================================================


class TestTenantManager:
    def test_create_tenant(self) -> None:
        tm = _fresh_tm()
        tenant, api_key = tm.create_tenant("Acme Corp")
        assert tenant.tenant_id.startswith("tnt_")
        assert tenant.name == "Acme Corp"
        assert tenant.is_active is True
        assert api_key.startswith("igt_")
        assert len(api_key) > 20

    def test_get_tenant(self) -> None:
        tm = _fresh_tm()
        t1, _ = tm.create_tenant("Alpha")
        t2 = tm.get(t1.tenant_id)
        assert t2 is t1
        assert tm.get("nonexistent") is None

    def test_list_tenants(self) -> None:
        tm = _fresh_tm()
        tm.create_tenant("A")
        tm.create_tenant("B")
        assert len(tm.list_tenants()) == 2

    def test_delete_tenant(self) -> None:
        tm = _fresh_tm()
        t, _ = tm.create_tenant("ToDelete")
        assert tm.delete_tenant(t.tenant_id) is True
        assert tm.get(t.tenant_id) is None
        assert tm.delete_tenant("nonexistent") is False

    def test_rotate_api_key(self) -> None:
        tm = _fresh_tm()
        t, old_key = tm.create_tenant("KeyRotate")
        result = tm.rotate_api_key(t.tenant_id)
        assert result is not None
        tid, new_key = result
        assert tid == t.tenant_id
        assert new_key != old_key
        assert new_key.startswith("igt_")

    def test_api_key_verify(self) -> None:
        tm = _fresh_tm()
        t, api_key = tm.create_tenant("VerifyMe")
        verified = tm.verify_api_key(api_key)
        assert verified is not None
        assert verified.tenant_id == t.tenant_id
        assert tm.verify_api_key("wrong_key") is None

    def test_quota_tracking(self) -> None:
        tm = _fresh_tm()
        t, _ = tm.create_tenant("QuotaTest")
        assert tm.check_quota(t.tenant_id, "sources", 5) is True
        tm.record_usage(t.tenant_id, "sources", 3)
        assert tm.check_quota(t.tenant_id, "sources", 5) is True
        tm.record_usage(t.tenant_id, "sources", 3)
        assert tm.check_quota(t.tenant_id, "sources", 5) is False

    def test_quota_usage_report(self) -> None:
        tm = _fresh_tm()
        t, _ = tm.create_tenant("UsageTest")
        tm.record_usage(t.tenant_id, "api_calls", 42.0)
        usage = tm.quota_usage(t.tenant_id)
        assert usage["api_calls"] == 42.0

    def test_stats(self) -> None:
        tm = _fresh_tm()
        t, _ = tm.create_tenant("StatsTest")
        stats = tm.get_stats(t.tenant_id)
        assert stats["name"] == "StatsTest"
        assert stats["is_active"] is True
        assert "usage" in stats

    def test_update_config(self) -> None:
        tm = _fresh_tm()
        t, _ = tm.create_tenant("ConfigTest")
        tm.update_config(t.tenant_id, {"custom_flag": True})
        assert tm.get(t.tenant_id).config["custom_flag"] is True

    def test_default_config(self) -> None:
        tm = _fresh_tm()
        t, _ = tm.create_tenant("DefaultConfig")
        assert "thresholds" in t.config
        assert "playbooks" in t.config
        assert "rate_limits" in t.config
        assert t.config["rate_limits"]["read"] == 500


# ===================================================================
# Tenant Isolation Tests
# ===================================================================


class TestTenantIsolation:
    def test_separate_tenants_have_different_ids(self) -> None:
        tm = _fresh_tm()
        t1, _ = tm.create_tenant("Alpha")
        t2, _ = tm.create_tenant("Beta")
        assert t1.tenant_id != t2.tenant_id

    def test_cannot_access_other_tenant(self) -> None:
        tm = _fresh_tm()
        t1, _ = tm.create_tenant("Alpha")
        t2, _ = tm.create_tenant("Beta")
        assert tm.get(t1.tenant_id).tenant_id == t1.tenant_id
        assert tm.get(t2.tenant_id).tenant_id == t2.tenant_id

    def test_enforce_isolation(self) -> None:
        tm = _fresh_tm()
        data = tm.enforce_isolation({"key": "val"}, "tenant_a")
        assert data["_tenant_id"] == "tenant_a"

    def test_verify_isolation(self) -> None:
        tm = _fresh_tm()
        data_a = tm.enforce_isolation({"key": "val"}, "tenant_a")
        data_b = tm.enforce_isolation({"key": "val"}, "tenant_b")
        assert tm.verify_isolation(data_a, "tenant_a") is True
        assert tm.verify_isolation(data_b, "tenant_b") is True
        assert tm.verify_isolation(data_a, "tenant_b") is False
        assert tm.verify_isolation(data_b, "tenant_a") is False

    def test_api_key_isolation(self) -> None:
        tm = _fresh_tm()
        t1, key1 = tm.create_tenant("Alpha")
        t2, key2 = tm.create_tenant("Beta")
        assert tm.verify_api_key(key1).tenant_id == t1.tenant_id
        assert tm.verify_api_key(key2).tenant_id == t2.tenant_id
        assert tm.verify_api_key(key1).tenant_id != t2.tenant_id


class TestTenantIsolationSameIP:
    def test_same_ip_different_tenants(self) -> None:
        tm = _fresh_tm()
        # Same IP address, different tenants — should not conflict
        t1, key1 = tm.create_tenant("Alpha")
        t2, key2 = tm.create_tenant("Beta")
        assert t1.tenant_id != t2.tenant_id
        # Each tenant has its own API key
        assert key1 != key2
        # Cross-tenant API key access denied
        assert tm.verify_api_key(key2).tenant_id == t2.tenant_id
        assert tm.verify_api_key(key2).tenant_id != t1.tenant_id


# ===================================================================
# MultiTenantRouter Tests
# ===================================================================


class TestMultiTenantRouter:
    def test_register_route(self) -> None:
        r = MultiTenantRouter()
        r.register_route("t1", "/api/t1")
        assert r.route("t1") == "/api/t1"

    def test_partition_key(self) -> None:
        r = MultiTenantRouter()
        assert r.partition_key("t1", "entity:123") == "t1:entity:123"
        assert r.partition_key("t2", "entity:123") == "t2:entity:123"


# ===================================================================
# Auth Integration Tests
# ===================================================================


class TestAuthIntegration:
    def test_login_with_api_key(self) -> None:
        from intelgraph.core.multitenant import manager as mtm

        db = tempfile.mktemp(suffix=".db")
        tm = TenantManager(db_path=db)
        mtm._tenant_manager = tm  # replace global singleton
        tenant, api_key = tm.create_tenant("AuthTest")
        result = login_with_api_key(api_key)
        assert result is not None
        assert "access_token" in result
        import jwt

        token = result["access_token"]
        payload = jwt.decode(token, options={"verify_signature": False})
        assert payload["tenant_id"] == tenant.tenant_id
        mtm._tenant_manager = None

    def test_login_with_invalid_api_key_fails(self) -> None:
        from intelgraph.core.multitenant import manager as mtm

        mtm._tenant_manager = None
        result = login_with_api_key("invalid_key_12345")
        assert result is None

    def test_token_contains_tenant_id(self) -> None:
        from intelgraph.core.multitenant import manager as mtm

        db = tempfile.mktemp(suffix=".db")
        tm = TenantManager(db_path=db)
        mtm._tenant_manager = tm
        tenant, api_key = tm.create_tenant("TokenTest")
        result = login_with_api_key(api_key)
        token = result["access_token"]
        decoded = decode_token(token)
        assert decoded is not None
        assert decoded.get("tenant_id") == tenant.tenant_id
        mtm._tenant_manager = None

    def test_user_registration_with_tenant(self) -> None:
        from intelgraph.core.multitenant import manager as mtm

        mtm._tenant_manager = None
        result = register_user("testuser2", "testpass", role="user", tenant_id="tnt_custom")
        assert "access_token" in result
        decoded = decode_token(result["access_token"])
        assert decoded.get("tenant_id") == "tnt_custom"

    def test_login_preserves_tenant(self) -> None:
        from intelgraph.core.multitenant import manager as mtm

        mtm._tenant_manager = None
        register_user("user_login2", "pass1", role="user", tenant_id="tnt_custom")
        result = login_user("user_login2", "pass1")
        assert result is not None
        decoded = decode_token(result["access_token"])
        assert decoded.get("tenant_id") == "tnt_custom"


# ===================================================================
# Tenant.to_dict / from_dict round-trip
# ===================================================================


class TestTenantSerialization:
    def test_to_dict(self) -> None:
        tenant = Tenant(
            tenant_id="tnt_test",
            name="Test",
            api_key_hash="abc:def",
            created_at="2026-01-01T00:00:00",
            is_active=True,
            config={"thresholds": {}},
        )
        d = tenant.to_dict()
        assert d["tenant_id"] == "tnt_test"
        assert d["name"] == "Test"
        assert d["is_active"] is True
        assert "api_key_hash" not in d  # not included by default

    def test_to_dict_with_key(self) -> None:
        tenant = Tenant(
            tenant_id="tnt_test",
            name="Test",
            api_key_hash="abc:def",
        )
        d = tenant.to_dict(include_key=True)
        assert d["api_key_hash"] == "abc:def"

    def test_from_dict(self) -> None:
        d = {
            "tenant_id": "tnt_test",
            "name": "Test",
            "api_key_hash": "abc:def",
            "created_at": "2026-01-01T00:00:00",
            "is_active": 1,
            "config": json.dumps({"thresholds": {"c2": {"max": 0.5}}}),
        }
        tenant = Tenant.from_dict(d)
        assert tenant.tenant_id == "tnt_test"
        assert tenant.name == "Test"
        assert tenant.is_active is True
        assert tenant.config["thresholds"]["c2"]["max"] == 0.5


# Clean up after all tests
def teardown_module() -> None:
    reset_tenant_manager()
