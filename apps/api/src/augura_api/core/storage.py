"""Stockage des artefacts générés (dossiers, exports).

Backend local sur disque en dev (sous `settings.artifacts_dir`), derrière une interface
minimale (`save_bytes`/`read_bytes`) qu'un bucket Supabase Storage ou un volume Modal
remplacera en prod sans toucher aux appelants. `storage_path` est TOUJOURS un chemin
relatif au répertoire d'artefacts (portable, jamais une URL absolue de machine).
"""

from __future__ import annotations

import re
from pathlib import Path

from augura_api.core.config import Settings

_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(component: str) -> str:
    """Neutralise un composant de chemin (anti path-traversal)."""
    cleaned = _SAFE.sub("_", component.strip()) or "_"
    return cleaned[:128]


def _root(settings: Settings) -> Path:
    return Path(settings.artifacts_dir)


def build_ref(org_id: str, name: str) -> str:
    """Construit un storage_path relatif déterministe (org/<org>/<name>)."""
    return f"org/{_safe(org_id)}/{_safe(name)}"


def save_bytes(settings: Settings, *, org_id: str, name: str, data: bytes) -> str:
    """Écrit `data` et renvoie le storage_path relatif (à stocker en base)."""
    ref = build_ref(org_id, name)
    dest = _root(settings) / ref
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return ref


def read_bytes(settings: Settings, storage_path: str) -> bytes:
    """Lit un artefact à partir de son storage_path relatif. Lève FileNotFoundError
    si absent. Refuse toute échappée hors du répertoire d'artefacts."""
    root = _root(settings).resolve()
    target = (root / storage_path).resolve()
    if not str(target).startswith(str(root)):
        raise FileNotFoundError("chemin d'artefact hors du répertoire autorisé")
    return target.read_bytes()


def exists(settings: Settings, storage_path: str) -> bool:
    root = _root(settings).resolve()
    target = (root / storage_path).resolve()
    return str(target).startswith(str(root)) and target.is_file()
