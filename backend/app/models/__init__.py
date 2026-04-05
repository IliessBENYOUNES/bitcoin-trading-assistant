"""
Package des modèles SQLAlchemy (tables de base de données).

Grâce à ce fichier, tu peux écrire :
    from app.models import Candle
    
Au lieu de :
    from app.models.candle import Candle
"""

from app.models.candle import Candle
from app.models.alert import Alert
from app.models.sentiment_history import SentimentHistory
from app.models.news_history import NewsHistory

__all__ = ["Candle", "Alert", "SentimentHistory", "NewsHistory"]
