import pytest

from involve_benchling import BenchlingConfig, ConfigError

BASE = "https://example.benchling.com"


def test_api_key_config():
    config = BenchlingConfig(base_url=BASE, api_key="sk_test")
    assert config.auth_method == "api_key"


def test_oauth_config():
    config = BenchlingConfig(base_url=BASE, oauth_client_id="id", oauth_client_secret="secret")
    assert config.auth_method == "oauth"


def test_missing_auth_rejected():
    with pytest.raises(ConfigError, match="api_key or oauth"):
        BenchlingConfig(base_url=BASE)


def test_both_auth_rejected():
    with pytest.raises(ConfigError, match="not both"):
        BenchlingConfig(base_url=BASE, api_key="k", oauth_client_id="id", oauth_client_secret="s")


def test_missing_base_url_rejected():
    with pytest.raises(ConfigError, match="base_url"):
        BenchlingConfig(base_url="", api_key="k")


def test_from_env(monkeypatch):
    monkeypatch.setenv("BENCHLING_BASE_URL", BASE)
    monkeypatch.setenv("BENCHLING_API_KEY", "sk_env")
    monkeypatch.setenv("BENCHLING_EARLY_ACCESS", "true")
    config = BenchlingConfig.from_env()
    assert config.api_key == "sk_env"
    assert config.early_access is True


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("BENCHLING_BASE_URL", BASE)
    monkeypatch.setenv("BENCHLING_API_KEY", "sk_env")
    config = BenchlingConfig.from_env(api_key="sk_override")
    assert config.api_key == "sk_override"


def test_with_options():
    config = BenchlingConfig(base_url=BASE, api_key="k")
    derived = config.with_options(early_access=True)
    assert derived.early_access is True
    assert config.early_access is False  # original untouched
