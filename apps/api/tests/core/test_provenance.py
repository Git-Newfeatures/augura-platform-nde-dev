"""Canonical hashing of artifacts: deterministic and key-order independent."""

from augura_api.core.provenance import canonical_json, content_hash, sha256_hex


def test_hash_is_deterministic() -> None:
    content = {"edges": [{"from": "x", "to": "y"}], "version": 1}
    assert content_hash(content) == content_hash(content)


def test_hash_is_key_order_invariant() -> None:
    # Same semantic content, different key order → same hash.
    a = {"from": "x", "to": "y", "rationale": "r"}
    b = {"to": "y", "rationale": "r", "from": "x"}
    assert content_hash(a) == content_hash(b)


def test_hash_changes_with_content() -> None:
    assert content_hash({"v": 1}) != content_hash({"v": 2})


def test_canonical_json_sorts_keys_compactly() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_sha256_hex_is_64_hex_chars() -> None:
    h = sha256_hex("augura")
    assert len(h) == 64 and all(c in "0123456789abcdef" for c in h)
