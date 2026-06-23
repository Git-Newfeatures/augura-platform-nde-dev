"""Canonical hashing of artifacts (reproducibility backbone, spec §1-2).

Reproducibility comes from *versioned + hashed* artifacts, never from a stochastic
re-run. The hash is deterministic and engine-independent (LLM/language):
same content → same SHA-256, forever. `core` module (pure, no I/O) ⇒ importable
everywhere and testable without a database.
"""

import hashlib
import json
from typing import Any


def canonical_json(content: Any) -> str:
    """Canonical serialization: sorted keys, compact separators, UTF-8 preserved.
    Two semantically equal contents produce the same string (hence the same hash)."""
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(content: Any) -> str:
    """SHA-256 of the canonicalized content — the fingerprint of an artifact."""
    return sha256_hex(canonical_json(content))
