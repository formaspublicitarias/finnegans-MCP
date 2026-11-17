# Finnegans MCP — online version, adapted per person (design)

Date: 2026-11-17 · Author: Juan Sbatella (with Claude)
Builds on: `2026-11-02-finnegans-mcp-extension-design.md` (the desktop extension, v1.0.2)

## 1. Intent

Today the Finnegans assistant runs as a Claude Desktop extension
(`finnegans.mcpb`). Each person installs it on their PC and types their own
Finnegans API keys into a form. It works, but only on a PC where it was
installed, never on the phone, and every person sees the whole API whether or not
their Finnegans account can use it.

The online version puts the same assistant on a public HTTPS address. Anyone at
SOUTEX or Formas adds it once in Claude (web, desktop or mobile), signs in with
their company Google account, and gets an assistant that only offers what
**their own** Finnegans account allows. Nothing is installed on anyone's device.

Why per person: Finnegans permissions differ by account. A restricted account
tested on 2026-11-17 was denied 100 of 238 reports and 13 of 126 entities.
Showing those endpoints to that person only produces dead ends and confusing
errors.

## 2. Goals

1. **No install, any device.** One connector URL that works in claude.ai,
   Claude Desktop and Claude mobile.
2. **Company sign-in.** People sign in with a Google account from either company
   domain. Only people an admin has added get in.
3. **Each person acts as themselves in Finnegans.** Every call uses that
   person's own Finnegans API keys, which an admin loads once. People never see
   or type keys.
4. **Adapted per person.** Search and `ver_endpoint` only show the endpoints that
   person's account can use. Permission refusals are explained in plain Spanish.
5. **Changes from day one.** `escribir` works online exactly as on desktop: it
   saves, then shows the diff. Each person's Finnegans permissions set the limits.
6. **Who did what.** Every change is logged with who, when, which record and the
   diff. Reads are logged without their data.
7. **One program, two ways to run it.** The same Python server runs as the
   desktop extension and as the online version, and fixes reach both.
8. **Stay at or near the $5 Workers Paid plan.** Target: no more than about $3 a
   month on top (§14).

## 3. Non-goals

- **Narrow versions** (`/mcp/facturar`, `/mcp/compras`, …). Finnegans
  permissions already narrow what each person can do, and guidance for a
  specific job comes from skills each person writes in Claude. The design leaves
  room to add a guided version at its own URL later, but none is built now.
- **`exportar` online.** The online version has no export tool and no file
  storage. The desktop extension keeps `exportar` unchanged.
- **Periodic permission scans.** Permissions rarely change in Finnegans. A scan
  runs when a person is added or their keys change, plus whenever an admin
  presses "Reescanear". Live calls correct the map in between (§8).
- **Probing write permissions up front.** There is no safe way to test a write
  without writing, so write permission is learned from real refusals only.
- **Rewriting the server in TypeScript**, or running it without a container.
- **One container per person.** It was considered first (§6) and dropped for cost.
- **Moving the desktop extension to its own repo.** It stays here and gets the
  same fixes.

## 4. Anti-goals (failure even if it technically works)

- One person seeing another person's tables, results, keys or log entries. With
  one shared server, this is the main risk. §11 and §15 exist to rule it out.
- A Finnegans key, token, swagger key or docs key appearing in any tool output,
  admin page, log line, audit entry or committed file.
- Someone who isn't on the admin's list using the connector.
- Someone who was removed from the list still using it after their next request.
- A permission refusal reported as "your keys are wrong" or "a parameter is
  missing". Today's extension does this (§8.4).
- Permission scans putting real load on Finnegans' production system (§8.2).
- The desktop extension and the online version drifting into two programs.

## 5. Constraints and verified facts

**Cloudflare** (checked 2026-11-17)
- Containers have been generally available since 2026-04-13. They need the
  Workers Paid plan ($5/month), which runs in Rodrigo Mateus's Cloudflare
  account. Juan is already a member of that account.
- A container is reached only through a Durable Object. Cold start takes about
  1–3 s plus our own start-up work.
- Disk is ephemeral: a restarted container starts clean.
- An idle timeout stops the container (`setInactivityTimeout`, up to 6 h). On
  stop it gets SIGTERM, then SIGKILL after up to 15 min.
- Environment variables reach the container on `start()` through the `env`
  option. `enableInternet: true` is needed for Finnegans calls.
- Instance types:

  | Type | vCPU | Memory | Disk |
  |---|---|---|---|
  | `lite` | 1/16 | 256 MiB | 2 GB |
  | `basic` | 1/4 | 1 GiB | 4 GB |
  | `standard-1` | 1/2 | 4 GiB | 8 GB |

  Larger types also exist.
