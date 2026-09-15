"""
Script de limpeza de dados antigos.

Uso:
    python backend/cleanup.py            # usa RETENTION_DAYS do .env
    python backend/cleanup.py --days 90  # força 90 dias
    python backend/cleanup.py --dry-run  # mostra o que seria removido

Agende no Windows com o "Agendador de Tarefas" (Task Scheduler)
ou no Linux com cron:
    0 3 * * *  cd /caminho/qrcode && venv/bin/python backend/cleanup.py
"""
import argparse
from pathlib import Path
import sys

# Permite importar database/security como módulos do backend
sys.path.insert(0, str(Path(__file__).resolve().parent))

from security import purge_old_scans, RETENTION_DAYS, logger
from database import get_connection


def count_old(days: int) -> int:
    from datetime import datetime, timedelta
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM scans WHERE timestamp < ?", (cutoff,)
        ).fetchone()[0]
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Remove scans antigos.")
    parser.add_argument("--days", type=int, default=RETENTION_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        n = count_old(args.days)
        print(f"[dry-run] {n} scans seriam removidos (mais antigos que {args.days} dias).")
        return

    removed = purge_old_scans(args.days)
    print(f"{removed} scans removidos (mais antigos que {args.days} dias).")


if __name__ == "__main__":
    main()