"""Hachage canonique des artefacts (colonne vertébrale reproductibilité, spec §1-2).

La reproductibilité vient d'artefacts *versionnés + hashés*, jamais d'un re-run
stochastique. Le hash est déterministe et indépendant du moteur (LLM/langage) :
même contenu → même SHA-256, à jamais. Module `core` (pur, sans I/O) ⇒ importable
partout et testable sans base.
"""

import hashlib
import json
from typing import Any


def canonical_json(content: Any) -> str:
    """Sérialisation canonique : clés triées, séparateurs compacts, UTF-8 conservé.
    Deux contenus sémantiquement égaux produisent la même chaîne (donc le même hash)."""
    return json.dumps(
        content, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_hash(content: Any) -> str:
    """SHA-256 du contenu canonicalisé — l'empreinte d'un artefact."""
    return sha256_hex(canonical_json(content))
