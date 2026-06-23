"""Storage for artifact bytes (uploaded datasets, exports).

Two backends behind a minimal async interface (`save_bytes`/`read_bytes`/`exists`),
chosen based on the settings:

- **Supabase Storage** (prod) when `supabase_url` AND `supabase_service_role_key` are
  set: objects in a private bucket via the Storage REST API. Consistent cross-container,
  unlike Modal's ephemeral, per-container local disk.
- **Local disk** (dev/test/CI with no secret) under `settings.artifacts_dir`.

`storage_path` is ALWAYS a deterministic relative path (portable, never an absolute machine
URL): under the disk backend it is resolved from `artifacts_dir`; on the Supabase side
it is the object's key in the bucket. The same ref works for both backends.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from augura_api.core.config import Settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_TIMEOUT = httpx.Timeout(30.0)


def _safe(component: str) -> str:
    """Neutralizes a path component (path-traversal guard)."""
    cleaned = _SAFE.sub("_", component.strip()) or "_"
    return cleaned[:128]


def _root(settings: Settings) -> Path:
    return Path(settings.artifacts_dir)


def build_ref(org_id: str, name: str) -> str:
    """Builds a deterministic relative storage_path (org/<org>/<name>)."""
    return f"org/{_safe(org_id)}/{_safe(name)}"


# ─── backend selection ──────────────────────────────────────────────────────────


def _use_supabase(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


# ─── backend Supabase Storage (prod) ────────────────────────────────────────────


def _object_url(settings: Settings, ref: str) -> str:
    base = (settings.supabase_url or "").rstrip("/")
    return f"{base}/storage/v1/object/{settings.storage_bucket}/{ref}"


def _auth_headers(settings: Settings) -> dict[str, str]:
    # The service_role key serves as both the `apikey` (Kong gateway) and the bearer.
    key = settings.supabase_service_role_key or ""
    return {"Authorization": f"Bearer {key}", "apikey": key}


async def _supabase_put(settings: Settings, ref: str, data: bytes) -> None:
    headers = {
        **_auth_headers(settings),
        "x-upsert": "true",  # re-uploading the same ref ⇒ replaces instead of a 409
        "Content-Type": "application/octet-stream",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_object_url(settings, ref), content=data, headers=headers)
    if resp.status_code // 100 != 2:
        raise OSError(f"Supabase Storage upload failed ({resp.status_code}): {resp.text}")


async def _supabase_get(settings: Settings, ref: str) -> bytes:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(_object_url(settings, ref), headers=_auth_headers(settings))
    if resp.status_code == 404:
        raise FileNotFoundError(f"Storage object not found: {ref}")
    if resp.status_code // 100 != 2:
        raise OSError(f"Supabase Storage download failed ({resp.status_code}): {resp.text}")
    return resp.content


# ─── public interface (async, backend-agnostic) ─────────────────────────────────


async def save_bytes(settings: Settings, *, org_id: str, name: str, data: bytes) -> str:
    """Writes `data` and returns the relative storage_path (to be stored in the DB)."""
    ref = build_ref(org_id, name)
    if _use_supabase(settings):
        await _supabase_put(settings, ref, data)
    else:
        dest = _root(settings) / ref
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return ref


async def read_bytes(settings: Settings, storage_path: str) -> bytes:
    """Reads an artifact from its relative storage_path. Raises FileNotFoundError if absent.
    On the disk backend, rejects any escape outside the artifacts directory."""
    if _use_supabase(settings):
        return await _supabase_get(settings, storage_path)
    root = _root(settings).resolve()
    target = (root / storage_path).resolve()
    if not str(target).startswith(str(root)):
        raise FileNotFoundError("artifact path outside the allowed directory")
    return target.read_bytes()


async def exists(settings: Settings, storage_path: str) -> bool:
    if _use_supabase(settings):
        try:
            await _supabase_get(settings, storage_path)
        except FileNotFoundError:
            return False
        return True
    root = _root(settings).resolve()
    target = (root / storage_path).resolve()
    return str(target).startswith(str(root)) and target.is_file()
