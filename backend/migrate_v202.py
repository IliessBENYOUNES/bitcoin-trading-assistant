"""
Migration v2.0.2 — Ajout des colonnes BTC context sur learning_signal.

5 nouvelles colonnes nullable, additif, rétrocompatible.

Usage :
    cd backend
    python migrate_v202.py
"""

import sys
sys.path.insert(0, ".")

from app.database import engine
from sqlalchemy import text, inspect

COLUMNS_TO_ADD = [
    ("btc_trend_at_entry", "VARCHAR(10)"),
    ("btc_move_during_pct", "DOUBLE PRECISION"),
    ("btc_move_after_exit_pct", "DOUBLE PRECISION"),
    ("missed_favorable_move", "INTEGER DEFAULT 0"),
    ("capture_efficiency_pct", "DOUBLE PRECISION"),
]


def migrate():
    inspector = inspect(engine)
    existing_cols = {col["name"] for col in inspector.get_columns("learning_signal")}

    with engine.begin() as conn:
        for col_name, col_type in COLUMNS_TO_ADD:
            if col_name not in existing_cols:
                sql = f"ALTER TABLE learning_signal ADD COLUMN {col_name} {col_type}"
                print(f"  ➕ {sql}")
                conn.execute(text(sql))
            else:
                print(f"  ✅ {col_name} existe déjà")

    print("\n✅ Migration v2.0.2 terminée.")


if __name__ == "__main__":
    migrate()

