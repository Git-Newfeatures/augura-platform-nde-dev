import time
from typing import Any
from uuid import uuid4

import jwt
import jwt.algorithms
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from augura_api.core.auth import Principal, authenticate, verify_token
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


# ── HS256 (secret partagé) ────────────────────────────────────────────────


def _hs_settings() -> Settings:
    return Settings(  # pyright: ignore[reportCallIssue] -- champs env
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


# ── RS256 via JWKS (mode Supabase asymétrique) ────────────────────────────


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

    settings = Settings(  # pyright: ignore[reportCallIssue] -- champs env
        env="dev", supabase_jwks_url="https://example.test/jwks"
    )
    principal = await authenticate(token, settings, jwks_fetcher=fetcher)
    assert str(principal.user_id) == claims["sub"]
