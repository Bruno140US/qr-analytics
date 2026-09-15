import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "analytics.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coltype: str) -> None:
    """Adiciona uma coluna se ela ainda não existir (migração leve)."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


def init_db() -> None:
    """Cria tabelas se não existirem e roda migrações leves."""
    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS qr_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qr_id TEXT UNIQUE NOT NULL,
                destination_url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                qr_id TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip TEXT,
                country TEXT,
                region TEXT,
                city TEXT,
                device TEXT,
                os TEXT,
                browser TEXT,
                FOREIGN KEY (qr_id) REFERENCES qr_codes(qr_id)
            );

            CREATE INDEX IF NOT EXISTS idx_scans_qr_id ON scans(qr_id);
            CREATE INDEX IF NOT EXISTS idx_scans_timestamp ON scans(timestamp);

            CREATE TABLE IF NOT EXISTS geolocation_cache (
                ip TEXT PRIMARY KEY,
                country TEXT,
                region TEXT,
                city TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        # Migrações leves (FASE 10 + FASE 11)
        _ensure_column(conn, "qr_codes", "name", "TEXT")
        _ensure_column(conn, "scans", "user_agent", "TEXT")
        _ensure_column(conn, "scans", "visitor_hash", "TEXT")

        # Índice para acelerar COUNT(DISTINCT visitor_hash)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scans_visitor_hash ON scans(visitor_hash)"
        )

        conn.commit()
    finally:
        conn.close()