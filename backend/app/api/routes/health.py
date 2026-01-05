"""
Routes de health check.

Ces routes vérifient que l'API et la base de données fonctionnent.
Utilisées par les load balancers et outils de monitoring.

Équivalent Spring : @GetMapping("/health") dans un @RestController
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db

# Création du router (groupe de routes)
router = APIRouter()


@router.get("/health")
def health_check():
    """
    Vérifie que l'API est en vie.
    
    Returns:
        dict: {"status": "healthy", "service": "..."}
    """
    return {
        "status": "healthy",
        "service": "bitcoin-trading-assistant"
    }


@router.get("/health/db")
def health_check_database(db: Session = Depends(get_db)):
    """
    Vérifie que la connexion à la base de données fonctionne.
    
    Depends(get_db) = injection de dépendances FastAPI.
    FastAPI appelle get_db() et passe la session en paramètre.
    
    Returns:
        dict: {"status": "healthy", "database": "connected"} ou erreur
    """
    try:
        # Exécute une requête simple pour tester la connexion
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }
