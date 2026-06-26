"""Tests for Sentry SDK initialisation in create_app.

Rules verified:
- DSN present  → sentry_sdk.init called exactly once, send_default_pii=False
- DSN absent   → sentry_sdk.init never called
- DSN blank    → validator collapses "" to None → sentry_sdk.init never called
- /healthz responds 200 in all three cases
"""

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

import augura_api.main as main_module
from augura_api.core.config import Settings
from augura_api.main import create_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dev_settings(**extra: Any) -> Settings:
    """Build a dev Settings; forward any extra keyword overrides."""
    return Settings(env="dev", **extra)  # type: ignore[arg-type]


async def _healthz_ok(app: Any) -> None:
    """Assert that /healthz returns HTTP 200."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/healthz")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_sentry_init_called_with_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_app with a non-None DSN calls sentry_sdk.init exactly once."""
    mock_init: MagicMock = MagicMock()
    monkeypatch.setattr(main_module.sentry_sdk, "init", mock_init)

    dsn = "https://x@sentry.example.io/1"
    create_app(_dev_settings(sentry_dsn=dsn))

    mock_init.assert_called_once()
    call_kwargs = mock_init.call_args.kwargs
    assert call_kwargs["dsn"] == dsn
    assert call_kwargs["send_default_pii"] is False


async def test_sentry_no_init_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """create_app with no DSN (default) must not call sentry_sdk.init."""
    mock_init: MagicMock = MagicMock()
    monkeypatch.setattr(main_module.sentry_sdk, "init", mock_init)

    create_app(_dev_settings())

    mock_init.assert_not_called()


async def test_sentry_no_init_with_blank_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank DSN collapses to None via the validator — init must not be called."""
    mock_init: MagicMock = MagicMock()
    monkeypatch.setattr(main_module.sentry_sdk, "init", mock_init)

    # The validator strips "" → None; sentry_dsn on the resulting Settings is None.
    settings = _dev_settings(sentry_dsn="")
    assert settings.sentry_dsn is None  # validator did its job

    create_app(settings)

    mock_init.assert_not_called()


async def test_healthz_ok_with_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """/healthz is reachable when Sentry is initialised."""
    monkeypatch.setattr(main_module.sentry_sdk, "init", MagicMock())
    app = create_app(_dev_settings(sentry_dsn="https://x@sentry.example.io/1"))
    await _healthz_ok(app)


async def test_healthz_ok_without_dsn() -> None:
    """/healthz is reachable when Sentry is not initialised."""
    app = create_app(_dev_settings())
    await _healthz_ok(app)


async def test_healthz_ok_with_blank_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """/healthz is reachable when DSN is blank (→ no Sentry init)."""
    mock_init: MagicMock = MagicMock()
    monkeypatch.setattr(main_module.sentry_sdk, "init", mock_init)
    app = create_app(_dev_settings(sentry_dsn=""))
    await _healthz_ok(app)
    mock_init.assert_not_called()


def test_blank_dsn_validator_normalises_to_none() -> None:
    """Unit-test the validator in isolation: empty/whitespace → None."""
    assert _dev_settings(sentry_dsn="").sentry_dsn is None
    assert _dev_settings(sentry_dsn="   ").sentry_dsn is None
    assert _dev_settings(sentry_dsn=None).sentry_dsn is None


def test_valid_dsn_is_preserved() -> None:
    """A non-blank DSN must pass through the validator unchanged."""
    dsn = "https://abc@o123.ingest.sentry.io/456"
    assert _dev_settings(sentry_dsn=dsn).sentry_dsn == dsn
