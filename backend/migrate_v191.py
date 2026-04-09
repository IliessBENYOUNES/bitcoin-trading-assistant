"""
Migration v1.9.1 : Ajouter les colonnes d'analyse économique au learning_signal.

Colonnes ajoutées :
- learning_signal.cost_estimated (FLOAT, nullable)
- learning_signal.pnl_net_estimated (FLOAT, nullable)
- learning_signal.usefulness_category (VARCHAR(30), nullable)

Ces colonnes enrichissent les échantillons d'apprentissage avec les métriques
économiques (coût estimé, PnL net, catégorie d'utilité) pour le module anti-churn.
"""
from app.database import SessionLocal
from sqlalchemy import text


COLUMNS_TO_ADD = [
    {
        "table": "learning_signal",
        "column": "cost_estimated",
        "sql": "ALTER TABLE learning_signal ADD COLUMN cost_estimated FLOAT",
    },
    {
        "table": "learning_signal",
        "column": "pnl_net_estimated",
        "sql": "ALTER TABLE learning_signal ADD COLUMN pnl_net_estimated FLOAT",
    },
    {
        "table": "learning_signal",
        "column": "usefulness_category",
        "sql": "ALTER TABLE learning_signal ADD COLUMN usefulness_category VARCHAR(30)",
    },
]


def migrate():
    db = SessionLocal()
    try:
        for col_def in COLUMNS_TO_ADD:
            table = col_def["table"]
            column = col_def["column"]

            result = db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}' AND column_name = '{column}'"
            ))
            if result.fetchone() is None:
                print(f"[MIGRATION] Adding {table}.{column} ...")
                db.execute(text(col_def["sql"]))
                print(f"[MIGRATION] OK {table}.{column} added.")
            else:
                print(f"[MIGRATION] {table}.{column} already exists, skipping.")

        db.commit()
        print("\n[MIGRATION] Migration v1.9.1 terminee avec succes !")
    except Exception as e:
        db.rollback()
        print(f"\n[MIGRATION] Erreur: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()

