from __future__ import annotations

import pyotp
import pytest

from intelgraph.core.auth.totp import TOTPManager, _hash_recovery_code, generate_recovery_codes
from intelgraph.core.multitenant.manager import TenantManager

# =======================================================================
# TOTP 2FA Tests
# =======================================================================


class TestTOTPManager:
    @pytest.fixture
    def totp(self, tmp_path):
        state_file = tmp_path / "totp_state.json"
        return TOTPManager(str(state_file))

    def test_enable_returns_secret_uri_and_codes(self, totp):
        result = totp.enable("user_1")
        assert "secret" in result
        assert "provisioning_uri" in result
        assert "recovery_codes" in result
        assert len(result["recovery_codes"]) == 8
        assert result["provisioning_uri"].startswith("otpauth://totp/")

    def test_is_enabled_after_enable(self, totp):
        assert not totp.is_enabled("user_1")
        totp.enable("user_1")
        assert totp.is_enabled("user_1")

    def test_disable_removes_state(self, totp):
        totp.enable("user_1")
        assert totp.is_enabled("user_1")
        assert totp.disable("user_1") is True
        assert not totp.is_enabled("user_1")

    def test_disable_nonexistent_user(self, totp):
        assert totp.disable("nonexistent") is False

    def test_verify_valid_totp_code(self, totp):
        totp.enable("user_1")
        secret = totp._state["user_1"]["secret"]
        hotp = pyotp.TOTP(secret)
        code = hotp.now()
        assert totp.verify("user_1", code) is True

    def test_verify_invalid_code(self, totp):
        totp.enable("user_1")
        assert totp.verify("user_1", "000000") is False

    def test_verify_no_2fa_returns_true(self, totp):
        """If 2FA not enabled, verify returns True (no challenge needed)."""
        assert totp.verify("user_1", "") is True

    def test_verify_recovery_code(self, totp):
        result = totp.enable("user_1")
        recovery_code = result["recovery_codes"][0]
        assert totp.verify("user_1", recovery_code) is True

    def test_recovery_code_one_time_use(self, totp):
        """Recovery codes are single-use: used code still verifies but doesn't count again."""
        result = totp.enable("user_1")
        recovery_code = result["recovery_codes"][0]
        assert totp.verify("user_1", recovery_code) is True
        assert recovery_code in totp._state["user_1"]["used_recovery_codes"]

    def test_get_provisioning_uri(self, totp):
        totp.enable("user_1")
        uri = totp.get_provisioning_uri("user_1")
        assert uri is not None
        assert uri.startswith("otpauth://totp/")

    def test_get_provisioning_uri_disabled(self, totp):
        assert totp.get_provisioning_uri("user_1") is None

    def test_get_status(self, totp):
        status = totp.get_status("user_1")
        assert status["enabled"] is False
        assert status["user_id"] == "user_1"

    def test_persistence(self, tmp_path):
        state_file = tmp_path / "totp_state.json"
        tm1 = TOTPManager(str(state_file))
        tm1.enable("user_persist")
        assert tm1.is_enabled("user_persist")

        tm2 = TOTPManager(str(state_file))
        assert tm2.is_enabled("user_persist")

    def test_enable_custom_issuer(self, totp):
        result = totp.enable("user_1", issuer="MyApp")
        assert "MyApp" in result["provisioning_uri"]


class TestRecoveryCodes:
    def test_generate_recovery_codes_count(self):
        codes = generate_recovery_codes()
        assert len(codes) == 8

    def test_recovery_code_format(self):
        codes = generate_recovery_codes()
        for c in codes:
            assert len(c) == 9  # XXXX-XXXX
            assert c[4] == "-"

    def test_hash_verify(self):
        code = "ABCD-1234"
        h = _hash_recovery_code(code)
        assert isinstance(h, str)
        assert len(h) == 64  # sha256 hex
        # Verify with same hash
        from intelgraph.core.auth.totp import _verify_recovery_code

        assert _verify_recovery_code(code, h) is True
        assert _verify_recovery_code("wrong", h) is False


# =======================================================================
# OAuth2 Client Credentials Tests
# =======================================================================


