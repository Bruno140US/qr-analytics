"""
Exporta o banco SQLite local para um dump SQL compatível com o Cloudflare D1.

- Escreve em UTF-8 (sem BOM) — corrige acentos corrompidos
- Remove BEGIN/COMMIT
- Remove PRAGMA writable_schema e manipulação de sqlite_sequence
- Mantém apenas CREATE TABLE, CREATE INDEX e INSERT
"""

import sqlite3
from pathlib import Path


# Ajuste se o caminho for diferente
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "analytics.db"
OUT_PATH = Path(__file__).resolve().parent / "db_dump.sql"


def main():
    if not DB_PATH.exists():
        print(f"ERRO: banco não encontrado em {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as f:
            for line in conn.iterdump():
                stripped = line.strip().upper()

                # Pula comandos que o D1 não aceita
                if stripped.startswith("BEGIN TRANSACTION"):
                    continue
                if stripped.startswith("COMMIT"):
                    continue
                if stripped.startswith("PRAGMA"):
                    continue
                if "SQLITE_SEQUENCE" in stripped:
                    continue
                if stripped.startswith("DELETE FROM SQLITE_SEQUENCE"):
                    continue

                f.write(line + "\n")

        print(f"Dump gerado em: {OUT_PATH}")
        print(f"Tamanho: {OUT_PATH.stat().st_size} bytes")
    finally:
        conn.close()


if __name__ == "__main__":
    main()