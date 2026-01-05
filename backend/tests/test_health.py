"""
Tests des routes de health check.

Vérifie que l'API démarre et que les endpoints de santé fonctionnent.
"""


def test_health_check(client):
    """
    Test de la route /health.
    
    Vérifie :
    - Code HTTP 200
    - Statut "healthy"
    """
    # Act
    response = client.get("/health")
    
    # Assert
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "bitcoin-trading-assistant"


def test_health_check_database(client):
    """
    Test de la route /health/db.
    
    Vérifie que la connexion à la base de données fonctionne.
    """
    response = client.get("/health/db")
    
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"


def test_root(client):
    """
    Test de la route racine /.
    """
    response = client.get("/")
    
    assert response.status_code == 200
    
    data = response.json()
    assert "message" in data
    assert "version" in data
    assert data["docs"] == "/docs"
