from intelgraph.core.enterprise.deployment import get_profile_config, list_profiles


class TestDeploymentProfiles:
    def test_list_profiles(self):
        profiles = list_profiles()
        assert "development" in profiles
        assert "staging" in profiles
        assert "production" in profiles

    def test_development_profile(self):
        cfg = get_profile_config("development")
        assert cfg["logging"]["level"] == "DEBUG"
        assert cfg["cors"]["origins"] == ["*"]
        assert cfg["rate_limit"]["max_requests"] == 1000

    def test_staging_profile(self):
        cfg = get_profile_config("staging")
        assert cfg["logging"]["level"] == "INFO"
        assert cfg["rate_limit"]["max_requests"] == 200

    def test_production_profile(self):
        cfg = get_profile_config("production")
        assert cfg["logging"]["level"] == "WARNING"
        assert cfg["rate_limit"]["max_requests"] == 100
        assert cfg["security"]["hsts"] is True

    def test_unknown_profile_falls_back_to_development(self):
        cfg = get_profile_config("nonexistent")
        assert cfg["logging"]["level"] == "DEBUG"
