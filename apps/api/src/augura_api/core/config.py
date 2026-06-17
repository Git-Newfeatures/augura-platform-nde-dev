from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_CORS_DEV_DEFAULT = "http://localhost:5173,http://127.0.0.1:5173"


class Settings(BaseSettings):
    """Configuration de l'application, lue depuis les variables AUGURA_*.

    Tout champ requis manquant fait échouer le boot (fail-fast).
    """

    model_config = SettingsConfigDict(env_prefix="AUGURA_", frozen=True)

    env: Literal["dev", "prod"]
    app_name: str = "augura-api"
    version: str = "0.1.0"
    log_level: str = "INFO"

    # CORS — origines autorisées pour le front (apps/web). Liste séparée par des
    # virgules : AUGURA_CORS_ORIGINS="https://app.augura.io,https://staging…".
    cors_origins: str = _CORS_DEV_DEFAULT

    # Infra — optionnels au boot (le healthcheck n'en a pas besoin) ; les
    # composants qui les consomment échouent franchement s'ils manquent.
    # Préfixe AUGURA_ : AUGURA_DATABASE_URL, AUGURA_SUPABASE_JWKS_URL, etc.
    database_url: str | None = None
    supabase_jwks_url: str | None = None
    supabase_jwt_secret: str | None = None  # repli HS256 (projets Supabase legacy)
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_issuer: str | None = None

    # Stockage des artefacts générés (dossiers PDF/HTML, exports). Local en dev ;
    # un bucket Supabase Storage / volume Modal prendra le relais en prod via la
    # même interface (core.storage). Chemin relatif → résolu depuis le CWD de l'API.
    artifacts_dir: str = "var/artifacts"

    # LLM (agents). Clés requises pour un run live ; absentes en local ⇒ les routes
    # /agents/* renvoient une 503 explicite « clé manquante ». On accepte le nom
    # préfixé AUGURA_* ET le nom standard sans préfixe (ANTHROPIC_API_KEY…), pour
    # ne pas dépendre d'un renommage des secrets côté plateforme.
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AUGURA_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AUGURA_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    # PubMed E-utilities (NCBI). Clé optionnelle : relève la limite de débit
    # (3→10 req/s). La recherche de littérature marche sans clé.
    ncbi_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AUGURA_NCBI_API_KEY", "NCBI_API_KEY"),
    )
    agent_model_dag: str = "claude-sonnet-4-6"
    agent_model_fast: str = "claude-haiku-4-5"
    agent_model_deep: str = "claude-opus-4-8"

    @field_validator("anthropic_api_key", "openai_api_key", "ncbi_api_key", mode="after")
    @classmethod
    def _blank_key_is_none(cls, v: str | None) -> str | None:
        # Une clé vide/whitespace dans .env (`ANTHROPIC_API_KEY=`) doit valoir « absente »
        # (None), sinon les constructeurs LLM bâtissent un client avec une clé vide et
        # échouent de façon opaque au lieu de renvoyer une 503 « clé manquante » propre.
        if isinstance(v, str):
            return v.strip() or None
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _require_explicit_prod_cors(self) -> "Settings":
        # En prod, la valeur localhost par défaut rejetterait le vrai front
        # (allow_credentials=True ⇒ pas de wildcard possible) : fail-fast au boot.
        if self.env == "prod" and self.cors_origins == _CORS_DEV_DEFAULT:
            raise ValueError(
                "AUGURA_CORS_ORIGINS doit être défini explicitement en prod "
                "(origine(s) du front), pas la valeur localhost par défaut."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- champs injectés par l'environnement
