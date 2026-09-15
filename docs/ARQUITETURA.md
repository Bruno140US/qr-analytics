# Arquitetura do QR Analytics

Documento técnico sobre as decisões de arquitetura, modelo de dados e fluxos do sistema.

## Visão geral

```
┌──────────────┐
│   Usuário    │
│  escaneia    │
│  o QR Code   │
└──────┬───────┘
       │ HTTPS
       ▼
┌─────────────────────┐
│  Cloudflare Tunnel  │  ← HTTPS + CDN (grátis, opcional)
└──────────┬──────────┘
           │ HTTP (localhost)
           ▼
┌──────────────────────────────────┐
│  FastAPI (uvicorn)               │
│  ├─ /r/{qr_id}   (público)       │
│  ├─ /api/*       (Basic Auth)    │
│  └─ /dashboard/  (estático)      │
└──────────┬───────────────────────┘
           │
   ┌───────┴────────┐
   │                │
   ▼                ▼
┌────────┐    ┌──────────────────┐
│ SQLite │    │ ip-api.com       │
│ (local)│    │ (geo por IP)     │
└────────┘    └──────────────────┘
```

## Fluxo de um scan (detalhado)

Quando o usuário escaneia o QR Code:

```
1. Celular lê o QR → contém https://SEU_DOMINIO/r/abc123
2. GET /r/abc123 chega ao FastAPI
3. Validação:
   a. qr_id tem formato válido? (8 chars alfanuméricos)
   b. Existe no banco?
4. Coleta de dados:
   a. IP real via header CF-Connecting-IP ou X-Forwarded-For
   b. User-Agent → parsed para device, OS, browser
   c. IP público → consulta ip-api.com (com cache de 7 dias)
   d. SHA-256(IP + UA) → visitor_hash
5. Persistência:
   INSERT INTO scans (qr_id, ip, user_agent, visitor_hash, country, ...)
6. Resposta:
   302 Redirect → destination_url
```

Ponto importante: **o visitante nunca vê a página intermediária**. Ele sai do QR e chega no site de destino sem perceber o rastreamento. Tudo acontece no servidor em ~50-100 ms.

## Modelo de dados

### Tabela `qr_codes`

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | Identificador interno |
| `qr_id` | TEXT UNIQUE NOT NULL | ID curto usado na URL (8 chars) |
| `destination_url` | TEXT NOT NULL | URL final após redirect |
| `name` | TEXT | Nome da campanha (opcional) |
| `created_at` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | Data de criação |

Índice implícito: `qr_id` (UNIQUE).

### Tabela `scans`

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | INTEGER PK AUTOINCREMENT | Identificador interno |
| `qr_id` | TEXT FK NOT NULL | Referência a `qr_codes.qr_id` |
| `timestamp` | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | Momento do scan |
| `ip` | TEXT | IP do visitante (completo, para retenção) |
| `user_agent` | TEXT | User-Agent completo |
| `visitor_hash` | TEXT | SHA-256(IP + UA), 32 chars |
| `country` | TEXT | País aproximado |
| `region` | TEXT | Estado/região |
| `city` | TEXT | Cidade |
| `device` | TEXT | Tipo de dispositivo (iPhone, Android, Desktop, ...) |
| `os` | TEXT | Sistema operacional |
| `browser` | TEXT | Navegador |

Índices: `qr_id`, `timestamp`, `visitor_hash` (criados explicitamente para acelerar agregações do dashboard).

### Tabela `geolocation_cache`

| Coluna | Tipo | Descrição |
|---|---|---|
| `ip` | TEXT PK | Chave de cache |
| `country`, `region`, `city` | TEXT | Dados geo |
| `updated_at` | TIMESTAMP | TTL de 7 dias |

Evita consultar a API externa repetidamente para o mesmo IP.

## Decisões arquiteturais

### Por que SQLite e não PostgreSQL?

**Contexto:** projeto pessoal, sem multiusuário, volume esperado < 100k scans/mês.

**Trade-offs:**

| SQLite | PostgreSQL |
|---|---|
| Zero configuração | Precisa de servidor |
| Um arquivo local | Serviço externo |
| Suficiente para até ~1M rows | Escala horizontal |
| Sem concorrência de escrita | Concorrência nativa |

**Decisão:** SQLite. A camada de acesso (`database.py`) isola o resto do código, então migrar para Postgres depois seria trocar ~50 linhas.

### Por que HTTP Basic Auth e não JWT?

**Contexto:** um único usuário admin, sem "login social", sem multiusuário.

**Trade-offs:**

