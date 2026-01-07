"""
Tests des routes de données de marché.

Vérifie le bon fonctionnement de /market/candles.
"""

from datetime import datetime, timezone
from app.models import Candle


def test_get_candles_empty(client):
    """
    Test de /market/candles quand la base est vide.

    Doit retourner une liste vide avec count=0.
    """
    response = client.get("/market/candles")

    assert response.status_code == 200

    data = response.json()
    assert data["data"] == []
    assert data["count"] == 0
    assert data["symbol"] == "BTC/USD"
    assert data["timeframe"] == "4h"  # Corrigé : valeur par défaut est "4h"


def test_get_candles_with_data(client, db_session):
    """
    Test de /market/candles avec des données.
    
    Insère des bougies et vérifie qu'elles sont retournées.
    """
    # Arrange : créer des bougies de test
    candle1 = Candle(
        symbol="BTC/USD",
        timeframe="1h",
        timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        open_price=42000.0,
        high_price=42500.0,
        low_price=41800.0,
        close_price=42300.0,
        volume=1234.56,
        source="manual"
    )
    candle2 = Candle(
        symbol="BTC/USD",
        timeframe="1h",
        timestamp=datetime(2024, 1, 15, 11, 0, 0, tzinfo=timezone.utc),
        open_price=42300.0,
        high_price=42800.0,
        low_price=42100.0,
        close_price=42600.0,
        volume=987.65,
        source="manual"
    )
    
    db_session.add(candle1)
    db_session.add(candle2)
    db_session.commit()
    
    # Act
    response = client.get("/market/candles?symbol=BTC/USD&timeframe=1h")
    
    # Assert
    assert response.status_code == 200
    
    data = response.json()
    assert data["count"] == 2
    assert len(data["data"]) == 2
    
    # Vérifie le tri (plus récent en premier)
    assert data["data"][0]["close_price"] == 42600.0
    assert data["data"][1]["close_price"] == 42300.0


def test_get_candles_filter_by_symbol(client, db_session):
    """
    Test du filtre par symbole.
    """
    # Arrange : bougies de deux symboles différents
    btc_candle = Candle(
        symbol="BTC/USD",
        timeframe="4h",  # Changé de "1h" à "4h"
        timestamp=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
        open_price=42000.0,
        high_price=42500.0,
        low_price=41800.0,
        close_price=42300.0,
        volume=1234.56,
        source="manual"
    )
    eth_candle = Candle(
        symbol="ETH/USD",
        timeframe="4h",  # Changé de "1h" à "4h"
        timestamp=datetime(2024, 1, 15, 8, 0, 0, tzinfo=timezone.utc),
        open_price=2200.0,
        high_price=2250.0,
        low_price=2180.0,
        close_price=2230.0,
        volume=567.89,
        source="manual"
    )

    db_session.add(btc_candle)
    db_session.add(eth_candle)
    db_session.commit()

    # Act
    response = client.get("/market/candles?symbol=BTC/USD&timeframe=4h")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["data"][0]["symbol"] == "BTC/USD"


def test_get_candles_with_limit(client, db_session):
    """
    Test du paramètre limit.
    """
    # Arrange : créer 5 bougies
    for i in range(5):
        candle = Candle(
            symbol="BTC/USD",
            timeframe="4h",  # Changé de "1h" à "4h"
            timestamp=datetime(2024, 1, 15, i * 4, 0, 0, tzinfo=timezone.utc),  # Intervalles de 4h
            open_price=42000.0 + i * 100,
            high_price=42500.0 + i * 100,
            low_price=41800.0 + i * 100,
            close_price=42300.0 + i * 100,
            volume=1000.0 + i * 10,
            source="manual"
        )
        db_session.add(candle)
    db_session.commit()

    # Act
    response = client.get("/market/candles?limit=3&timeframe=4h")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
