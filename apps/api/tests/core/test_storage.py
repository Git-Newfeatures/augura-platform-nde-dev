"""Tests for artifact storage (core.storage): the local-disk backend (dev/test) and the
Supabase Storage backend (prod), selected from the presence of the Supabase settings."""

import pytest

from augura_api.core import storage
from augura_api.core.config import Settings


def _disk_settings(tmp_path: object) -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue] -- fields injected by the environment
        env="dev", artifacts_dir=str(tmp_path)
    )


def _supabase_settings() -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue] -- fields injected by the environment
        env="dev",
        supabase_url="https://proj.supabase.co",
        supabase_service_role_key="svc-secret",
        storage_bucket="datasets",
    )


# ─── settings ────────────────────────────────────────────────────────────────


def test_storage_settings_defaults() -> None:
    s = Settings(env="dev")  # pyright: ignore[reportCallIssue]
    assert s.supabase_url is None
    assert s.supabase_service_role_key is None
    assert s.storage_bucket == "datasets"


# ─── local-disk backend (dev/test) ─────────────────────────────────────────────


async def test_disk_roundtrip(tmp_path: object) -> None:
    settings = _disk_settings(tmp_path)
    ref = await storage.save_bytes(settings, org_id="org-1", name="f.csv", data=b"hello")
    assert await storage.read_bytes(settings, ref) == b"hello"
    assert await storage.exists(settings, ref) is True


async def test_disk_read_missing_raises(tmp_path: object) -> None:
    settings = _disk_settings(tmp_path)
    with pytest.raises(FileNotFoundError):
        await storage.read_bytes(settings, "org/x/missing.csv")


# ─── Supabase Storage backend (prod) ────────────────────────────────────────────


class _FakeResp:
    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content
        self.text = content.decode("utf-8", "replace")


def _install_fake_http(
    monkeypatch: pytest.MonkeyPatch, resp: _FakeResp
) -> list[tuple[str, str, bytes | None, dict[str, str]]]:
    """Replaces httpx.AsyncClient with a fake that records calls and returns `resp`.
    Returns the recorded calls as (method, url, body, headers)."""
    calls: list[tuple[str, str, bytes | None, dict[str, str]]] = []

    class _Client:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def post(
            self, url: str, *, content: bytes | None = None, headers: dict[str, str]
        ) -> _FakeResp:
            calls.append(("POST", url, content, headers))
            return resp

        async def get(self, url: str, *, headers: dict[str, str]) -> _FakeResp:
            calls.append(("GET", url, None, headers))
            return resp

    monkeypatch.setattr(storage.httpx, "AsyncClient", _Client)
    return calls


async def test_supabase_save_bytes_uploads_to_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _supabase_settings()
    calls = _install_fake_http(monkeypatch, _FakeResp(200))

    ref = await storage.save_bytes(settings, org_id="org-1", name="f.csv", data=b"payload")

    assert ref == "org/org-1/f.csv"
    assert len(calls) == 1
    method, url, body, headers = calls[0]
    assert method == "POST"
    assert url == "https://proj.supabase.co/storage/v1/object/datasets/org/org-1/f.csv"
    assert body == b"payload"
    assert headers["Authorization"] == "Bearer svc-secret"
    assert headers["apikey"] == "svc-secret"
    assert headers["x-upsert"] == "true"


async def test_supabase_save_bytes_raises_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _supabase_settings()
    _install_fake_http(monkeypatch, _FakeResp(500, b"boom"))
    with pytest.raises(OSError):
        await storage.save_bytes(settings, org_id="o", name="f", data=b"x")


async def test_supabase_read_bytes_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _supabase_settings()
    calls = _install_fake_http(monkeypatch, _FakeResp(200, b"the-bytes"))

    out = await storage.read_bytes(settings, "org/o/f.csv")

    assert out == b"the-bytes"
    method, url, _body, headers = calls[0]
    assert method == "GET"
    assert url == "https://proj.supabase.co/storage/v1/object/datasets/org/o/f.csv"
    assert headers["apikey"] == "svc-secret"


async def test_supabase_read_bytes_404_raises_filenotfound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _supabase_settings()
    _install_fake_http(monkeypatch, _FakeResp(404, b"not found"))
    with pytest.raises(FileNotFoundError):
        await storage.read_bytes(settings, "org/o/missing.csv")


async def test_read_bytes_rejects_foreign_org_prefix(tmp_path: object) -> None:
    settings = _disk_settings(tmp_path)
    ref = await storage.save_bytes(settings, org_id="org-1", name="f.csv", data=b"hi")
    # Correct org: allowed.
    assert await storage.read_bytes(settings, ref, expected_org="org-1") == b"hi"
    # Foreign org: refused before any backend access.
    with pytest.raises(FileNotFoundError):
        await storage.read_bytes(settings, ref, expected_org="org-2")
