import time
from typing import Any
from uuid import uuid4

import jwt
import jwt.algorithms
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from augura_api.core.auth import Principal, authenticate, clear_jwks_cache, verify_token
from augura_api.core.config import Settings
from augura_api.core.errors import UnauthorizedError


def _claims(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "sub": str(uuid4()),
        "email": "user@augura.dev",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    base.update(overrides)
    return base


# ── HS256 (shared secret) ─────────────────────────────────────────────────


def _hs_settings() -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue] -- env fields
        env="dev",
        supabase_jwt_secret="test-secret-please-ignore-0123456789abcdef",
        supabase_jwt_audience="authenticated",
    )


async def test_authenticate_hs256_happy_path() -> None:
    claims = _claims()
    token = jwt.encode(claims, "test-secret-please-ignore-0123456789abcdef", algorithm="HS256")
    principal = await authenticate(token, _hs_settings())
    assert isinstance(principal, Principal)
    assert str(principal.user_id) == claims["sub"]
    assert principal.email == "user@augura.dev"


async def test_expired_token_is_rejected() -> None:
    token = jwt.encode(
        _claims(exp=int(time.time()) - 10),
        "test-secret-please-ignore-0123456789abcdef",
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError):
        await authenticate(token, _hs_settings())


async def test_wrong_audience_is_rejected() -> None:
    token = jwt.encode(
        _claims(aud="someone-else"), "test-secret-please-ignore-0123456789abcdef", algorithm="HS256"
    )
    with pytest.raises(UnauthorizedError):
        await authenticate(token, _hs_settings())


def test_non_uuid_sub_is_rejected() -> None:
    token = jwt.encode(
        _claims(sub="not-a-uuid"), "test-secret-please-ignore-0123456789abcdef", algorithm="HS256"
    )
    with pytest.raises(UnauthorizedError):
        verify_token(
            token,
            key="test-secret-please-ignore-0123456789abcdef",
            algorithms=["HS256"],
            audience="authenticated",
        )


# ── RS256 via JWKS (asymmetric Supabase mode) ─────────────────────────────


async def test_authenticate_rs256_via_jwks() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    claims = _claims()
    token = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "k1"})

    jwk: dict[str, Any] = jwt.algorithms.RSAAlgorithm.to_jwk(  # type: ignore[no-untyped-call]
        private_key.public_key(), as_dict=True
    )
    jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})

    async def fetcher() -> dict[str, Any]:
        return {"keys": [jwk]}

    settings = Settings(  # pyright: ignore[reportCallIssue] -- env fields
        env="dev", supabase_jwks_url="https://example.test/jwks"
    )
    principal = await authenticate(token, settings, jwks_fetcher=fetcher)
    assert str(principal.user_id) == claims["sub"]


def _make_rsa_jwk(kid: str) -> tuple[Any, dict[str, Any]]:
    """Return (private_key, JWK-dict) for use in JWKS fetcher stubs."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk: dict[str, Any] = jwt.algorithms.RSAAlgorithm.to_jwk(  # type: ignore[no-untyped-call]
        private_key.public_key(), as_dict=True
    )
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private_key, jwk


async def test_jwks_missing_kid_rejected() -> None:
    """A token with no kid header in JWKS mode → UnauthorizedError (not silent first-key)."""
    private_key, jwk = _make_rsa_jwk("k1")
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    # Encode WITHOUT a kid header — PyJWT omits kid when not provided in headers
    token = jwt.encode(_claims(), private_pem, algorithm="RS256")

    async def fetcher() -> dict[str, Any]:
        return {"keys": [jwk]}

    settings = Settings(  # pyright: ignore[reportCallIssue] -- env fields
        env="dev", supabase_jwks_url="https://example.test/jwks"
    )
    clear_jwks_cache()
    with pytest.raises(UnauthorizedError):
        await authenticate(token, settings, jwks_fetcher=fetcher)


async def test_jwks_cached_within_ttl() -> None:
    """A second authenticate call within TTL reuses the cached JWKS (fetcher called once)."""
    private_key, jwk = _make_rsa_jwk("k2")
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    call_count = 0

    async def fetcher() -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {"keys": [jwk]}

    settings = Settings(  # pyright: ignore[reportCallIssue] -- env fields
        env="dev", supabase_jwks_url="https://example.test/jwks-cache"
    )
    clear_jwks_cache()
    token = jwt.encode(_claims(), private_pem, algorithm="RS256", headers={"kid": "k2"})
    await authenticate(token, settings, jwks_fetcher=fetcher)
    await authenticate(token, settings, jwks_fetcher=fetcher)
    assert call_count == 1, f"expected 1 fetch, got {call_count}"


async def test_jwks_unknown_kid_triggers_one_refetch() -> None:
    """Unknown kid triggers exactly one refetch before raising UnauthorizedError."""
    private_key, jwk_k1 = _make_rsa_jwk("k1")
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    # Token signed with k1 but the fetcher returns k9 (unknown kid)
    token = jwt.encode(_claims(), private_pem, algorithm="RS256", headers={"kid": "k9"})

    call_count = 0

    async def fetcher() -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return {"keys": [jwk_k1]}  # only k1, never k9

    settings = Settings(  # pyright: ignore[reportCallIssue] -- env fields
        env="dev", supabase_jwks_url="https://example.test/jwks-miss"
    )
    # Seed a stale cache entry so the first call is a cache hit, then one refetch
    clear_jwks_cache()
    with pytest.raises(UnauthorizedError):
        await authenticate(token, settings, jwks_fetcher=fetcher)
    # Must have fetched exactly twice: initial (miss→fetch) + one refetch on unknown kid
    assert call_count == 2, f"expected 2 fetches, got {call_count}"


# ── MFA / aal2 enforcement ────────────────────────────────────────────────


def _hs_settings_mfa(require_mfa: bool) -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue] -- env fields
        env="dev",
        supabase_jwt_secret="test-secret-please-ignore-0123456789abcdef",
        supabase_jwt_audience="authenticated",
        require_mfa=require_mfa,
    )


async def test_mfa_required_no_aal_claim_rejected() -> None:
    """require_mfa=True + token without aal claim → UnauthorizedError."""
    claims = _claims()  # no aal key
    token = jwt.encode(claims, "test-secret-please-ignore-0123456789abcdef", algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        await authenticate(token, _hs_settings_mfa(require_mfa=True))


async def test_mfa_required_aal1_rejected() -> None:
    """require_mfa=True + aal1 token → UnauthorizedError."""
    claims = _claims(aal="aal1")
    token = jwt.encode(claims, "test-secret-please-ignore-0123456789abcdef", algorithm="HS256")
    with pytest.raises(UnauthorizedError):
        await authenticate(token, _hs_settings_mfa(require_mfa=True))


async def test_mfa_required_aal2_accepted() -> None:
    """require_mfa=True + aal2 token → succeeds."""
    claims = _claims(aal="aal2")
    token = jwt.encode(claims, "test-secret-please-ignore-0123456789abcdef", algorithm="HS256")
    principal = await authenticate(token, _hs_settings_mfa(require_mfa=True))
    assert isinstance(principal, Principal)


async def test_mfa_disabled_aal_ignored() -> None:
    """require_mfa=False (default) → aal claim is ignored; no aal = OK."""
    claims = _claims()  # no aal key
    token = jwt.encode(claims, "test-secret-please-ignore-0123456789abcdef", algorithm="HS256")
    principal = await authenticate(token, _hs_settings_mfa(require_mfa=False))
    assert isinstance(principal, Principal)
