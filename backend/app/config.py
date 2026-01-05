"""
Configuration de l'application.

Charge les variables d'environnement depuis .env et les expose
sous forme d'objet Python typé.

Équivalent Java  : @ConfigurationProperties + application.yml
Équivalent Node  : dotenv + config object
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    Classe de configuration principale.
    
    Pydantic charge automatiquement les variables depuis .env
    et valide leurs types.
    """
    
    # URL de connexion PostgreSQL (OBLIGATOIRE)
    # Format : postgresql://user:password@host:port/database
    database_url: str
    
    # Environnement : development, staging, production
    app_env: str = "development"
    
    # Mode debug : affiche les requêtes SQL si True
    debug: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """
    Retourne l'instance de configuration (singleton).
    
    @lru_cache() met en cache le résultat : la config n'est lue qu'une fois.
    """
    return Settings()
