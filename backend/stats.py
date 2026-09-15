from fastapi import APIRouter, Depends, Query

from database import get_connection
from security import require_auth


router = APIRouter(prefix="/api", tags=["analytics"], dependencies=[Depends(require_auth)])


UNIQUE_EXPR = """COUNT(DISTINCT COALESCE(
    visitor_hash,
    ip || '|' || COALESCE(device, '') || '|' || COALESCE(os, '')
))"""


@router.get("/stats")
def get_stats():
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE DATE(timestamp) = DATE('now')"
        ).fetchone()[0]
        last_7 = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE timestamp >= DATE('now', '-7 days')"
        ).fetchone()[0]
        unique = conn.execute(
            f"SELECT {UNIQUE_EXPR} FROM scans WHERE ip IS NOT NULL"
        ).fetchone()[0]
        unique_today = conn.execute(
            f"SELECT {UNIQUE_EXPR} FROM scans WHERE ip IS NOT NULL AND DATE(timestamp) = DATE('now')"
        ).fetchone()[0]
        unique_7 = conn.execute(
            f"SELECT {UNIQUE_EXPR} FROM scans WHERE ip IS NOT NULL AND timestamp >= DATE('now', '-7 days')"
        ).fetchone()[0]
        total_qr = conn.execute("SELECT COUNT(*) FROM qr_codes").fetchone()[0]

        return {
            "total_scans": total,
            "unique_scans": unique,
            "unique_today": unique_today,
            "unique_last_7_days": unique_7,
            "today": today,
            "last_7_days": last_7,
            "total_qr_codes": total_qr,
        }
    finally:
        conn.close()


@router.get("/scans/daily")
def get_scans_daily(days: int = Query(30, ge=1, le=365)):
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT DATE(timestamp) as date, COUNT(*) as scans
            FROM scans
            WHERE timestamp >= DATE('now', ?)
            GROUP BY DATE(timestamp)
            ORDER BY date
            """,
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/scans/unique-daily")
def get_unique_daily(days: int = Query(30, ge=1, le=365)):
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""
            SELECT DATE(timestamp) as date,
                   COUNT(*) as scans,
                   {UNIQUE_EXPR} as unique_visitors
            FROM scans
            WHERE timestamp >= DATE('now', ?)
            GROUP BY DATE(timestamp)
            ORDER BY date
            """,
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/scans/cities")
def get_scans_cities(limit: int = Query(10, ge=1, le=100)):
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT city, country, COUNT(*) as scans
            FROM scans
            WHERE city IS NOT NULL AND city != ''
            GROUP BY city, country
            ORDER BY scans DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/scans/devices")
def get_scans_devices():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT COALESCE(device, 'Desconhecido') as device, COUNT(*) as scans
            FROM scans GROUP BY device ORDER BY scans DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/scans/os")
def get_scans_os():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT COALESCE(os, 'Desconhecido') as os, COUNT(*) as scans
            FROM scans GROUP BY os ORDER BY scans DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/scans/browsers")
def get_scans_browsers():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT COALESCE(browser, 'Desconhecido') as browser, COUNT(*) as scans
            FROM scans GROUP BY browser ORDER BY scans DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/qr_codes/ranking")
def get_qr_ranking():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT q.qr_id, q.name, q.destination_url, q.created_at,
                   COUNT(s.id) as scans
            FROM qr_codes q
            LEFT JOIN scans s ON s.qr_id = q.qr_id
            GROUP BY q.qr_id
            ORDER BY scans DESC, q.created_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()