import pytest


@pytest.fixture(autouse=True)
def _isolated_env(clean_env: pytest.MonkeyPatch) -> None:
    """Unit tests never see the developer's ``BENCHLING_*`` variables."""
