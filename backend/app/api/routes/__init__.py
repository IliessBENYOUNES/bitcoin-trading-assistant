"""
Package des routes API.

Exporte les routers pour simplifier les imports dans main.py.
"""

from app.api.routes.health import router as health_router
from app.api.routes.market import router as market_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.news import router as news_router
from app.api.routes.decision import router as decision_router
from app.api.routes.backtest import router as backtest_router
from app.api.routes.verification import router as verification_router
from app.api.routes.sentiment import router as sentiment_router
from app.api.routes.risk import router as risk_router
from app.api.routes.paper_trading import router as paper_router

__all__ = ["health_router", "market_router", "alerts_router", "news_router", "decision_router", "backtest_router", "verification_router", "sentiment_router", "risk_router", "paper_router"]
