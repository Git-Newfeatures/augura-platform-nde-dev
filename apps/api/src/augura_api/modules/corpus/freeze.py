"""Reproducible freeze of evidence artifacts: SHA-256 content hash.

The hash is computed over a CANONICAL serialization of the payload (sorted keys,
UTF-8, no insignificant whitespace): the same data always produces the same hash,
regardless of the machine. On write we compute and store `content_hash`;
on read we recompute and compare — a divergence = tampering/corruption
= hard error (never a silent return). The artifact is thus self-verifiable
and portable (the DAG artifact will later carry the same shape, with no DB dependency).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from augura_api.core.errors import AppError

CONTENT_HASH_FIELD = "content_hash"


class ContentIntegrityError(AppError):
    """The recomputed content_hash does not match the stored one (tampering/corruption)."""

    code = "content_integrity"
    http_status = 500
    title = "Content integrity check failed"


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Canonical serialization of the payload, excluding the `content_hash` field.

    sorted keys + UTF-8 + compact separators ⇒ stable representation. The order of
    lists (e.g. the results list) IS significant and preserved as-is.
    """
    body = {k: v for k, v in payload.items() if k != CONTENT_HASH_FIELD}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def content_hash(payload: dict[str, Any]) -> str:
    """SHA-256 (hex) of the canonicalized payload."""
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def verify_content_hash(payload: dict[str, Any]) -> str:
    """Recompute and compare against the `content_hash` present in the payload.

    Returns the hash if everything matches; raises `ContentIntegrityError` if the
    field is absent or the value diverges — hard error, no silent return.
    """
    stored = payload.get(CONTENT_HASH_FIELD)
    if not isinstance(stored, str) or not stored:
        raise ContentIntegrityError("content_hash missing from artifact")
    recomputed = content_hash(payload)
    if stored != recomputed:
        raise ContentIntegrityError(
            "content_hash divergent — artifact tampered with or corrupted",
            stored=stored,
            recomputed=recomputed,
        )
    return recomputed
