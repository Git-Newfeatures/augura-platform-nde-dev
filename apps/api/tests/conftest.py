from collections.abc import Iterator

import pytest

from augura_api.core.config import get_settings


@pytest.fixture(autouse=True)
def _base_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Chaque test démarre avec un environnement dev propre et un cache settings vide."""
    monkeypatch.setenv("AUGURA_ENV", "dev")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
