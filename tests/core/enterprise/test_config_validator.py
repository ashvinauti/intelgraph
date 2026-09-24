import pytest

from intelgraph.core.enterprise.config_validator import (
    ConfigValidationError,
    _deep_get,
    _deep_set,
    load_env_overrides,
    validate_config,
)


class TestValidateConfig:
    def test_valid_config(self):
        cfg = {
            "storage": {"backend": "sqlite"},
            "logging": {"level": "INFO"},
            "distributed": {"enabled": False},
            "api": {"read_auth_required": False},
        }
        validate_config(cfg)

    def test_missing_required(self):
        with pytest.raises(ConfigValidationError, match="Missing required"):
            validate_config({})

    def test_wrong_type(self):
        cfg = {"storage": {"backend": 123}, "logging": {"level": "INFO"}}
        with pytest.raises(ConfigValidationError, match="expected str"):
            validate_config(cfg)


class TestDeepGet:
    def test_nested_key(self):
        d = {"a": {"b": {"c": 1}}}
        assert _deep_get(d, "a.b.c") == 1

    def test_missing_key(self):
        assert _deep_get({"a": 1}, "a.b") is None

    def test_top_level(self):
        assert _deep_get({"x": 42}, "x") == 42


class TestDeepSet:
    def test_set_nested(self):
        d = {}
        _deep_set(d, "a.b.c", 1)
        assert d == {"a": {"b": {"c": 1}}}

    def test_overwrite(self):
        d = {"a": {"b": 1}}
        _deep_set(d, "a.b", 2)
        assert d["a"]["b"] == 2


class TestLoadEnvOverrides:
    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("INTELGRAPH_LOG_LEVEL", "DEBUG")
        result = load_env_overrides()
        assert result.get("logging", {}).get("level") == "DEBUG"

    def test_no_env_set(self, monkeypatch):
        monkeypatch.delenv("INTELGRAPH_LOG_LEVEL", raising=False)
        result = load_env_overrides()
        assert result == {}
