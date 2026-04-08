"""
Migration v1.7 : Ajouter les colonnes multi-position.

Colonnes ajoutées :
- paper_account.max_open_positions (Integer, NOT NULL, default 1)
- paper_trade.slot (VARCHAR(20), nullable)
"""
from app.database import SessionLocal
from sqlalchemy import text

def migrate():
    db = SessionLocal()
    try:
        # --- paper_account.max_open_positions ---
        result = db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'paper_account' AND column_name = 'max_open_positions'"
        ))
        if result.fetchone() is None:
            print("[MIGRATION] Adding paper_account.max_open_positions ...")
            db.execute(text(
                "ALTER TABLE paper_account ADD COLUMN max_open_positions INTEGER NOT NULL DEFAULT 1"
            ))
            print("[MIGRATION] ✅ paper_account.max_open_positions added.")
        else:
            print("[MIGRATION] paper_account.max_open_positions already exists, skipping.")

        # --- paper_trade.slot ---
        result = db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'paper_trade' AND column_name = 'slot'"
        ))
        if result.fetchone() is None:
            print("[MIGRATION] Adding paper_trade.slot ...")
            db.execute(text(
                "ALTER TABLE paper_trade ADD COLUMN slot VARCHAR(20)"
            ))
            print("[MIGRATION] ✅ paper_trade.slot added.")
        else:
            print("[MIGRATION] paper_trade.slot already exists, skipping.")

        db.commit()
        print("\n[MIGRATION] ✅ Migration v1.7 terminée avec succès !")
    except Exception as e:
        db.rollback()
        print(f"\n[MIGRATION] ❌ Erreur: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate()

