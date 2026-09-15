import logging
import os
import re
import secrets
from datetime import datetime, timedelta

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address


# Carrega .env da raiz do projeto
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------

logger = logging.getLogger("qr_analytics")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# -----------------------------------------------------------------------------
# Rate limiting
# -----------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)


# -----------------------------------------------------------------------------
# Autenticação HTTP Basic (dashboard + endpoints de admin)
# -----------------------------------------------------------------------------

security = HTTPBasic()

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "troque-esta-senha")


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Verifica usuário/senha via HTTP Basic.
    Usa compare_digest para evitar timing attacks.
    """
    user_ok = secrets.compare_digest(credentials.username, ADMIN_USER)
    pass_ok = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)

    if not (user_ok and pass_ok):
        logger.warning(
            "Falha de autenticação: user=%r ip=%s",
            credentials.username,
            # request não está acessível aqui sem injeção; deixa no log do endpoint
            "-",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# -----------------------------------------------------------------------------
# Mascaramento de IP (LGPD)
# -----------------------------------------------------------------------------

_IPV4_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


def mask_ip(ip: str | None) -> str | None:
    """
    Mascara a parte final do IP para exibição:
      - IPv4: 191.32.108.7   -> 191.32.108.x
      - IPv6: 2001:db8::1    -> 2001:db8::x
    Retorna None para IP vazio/None.
    """
    if not ip:
        return None

    m = _IPV4_RE.match(ip)
    if m:
        return f"{m.group(1)}.{m.group(2)}.{m.group(3)}.x"

    # IPv6 simplificado: troca o último grupo por "x"
    if ":" in ip:
        parts = ip.split(":")
        if len(parts) > 1:
            parts[-1] = "x"
            return ":".join(parts)
    return "x.x.x.x"


# -----------------------------------------------------------------------------
# Retenção de dados
# -----------------------------------------------------------------------------

RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "180"))


def purge_old_scans(days: int = RETENTION_DAYS) -> int:
    """
    Remove scans mais antigos que `days` dias.
    Retorna a quantidade de registros removidos.
    """
    from database import get_connection
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM scans WHERE timestamp < ?", (cutoff,))
        removed = cur.rowcount
        conn.commit()
        if removed:
            logger.info("Retenção: %s scans removidos (mais antigos que %s)", removed, cutoff)
        return removed
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Segurança de URL
# -----------------------------------------------------------------------------

SAFE_SCHEMES = ("http", "https")


def is_safe_url(url: str | None) -> bool:
    """
    Bloqueia esquemas perigosos no redirect (javascript:, data:, file:, etc.).
    Rejeita também URLs vazias.
    """
    if not url or not isinstance(url, str):
        return False
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    return parsed.scheme in SAFE_SCHEMES and bool(parsed.netloc)