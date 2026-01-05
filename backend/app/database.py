"""
Configuration de la connexion à PostgreSQL avec SQLAlchemy.

SQLAlchemy est un ORM (Object-Relational Mapper) :
- Classes Python → Tables SQL
- Objets Python → Lignes de table
- Requêtes Python → Requêtes SQL

Équivalent Java  : Hibernate / JPA
Équivalent Node  : Sequelize / TypeORM
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import get_settings

# Récupère la configuration
settings = get_settings()

# ============================================================
# ENGINE : Moteur de connexion
# ============================================================
# Gère le pool de connexions à PostgreSQL.
# pool_pre_ping=True : vérifie que la connexion est vivante
# echo=True : affiche les requêtes SQL (debug)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    echo=settings.debug
)

# ============================================================
# SESSION FACTORY : Usine à sessions
# ============================================================
# Une session = une conversation avec la base de données.
# autocommit=False : tu dois appeler commit() explicitement
# autoflush=False : contrôle manuel de la synchronisation

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)


# ============================================================
# BASE : Classe parente des modèles
# ============================================================
# Tous les modèles (tables) héritent de cette classe.

class Base(DeclarativeBase):
    """Classe de base pour tous les modèles SQLAlchemy."""
    pass


# ============================================================
# GET_DB : Injection de dépendances
# ============================================================
# Utilisé par FastAPI pour fournir une session à chaque requête.
# Équivalent Spring : @Autowired EntityManager

def get_db():
    """
    Crée une session de base de données pour une requête.
    
    Le mot-clé 'yield' en fait un générateur :
    1. Crée la session
    2. La fournit à la requête (yield)
    3. La ferme après la requête (finally)
    
    Usage :
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
