"""Vérification du JWT Supabase (spec §7).

Le front envoie le JWT en `Authorization: Bearer`. On vérifie signature, exp et
audience, puis on en extrait le `UserId`. Deux modes :
- asymétrique : JWKS Supabase (RS256/ES256), clés mises en cache par `kid` ;
- symétrique : secret partagé HS256 (projets Supabase legacy).

`verify_token` est pur et synchrone (cœur testable). `authenticate` résout la
clé (JWKS via httpx, injectable) puis délègue à `verify_token`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import jwt
from jwt import PyJWKSet

from augura_api.core.config import Settings
from augura_api.core.errors import UnauthorizedError
from augura_api.core.ids import UserId

JwksFetcher = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Principal:
    """Utilisateur authentifié (pas encore résolu à un tenant)."""

    user_id: UserId
    email: str | None
    claims: dict[str, Any]


def verify_token(
    token: str,
    *,
    key: Any,
    algorithms: list[str],
    audience: str,
    issuer: str | None = None,
) -> Principal:
    """Décode et valide un JWT. Lève UnauthorizedError sur tout échec."""
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=audience,
            issuer=issuer,
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("jwt invalide", reason=str(exc)) from exc

    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise UnauthorizedError("jwt sans sub exploitable")
    try:
        user_id = UserId(UUID(sub))
    except ValueError as exc:
        raise UnauthorizedError("sub n'est pas un uuid", sub=sub) from exc

    email = claims.get("email")
    return Principal(
        user_id=user_id,
        email=email if isinstance(email, str) else None,
        claims=claims,
    )


def _unverified_kid(token: str) -> str | None:
    try:
        return jwt.get_unverified_header(token).get("kid")
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("en-tête jwt illisible", reason=str(exc)) from exc


def _signing_key_from_jwks(jwks: dict[str, Any], kid: str | None) -> Any:
    key_set = PyJWKSet.from_dict(jwks)
    for jwk in key_set.keys:
        if kid is None or jwk.key_id == kid:
            return jwk.key
    raise UnauthorizedError("clé de signature introuvable", kid=kid)


async def _default_jwks_fetcher(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data


async def authenticate(
    token: str,
    settings: Settings,
    *,
    jwks_fetcher: JwksFetcher | None = None,
) -> Principal:
    """Résout la clé (secret HS256 ou JWKS) puis vérifie le token."""
    if settings.supabase_jwt_secret is not None:
        return verify_token(
            token,
            key=settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            issuer=settings.supabase_jwt_issuer,
        )

    if settings.supabase_jwks_url is None:
        raise UnauthorizedError("aucune clé configurée (AUGURA_SUPABASE_JWKS_URL ou _JWT_SECRET)")

    fetcher = jwks_fetcher
    if fetcher is None:
        jwks_url = settings.supabase_jwks_url

        async def _fetch() -> dict[str, Any]:
            return await _default_jwks_fetcher(jwks_url)

        fetcher = _fetch

    jwks = await fetcher()
    key = _signing_key_from_jwks(jwks, _unverified_kid(token))
    return verify_token(
        token,
        key=key,
        algorithms=["RS256", "ES256"],
        audience=settings.supabase_jwt_audience,
        issuer=settings.supabase_jwt_issuer,
    )
