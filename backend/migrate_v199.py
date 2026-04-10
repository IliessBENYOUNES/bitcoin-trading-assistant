"""Migration v1.9.9 — Ajouter les colonnes quality gate à tick_activity_log."""
import sqlite3
import os

NEW_COLS = [
    ("market_quality_score", "INTEGER"),
    ("volume_ratio", "REAL"),
    ("price_position_pct", "REAL"),
    ("range_width_atr", "REAL"),
    ("micro_trend_score", "INTEGER"),
    ("vwap_distance_pct", "REAL"),
    ("quality_gate_passed", "INTEGER"),
    ("quality_gate_reason", "VARCHAR(500)"),
]

def migrate(db_path):
    if not os.path.exists(db_path):
        print(f"  {db_path} n'existe pas, skip")
        return
    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "tick_activity_log" not in tables:
        print(f"  {db_path}: pas de table tick_activity_log, skip")
        conn.close()
        return
    existing = [row[1] for row in conn.execute("PRAGMA table_info(tick_activity_log)").fetchall()]
    added = 0
    for col_name, col_type in NEW_COLS:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE tick_activity_log ADD COLUMN {col_name} {col_type}")
            print(f"  + {col_name} ({col_type})")
            added += 1
    conn.commit()
    conn.close()
    print(f"  {db_path}: {added} colonnes ajoutees")

if __name__ == "__main__":
    print("Migration v1.9.9 — quality gate columns")
    migrate("test.db")
    migrate(os.path.join("..", "test.db"))
    print("Done.")

