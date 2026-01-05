"""
Package des services métier.

Les services contiennent la logique métier de l'application.
Ils sont appelés par les routes API.
"""

from app.services.coingecko_service import CoinGeckoService

__all__ = ["CoinGeckoService"]