from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import (
    HTMLResponse, JSONResponse, RedirectResponse, Response,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from database import get_connection, init_db
from analytics import (
    parse_user_agent,
    get_location_from_ip,
    get_client_ip,
    compute_visitor_hash,
)
from security import (
    limiter,
    require_auth,
    mask_ip,
    is_safe_url,
    purge_old_scans,
    logger,
)
from stats import router as stats_router
from models import QRCodeCreate, QRCodeUpdate
from qr_service import (
    create_qr,
    get_qr,
    update_qr,
    delete_qr,
    get_qr_analytics,
    generate_qr_png,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("QR Analytics iniciado")
    yield
    logger.info("QR Analytics finalizado")


app = FastAPI(
    title="QR Analytics",
    description="API de rastreamento de QR Codes",
    version="0.4.0",
    lifespan=lifespan,
    docs_url=None,          # desabilitado por padrão; rota customizada abaixo
    redoc_url=None,
    openapi_url=None,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Registra o roteador de analytics (/api/stats, /api/scans/...)
app.include_router(stats_router)


# -----------------------------------------------------------------------------
# Middleware: headers de segurança + tratamento de erro
# -----------------------------------------------------------------------------

@app.middleware("http")
async def security_headers(request: Request, call_next):
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception(
            "Erro não tratado em %s %s: %s", request.method, request.url.path, exc
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno do servidor"},
        )

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'"
    )
    return response


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def get_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get(
        "x-forwarded-host",
        request.headers.get("host", "localhost:8000"),
    )
    return f"{proto}://{host}".rstrip("/")


QR_NOT_FOUND_HTML = """
<!doctype html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <title>QR Code não encontrado</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body {
            font-family: system-ui, -apple-system, sans-serif;
            background: #0b1220;
            color: #e6edf7;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            text-align: center;
            padding: 24px;
        }
        .box { max-width: 420px; }
        h1 { font-size: 20px; margin-bottom: 8px; font-weight: 600; }
        p { color: #94a3b8; line-height: 1.6; margin: 8px 0; }
        a { color: #3b82f6; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="box">
        <h1>QR Code não encontrado</h1>
        <p>Este QR Code não existe, foi removido ou está incorreto.</p>
        <p><a href="/">Ir para a página inicial</a></p>
    </div>
</body>
</html>
"""


# -----------------------------------------------------------------------------
# Rota raiz — pública, redireciona para o dashboard
# -----------------------------------------------------------------------------

@app.get("/")
def root():
    return RedirectResponse(url="/dashboard/")


# -----------------------------------------------------------------------------
# Endpoint PÚBLICO: o QR aponta para cá
# -----------------------------------------------------------------------------

@app.get("/r/{qr_id}")
@limiter.limit("60/minute")
def redirect_qr(qr_id: str, request: Request):
    """
    Endpoint que o QR aponta. É o único público.
    - Rate limit: 60 req/min por IP
    - Valida a URL de destino antes de redirecionar (anti open-redirect)
    - Só redireciona se o destino for http/https
    - Retorna HTML amigável se o QR não existe
    """
    # Sanitização básica do identificador
    if not qr_id or len(qr_id) > 64 or not qr_id.isalnum():
        return HTMLResponse(status_code=404, content=QR_NOT_FOUND_HTML)

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT destination_url FROM qr_codes WHERE qr_id = ?",
            (qr_id,),
        ).fetchone()

        if row is None:
            return HTMLResponse(status_code=404, content=QR_NOT_FOUND_HTML)

        destination_url = row["destination_url"]

        # Blindagem extra: mesmo que alguém insira URL inválida no banco,
        # nunca redirecionamos para esquemas perigosos (javascript:, data:, etc.)
        if not is_safe_url(destination_url):
            logger.warning(
                "Redirect bloqueado: qr_id=%s url=%r", qr_id, destination_url
            )
            raise HTTPException(status_code=500, detail="Destino inválido")

        user_agent = request.headers.get("user-agent", "")
        client_ip = get_client_ip(request)

        ua_info = parse_user_agent(user_agent)
        location = get_location_from_ip(client_ip)
        visitor_hash = compute_visitor_hash(client_ip, user_agent)

        conn.execute(
            """
            INSERT INTO scans
                (qr_id, ip, user_agent, visitor_hash,
                 country, region, city, device, os, browser)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                qr_id, client_ip, user_agent, visitor_hash,
                location["country"], location["region"], location["city"],
                ua_info["device"], ua_info["os"], ua_info["browser"],
            ),
        )
        conn.commit()

        return RedirectResponse(url=destination_url, status_code=302)
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# CRUD de QR Codes (protegido por Basic Auth)
# -----------------------------------------------------------------------------

@app.get("/api/qr_codes")
def list_qr_codes(_user: str = Depends(require_auth)):
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT q.qr_id, q.destination_url, q.name, q.created_at,
                   COUNT(s.id) as scans
            FROM qr_codes q
            LEFT JOIN scans s ON s.qr_id = q.qr_id
            GROUP BY q.qr_id
            ORDER BY q.created_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@app.post("/api/qr_codes", status_code=201)
def create_qr_endpoint(
    payload: QRCodeCreate,
    request: Request,
    _user: str = Depends(require_auth),
):
    base_url = get_base_url(request)
    return create_qr(payload.destination_url, payload.name, base_url)


@app.get("/api/qr_codes/{qr_id}")
def get_qr_endpoint(qr_id: str, _user: str = Depends(require_auth)):
    qr = get_qr(qr_id)
    if qr is None:
        raise HTTPException(status_code=404, detail="QR Code não encontrado")
    return qr


@app.put("/api/qr_codes/{qr_id}")
def update_qr_endpoint(
    qr_id: str,
    payload: QRCodeUpdate,
    _user: str = Depends(require_auth),
):
    return update_qr(qr_id, payload.destination_url, payload.name)


@app.delete("/api/qr_codes/{qr_id}")
def delete_qr_endpoint(qr_id: str, _user: str = Depends(require_auth)):
    scans_deleted = delete_qr(qr_id)
    return {"ok": True, "scans_deleted": scans_deleted}


@app.get("/api/qr_codes/{qr_id}/analytics")
def qr_analytics_endpoint(qr_id: str, _user: str = Depends(require_auth)):
    return get_qr_analytics(qr_id)


@app.get("/api/qr_codes/{qr_id}/image")
def qr_image_endpoint(
    qr_id: str,
    request: Request,
    size: int = Query(10, ge=3, le=30),
    _user: str = Depends(require_auth),
):
    qr = get_qr(qr_id)
    if qr is None:
        raise HTTPException(status_code=404, detail="QR Code não encontrado")

    tracking_url = f"{get_base_url(request)}/r/{qr_id}"
    png_bytes = generate_qr_png(tracking_url, box_size=size)

    filename = f'qr_{qr_id}.png'
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# -----------------------------------------------------------------------------
# Scans (protegido, com IP mascarado)
# -----------------------------------------------------------------------------

@app.get("/api/scans")
def list_scans(limit: int = 50, _user: str = Depends(require_auth)):
    """
    Lista os scans recentes.
    O IP é retornado MASCARADO (ex: 191.32.108.x) por LGPD.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, qr_id, timestamp, ip, user_agent, visitor_hash,
                   country, region, city, device, os, browser
            FROM scans
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        out = []
        for r in rows:
            d = dict(r)
            d["ip"] = mask_ip(d.get("ip"))
            out.append(d)
        return out
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# Admin: retenção de dados
# -----------------------------------------------------------------------------

@app.post("/api/admin/purge")
def admin_purge(
    days: int = Query(..., ge=1, le=3650),
    _user: str = Depends(require_auth),
):
    """
    Remove scans mais antigos que `days` dias.
    Requer autenticação. Uso:
      POST /api/admin/purge?days=180
    """
    removed = purge_old_scans(days)
    return {"ok": True, "removed": removed, "days": days}


# -----------------------------------------------------------------------------
# Debug (protegido)
# -----------------------------------------------------------------------------

class UAParseRequest(BaseModel):
    user_agent: str


@app.post("/api/debug/parse-ua")
def debug_parse_ua(payload: UAParseRequest, _user: str = Depends(require_auth)):
    return parse_user_agent(payload.user_agent)


# -----------------------------------------------------------------------------
# Docs (protegido — não expor publicamente em produção)
# -----------------------------------------------------------------------------

@app.get("/docs", include_in_schema=False)
def docs(_user: str = Depends(require_auth)):
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="QR Analytics — Docs",
    )


@app.get("/openapi.json", include_in_schema=False)
def openapi(_user: str = Depends(require_auth)):
    return app.openapi()


# -----------------------------------------------------------------------------
# Dashboard estático (precisa ser a ÚLTIMA coisa registrada)
# -----------------------------------------------------------------------------

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"

if DASHBOARD_DIR.exists():
    app.mount(
        "/dashboard",
        StaticFiles(directory=DASHBOARD_DIR, html=True),
        name="dashboard",
    )