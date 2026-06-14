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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- champs injectés par l'environnement