- Billing: memory and disk are billed while the container runs; CPU only while
  it's in use.
- Included per month in Workers Paid:
  - 25 GiB-h memory, then $0.0000025 per GiB-s (about $0.009 per GiB-hour);
  - 375 vCPU-min, then $0.000020 per vCPU-s;
  - 200 GB-h disk, then $0.00000007 per GB-s;
  - egress: 500 GB to 1 TB depending on region.
- Workers requests, Durable Objects, D1 and KV each have their own included
  amounts. At this scale they stay well inside them.
- `@cloudflare/workers-oauth-provider` implements the OAuth server side on a
  Worker:
  - client registration through DCR and through CIMD
    (`clientIdMetadataDocumentEnabled`, which needs the
    `global_fetch_strictly_public` compatibility flag);
  - PKCE;
  - it hands the signed-in user's props to the API handler;
  - its storage is a KV namespace bound as `OAUTH_KV`.

**Claude connectors** (checked 2026-11-17)
- claude.ai, Desktop and mobile share one OAuth client, with the callback
  `https://claude.ai/api/mcp/auth_callback`.
- Claude Code uses a loopback redirect on any port (`http://localhost/callback`,
  `http://127.0.0.1/callback`). Supporting it is cheap.
- Sign-in starts only on a **401** with
  `WWW-Authenticate: Bearer resource_metadata="…"`.
- The protected resource metadata's `resource` must equal the connector URL
  exactly. Claude uses only the first entry in `authorization_servers`.
- CIMD is used only if the authorization server metadata advertises both
  `client_id_metadata_document_supported: true` and `"none"` in
  `token_endpoint_auth_methods_supported`. Otherwise Claude falls back to DCR.
- PKCE S256 is required.
- The token endpoint must:
  - accept form-urlencoded bodies;
  - return `invalid_grant` for a dead refresh token;
  - rotate refresh tokens for public clients.
- Claude allows 10 s for discovery, registration and token calls, and 30 s for
  a refresh.
- Anthropic's outbound traffic comes from `160.79.104.0/21`.

**MCP Python SDK** (installed: `mcp` 2.3.0)
- `MCPServer.run(transport="streamable-http", host=…, port=…,
  stateless_http=…, json_response=…, transport_security=…)` exists.
- DNS-rebinding protection checks the Host header against `allowed_hosts`.
- Sync tools run in worker threads via `anyio.to_thread.run_sync`, which copies
  `contextvars`. So a per-request context variable set before the tool runs is
  visible inside it. The builder confirms this with a test.

**Finnegans** (verified live 2026-11-17, read-only; see memory
`finnegans-permisos-por-cuenta`)
- swaggerGlobal works only with the company docs key and returns the same 586
  paths for everyone. It rejects API tokens, so there is no per-account swagger.
- No endpoint lists an account's permissions.
- **Reports:** a denied account gets `403 "Forbidden: Prestacion sin permiso"`
  *before* parameter validation. An allowed account's report actually **runs**,
  even without parameters.
- **Entities:** `GET /{entidad}/ZZ-NOEXISTE` answers 404 when allowed, or 500
  `"No tiene permisos para transacciones de la categoría…"` when denied.
- A full scan is about 364 calls and took about 2 minutes. Write refusals have
  not been observed yet.

**Repo rules that carry over**
- Never read, print or commit `.env` values. Tests use fake credentials only.
- Admin emails and company domains live in deployment settings, never in code,
  docs or the `.mcpb`.
- No production writes from tests or scripts without Juan's explicit go.
- The redactor rule stays: **redact first, then truncate**.
- User-facing text is in Spanish (Argentina).

## 6. Approaches considered

| Approach | Trade-off | Verdict |
|---|---|---|
| **B. One shared server for everyone** (the standard design for remote MCP servers), behind a Worker that handles sign-in, admin and keys | One container, awake only during working hours, so cost stays near the plan (§14). The server must keep each person's token, tables and permission map apart in one process, which is real refactoring with isolation tests. | **Chosen by Juan** |
| A. One container per person | The server barely changes, and isolation comes from the design itself. Cost grows with every active person: about $15/month on top of the plan for 15 people at 4 h/day. | Rejected (cost; not the standard design) |
| C. Rewrite on Workers without containers | Loses DuckDB and the proven search and vocabulary logic for no gain. | Rejected |

Juan first chose A. After seeing the costs, and given that he prefers the
standard design, he switched to B.

## 7. Architecture

