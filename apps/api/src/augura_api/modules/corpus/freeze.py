"""Gel reproductible des artefacts de preuve : hash de contenu SHA-256.

Le hash est calculé sur une sérialisation CANONIQUE de la charge (clés triées,
UTF-8, sans espace insignifiant) : la même donnée produit toujours le même hash,
quelle que soit la machine. À l'écriture on calcule et on stocke `content_hash` ;
à la lecture on recalcule et on compare — une divergence = altération/corruption
= erreur dure (jamais de retour silencieux). L'artefact est ainsi auto-vérifiable
et portable (l'artefact DAG plus tard portera la même forme, sans dépendance base).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from augura_api.core.errors import AppError

CONTENT_HASH_FIELD = "content_hash"


class ContentIntegrityError(AppError):
    """Le content_hash recalculé ne correspond pas au stocké (altération/corruption)."""

    code = "content_integrity"
    http_status = 500
    title = "Content integrity check failed"


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Sérialisation canonique de la charge, hors champ `content_hash`.

    clés triées + UTF-8 + séparateurs compacts ⇒ représentation stable. L'ordre des
    listes (ex. la liste de résultats) EST significatif et préservé tel quel.
    """
    body = {k: v for k, v in payload.items() if k != CONTENT_HASH_FIELD}
    return json.dumps(
        body, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def content_hash(payload: dict[str, Any]) -> str:
    """SHA-256 (hex) de la charge canonicalisée."""
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def verify_content_hash(payload: dict[str, Any]) -> str:
    """Recalcule et compare au `content_hash` présent dans la charge.

    Renvoie le hash si tout concorde ; lève `ContentIntegrityError` si le champ est
    absent ou si la valeur diverge — erreur dure, pas de retour silencieux.
    """
    stored = payload.get(CONTENT_HASH_FIELD)
    if not isinstance(stored, str) or not stored:
        raise ContentIntegrityError("content_hash absent de l'artefact")
    recomputed = content_hash(payload)
    if stored != recomputed:
        raise ContentIntegrityError(
            "content_hash divergent — artefact altéré ou corrompu",
            stored=stored,
            recomputed=recomputed,
        )
    return recomputed
