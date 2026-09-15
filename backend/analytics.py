import hashlib
import ipaddress
from datetime import datetime, timedelta
from typing import Optional

import requests
from user_agents import parse as parse_user_agent_string
from fastapi import Request

from database import get_connection


# -----------------------------------------------------------------------------
# Configuração
# -----------------------------------------------------------------------------

CACHE_TTL_DAYS = 7
GEO_API_TIMEOUT = 3
GEO_API_URL = "http://ip-api.com/json/{ip}"
GEO_API_FIELDS = "status,country,regionName,city"


# -----------------------------------------------------------------------------
# Normalização de nomes
# -----------------------------------------------------------------------------

OS_NORMALIZATION = {
    "Mac OS X": "macOS",
    "Ubuntu": "Linux",
    "Debian": "Linux",
    "Fedora": "Linux",
    "Arch Linux": "Linux",
    "Chrome OS": "ChromeOS",
}

BROWSER_NORMALIZATION = {
    "Mobile Safari": "Safari",
    "Mobile Safari UI/WKWebView": "Safari (WebView)",
    "Chrome Mobile": "Chrome",
    "Chrome Mobile iOS": "Chrome",
    "Firefox Mobile": "Firefox",
    "Edge Mobile": "Edge",
    "Samsung Browser": "Samsung Internet",
    "MIUI Browser": "MIUI Browser",
    "Opera Mini": "Opera",
    "Opera Mobile": "Opera",
}


def _normalize_os(os_family: str) -> str:
    if not os_family:
        return "Desconhecido"
    return OS_NORMALIZATION.get(os_family, os_family)


def _normalize_browser(browser_family: str) -> str:
    if not browser_family:
        return "Desconhecido"
    return BROWSER_NORMALIZATION.get(browser_family, browser_family)


def _detect_device(ua, user_agent_string: str) -> str:
    ua_lower = user_agent_string.lower()

    if "ipad" in ua_lower:
        return "iPad"
    if "iphone" in ua_lower:
        return "iPhone"
    if "ipod" in ua_lower:
        return "iPod"

    if "android" in ua_lower:
        if ua.is_tablet:
            return "Tablet Android"
        brand = ua.device.brand
        if brand and brand.lower() not in ("generic", "android"):
            return f"Android ({brand})"
        return "Android"

    if "macintosh" in ua_lower and "mobile" in ua_lower:
        return "iPad"

    if ua.is_mobile:
        return "Mobile"
    if ua.is_tablet:
        return "Tablet"
    if ua.is_pc:
        return "Desktop"
    if ua.is_bot:
        return "Bot"

    return "Outro"


def parse_user_agent(user_agent: str) -> dict:
    if not user_agent:
        return {
            "device": "Desconhecido",
            "os": "Desconhecido",
            "browser": "Desconhecido",
        }
    ua = parse_user_agent_string(user_agent)
    return {
        "device": _detect_device(ua, user_agent),
        "os": _normalize_os(ua.os.family),
        "browser": _normalize_browser(ua.browser.family),
    }


# -----------------------------------------------------------------------------
# IP
# -----------------------------------------------------------------------------

def is_private_ip(ip: str) -> bool:
    if not ip:
        return True
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return True


def get_client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip"):
        value = request.headers.get(header)
        if value:
            return value.strip()

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else ""


# -----------------------------------------------------------------------------
# Visitante único (FASE 11)
# -----------------------------------------------------------------------------

def compute_visitor_hash(ip: str, user_agent: str) -> str:
    """
    Gera um hash de identificação aproximada de visitante.

    Combina IP + User-Agent completo:
      - Duas visitas do mesmo dispositivo na mesma rede -> mesmo hash
      - Mesmo dispositivo trocando de rede (Wi-Fi -> 4G) -> hashes diferentes
      - Vários dispositivos no mesmo IP (NAT de empresa/escola) -> hashes diferentes

    Não é identificação perfeita. Ver LIMITAÇÕES no README.

    Usa SHA-256 truncado em 32 chars (128 bits) — suficiente e compacto.
    """
    raw = f"{ip or ''}||{user_agent or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# -----------------------------------------------------------------------------
# Geolocalização com cache
# -----------------------------------------------------------------------------

def _fetch_location_from_api(ip: str) -> Optional[dict]:
    try:
        response = requests.get(
            GEO_API_URL.format(ip=ip),
            params={"fields": GEO_API_FIELDS},
            timeout=GEO_API_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "success":
            return None

        return {
            "country": data.get("country") or None,
            "region": data.get("regionName") or None,
            "city": data.get("city") or None,
        }
    except (requests.RequestException, ValueError):
        return None


def _read_cache(ip: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT country, region, city, updated_at
            FROM geolocation_cache
            WHERE ip = ?
            """,
            (ip,),
        ).fetchone()

        if row is None:
            return None

        updated_at = datetime.fromisoformat(row["updated_at"])
        if datetime.utcnow() - updated_at > timedelta(days=CACHE_TTL_DAYS):
            return None

        return {
            "country": row["country"],
            "region": row["region"],
            "city": row["city"],
        }
    finally:
        conn.close()


def _write_cache(ip: str, location: dict) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO geolocation_cache (ip, country, region, city, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(ip) DO UPDATE SET
                country = excluded.country,
                region = excluded.region,
                city = excluded.city,
                updated_at = CURRENT_TIMESTAMP
            """,
            (ip, location.get("country"), location.get("region"), location.get("city")),
        )
        conn.commit()
    finally:
        conn.close()


def get_location_from_ip(ip: str) -> dict:
    empty = {"country": None, "region": None, "city": None}

    if not ip or is_private_ip(ip):
        return empty

    cached = _read_cache(ip)
    if cached is not None:
        return cached

    location = _fetch_location_from_api(ip)
    if location is None:
        return empty

    _write_cache(ip, location)
    return location