```
Claude (web / desktop / mobile)
   │  HTTPS, OAuth bearer token
   ▼
Worker  "finnegans-remoto"  (TypeScript)
   ├─ OAuth server for Claude (workers-oauth-provider: CIMD + DCR + PKCE)
   ├─ Google sign-in (OIDC) for people and for the admin page
   ├─ /admin        admin page (Juan, Rodrigo)
   ├─ /mcp          checks the person is active → forwards with internal headers
   ├─ /_interno/*   callbacks from the container (shared secret)
   ├─ audit log     written from the traffic it forwards
   ├─ D1            people, encrypted keys, permission maps, audit log
   └─ secrets       master key, Google client, swagger key, docs keys, internal secret
          │
          ▼
Durable Object "Servidor" (a single instance) → starts/stops the one container, forwards
          │
          ▼
Container (Python, same server as the .mcpb, started in online mode)
   ├─ MCPServer over streamable HTTP (stateless, JSON responses), 7 tools
   ├─ one Contexto per person: Finnegans client + token, DuckDB workspace, permission map
   ├─ shared by all: swagger catalog, docs search (same company keys for everyone)
   └─ permission scanner
          │
          ▼
api.finneg.com · swaggerGlobal · Finnegans docs MCP
```

### 7.1 Connector URL

