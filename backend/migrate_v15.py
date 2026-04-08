"""
Migration v1.5 — Ajouter les colonnes et tables pour le Journal d'Évaluation,
les Profils de Trading, le Levier Automatique et la Qualification du Style.

Additive uniquement : aucune destruction de données existantes.
"""

from app.database import engine
from sqlalchemy import text

MIGRATIONS = [
    # 1. paper_account — profil actif
    "ALTER TABLE paper_account ADD COLUMN IF NOT EXISTS active_profile VARCHAR(20) NOT NULL DEFAULT 'conservative'",

    # 2. paper_trade — levier
    "ALTER TABLE paper_trade ADD COLUMN IF NOT EXISTS leverage FLOAT NOT NULL DEFAULT 1.0",
    "ALTER TABLE paper_trade ADD COLUMN IF NOT EXISTS effective_size_usd FLOAT",
    "ALTER TABLE paper_trade ADD COLUMN IF NOT EXISTS leverage_reason VARCHAR(200)",
    "ALTER TABLE paper_trade ADD COLUMN IF NOT EXISTS profile_type VARCHAR(20)",

    # 3. tick_activity_log — journal de chaque tick
    """CREATE TABLE IF NOT EXISTS tick_activity_log (
        id SERIAL PRIMARY KEY,
        account_id INTEGER NOT NULL REFERENCES paper_account(id),
        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
        btc_price FLOAT,
        action_taken VARCHAR(30) NOT NULL,
        decision_score FLOAT,
        decision_action VARCHAR(20),
        decision_confidence VARCHAR(20),
        reason_no_trade VARCHAR(50),
        reason_detail VARCHAR(500),
        profile_type VARCHAR(20) NOT NULL DEFAULT 'conservative',
        leverage_recommended FLOAT,
        leverage_final FLOAT,
        leverage_reason VARCHAR(200),
        had_open_position INTEGER NOT NULL DEFAULT 0,
        unrealized_pnl FLOAT,
        trade_id INTEGER
    )""",
]

def run():
    with engine.connect() as conn:
        for i, sql in enumerate(MIGRATIONS):
            try:
                conn.execute(text(sql))
                first_line = sql.strip().split('\n')[0][:80]
                print(f"  [{i+1}/{len(MIGRATIONS)}] OK: {first_line}")
            except Exception as e:
                print(f"  [{i+1}/{len(MIGRATIONS)}] SKIP: {e}")
        conn.commit()
    print("\nMigration v1.5 terminée avec succès.")


if __name__ == "__main__":
    print("=== Migration v1.5 — Paper Trading Journal + Profiles + Leverage ===\n")
    run()

