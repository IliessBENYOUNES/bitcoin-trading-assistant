"""
Package des routes API.

Exporte les routers pour simplifier les imports dans main.py.
"""

from app.api.routes.health import router as health_router
from app.api.routes.market import router as market_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.news import router as news_router
from app.api.routes.decision import router as decision_router

__all__ = ["health_router", "market_router", "alerts_router", "news_router", "decision_router"]
