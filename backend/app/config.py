"""
Configuration de l'application via variables d'environnement.

Utilise pydantic-settings pour la validation et le parsing.
Les variables sont lues depuis le fichier .env à la racine du projet backend.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration de l'application.

    Les variables sont automatiquement lues depuis :
    1. Les variables d'environnement système
    2. Le fichier .env (si présent)

    Convention de nommage :
    - En Python : snake_case (ex: database_url)
    - En .env   : SCREAMING_SNAKE_CASE (ex: DATABASE_URL)
    """

    # Base de données
    database_url: str = "postgresql://btc_user:btc_password_123@localhost:5432/bitcoin_assistant"

    # Mode debug
    debug: bool = True

    # Scheduler
    scheduler_enabled: bool = False
    scheduler_interval_minutes: int = 240  # 4h job interval
    scheduler_interval_30m_minutes: int = 30  # 30m job interval (nouveau)
    scheduler_interval_news_minutes: int = 10  # News RSS persist interval
    scheduler_symbol: str = "BTC/USD"
    scheduler_days: int = 7  # Legacy, non utilisé directement


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Changé de "forbid" à "ignore" pour plus de flexibilité
    )


@lru_cache
def get_settings() -> Settings:
    """
    Retourne une instance unique (singleton) des settings.

    Le décorateur @lru_cache garantit qu'on ne relit pas
    le fichier .env à chaque appel.
    """
    return Settings()
