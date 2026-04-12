"""
Migration v2.0.15 — Ajout de la colonne entry_candle_direction sur paper_trade.

Permet de stocker la couleur de la bougie ("green"/"red") au moment de l'entrée
en position, pour vérifier la cohérence direction/bougie dans le frontend.

Colonne nullable, additif, rétrocompatible.

Usage :
    cd backend
    python migrate_v2015.py
"""

import sys
sys.path.insert(0, ".")

from app.database import engine
from sqlalchemy import text, inspect


def migrate():
    inspector = inspect(engine)
    existing_cols = {col["name"] for col in inspector.get_columns("paper_trade")}

    with engine.begin() as conn:
        col_name = "entry_candle_direction"
        if col_name not in existing_cols:
            sql = f"ALTER TABLE paper_trade ADD COLUMN {col_name} VARCHAR(10)"
            print(f"  ➕ {sql}")
            conn.execute(text(sql))
        else:
            print(f"  ✅ {col_name} existe déjà")

    print("\n✅ Migration v2.0.15 terminée.")


if __name__ == "__main__":
    migrate()

