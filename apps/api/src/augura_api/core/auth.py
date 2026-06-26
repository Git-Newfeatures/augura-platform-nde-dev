"""Supabase JWT verification (spec §7).

The frontend sends the JWT in `Authorization: Bearer`. We verify signature, exp and
audience, then extract the `UserId` from it. Two modes:
- asymmetric: Supabase JWKS (RS256/ES256), keys cached by `kid`;
- symmetric: shared HS256 secret (legacy Supabase projects).

`verify_token` is pure and synchronous (testable core). `authenticate` resolves the
key (JWKS via httpx, injectable) then delegates to `verify_token`.

JWKS cache: module-level dict keyed by URL, entries expire after JWKS_TTL_SECONDS.
On an unknown kid the cache entry is busted and the JWKS is refetched once before
raising. A token that omits `kid` entirely is rejected (no silent first-key fallback).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import jwt
import structlog
from jwt import PyJWKSet

from augura_api.core.config import Settings
from augura_api.core.errors import UnauthorizedError
from augura_api.core.ids import UserId

log = structlog.get_logger(__name__)

JwksFetcher = Callable[[], Awaitable[dict[str, Any]]]

# TTL for the in-process JWKS cache (seconds). Short enough that key rotations
# propagate within a few minutes; long enough to avoid hammering the JWKS endpoint.
JWKS_TTL_SECONDS: float = 300.0

# {url: (fetched_at_monotonic, jwks_dict)}
_jwks_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_jwks_cache() -> None:
    """Evict all cached JWKS entries. Intended for tests."""
    _jwks_cache.clear()


@dataclass(frozen=True)
class Principal:
    """Authenticated user (not yet resolved to a tenant)."""

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
    """Decode and validate a JWT. Raises UnauthorizedError on any failure."""
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
        log.info("jwt_rejected", reason=str(exc))
        raise UnauthorizedError("invalid jwt") from exc

    sub = claims.get("sub")
    if not isinstance(sub, str):
        raise UnauthorizedError("jwt without usable sub")
    try:
        user_id = UserId(UUID(sub))
    except ValueError as exc:
        log.info("jwt_sub_not_uuid")
        raise UnauthorizedError("invalid jwt") from exc

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
        raise UnauthorizedError("unreadable jwt header", reason=str(exc)) from exc


def _signing_key_from_jwks(jwks: dict[str, Any], kid: str) -> Any:
    """Return the signing key matching *kid* from *jwks*.

    Raises UnauthorizedError if *kid* is not found (never falls back to first key).
    Callers must validate that `kid` is not None before calling this function.
    """
    key_set = PyJWKSet.from_dict(jwks)
    for jwk in key_set.keys:
        if jwk.key_id == kid:
            return jwk.key
    raise UnauthorizedError("signing key not found")


async def _default_jwks_fetcher(url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        return data


async def _fetch_jwks(url: str, fetcher: JwksFetcher, *, bust: bool = False) -> dict[str, Any]:
    """Return the JWKS for *url*, using the module-level TTL cache.

    If *bust* is True the cache entry for *url* is evicted before fetching
    (used for a single refetch on unknown-kid).
    """
    now = time.monotonic()
    if not bust:
        cached = _jwks_cache.get(url)
        if cached is not None:
            fetched_at, jwks = cached
            if now - fetched_at < JWKS_TTL_SECONDS:
                return jwks
    # Cache miss, expired, or bust — fetch fresh.
    jwks = await fetcher()
    _jwks_cache[url] = (now, jwks)
    return jwks


def _check_mfa(principal: Principal, settings: Settings) -> None:
    """Raise UnauthorizedError if MFA enforcement is enabled and the token lacks aal2."""
    if not settings.require_mfa:
        return
    if principal.claims.get("aal") != "aal2":
        raise UnauthorizedError("mfa required")


async def authenticate(
    token: str,
    settings: Settings,
    *,
    jwks_fetcher: JwksFetcher | None = None,
) -> Principal:
    """Resolve the key (HS256 secret or JWKS) then verify the token."""
    if settings.supabase_jwt_secret is not None:
        principal = verify_token(
            token,
            key=settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience,
            issuer=settings.supabase_jwt_issuer,
        )
        _check_mfa(principal, settings)
        return principal

    if settings.supabase_jwks_url is None:
        raise UnauthorizedError("no key configured (AUGURA_SUPABASE_JWKS_URL or _JWT_SECRET)")

    jwks_url = settings.supabase_jwks_url

    # Build the fetcher callable so _fetch_jwks can delegate to it.
    effective_fetcher: JwksFetcher
    if jwks_fetcher is not None:
        effective_fetcher = jwks_fetcher
    else:

        async def _default_fetch() -> dict[str, Any]:
            return await _default_jwks_fetcher(jwks_url)

        effective_fetcher = _default_fetch

    # Require kid — never silently fall back to the first key.
    kid = _unverified_kid(token)
    if kid is None:
        raise UnauthorizedError("jwt missing kid")

    # Attempt key lookup from (possibly cached) JWKS.
    jwks = await _fetch_jwks(jwks_url, effective_fetcher)
    try:
        key = _signing_key_from_jwks(jwks, kid)
    except UnauthorizedError:
        # Unknown kid: bust the cache and refetch exactly once.
        log.info("jwks_unknown_kid_refetch", kid=kid)
        jwks = await _fetch_jwks(jwks_url, effective_fetcher, bust=True)
        key = _signing_key_from_jwks(jwks, kid)  # raises UnauthorizedError if still not found

    principal = verify_token(
        token,
        key=key,
        algorithms=["RS256", "ES256"],
        audience=settings.supabase_jwt_audience,
        issuer=settings.supabase_jwt_issuer,
    )
    _check_mfa(principal, settings)
    return principal