class TestOAuth2:
    def test_register_and_authenticate(self):
        from intelgraph.api.auth import authenticate_oauth_client, register_oauth_client

        result = register_oauth_client("client_test", "super_secret_key_123!", tenant_id="tenant_1")
        assert result["client_id"] == "client_test"
        assert result["tenant_id"] == "tenant_1"

        token_resp = authenticate_oauth_client("client_test", "super_secret_key_123!")
        assert token_resp is not None
        assert "access_token" in token_resp
        assert "refresh_token" in token_resp
        assert token_resp["token_type"] == "bearer"
        assert token_resp["expires_in"] == 900
        assert "read" in token_resp["scope"]

    def test_authenticate_wrong_secret(self):
        from intelgraph.api.auth import authenticate_oauth_client, register_oauth_client

        register_oauth_client("client_test2", "correct_secret_12345!")
        assert authenticate_oauth_client("client_test2", "wrong_secret") is None

    def test_authenticate_nonexistent_client(self):
        from intelgraph.api.auth import authenticate_oauth_client

        assert authenticate_oauth_client("nonexistent", "secret") is None

    def test_refresh_token(self):
        from intelgraph.api.auth import (
            authenticate_oauth_client,
            refresh_oauth_token,
            register_oauth_client,
        )

        register_oauth_client("client_refresh", "my_secret_key_12345!")
        resp = authenticate_oauth_client("client_refresh", "my_secret_key_12345!")
        assert resp is not None
        refresh_resp = refresh_oauth_token(resp["refresh_token"])
        assert refresh_resp is not None
        assert "access_token" in refresh_resp

    def test_refresh_invalid_token(self):
        from intelgraph.api.auth import refresh_oauth_token

        assert refresh_oauth_token("invalid.jwt.token") is None

    def test_token_contains_scope(self):
        from intelgraph.api.auth import authenticate_oauth_client, register_oauth_client

        register_oauth_client("client_scope", "secret_key_12345!!!", scopes=["read", "write"])
        resp = authenticate_oauth_client("client_scope", "secret_key_12345!!!")
        assert resp is not None
        assert "read" in resp["scope"]
        assert "write" in resp["scope"]


# =======================================================================
# 2FA Login Flow Tests
# =======================================================================


class Test2FALoginFlow:
    def test_login_without_2fa_returns_token(self):
        from intelgraph.api.auth import login_with_2fa_step1, register_user

        register_user("flow_user", "pass123")
        result = login_with_2fa_step1("flow_user", "pass123")
        assert result is not None
        assert "access_token" in result

    def test_login_with_wrong_password(self):
        from intelgraph.api.auth import login_with_2fa_step1, register_user

        register_user("flow_user2", "pass123")
        assert login_with_2fa_step1("flow_user2", "wrong") is None

    def test_login_with_2fa_requires_temp_token(self):
        from intelgraph.api.auth import get_totp_manager, login_with_2fa_step1, register_user

        register_user("2fa_user", "pass123")
        # Enable 2FA
        totp = get_totp_manager()
        # Find the user's uid
        from intelgraph.api.auth import _token_store

        uid = None
        for uid_key, data in _token_store.items():
            if data["username"] == "2fa_user":
                uid = uid_key
                break
        assert uid is not None
        totp.enable(uid)
        # Login should return 2fa_required
        result = login_with_2fa_step1("2fa_user", "pass123")
        assert result is not None
        assert result["status"] == "2fa_required"
        assert "temp_token" in result

    def test_verify_2fa_code_completes_login(self):
        from intelgraph.api.auth import (
            _token_store,
            get_totp_manager,
            login_with_2fa_step1,
            register_user,
            verify_2fa_code,
        )

        register_user("2fa_user2", "pass123")
        totp = get_totp_manager()
        uid = None
        for uid_key, data in _token_store.items():
            if data["username"] == "2fa_user2":
                uid = uid_key
                break
        assert uid is not None
        enable_result = totp.enable(uid)
        secret = enable_result["secret"]
        # Get step1 result
        step1 = login_with_2fa_step1("2fa_user2", "pass123")
        assert step1["status"] == "2fa_required"
        # Generate TOTP code
        hotp = pyotp.TOTP(secret)
        code = hotp.now()
        # Verify
        result = verify_2fa_code(step1["temp_token"], code)
        assert result is not None
        assert "access_token" in result

    def test_verify_2fa_wrong_code(self):
        from intelgraph.api.auth import (
            _token_store,
            get_totp_manager,
            login_with_2fa_step1,
            register_user,
            verify_2fa_code,
        )

        register_user("2fa_user3", "pass123")
        totp = get_totp_manager()
        uid = None
        for uid_key, data in _token_store.items():
            if data["username"] == "2fa_user3":
                uid = uid_key
                break
        assert uid is not None
        totp.enable(uid)
        step1 = login_with_2fa_step1("2fa_user3", "pass123")
        assert step1["status"] == "2fa_required"
        result = verify_2fa_code(step1["temp_token"], "000000")
        assert result is None

    def test_verify_2fa_invalid_temp_token(self):
        from intelgraph.api.auth import verify_2fa_code

        assert verify_2fa_code("invalid.jwt.token", "123456") is None


# =======================================================================
# API Key Rotation + Grace Period Tests
# =======================================================================


