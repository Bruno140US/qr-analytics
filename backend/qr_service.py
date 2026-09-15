import io
import uuid

import qrcode
from fastapi import HTTPException

from database import get_connection


def _generate_unique_qr_id(conn) -> str:
    """Gera um qr_id curto (8 chars) garantindo que não existe no banco."""
    for _ in range(5):
        candidate = uuid.uuid4().hex[:8]
        exists = conn.execute(
            "SELECT 1 FROM qr_codes WHERE qr_id = ?", (candidate,)
        ).fetchone()
        if not exists:
            return candidate
    raise HTTPException(status_code=500, detail="Não foi possível gerar um ID único")


def create_qr(destination_url: str, name: str | None, base_url: str) -> dict:
    """Cria um novo QR Code no banco e retorna os dados + URL de rastreamento."""
    conn = get_connection()
    try:
        qr_id = _generate_unique_qr_id(conn)
        conn.execute(
            "INSERT INTO qr_codes (qr_id, destination_url, name) VALUES (?, ?, ?)",
            (qr_id, destination_url, name),
        )
        conn.commit()

        return {
            "qr_id": qr_id,
            "destination_url": destination_url,
            "name": name,
            "tracking_url": f"{base_url}/r/{qr_id}",
        }
    finally:
        conn.close()


def get_qr(qr_id: str) -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT qr_id, destination_url, name, created_at FROM qr_codes WHERE qr_id = ?",
            (qr_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_qr(qr_id: str, destination_url: str | None, name: str | None) -> dict:
    """Atualiza os campos informados. Campos None são ignorados."""
    conn = get_connection()
    try:
        current = conn.execute(
            "SELECT qr_id, destination_url, name, created_at FROM qr_codes WHERE qr_id = ?",
            (qr_id,),
        ).fetchone()
        if current is None:
            raise HTTPException(status_code=404, detail="QR Code não encontrado")

        new_url = destination_url if destination_url is not None else current["destination_url"]
        new_name = name if name is not None else current["name"]

        conn.execute(
            "UPDATE qr_codes SET destination_url = ?, name = ? WHERE qr_id = ?",
            (new_url, new_name, qr_id),
        )
        conn.commit()

        return {
            "qr_id": qr_id,
            "destination_url": new_url,
            "name": new_name,
            "created_at": current["created_at"],
        }
    finally:
        conn.close()


def delete_qr(qr_id: str) -> int:
    """
    Remove o QR e todos os scans associados.
    Retorna o número de scans removidos.
    """
    conn = get_connection()
    try:
        exists = conn.execute(
            "SELECT 1 FROM qr_codes WHERE qr_id = ?", (qr_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="QR Code não encontrado")

        scans_deleted = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE qr_id = ?", (qr_id,)
        ).fetchone()[0]

        conn.execute("DELETE FROM scans WHERE qr_id = ?", (qr_id,))
        conn.execute("DELETE FROM qr_codes WHERE qr_id = ?", (qr_id,))
        conn.commit()

        return scans_deleted
    finally:
        conn.close()


def get_qr_analytics(qr_id: str) -> dict:
    """Estatísticas completas de um QR específico."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT qr_id, destination_url, name, created_at FROM qr_codes WHERE qr_id = ?",
            (qr_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="QR Code não encontrado")

        total = conn.execute(
            "SELECT COUNT(*) FROM scans WHERE qr_id = ?", (qr_id,)
        ).fetchone()[0]

        unique = conn.execute(
            """
            SELECT COUNT(DISTINCT ip || '|' || COALESCE(device, '') || '|' || COALESCE(os, ''))
            FROM scans
            WHERE qr_id = ? AND ip IS NOT NULL
            """,
            (qr_id,),
        ).fetchone()[0]

        daily = [dict(r) for r in conn.execute(
            """
            SELECT DATE(timestamp) as date, COUNT(*) as scans
            FROM scans
            WHERE qr_id = ? AND timestamp >= DATE('now', '-30 days')
            GROUP BY DATE(timestamp)
            ORDER BY date
            """,
            (qr_id,),
        ).fetchall()]

        cities = [dict(r) for r in conn.execute(
            """
            SELECT city, country, COUNT(*) as scans
            FROM scans
            WHERE qr_id = ? AND city IS NOT NULL AND city != ''
            GROUP BY city, country
            ORDER BY scans DESC
            LIMIT 10
            """,
            (qr_id,),
        ).fetchall()]

        devices = [dict(r) for r in conn.execute(
            """
            SELECT COALESCE(device, 'Desconhecido') as device, COUNT(*) as scans
            FROM scans WHERE qr_id = ?
            GROUP BY device ORDER BY scans DESC
            """,
            (qr_id,),
        ).fetchall()]

        return {
            "qr": dict(row),
            "total_scans": total,
            "unique_scans": unique,
            "daily": daily,
            "cities": cities,
            "devices": devices,
        }
    finally:
        conn.close()


def generate_qr_png(data: str, box_size: int = 10) -> bytes:
    """Gera o PNG do QR Code em memória a partir de uma string."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=3,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()