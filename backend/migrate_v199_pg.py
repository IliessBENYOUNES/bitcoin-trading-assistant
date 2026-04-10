"""Migration v1.9.9 PostgreSQL — Ajouter les colonnes quality gate à tick_activity_log."""
from app.database import engine
from sqlalchemy import text

NEW_COLS = [
    ("market_quality_score", "INTEGER"),
    ("volume_ratio", "DOUBLE PRECISION"),
    ("price_position_pct", "DOUBLE PRECISION"),
    ("range_width_atr", "DOUBLE PRECISION"),
    ("micro_trend_score", "INTEGER"),
    ("vwap_distance_pct", "DOUBLE PRECISION"),
    ("quality_gate_passed", "INTEGER"),
    ("quality_gate_reason", "VARCHAR(500)"),
]

def migrate():
    with engine.connect() as conn:
        # Get existing columns
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'tick_activity_log'"
        ))
        existing = [row[0] for row in result.fetchall()]
        print(f"Existing columns ({len(existing)}): {existing}")

        added = 0
        for col_name, col_type in NEW_COLS:
            if col_name not in existing:
                sql = f"ALTER TABLE tick_activity_log ADD COLUMN {col_name} {col_type}"
                conn.execute(text(sql))
                print(f"  + Added: {col_name} ({col_type})")
                added += 1
            else:
                print(f"  = Already exists: {col_name}")

        conn.commit()
        print(f"\nPostgreSQL migration v1.9.9 done. {added} columns added.")

if __name__ == "__main__":
    migrate()

