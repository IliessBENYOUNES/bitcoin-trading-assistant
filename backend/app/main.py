"""
Point d'entrée de l'application FastAPI.

Ce fichier :
1. Crée l'instance FastAPI
2. Configure les middlewares (CORS)
3. Enregistre les routes
4. Crée les tables au démarrage

Équivalent Spring Boot : classe @SpringBootApplication
Équivalent Express    : app.js avec app.use(...)

Lancement : uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import engine, Base
from app.api.routes import health_router, market_router

# IMPORTANT : importer les modèles pour que SQLAlchemy les connaisse
from app.models import Candle  # noqa: F401

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
    # En production, utiliser Alembic pour les migrations
    Base.metadata.create_all(bind=engine)
    print("✅ Tables prêtes")
    
    yield  # L'application tourne ici
    
    # === ARRÊT ===
    print("👋 Arrêt de l'application...")


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
        "- Analyse de sentiment\n"
        "- Recommandations de trading"
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)


# ============================================================
# MIDDLEWARE CORS
# ============================================================
# Permet au frontend (ex: localhost:5173) d'appeler l'API (localhost:8000)

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

app.include_router(health_router)  # /health, /health/db
app.include_router(market_router)  # /market/candles


# ============================================================
# ROUTE RACINE
# ============================================================

@app.get("/", tags=["Root"])
def root():
    """Route racine pour vérifier que l'API répond."""
    return {
        "message": "Bitcoin Trading Assistant API",
        "version": "0.1.0",
        "docs": "/docs"
    }
