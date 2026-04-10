"""Migration v2.0.0 PostgreSQL — Colonnes economic viability + rejection_category."""
from app.database import engine
from sqlalchemy import text

NEW_COLS = [
    ("estimated_round_trip_cost", "DOUBLE PRECISION"),
    ("min_capture_required_pct", "DOUBLE PRECISION"),
    ("economic_gate_passed", "INTEGER"),
    ("rejection_category", "VARCHAR(30)"),
]

def migrate():
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'tick_activity_log'"
        ))
        existing = [row[0] for row in result.fetchall()]
        print(f"Existing columns ({len(existing)})")

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
        print(f"\nPostgreSQL migration v2.0.0 done. {added} columns added.")

if __name__ == "__main__":
    migrate()

