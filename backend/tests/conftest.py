"""
Configuration des tests pytest.

Ce fichier contient les "fixtures" : fonctions qui préparent
l'environnement de test.

Les fixtures sont automatiquement disponibles dans tous les tests.

Équivalent Java  : @BeforeEach, @BeforeAll (JUnit)
Équivalent Node  : beforeEach(), beforeAll() (Jest)
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db


# ============================================================
# BASE DE DONNÉES DE TEST (SQLite en mémoire)
# ============================================================
# Pour les tests, on utilise SQLite en mémoire au lieu de PostgreSQL.
# Avantages :
# - Pas besoin de PostgreSQL pour lancer les tests
# - Très rapide (tout en RAM)
# - Base vierge à chaque test

SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine
)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture(scope="function")
def db_session():
    """
    Crée une session de base de données de test.
    
    scope="function" = nouvelle session pour chaque test
    """
    # Crée les tables
    Base.metadata.create_all(bind=test_engine)
    
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        # Supprime les tables après le test
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """
    Crée un client HTTP de test.
    
    Simule des requêtes HTTP vers l'API sans lancer le serveur.
    
    Équivalent Java  : MockMvc, RestAssured
    Équivalent Node  : supertest
    """
    # Remplace la vraie BDD par la BDD de test
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()
