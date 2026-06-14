from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration de l'application, lue depuis les variables AUGURA_*.

    Tout champ requis manquant fait échouer le boot (fail-fast).
    """

    model_config = SettingsConfigDict(env_prefix="AUGURA_", frozen=True)

    env: Literal["dev", "prod"]
    app_name: str = "augura-api"
    version: str = "0.1.0"
    log_level: str = "INFO"

    # Infra — optionnels au boot (le healthcheck n'en a pas besoin) ; les
    # composants qui les consomment échouent franchement s'ils manquent.
    # Préfixe AUGURA_ : AUGURA_DATABASE_URL, AUGURA_SUPABASE_JWKS_URL, etc.
    database_url: str | None = None
    supabase_jwks_url: str | None = None
    supabase_jwt_secret: str | None = None  # repli HS256 (projets Supabase legacy)
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_issuer: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- champs injectés par l'environnement
