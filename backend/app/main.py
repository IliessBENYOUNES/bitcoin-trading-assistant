"""
Point d'entrée de l'application FastAPI.

Ce fichier :
1. Crée l'instance FastAPI
2. Configure les middlewares (CORS)
3. Enregistre les routes
4. Crée les tables au démarrage
5. Démarre/arrête le scheduler

Lancement : uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine, Base
from app.api.routes import health_router, market_router, alerts_router, news_router, decision_router, backtest_router, verification_router, sentiment_router
from app.api.routes.scheduler import router as scheduler_router
from app.tasks.scheduler import start_scheduler, stop_scheduler

# IMPORTANT : importer les modèles pour que SQLAlchemy les connaisse
from app.models import Candle, Alert, SentimentHistory  # noqa: F401

# Configuration
settings = get_settings()


# ============================================================
# LIFESPAN : Code exécuté au démarrage et à l'arrêt
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestionnaire du cycle de vie de l'application.

    - Code AVANT yield = exécuté au DÉMARRAGE
    - Code APRÈS yield = exécuté à l'ARRÊT
    """
    # === DÉMARRAGE ===
    print("🚀 Démarrage de l'application...")
    print("📦 Création des tables si nécessaire...")

    # Crée les tables qui n'existent pas encore
    Base.metadata.create_all(bind=engine)
    print("✅ Tables prêtes")

    # Démarrer le scheduler (si activé)
    start_scheduler()

    yield  # L'application tourne ici

    # === ARRÊT ===
    print("👋 Arrêt de l'application...")

    # Arrêter le scheduler
    stop_scheduler()


# ============================================================
# CRÉATION DE L'APPLICATION
# ============================================================

app = FastAPI(
    title="Bitcoin Trading Assistant",
    description=(
        "API pour l'analyse de trading Bitcoin.\n\n"
        "Fonctionnalités :\n"
        "- Données de marché (OHLCV)\n"
        "- Indicateurs techniques\n"
        "- Scheduler automatique\n"
        "- Analyse et recommandations"
    ),
    version="0.3.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)


# ============================================================
# MIDDLEWARE CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["https://ton-domaine.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# ENREGISTREMENT DES ROUTES
# ============================================================

app.include_router(health_router)      # /health, /health/db
app.include_router(market_router)      # /market/candles, /market/indicators, /market/signals
app.include_router(decision_router)    # /market/decision
app.include_router(alerts_router)      # /alerts CRUD + /alerts/check
app.include_router(news_router)        # /news, /news/sentiment
app.include_router(backtest_router)    # /backtest/run
app.include_router(verification_router) # /backtest/verify, /backtest/walk-forward, /backtest/history/*
app.include_router(sentiment_router)    # /sentiment/history/load, range, coverage, at-date
app.include_router(scheduler_router)   # /scheduler/status


# ============================================================
# ROUTE RACINE
# ============================================================

@app.get("/", tags=["Root"])
def root():
    """Route racine pour vérifier que l'API répond."""
    return {
        "message": "Bitcoin Trading Assistant API",
        "version": "0.3.0",
        "docs": "/docs"
    }
