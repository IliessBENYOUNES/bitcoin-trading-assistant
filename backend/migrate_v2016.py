"""
Migration v2.0.16 — Ajout exit_candle_direction + enrichissement learning_signal.

Nouvelles colonnes :
- paper_trade.exit_candle_direction VARCHAR(10) — couleur bougie à la sortie
- learning_signal.entry_candle_direction VARCHAR(10) — couleur bougie à l'entrée (copié du trade)
- learning_signal.exit_candle_direction VARCHAR(10) — couleur bougie à la sortie (copié du trade)

Toutes nullable, additif, rétrocompatible.

Usage :
    cd backend
    python migrate_v2016.py
"""

import sys
sys.path.insert(0, ".")

from app.database import engine
from sqlalchemy import text, inspect


def migrate():
    inspector = inspect(engine)

    # --- paper_trade ---
    pt_cols = {col["name"] for col in inspector.get_columns("paper_trade")}
    with engine.begin() as conn:
        col = "exit_candle_direction"
        if col not in pt_cols:
            sql = f"ALTER TABLE paper_trade ADD COLUMN {col} VARCHAR(10)"
            print(f"  ➕ paper_trade.{col}")
            conn.execute(text(sql))
        else:
            print(f"  ✅ paper_trade.{col} existe déjà")

    # --- learning_signal ---
    ls_cols = {col["name"] for col in inspector.get_columns("learning_signal")}
    with engine.begin() as conn:
        for col in ["entry_candle_direction", "exit_candle_direction"]:
            if col not in ls_cols:
                sql = f"ALTER TABLE learning_signal ADD COLUMN {col} VARCHAR(10)"
                print(f"  ➕ learning_signal.{col}")
                conn.execute(text(sql))
            else:
                print(f"  ✅ learning_signal.{col} existe déjà")

    print("\n✅ Migration v2.0.16 terminée.")


if __name__ == "__main__":
    migrate()

