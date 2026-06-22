"""Stockage des octets d'artefacts (datasets uploadés, exports).

Deux backends derrière une interface async minimale (`save_bytes`/`read_bytes`/`exists`),
choisis selon les settings :

- **Supabase Storage** (prod) quand `supabase_url` ET `supabase_service_role_key` sont
  définis : objets dans un bucket privé via l'API REST Storage. Cohérent cross-conteneur,
  contrairement au disque local éphémère et par-conteneur de Modal.
- **Disque local** (dev/test/CI sans secret) sous `settings.artifacts_dir`.

`storage_path` est TOUJOURS un chemin relatif déterministe (portable, jamais une URL absolue
de machine) : sous le backend disque il est résolu depuis `artifacts_dir` ; côté Supabase
c'est la clé de l'objet dans le bucket. Le même ref fonctionne pour les deux backends.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from augura_api.core.config import Settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_TIMEOUT = httpx.Timeout(30.0)


def _safe(component: str) -> str:
    """Neutralise un composant de chemin (anti path-traversal)."""
    cleaned = _SAFE.sub("_", component.strip()) or "_"
    return cleaned[:128]


def _root(settings: Settings) -> Path:
    return Path(settings.artifacts_dir)


def build_ref(org_id: str, name: str) -> str:
    """Construit un storage_path relatif déterministe (org/<org>/<name>)."""
    return f"org/{_safe(org_id)}/{_safe(name)}"


# ─── sélection du backend ──────────────────────────────────────────────────────


def _use_supabase(settings: Settings) -> bool:
    return bool(settings.supabase_url and settings.supabase_service_role_key)


# ─── backend Supabase Storage (prod) ────────────────────────────────────────────


def _object_url(settings: Settings, ref: str) -> str:
    base = (settings.supabase_url or "").rstrip("/")
    return f"{base}/storage/v1/object/{settings.storage_bucket}/{ref}"


def _auth_headers(settings: Settings) -> dict[str, str]:
    # La clé service_role sert à la fois d'`apikey` (passerelle Kong) et de bearer.
    key = settings.supabase_service_role_key or ""
    return {"Authorization": f"Bearer {key}", "apikey": key}


async def _supabase_put(settings: Settings, ref: str, data: bytes) -> None:
    headers = {
        **_auth_headers(settings),
        "x-upsert": "true",  # ré-upload du même ref ⇒ remplace au lieu d'un 409
        "Content-Type": "application/octet-stream",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_object_url(settings, ref), content=data, headers=headers)
    if resp.status_code // 100 != 2:
        raise OSError(f"upload Supabase Storage échoué ({resp.status_code}): {resp.text}")


async def _supabase_get(settings: Settings, ref: str) -> bytes:
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(_object_url(settings, ref), headers=_auth_headers(settings))
    if resp.status_code == 404:
        raise FileNotFoundError(f"objet Storage introuvable : {ref}")
    if resp.status_code // 100 != 2:
        raise OSError(f"download Supabase Storage échoué ({resp.status_code}): {resp.text}")
    return resp.content


# ─── interface publique (async, agnostique du backend) ──────────────────────────


async def save_bytes(settings: Settings, *, org_id: str, name: str, data: bytes) -> str:
    """Écrit `data` et renvoie le storage_path relatif (à stocker en base)."""
    ref = build_ref(org_id, name)
    if _use_supabase(settings):
        await _supabase_put(settings, ref, data)
    else:
        dest = _root(settings) / ref
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return ref


async def read_bytes(settings: Settings, storage_path: str) -> bytes:
    """Lit un artefact à partir de son storage_path relatif. Lève FileNotFoundError si absent.
    Sur le backend disque, refuse toute échappée hors du répertoire d'artefacts."""
    if _use_supabase(settings):
        return await _supabase_get(settings, storage_path)
    root = _root(settings).resolve()
    target = (root / storage_path).resolve()
    if not str(target).startswith(str(root)):
        raise FileNotFoundError("chemin d'artefact hors du répertoire autorisé")
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
