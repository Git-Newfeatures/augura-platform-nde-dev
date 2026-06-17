"""Tier 2 — hash de contenu reproductible (gates 5 & 6).

Pur, sans base : mêmes données → même hash (indépendant de l'ordre des clés) ;
toute altération d'un octet stocké lève une erreur dure à la vérification.
"""

import pytest

from augura_api.modules.corpus.freeze import (
    ContentIntegrityError,
    canonical_bytes,
    content_hash,
    verify_content_hash,
)


def _artifact() -> dict[str, object]:
    return {
        "model_version": "claude-sonnet-4",
        "prompt_version": "v1",
        "sources": ["pubmed", "ctgov"],
        "query": "engagement and hba1c",
        "results": [
            {
                "source": "pubmed",
                "id": "35319473",
                "title": "Paper",
                "query_string": "engagement and hba1c",
                "retrieval_date": "2026-06-16",
                "record": {"pmid": "35319473", "doi": "10.1/x"},
                "annotation": None,
            }
        ],
    }


def test_same_content_same_hash_regardless_of_key_order() -> None:
    a = {"b": 1, "a": 2, "nested": {"y": 1, "x": 2}}
    b = {"a": 2, "nested": {"x": 2, "y": 1}, "b": 1}
    assert content_hash(a) == content_hash(b)


def test_list_order_is_significant() -> None:
    a = {"results": [{"id": "1"}, {"id": "2"}]}
    b = {"results": [{"id": "2"}, {"id": "1"}]}
    assert content_hash(a) != content_hash(b)


def test_content_hash_field_is_excluded_from_hash() -> None:
    art = _artifact()
    h = content_hash(art)
    art_with_hash = {**art, "content_hash": h}
    # Ajouter le champ content_hash ne change pas le hash calculé.
    assert content_hash(art_with_hash) == h


def test_unicode_is_preserved_and_stable() -> None:
    art = {"title": "café — naïve coördination"}
    assert "café".encode() in canonical_bytes(art)
    assert content_hash(art) == content_hash(dict(art))


def test_verify_ok_returns_hash() -> None:
    art = _artifact()
    art["content_hash"] = content_hash(art)
    assert verify_content_hash(art) == art["content_hash"]


def test_verify_missing_hash_raises() -> None:
    with pytest.raises(ContentIntegrityError):
        verify_content_hash(_artifact())


def test_verify_tamper_one_byte_raises() -> None:
    art = _artifact()
    art["content_hash"] = content_hash(art)
    # Altère un octet de la charge après coup → divergence à la relecture.
    results = art["results"]
    assert isinstance(results, list)
    results[0]["title"] = "Paperr"
    with pytest.raises(ContentIntegrityError):
        verify_content_hash(art)
