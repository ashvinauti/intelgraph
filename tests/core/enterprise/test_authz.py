from intelgraph.core.enterprise.authz import Role, has_permission, user_role


class TestRole:
    def test_role_values(self):
        assert Role.USER.value == "user"
        assert Role.ANALYST.value == "analyst"
        assert Role.REVIEWER.value == "reviewer"
        assert Role.ADMIN.value == "admin"


class TestHasPermission:
    def test_admin_has_all(self):
        assert has_permission(Role.ADMIN, "entity:read")
        assert has_permission(Role.ADMIN, "entity:create")
        assert has_permission(Role.ADMIN, "entity:update")
        assert has_permission(Role.ADMIN, "entity:delete")
        assert has_permission(Role.ADMIN, "admin:access")

    def test_analyst_can_create_entity(self):
        assert has_permission(Role.ANALYST, "entity:create")

    def test_analyst_cannot_delete(self):
        assert not has_permission(Role.ANALYST, "entity:delete")

    def test_user_cannot_create_entity(self):
        assert not has_permission(Role.USER, "entity:create")

    def test_user_cannot_delete(self):
        assert not has_permission(Role.USER, "entity:delete")

    def test_reviewer_can_update_verification(self):
        assert has_permission(Role.REVIEWER, "verification:update")

    def test_analyst_cannot_update_verification(self):
        assert not has_permission(Role.ANALYST, "verification:update")

    def test_admin_only_access(self):
        assert has_permission(Role.ADMIN, "admin:access")
        assert not has_permission(Role.USER, "admin:access")
        assert not has_permission(Role.ANALYST, "admin:access")
        assert not has_permission(Role.REVIEWER, "admin:access")

    def test_string_role(self):
        assert has_permission("admin", "entity:delete")
        assert not has_permission("user", "entity:delete")
        assert not has_permission("invalid_role", "entity:read")

    def test_unknown_permission(self):
        assert not has_permission(Role.ADMIN, "nonexistent:perm")


class TestUserRole:
    def test_none_user(self):
        assert user_role(None) == Role.USER

    def test_from_data(self):
        assert user_role({"role": "admin"}) == Role.ADMIN
        assert user_role({"role": "analyst"}) == Role.ANALYST
        assert user_role({"role": "reviewer"}) == Role.REVIEWER
        assert user_role({"role": "user"}) == Role.USER

    def test_default_when_missing(self):
        assert user_role({}) == Role.USER
