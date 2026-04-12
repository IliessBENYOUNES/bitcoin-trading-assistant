"""
Migration v2.0.18 — Ajout reversal_delay_seconds à paper_trade et learning_signal.

Ajoute le tracking du délai de reversal (candle color flip) pour :
- paper_trade.reversal_delay_seconds : suivi temps réel
- learning_signal.reversal_delay_seconds : apprentissage ML

Idempotent : peut être relancé sans erreur.
"""

import sqlite3
import os
import sys


def migrate(db_path: str = "test.db"):
    """Ajoute les colonnes reversal_delay_seconds si absentes."""
    if not os.path.exists(db_path):
        print(f"⚠️  Base {db_path} non trouvée, skip")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- paper_trade.reversal_delay_seconds ---
    cursor.execute("PRAGMA table_info(paper_trade)")
    pt_columns = {row[1] for row in cursor.fetchall()}

    if "reversal_delay_seconds" not in pt_columns:
        cursor.execute("ALTER TABLE paper_trade ADD COLUMN reversal_delay_seconds REAL")
        print("✅ paper_trade.reversal_delay_seconds ajouté")
    else:
        print("ℹ️  paper_trade.reversal_delay_seconds existe déjà")

    # --- learning_signal.reversal_delay_seconds ---
    cursor.execute("PRAGMA table_info(learning_signal)")
    ls_columns = {row[1] for row in cursor.fetchall()}

    if "reversal_delay_seconds" not in ls_columns:
        cursor.execute("ALTER TABLE learning_signal ADD COLUMN reversal_delay_seconds REAL")
        print("✅ learning_signal.reversal_delay_seconds ajouté")
    else:
        print("ℹ️  learning_signal.reversal_delay_seconds existe déjà")

    conn.commit()
    conn.close()
    print("🎉 Migration v2.0.18 terminée")


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "test.db"
    migrate(db)

