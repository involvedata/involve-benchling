import pytest

from involve_benchling import BenchlingConfig, ConfigError
from tests.fixtures.config import BASE_URL


def test_api_key_config(api_key_config):
    assert api_key_config.auth_method == "api_key"


def test_oauth_config(oauth_config):
    assert oauth_config.auth_method == "oauth"


def test_missing_auth_rejected():
    with pytest.raises(ConfigError, match="api_key or oauth"):
        BenchlingConfig(base_url=BASE_URL)


def test_both_auth_rejected():
    with pytest.raises(ConfigError, match="not both"):
        BenchlingConfig(
            base_url=BASE_URL, api_key="k", oauth_client_id="id", oauth_client_secret="s"
        )


def test_missing_base_url_rejected():
    with pytest.raises(ConfigError, match="base_url"):
        BenchlingConfig(base_url="", api_key="k")


def test_from_env(api_key_env, clean_env):
    clean_env.setenv("BENCHLING_EARLY_ACCESS", "true")
    config = BenchlingConfig.from_env()
    assert config.api_key == api_key_env["BENCHLING_API_KEY"]
    assert config.early_access is True


def test_from_env_without_variables_rejected():
    with pytest.raises(ConfigError, match="base_url"):
        BenchlingConfig.from_env()


def test_from_env_overrides(api_key_env):
    assert BenchlingConfig.from_env(api_key="sk_override").api_key == "sk_override"


def test_with_options(api_key_config):
    derived = api_key_config.with_options(early_access=True)
    assert derived.early_access is True
    assert api_key_config.early_access is False
