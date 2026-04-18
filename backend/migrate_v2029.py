"""
Migration v2.0.29 — Ajout des colonnes frais de trading.

Ajoute :
- paper_trade.gross_pnl (Float, nullable)
- paper_trade.trading_fees (Float, nullable, default 0)
- paper_account.total_fees (Float, nullable, default 0)

Ces colonnes permettent de tracker le PnL brut et les frais séparément.
"""

import os
import sys

# Ajouter le dossier backend au path
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://btc_user:btc_password_123@localhost:5432/bitcoin_assistant"
)


def migrate(db_url: str = DATABASE_URL):
    engine = create_engine(db_url)

    columns_to_add = [
        ("paper_trade", "gross_pnl", "FLOAT"),
        ("paper_trade", "trading_fees", "FLOAT DEFAULT 0"),
        ("paper_account", "total_fees", "FLOAT DEFAULT 0"),
    ]

    with engine.connect() as conn:
        for table, column, col_type in columns_to_add:
            # Check if column already exists
            result = conn.execute(text(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name='{table}' AND column_name='{column}'"
            ))
            if result.fetchone() is None:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                print(f"  + {table}.{column} ({col_type})")
            else:
                print(f"  = {table}.{column} already exists")
        conn.commit()

    print("Migration v2.0.29 done.")


if __name__ == "__main__":
    migrate()
