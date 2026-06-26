from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_CORS_DEV_DEFAULT = "http://localhost:5173,http://127.0.0.1:5173"


class Settings(BaseSettings):
    """Application configuration, read from the AUGURA_* variables.

    Any missing required field fails the boot (fail-fast).
    """

    model_config = SettingsConfigDict(env_prefix="AUGURA_", frozen=True)

    env: Literal["dev", "prod"]
    app_name: str = "augura-api"
    version: str = "0.1.0"
    log_level: str = "INFO"

    # CORS — allowed origins for the frontend (apps/web). Comma-separated
    # list: AUGURA_CORS_ORIGINS="https://app.augura.io,https://staging…".
    cors_origins: str = _CORS_DEV_DEFAULT
    # Optional origin regex, in addition to the explicit list. Essential for
    # dynamic Vercel previews: AUGURA_CORS_ORIGIN_REGEX='^https://.*\.vercel\.app$'.
    cors_origin_regex: str | None = None

    # Infra — optional at boot (the healthcheck does not need them); the
    # components that consume them fail outright if they are missing.
    # AUGURA_ prefix: AUGURA_DATABASE_URL, AUGURA_SUPABASE_JWKS_URL, etc.
    database_url: str | None = None
    supabase_jwks_url: str | None = None
    supabase_jwt_secret: str | None = None  # HS256 fallback (legacy Supabase projects)
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_issuer: str | None = None

    # Storage for generated artifacts (PDF/HTML dossiers, exports). Local in dev;
    # a Supabase Storage bucket / Modal volume takes over in prod through the
    # same interface (core.storage). Relative path → resolved from the API's CWD.
    artifacts_dir: str = "var/artifacts"

    # Supabase Storage (object store) for the bytes of uploaded datasets. In prod the
    # Modal FS is ephemeral AND per-container: an upload served by one ASGI container is
    # not re-read by the one that runs the DQ afterwards. When `supabase_url` AND
    # `supabase_service_role_key` are set, core.storage reads/writes via the Storage API
    # (consistent cross-container); otherwise it falls back to local disk (dev/test/CI with
    # no secret). The service_role key bypasses Storage RLS: backend secret only, never frontend.
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    storage_bucket: str = "datasets"

    # LLM (agents). Keys required for a live run; absent locally ⇒ the
    # /agents/* routes return an explicit 503 "missing key". We accept both the
    # AUGURA_* prefixed name AND the standard unprefixed name (ANTHROPIC_API_KEY…),
    # so as not to depend on a renaming of the secrets on the platform side.
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AUGURA_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AUGURA_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    # PubMed E-utilities (NCBI). Optional key: raises the rate limit
    # (3→10 req/s). Literature search works without a key.
    ncbi_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AUGURA_NCBI_API_KEY", "NCBI_API_KEY"),
    )
    # Workaround for the CT.gov WAF (403 from Modal datacenter IPs). Two options,
    # both optional (absent ⇒ direct call = graceful degradation):
    #  - relay  : URL of an HTTP relay (Vercel function) that re-issues to CT.gov from
    #    an allowed egress. Replaces the CT.gov base. PREFERRED mechanism.
    #  - proxy  : outbound httpx proxy (residential IP) for the CT.gov calls.
    ctgov_relay_url: str | None = None
    ctgov_proxy_url: str | None = None
    agent_model_dag: str = "claude-sonnet-4-6"
    agent_model_fast: str = "claude-haiku-4-5"
    agent_model_deep: str = "claude-opus-4-8"

    # MFA enforcement — require aal2 (MFA-satisfied) tokens on all authenticated routes.
    # Default OFF: flip to True only after MFA enrollment is live for all users.
    require_mfa: bool = False  # enforce aal2 on PHI routes once MFA enrollment is live

    @field_validator(
        "anthropic_api_key",
        "openai_api_key",
        "ncbi_api_key",
        "ctgov_relay_url",
        "ctgov_proxy_url",
        mode="after",
    )
    @classmethod
    def _blank_key_is_none(cls, v: str | None) -> str | None:
        # An empty/whitespace key in .env (`ANTHROPIC_API_KEY=`) must count as "absent"
        # (None), otherwise the LLM constructors build a client with an empty key and
        # fail opaquely instead of returning a clean 503 "missing key".
        if isinstance(v, str):
            return v.strip() or None
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _require_explicit_prod_cors(self) -> "Settings":
        # In prod, the default localhost value would reject the real frontend
        # (allow_credentials=True ⇒ no wildcard allowed): fail-fast at boot.
        if (
            self.env == "prod"
            and self.cors_origins == _CORS_DEV_DEFAULT
            and not self.cors_origin_regex
        ):
            raise ValueError(
                "AUGURA_CORS_ORIGINS or AUGURA_CORS_ORIGIN_REGEX must be set "
                "explicitly in prod (the frontend origin(s)), not the default localhost value."
            )
        return self

    @model_validator(mode="after")
    def _require_tls_db_in_prod(self) -> "Settings":
        # PHI-bearing SQL must use TLS. asyncpg does NOT negotiate TLS unless told to,
        # so in prod we require an explicit sslmode/ssl in the URL and verify it at
        # connect time (core/db.py). Fail-fast at boot, like the CORS guard above.
        if self.env == "prod" and self.database_url is not None:
            url = self.database_url.lower()
            if "sslmode=" not in url and "ssl=" not in url:
                raise ValueError(
                    "AUGURA_DATABASE_URL must request TLS in prod "
                    "(append ?sslmode=require — connection is then certificate-verified)."
                )
        return self

    @model_validator(mode="after")
    def _forbid_symmetric_jwt_in_prod(self) -> "Settings":
        # HS256 uses one shared secret to sign AND verify: a leak = tenant-wide token
        # forgery. Prod must verify with the asymmetric Supabase JWKS only.
        if self.env == "prod" and self.supabase_jwt_secret is not None:
            raise ValueError(
                "AUGURA_SUPABASE_JWT_SECRET (HS256) must not be set in prod — "
                "use AUGURA_SUPABASE_JWKS_URL (asymmetric) instead."
            )
        return self

    @model_validator(mode="after")
    def _require_object_store_in_prod(self) -> "Settings":
        # The local-disk storage backend writes unencrypted bytes to the (ephemeral,
        # per-container) Modal FS. In prod the object store is mandatory: fail-fast
        # rather than silently degrade to plaintext-on-disk.
        if self.env == "prod" and not (self.supabase_url and self.supabase_service_role_key):
            raise ValueError(
                "AUGURA_SUPABASE_URL and AUGURA_SUPABASE_SERVICE_ROLE_KEY are required "
                "in prod (object store) — the local-disk fallback is dev/test only."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- fields injected by the environment
