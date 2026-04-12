import os

# Définir les variables d'environnement AVANT tout import de l'app
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from fastapi.testclient import TestClient


# Configuration de la base de test en mémoire
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    """Crée une session de base de données pour les tests."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Client de test FastAPI avec override de la DB."""
    # Import ici pour éviter les problèmes d'ordre
    from app.main import app

    def override_get_db():
        # Utiliser la MÊME session que db_session
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_sas_state():
    """[v2.0.22] Nettoie l'état SAS entre chaque test pour éviter les fuites.
    Le EntrySasService stocke l'état en class-level (in-memory), il faut le
    nettoyer avant chaque test pour garantir l'isolation."""
    from app.services.entry_sas_service import EntrySasService
    EntrySasService.clear()
    yield
    EntrySasService.clear()