class TestAPIKeyRotationGracePeriod:
    @pytest.fixture
    def tenant_mgr(self, tmp_path):
        db_path = tmp_path / "test_grace.db"
        mgr = TenantManager(db_path=str(db_path))
        tenant, api_key = mgr.create_tenant("Grace Tenant")
        mgr._test_tenant_id = tenant.tenant_id
        mgr._test_api_key = api_key
        return mgr

    def test_rotate_generates_new_key(self, tenant_mgr):
        tid = tenant_mgr._test_tenant_id
        old_key = tenant_mgr._test_api_key
        result, new_key = tenant_mgr.rotate_api_key(tid)
        assert result == tid
        assert new_key != old_key
        assert tenant_mgr.verify_api_key(new_key) is not None

    def test_grace_period_accepts_old_key(self, tenant_mgr):
        tid = tenant_mgr._test_tenant_id
        old_key = tenant_mgr._test_api_key
        tenant_mgr.rotate_api_key(tid)
        tenant = tenant_mgr.verify_api_key(old_key)
        assert tenant is not None
        assert tenant.tenant_id == tid

    def test_new_key_also_works_during_grace(self, tenant_mgr):
        tid = tenant_mgr._test_tenant_id
        old_key = tenant_mgr._test_api_key
        _, new_key = tenant_mgr.rotate_api_key(tid)
        assert tenant_mgr.verify_api_key(new_key) is not None
        assert tenant_mgr.verify_api_key(old_key) is not None

    def test_rotation_history_recorded(self, tenant_mgr):
        tid = tenant_mgr._test_tenant_id
        tenant_mgr.rotate_api_key(tid, rotated_by="admin")
        tenant = tenant_mgr.get(tid)
        assert len(tenant.rotation_history) == 1
        assert tenant.rotation_history[0]["rotated_by"] == "admin"

    def test_previous_key_hash_set_after_rotation(self, tenant_mgr):
        tid = tenant_mgr._test_tenant_id
        tenant_mgr.rotate_api_key(tid)
        tenant = tenant_mgr.get(tid)
        assert tenant.previous_key_hash != ""

    def test_key_rotated_at_set(self, tenant_mgr):
        tid = tenant_mgr._test_tenant_id
        tenant_mgr.rotate_api_key(tid)
        tenant = tenant_mgr.get(tid)
        assert tenant.key_rotated_at != ""

    def test_to_dict_includes_rotation_data(self, tenant_mgr):
        tid = tenant_mgr._test_tenant_id
        tenant_mgr.rotate_api_key(tid)
        tenant = tenant_mgr.get(tid)
        d = tenant.to_dict()
        assert "key_rotated_at" in d
        assert "rotation_count" in d
        assert d["rotation_count"] == 1

    def test_verify_unknown_key(self, tenant_mgr):
        assert tenant_mgr.verify_api_key("igt_unknown_key_1234567890abcdef") is None


# =======================================================================
# Integration: TOTP + Auth API (via direct calls, not HTTP)
# =======================================================================


class TestAuthIntegration:
    def test_register_and_2fa_enable_then_login(self):
        from intelgraph.api.auth import (
            _token_store,
            get_totp_manager,
            login_with_2fa_step1,
            register_user,
            verify_2fa_code,
        )

        register_user("integration_user", "pass123")

        # Find uid
        uid = None
        for k, v in _token_store.items():
            if v["username"] == "integration_user":
                uid = k
                break
        assert uid

        # Enable 2FA
        totp = get_totp_manager()
        enable_result = totp.enable(uid)
        secret = enable_result["secret"]
        assert totp.is_enabled(uid)

        # Login flow
        step1 = login_with_2fa_step1("integration_user", "pass123")
        assert step1["status"] == "2fa_required"

        # Generate TOTP code
        hotp = pyotp.TOTP(secret)
        code = hotp.now()

        # Complete login
        result = verify_2fa_code(step1["temp_token"], code)
        assert result is not None
        assert "access_token" in result

    def test_register_and_2fa_enable_then_login_recovery(self):
        from intelgraph.api.auth import (
            _token_store,
            get_totp_manager,
            login_with_2fa_step1,
            register_user,
            verify_2fa_code,
        )

        register_user("integration_user2", "pass123")

        uid = None
        for k, v in _token_store.items():
            if v["username"] == "integration_user2":
                uid = k
                break
        assert uid

        totp = get_totp_manager()
        enable_result = totp.enable(uid)
        recovery_code = enable_result["recovery_codes"][0]

        step1 = login_with_2fa_step1("integration_user2", "pass123")
        assert step1["status"] == "2fa_required"

        # Use recovery code instead of TOTP code
        result = verify_2fa_code(step1["temp_token"], recovery_code)
        assert result is not None
        assert "access_token" in result

    def test_oauth_client_authenticated(self):
        import jwt

        from intelgraph.api.auth import authenticate_oauth_client, register_oauth_client

        register_oauth_client("oauth_integration", "my_oauth_secret_1234!", tenant_id="t1")
        resp = authenticate_oauth_client("oauth_integration", "my_oauth_secret_1234!")
        assert resp is not None
        # Decode the access token and verify claims
        from intelgraph.api.auth import _SECRET_KEY, TOKEN_ALGORITHM

        payload = jwt.decode(resp["access_token"], _SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
        assert payload["sub"] == "oauth_integration"
        assert payload.get("tenant_id") == "t1"
        assert "read" in payload.get("scope", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