At launch the URL is `https://finnegans-remoto.<subdomain>.workers.dev/mcp`. A
custom domain on a company zone can come later. Changing the URL means
everyone re-adds the connector, so do it before the team rollout or not at all.
*(Builder's call; noted.)*

### 7.2 Sign-in flow (people)

1. Claude calls `/mcp` without a token. The Worker answers **401** with
   `WWW-Authenticate: Bearer resource_metadata="https://…/.well-known/oauth-protected-resource"`.
   The metadata's `resource` is exactly the `/mcp` URL.
2. Claude registers, by CIMD if possible and otherwise by DCR, then opens
   `/authorize`.
3. The Worker's `/authorize` sends the person to Google OIDC.
   - There are two company domains (SOUTEX and Formas), so the Google OAuth
     client is **External**, with publishing status **In production**.
   - It asks only for `openid email profile`. These scopes are non-sensitive, so
     Google doesn't require app verification, and "In production" avoids the
     testing mode's 100-user cap.
   - No `hd` hint is sent.
4. On return, the Worker verifies the ID token: issuer, audience, and
   `email_verified = true`.
   - Both the `hd` claim **and** the email's domain must be in
     `ALLOWED_DOMAINS`, a comma-separated Worker variable set at deploy time
     (never committed). A personal `@gmail.com` account has no `hd` and is
     refused.
   - The real gate is the list of people. The Worker looks up the email in
     `personas`:
     - **active** → `completeAuthorization()` with props `{ email }`, then back
       to Claude.
     - **unknown or disabled** → a Spanish page: "Todavía no tenés acceso al
       asistente de Finnegans. Pedíselo a Juan o a Rodrigo." No token is issued.
       The names come from the `CONTACTO_ADMIN` variable.
5. **Every** `/mcp` request re-checks that the email is still active (a cached
   lookup of up to 60 s is fine). Removing someone takes effect on their next
   request. The Worker also tells the container to drop that person's context
   (`POST /_interno/olvidar`).

### 7.3 Admin page (`/admin`)

- **Access:**
  - Same Google sign-in, with a separate cookie session.
  - Only emails listed in the `ADMIN_EMAILS` secret (Juan and Rodrigo) get in.
    Everyone else gets 403.
  - Every write action carries a CSRF token.
  - The session cookie is `HttpOnly`, `Secure` and `SameSite=Lax`, and lasts
    8 h.
- **Screens** (Spanish, plain, phone-friendly):
  - **Personas:** a list with name, email, active, last use, and a permission
    summary such as "138 de 238 reportes · 113 de 126 entidades · escaneado el
    17/11". Actions: add, disable/enable, remove, and "Reescanear".
  - **Agregar / reemplazar claves:** email, name, Finnegans client ID and client
    secret.
    - Saving first checks the token against Finnegans and refuses keys that
      don't authenticate.
    - Saved secrets are never shown again: the fields are write-only and show
      only "cargada el 17/11/2026".
    - Saving new keys drops that person's context in the container and starts a
      scan.
  - **Registro:** the audit log, filterable by person, date, tool and "solo
    cambios".

### 7.4 Keys and secrets

- **Per person** (in D1): the Finnegans `client_id` and `client_secret`.
  - Each is encrypted with AES-256-GCM, using `MASTER_KEY` (a Worker secret) and
    a random nonce per value.
  - The AAD is the person's email, so a ciphertext copied to another row fails
    to decrypt.
  - A `clave_version` column allows rotating `MASTER_KEY` later.
- **Shared** (Worker secrets and variables only):
  - `FINNEGANS_SWAGGER_KEY`, `FINNEGANS_DOCS_CLIENT_ID`,
    `FINNEGANS_DOCS_SECRET_KEY`;
  - `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`;
  - `MASTER_KEY`, `INTERNAL_SECRET`;
  - `ADMIN_EMAILS`, `ALLOWED_DOMAINS`, `CONTACTO_ADMIN`.
- **The container** gets the shared Finnegans keys and `INTERNAL_SECRET` as env
  vars at start. These are the env vars `Settings.from_env` already reads, minus
  the per-person ones.
- **Per-person keys reach the container per request** (§7.5). They are decrypted
  by the Worker, sent only on the internal hop, and never logged by either side.
- Worker code never logs a URL with a query string, an env var, a header
  starting with `X-Finnegans-`, or a key column.

### 7.5 Worker → container

- **One Durable Object** (`idFromName("servidor")`) runs one container,
  instance `basic` (1 GiB).
- **Idle timeout:** 15 minutes. The container sleeps nights and weekends and
  wakes on the first request, which then waits a few extra seconds.
- **Readiness:** before forwarding, the Durable Object waits until `GET /salud`
  answers.
- **Start failure:** if the container can't start, the person gets a Spanish MCP
  error ("El asistente no pudo arrancar, probá de nuevo en un minuto"), never a
  raw 5xx page.
- **Forwarding** applies only to `/mcp`. The Worker **removes** any incoming
  `X-Finnegans-*` header, then adds:
  - `X-Finnegans-Persona: <email>`, taken from the verified OAuth props and never
    from anything the client sent;
  - `X-Finnegans-Client-Id` and `X-Finnegans-Client-Secret`, the person's keys,
    decrypted;
  - `X-Finnegans-Clave-Version` and `X-Finnegans-Permisos-Version`;
  - `X-Finnegans-Firma`: an HMAC-SHA256, keyed with `INTERNAL_SECRET`, over the
    email, both versions and a timestamp.
- **The container rejects any `/mcp` request** whose signature is missing, wrong,
  or more than 60 s old. Only the Durable Object can reach the container, so
  this is defence in depth.
- **Internal paths** (`/salud`, `/_interno/*`) are not reachable through the
  public `/mcp` route.
- **Transport:**
  - The container runs with `stateless_http=True, json_response=True`. No tool
    depends on MCP session state, because each person's tables belong to their
    `Contexto`, not to a session. A container restart therefore never breaks a
    conversation with "unknown session".
  - DNS-rebinding protection stays on, with `allowed_hosts` set to the host the
    Durable Object uses when forwarding.
  - The Durable Object's forward allows up to 240 s per request.

### 7.6 Container → Worker callbacks

The container calls the Worker at `/_interno/*`, with
`Authorization: Bearer <INTERNAL_SECRET>`:

- `GET /_interno/permisos?email=…` returns that person's permission map and its
  version.
- `POST /_interno/permisos` sends corrections learned from live calls:
  `{email, path, acceso, fuente}`.
- `POST /_interno/escaneo` delivers a finished scan: `{email, version, filas[]}`.

The Worker serves `/_interno/*` only when the bearer matches, and refuses it on
any other origin route. Corrections are sent fire-and-forget with a short
timeout. A lost one costs nothing lasting: the next live call or scan corrects
the map again.

## 8. Permissions per person

### 8.1 The map

One row per `(email, path)` in D1:

- `acceso`: `permitido` | `denegado` | `desconocido`
- `fuente`: `escaneo` | `uso`
- `escaneado_en`

Each person also has:

- `permisos_version`, which goes up on every change;
- `escaneo_estado` and `escaneo_fin`.

Paths are the swagger's canonical ones: `/reports/{Nombre}`, or `/{entidad}`,
which also covers its `/{codigo}` and `/list`.

Write refusals are stored separately, per entity (`escritura_denegada = true`),
because reading and writing are different permissions.

### 8.2 The scan

- **Where:** inside the container, with that person's own token. The admin
  action calls the Durable Object, which calls `POST /_interno/escanear` with the
  person's keys in signed headers, as in §7.5. The Durable Object keeps that
  request open until the scan finishes, so the container can't sleep mid-scan.
  The result goes to the Worker via `POST /_interno/escaneo`.
- **When:**
  - when a person is added;
  - when their keys are replaced;
  - when an admin presses "Reescanear".

  There is no periodic scan. Only one scan per person runs at a time.
- **Targets:** every viewer and every entity in the swagger.
- **Entities:** `GET /api/{entidad}/ZZ-NOEXISTE`.
  - 500 containing "No tiene permisos" → `denegado`.
  - 404 → `permitido`.
  - Anything else → `desconocido`, which is treated as allowed.
- **Reports:** `GET /api/reports/{Nombre}`.
  - 403 containing "Prestacion sin permiso" → `denegado`.
  - **Anything else → `permitido`**, including 200, 500 and timeouts. The denial
    arrives before any work starts, so a slow answer means the report is
    running, which means it's allowed.
- **Load on Finnegans:** closing the connection doesn't stop a report that has
  already started. With no params, a probe of an allowed report really runs
  that report, possibly over its whole history.
  - **First task of the plan, a read-only spike with Juan's account.** Find a
    report probe that, when allowed, fails fast **after** the permission check.
    Candidates: an invalid value for a required parameter, `desde` after
    `hasta`, or a 1-day range. Measure 3–5 known-heavy reports. If one works, it
    becomes the report probe.
  - **Until such a probe is proven**, scans that include reports run in the
    evening where possible. The admin page offers "escanear esta noche" as the
    default, and "ahora" on demand.
- **Client-side limits:**
  - at most 4 requests in flight;
  - a 10 s timeout per request;
  - read only the status line and the first 2 KB of the body, then close;
  - one token for the whole scan.

  A full scan takes about 2 minutes.
- **On failure:** a scan that fails partway keeps the previous map, and the admin
  page shows "último escaneo falló".
- **Rescans** replace the `escaneo` rows but keep the `uso` corrections and the
  `escritura_denegada` rows.

### 8.3 How the map is used

The container's `Contexto` loads the map through `GET /_interno/permisos` on
first use. It reloads when the `X-Finnegans-Permisos-Version` header is newer
than the version it holds. Until a person's first scan finishes, everything is
shown and refusals are still translated.

- **`buscar_endpoint`:**
  - Drops swagger and docs results whose path is `denegado` for this person.
  - If every match was dropped, it says so plainly: "Lo que buscás existe en
    Finnegans, pero tu usuario no tiene permiso. Si lo necesitás, pedíselo a
    quien administra Finnegans (y después pedí que te reescaneen)."
  - Entities with `escritura_denegada` are tagged "solo lectura para vos".
- **`ver_endpoint`:** for a `denegado` path, returns that message instead of the
  schema. Entities with `escritura_denegada` get the same "solo lectura para
  vos" tag.
- **`leer`:** still **tries** a `denegado` path, because a permission may have
  been granted after the scan.
  - If the call succeeds, the map is corrected to `permitido` (`fuente: uso`).
  - If it's refused, the person gets the message from §8.4.
- **`escribir`:** always listed. A write refused for lack of permission records
  `escritura_denegada` for that entity. Writes can't be probed, so this is the
  only source.
  - The refusal shape for writes hasn't been observed yet. Classify as a
    permission refusal any 403, and any 500 whose body contains "permiso".
  - The first real refusal in the audit log confirms the shape.
- **Paths missing from the map** (for example, new in the swagger since the
  scan) are treated as allowed.

### 8.4 Error translation (also fixes the desktop extension)

Today the code gets permission refusals wrong:

- `errores.traducir_error` turns a read **403 "Prestacion sin permiso"** into
  "Finnegans rechazó las credenciales…".
- It turns a **500 "No tiene permisos…"** into "falta un parámetro".
- `FinnegansClient` retries every 403 with a fresh token, which doubles each
  refused call.

The fix goes in `finnegans_core`, so the desktop extension gets it too:

- Detect permission refusals by body text ("Prestacion sin permiso", "No tiene
  permisos"), not only by status code.
- On a 403 whose body says "sin permiso", don't re-authenticate.
- New message, depending on the mode:
  - Online: "Tu usuario de Finnegans no tiene permiso para {acción} en
    '{recurso}'. Si lo necesitás, pedíselo a quien administra Finnegans."
  - Desktop: a variant that mentions the extension's API user.
- Credential messages that point to "configuración de la extensión en Claude
  Desktop" get an online variant built from `FINNEGANS_CONTACTO_ADMIN`: "avisale
  a {contacto} para que revisen tus claves".

## 9. The server in online mode

`finnegans_mcp` gains an online entry point. The desktop entry point
(`__main__`, stdio) keeps working with today's behaviour.

### 9.1 Per-person context

Today `crear_servidor` closes over a single `client`, `workspace`,
`origen_tabla`, redactor and `candado`. These move into a `Contexto`:

```
Contexto(email)
  client:      FinnegansClient (this person's keys, own token cache)
  workspace:   Workspace (own in-memory DuckDB, own private temp dir)
  origen_tabla, candado (RLock), permisos (map + version), ultimo_uso
```

- **Selecting the context:** a `contextvars.ContextVar` holds the current
  `Contexto`. Every tool reads it at the start of the call, never at
  registration time.
  - **Desktop:** one fixed `Contexto`, built from `Settings.from_env()` exactly
    as today.
  - **Online:** an ASGI middleware in front of the MCP app verifies the signature
    (§7.5) and finds or creates the `Contexto` for `X-Finnegans-Persona`, then
    sets the variable.
    - If `X-Finnegans-Clave-Version` changed, the old context is closed and
      rebuilt.
    - A request without a valid signature gets 401 and never reaches a tool.
- **Shared across people:** `SwaggerCatalog` and `DocsMcp`. They use the
  company's docs keys and already cache per process. Only their outputs are
  filtered per person.
- **Memory:**
  - Each `Workspace` is created with a DuckDB `memory_limit` of 128 MB (start
    value; the builder measures).
  - At most 6 live contexts. The least recently used one is closed first.
  - A context idle for 30 minutes is closed and its temp dir deleted.
  - Each close frees that person's tables. If Claude needs them again, it
    reloads them. A tool that refers to a table that's gone gets the existing
    "no hay ninguna tabla … cargada" message.
- **Redaction:** each output is redacted by a redactor that knows:
  - that person's keys and token;
  - the shared keys;
  - **every other live context's keys and tokens.**

  If anything ever crossed between people, it would still come out masked. Redact
  first, then truncate.

### 9.2 Tools and text

- Online mode registers **7 tools**, without `exportar`, and uses online
  instructions: the same five rules without the word "exportar". Rule 3 becomes
  "…trabajá con consultar (SQL); nunca pidas ni muestres todas las filas".
- The guide topics that mention `exportar` (`clientes.md`, `parametros.md`) get
  wording that works in both modes, or a line per mode.
- `verificar_conexion` online checks the person's token, the swagger and the docs,
  as today. It also reports the scan state: "Permisos escaneados el 17/11: 138
  reportes y 113 entidades disponibles".

### 9.3 Running

- `transport="streamable-http"`, host `0.0.0.0`, port 8080, path `/mcp`,
  stateless, with JSON responses.
- Starlette routes for `/salud` and `/_interno/*`. The internal routes require
  the signature too.
- **Start-up:** today the swagger spec (586 paths) is downloaded on first use.
  - Measure the cold path: container start plus the first `buscar_endpoint`.
  - If it's over 10 s, warm the swagger in the background at process start.
  - If that's still not enough, the Worker caches the spec in KV and passes it
    in.

  *(The builder measures and decides.)*
- **Limits:** responses keep today's cap, `RESPUESTA_MAX_CHARS` = 8,000 chars,
  far below Claude's per-result limit. Finnegans calls keep their 30 s timeout.
  The scan has its own 10 s per request.
- **Logging:** `_LOGGERS_HTTP` stays at WARNING. Container stdout/stderr go to
  Cloudflare logs, so anything written there goes through the redactor first.
  The middleware never logs headers.

## 10. Audit log ("who did what")

**Written by the Worker, from the traffic it forwards.** The container returns
JSON responses, so the Worker sees every `tools/call` request (tool name and
arguments) and its complete result.

- **`escribir`:** the audit row is **awaited before the response goes back to
  Claude**.
  - If D1 fails, the Worker retries once.
  - If that also fails, the result goes back with an added line ("Ojo: el cambio
    se hizo, pero no quedó registrado en el historial; avisale a {contacto}"),
    and the failure is logged.
  - A change is never silently missing from the log.
- **Other tools:** the row is written with `waitUntil`, so it adds no delay.
- **Redaction:** the result text was already redacted by the container. The
  Worker applies the same redact-then-truncate rule again, with the secrets it
  knows (the person's keys, the swagger key, the docs keys), before storing
  anything.

D1 table `auditoria`:

| Column | Holds |
|---|---|
| `id` | row id |
| `cuando` | time, UTC |
| `email` | who |
| `herramienta` | which tool |
| `metodo` | HTTP method |
| `path` | Finnegans path |
| `codigo` | record code |
| `resultado` | `ok` \| `denegado` \| `error` |
| `filas` | row count, for reads |
| `detalle` | see below |

What goes in `detalle`:

- **`escribir`:** the diff that `escribir` already produces, plus the code
  Finnegans assigned, cut to 20,000 chars after redaction.
- **Reads:** for `leer`, `consultar`, `ver_endpoint` and `buscar_endpoint`, the
  tool, path, params (redacted) and row count. **Never row data.** The SQL of
  `consultar` is kept, cut to 2,000 chars after redaction.
- **Other events:** sign-ins, admin actions (add, replace keys, rescan, remove)
  and scans are logged too, with `herramienta` set to `acceso`, `admin` or
  `escaneo`.

Rows are kept for 365 days. A daily Worker cron deletes older ones. Only the
admins can read the log, on the admin page.

## 11. Isolation (one shared server)

- **Identity comes from the Worker:** from the verified OAuth props, never from
  anything the client sends. The Worker strips client-sent `X-Finnegans-*`
  headers, and the container accepts only signed requests.
- **One `Contexto` per person**, each with:
  - its own `FinnegansClient` and token cache;
  - its own in-memory DuckDB with its own allowed temp dir and
    `enable_external_access=false` (unchanged);
  - its own `origen_tabla` and lock.
- **No tool reads module-level mutable state** except the shared swagger and docs
  caches, which hold company-wide public metadata, not results.
- **Every person-specific thing is created inside the `Contexto`.** A review rule
  for the builder: no new global caches of results.
- **Removing a person** means:
  - deny on their next request;
  - drop their context in the container;
  - delete their keys, permission map and OAuth grants.

  Their audit rows are kept.

## 12. Repo layout and the desktop extension

```
src/finnegans_core/            shared + permisos.py (map, scan, refusal classification)
src/finnegans_mcp/server.py    tools read the current Contexto; crear_servidor(modo=…)
src/finnegans_mcp/contexto.py  Contexto, the registry (LRU, idle close), the ContextVar
src/finnegans_mcp/remoto.py    online entry point: HTTP, signature middleware, internal routes, callbacks
src/finnegans_mcp/__main__.py  desktop entry point (stdio), unchanged behaviour
remoto/                        Worker + Durable Object (TypeScript), wrangler config, D1 migrations, admin page
Dockerfile                     container image for the online server (uv, Python 3.12)
tests/                         Python tests (fakes only)
remoto/test/                   Worker tests (vitest + Cloudflare's Workers test pool)
```

- **The desktop extension** stays here and is built from the same code. It keeps
  all 8 tools and gets every fix.
  - Tag today's state as `v1.0.2` before the online work starts.
  - The online version is the one announced to the team. The `.mcpb` stays on
    the GitHub releases page as a backup.
- **`.mcpbignore`** excludes `remoto/`, `Dockerfile` and `remoto.py`, so the
  desktop bundle doesn't grow.
- **The repo is public today**, under the `JPSformas` GitHub organization. No
  secrets, emails, domains, account IDs or the workers.dev subdomain go in
  committed files. Deployment values live in Wrangler secrets and variables, or
  in a local, git-ignored override.
- **Juan may move the repo** to the company's official GitHub organization and
  make it private. The design doesn't depend on where it lives. A GitHub Actions
  deploy to Cloudflare, with the Cloudflare token stored in that organization's
  secrets, is optional and can come later.

## 13. Rollout

1. **Setup.** Juan does this in Rodrigo's Cloudflare account:
   - the D1 database, the KV namespace, and the Worker secrets and variables;
   - in either company's Google Cloud: an OAuth client that is External and In
     production, with scopes `openid email profile` and the redirect URI for the
     Worker's Google callback.
2. **Report-probe spike** (§8.2), read-only, with Juan's account.
3. **Juan alone:**
   - add himself;
   - run a scan;
   - read-only checks from the web, Desktop and the phone.
4. **Restricted account:** add the account used in the 2026-11-17 test.
   - Check that search hides what it should and that refusals read well.
   - **Isolation check:** two people at the same time, each running
     `consultar("SHOW TABLES")`, each seeing only their own tables.
5. **First live write:** only with Juan's explicit go, on a record he picks.
6. **Rodrigo, then the team.**
   - If the company is on Claude Team or Enterprise, an Owner adds the connector
     once for the organization.
   - Otherwise each person adds the URL under Settings → Connectors.

## 14. Cost (estimate, to check after the first month)

Everything runs inside Rodrigo's Workers Paid plan ($5/month). Only the
container can add to that.

**Assumptions:** one `basic` container (1 GiB memory, 4 GB disk, 1/4 vCPU).
It's awake during working hours plus the 15-minute idle tail, about
11 h × 22 days ≈ 240 h a month, and asleep nights and weekends.

| Item | Use per month | Included | Extra cost |
|---|---|---|---|
| Container memory | 240 GiB-h | 25 GiB-h | ≈ $1.95 |
| Container disk | 960 GB-h | 200 GB-h | ≈ $0.20 |
| Container CPU (active only) | 15 people × 100 calls/day × ~0.5 s ≈ 275 vCPU-min | 375 vCPU-min | $0 |
| Workers, Durable Object, D1, KV, logs, egress | small | well within | $0 |
| **Total on top of the $5 plan** | | | **≈ $2–3** |

What moves the number:

- Every extra hour the container stays awake costs about $0.01.
- A larger instance multiplies the memory line. `standard-1` would be about $8
  extra.
- Weekend or late-night use keeps it awake longer.

Pure $0 extra would need the container to be awake no more than about 25 hours a
month. The admin page shows the month's container hours, so the estimate can be
checked.

## 15. Testing

**Python** (fakes only):

- **Isolation:**
  - Two contexts, A and B, loaded with different tables. A's `SHOW TABLES`,
    `consultar` and `escribir base` never see B's.
  - Concurrent requests for A and B, using threads, keep the right context. This
    proves the ContextVar crosses `anyio.to_thread`.
  - B's secrets are masked even if they appear in A's output.
  - Requests without a signature, or with a stale or wrong one, never reach a
    tool.
- **Registry:**
  - LRU eviction and idle close free the DuckDB and its temp dir.
  - A key-version change rebuilds the context.
- **Scan:**
  - the classification for every response shape in §8.2, including timeouts;
  - the limit of 4 in flight is respected.
- **Filter:**
  - `buscar_endpoint` and `ver_endpoint` hide `denegado` paths.
  - `leer` self-corrects a stale `denegado`.
  - Write refusals are recorded.
- **Errors:** the new permission messages, and no 403 retry on "sin permiso".
- **Online mode:**
  - exactly 7 tools;
  - no "exportar" in any tool description, instruction or guide text shown
    online.
- **Redaction:** on audit payloads, a secret split by the cut is still masked.
- **Desktop mode unchanged:** the current 413 tests still pass.

**Worker:**

- **Sign-in:**
  - a 401 with `resource_metadata` on an unauthenticated `/mcp`;
  - the metadata fields required by Claude (§5);
  - an email outside `ALLOWED_DOMAINS`, or not on the list, gets no token;
  - someone disabled after signing in is denied on their next request.
- **Headers:**
  - client-sent `X-Finnegans-*` headers are stripped;
  - the signature is added.
- **Admin:** admin routes reject non-admins and requests without the CSRF token.
- **Keys:** the encryption round-trips, and a mismatched AAD fails.
- **Callbacks:** `/_interno/*` rejects a missing or wrong bearer.
- **Audit:** the `escribir` audit row is awaited, and the fallback warning line
  appears when D1 fails.

**Live** (manual, §13): connect from claude.ai, Desktop and mobile, run read-only
checks, and run the two-person isolation check. Writes only with Juan's go.

## 16. Decisions made in the conversation

- **Sign-in:** company Google accounts from **two domains** (SOUTEX and Formas),
  which is why the Google client is External. Everyone who'd use it has a
  company Google account.
- **Keys:** each person acts with their own Finnegans API keys, loaded by an
  admin.
- **Admins:** Juan and Rodrigo.
- **Hosting:** Rodrigo's Cloudflare account, with Juan as a member.
- **Writes:** changes allowed from day one, with an audit log.
- **Approach B:** one shared server, the standard design. Approach A was dropped
  for cost.
- **Budget:** stay at or near the $5 plan.
- **No periodic permission scans:** an initial scan plus manual rescans are
  enough.
- **No narrow versions:** permissions narrow what each person sees, and skills
  guide.
- **No `exportar` online:** the desktop extension keeps it.
- **Online is the main version.** The desktop extension stays in this repo and
  gets the same fixes.

## 17. Calls made by Claude (check these)

- **Access:** only people added on the admin page get in. Others see a "pedile
  acceso" page.
- **Container:** a single `basic` container with a 15-minute idle timeout.
- **Memory per person:** DuckDB at 128 MB each, at most 6 live contexts, and a
  30-minute idle close per person.
- **Per-person keys travel per request** in signed internal headers, rather than
  the container reading D1 itself.
- **Scans:** reports are scanned in the evening by default until a cheap probe is
  proven, and live calls self-correct the map.
- **Audit:**
  - the Worker writes the log from forwarded traffic, and change rows are
    awaited;
  - kept 365 days;
  - diffs up to 20,000 chars;
  - no row data from reads.
- **Admin page sign-in:** the same Google sign-in, rather than Cloudflare Access.
- **URL:** a workers.dev URL at launch.
- **Permission errors:** the translation is fixed in the shared core, so the
  desktop extension benefits too.

## 18. Left to the builder

- Whether to use the native Durable Object container API (`ctx.container`) or the
  `@cloudflare/containers` helper class. Pin versions at plan time.
- Whether the swagger needs warming or caching (§9.3); measure first.
- The final per-person DuckDB limit and the cap on live contexts, measured on the
  `basic` instance.
- Admin page markup and styling: plain, Spanish, works on a phone.
- D1 schema details beyond the fields named here.