| Basic Auth | JWT |
|---|---|
| Stateless, funciona com qualquer proxy | Precisa de refresh, revogação |
| Simples, sem biblioteca extra | Biblioteca pesada |
| Senha em Base64 (precisa HTTPS) | Token assinado |

**Decisão:** Basic Auth. Cloudflare Tunnel fornece HTTPS automático, o que elimina o único ponto fraco do Basic Auth (transmissão em claro). Se o projeto crescer para multiusuário, migrar para JWT ou OAuth seria o próximo passo.

### Por que hash de IP+UA e não cookies?

**Contexto:** LGPD, sem rastreamento persistente entre sites.

**Trade-offs:**

| Hash de IP+UA | Cookie |
|---|---|
| Sem armazenamento no cliente | Armazena identificador |
| Não requer consentimento | Requer aviso de cookie |
| Aproximação (mesmo usuário trocando de rede → conta 2x) | Precisão alta |
| Funciona sem JavaScript | Depende de JS |

**Decisão:** hash. É aproximado, mas suficiente para analytics e alinhado com LGPD. Documentado em [LIMITACOES.md](../LIMITACOES.md).

### Por que Cloudflare Tunnel e não deploy em VM?

**Contexto:** portfólio / demo, sem orçamento para hospedagem.

**Trade-offs:**

| Tunnel | VM (VPS) |
|---|---|
| Grátis | R$ 20-50/mês |
| HTTPS automático | Precisa de Let's Encrypt |
| Zero configuração de firewall | Abrir portas |
| Depende do PC ligado | Sempre online |

**Decisão:** Tunnel. Para demonstração e portfólio, é perfeito. Se virar produto, migrar para VPS ou container em cloud (Fly.io, Railway, Render).

### Por que Chart.js via CDN?

**Contexto:** evitar etapa de build no frontend.

**Trade-offs:**

| CDN | Bundler (webpack, vite) |
|---|---|
| Sem `npm install` | Precisa de Node |
| Cache do navegador | Controle de versão exato |
| Um `<script>` e funciona | Requer build step |

**Decisão:** CDN. O objetivo é que quem clonar o repositório possa abrir e rodar com o mínimo de dependências.

## Camadas de segurança

| Camada | Implementação |
|---|---|
| **Transporte** | HTTPS via Cloudflare Tunnel |
| **Autenticação** | HTTP Basic Auth + compare_digest (anti timing attack) |
| **Autorização** | Endpoints `/api/*` protegidos; `/r/{qr_id}` público |
| **Rate limiting** | 60 req/min por IP (slowapi) |
| **Validação de entrada** | Pydantic (URLs, tipos, tamanhos) |
| **Sanitização de saída** | `escapeHtml()` no JS |
| **SQL Injection** | Queries parametrizadas em 100% dos acessos |
| **Open redirect** | Validação de esquema http/https na URL de destino |
| **CSRF** | Não aplicável (Basic Auth não usa cookies) |
| **Headers HTTP** | CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy |
| **LGPD** | IP mascarado na API (`191.32.108.x`) |
| **Retenção** | Script `cleanup.py` + endpoint `/api/admin/purge` |

## Limitações conhecidas

1. **Únicos aproximados:** duas visitas do mesmo dispositivo em redes diferentes contam como 2. Duas visitas de dispositivos diferentes no mesmo IP+UA contam como 1.
2. **Geolocalização por IP:** precisão de cidade/região aproximada. Sem GPS.
3. **Cache em memória do rate limiter:** reiniciar o servidor reseta contadores.
4. **Sem HTTPS nativo:** depende do Cloudflare Tunnel ou de um proxy reverso configurado à mão.
5. **Escala vertical:** SQLite é suficiente até certo volume. Acima disso, migrar para Postgres.

## Como estender

| Extensão | Como implementar |
|---|---|
| Migrar para Postgres | Trocar `database.py`, ajustar dialeto SQL |
| Multiusuário | Adicionar tabela `users`, trocar Basic por JWT |
| Deploy em produção | Docker + Fly.io/Railway + Postgres + Redis |
| Cache de geo em Redis | Trocar tabela `geolocation_cache` por Redis com TTL nativo |
| Filtros no dashboard | Query params em `/api/scans/daily?from=&to=` |
| Exportar CSV | Endpoint `/api/scans/export` retornando `text/csv` |
| Notificações | Webhook ao atingir N scans por QR Code |

## Referências

- [FastAPI docs](https://fastapi.tiangolo.com/)
- [SQLite docs](https://www.sqlite.org/docs.html)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [OWASP Secure Headers](https://owasp.org/www-project-secure-headers/)
- [LGPD - Lei 13.709/2018](http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm)