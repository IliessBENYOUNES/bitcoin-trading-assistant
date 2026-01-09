"""
Dialect-aware upsert helper compatible SQLite et PostgreSQL.
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects import postgresql, sqlite

from app.models import Candle


def upsert_candles(
        db: Session,
        records: List[Dict[str, Any]],
        conflict_keys: Optional[List[str]] = None,
        update_keys: Optional[List[str]] = None,
) -> int:
    """
    Upsert batch de candles compatible SQLite/PostgreSQL.

    Args:
        db: Session SQLAlchemy
        records: Liste de dicts avec les données candle
        conflict_keys: Clés de conflit (défaut: symbol, timeframe, timestamp)
        update_keys: Clés à mettre à jour en cas de conflit

    Returns:
        Nombre de records traités
    """
    if not records:
        return 0

    if conflict_keys is None:
        conflict_keys = ["symbol", "timeframe", "timestamp"]

    if update_keys is None:
        update_keys = ["open_price", "high_price", "low_price", "close_price", "volume", "source"]

    dialect = db.bind.dialect.name

    if dialect == "postgresql":
        stmt = postgresql.insert(Candle.__table__).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_keys,
            set_={key: stmt.excluded[key] for key in update_keys}
        )
    elif dialect == "sqlite":
        stmt = sqlite.insert(Candle.__table__).values(records)
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_keys,
            set_={key: stmt.excluded[key] for key in update_keys}
        )
    else:
        # Fallback: insertion un par un
        for record in records:
            existing = db.query(Candle).filter_by(
                symbol=record["symbol"],
                timeframe=record["timeframe"],
                timestamp=record["timestamp"]
            ).first()

            if existing:
                for key in update_keys:
                    if key in record:
                        setattr(existing, key, record[key])
            else:
                db.add(Candle(**record))

        db.commit()
        return len(records)

    db.execute(stmt)
    db.commit()
    return len(records)


def upsert_candle(
        db: Session,
        record: Dict[str, Any],
        conflict_keys: Optional[List[str]] = None,
        update_keys: Optional[List[str]] = None,
) -> int:
    """Upsert d'un seul candle."""
    return upsert_candles(db, [record], conflict_keys, update_keys)
