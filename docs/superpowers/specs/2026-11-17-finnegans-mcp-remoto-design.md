# Finnegans MCP — online version, adapted per person (design)

Date: 2026-11-17 · Author: Juan Sbatella (with Claude)
Builds on: `2026-11-02-finnegans-mcp-extension-design.md` (the desktop extension, v1.0.2)

## 1. Intent

Today the Finnegans assistant runs as a Claude Desktop extension (`finnegans.mcpb`):
each person installs it on their PC and types their own Finnegans API keys into a
form. It works, but only on a PC where it was installed, never on the phone, and
every person sees the whole API whether or not their Finnegans account can use it.

The online version puts the same assistant on a public HTTPS address. Anyone at the
company adds it once in Claude (web, desktop or mobile), signs in with their company
Google account, and gets an assistant that only offers what **their own** Finnegans
account allows. Nothing is installed on anyone's device.

Why per person: Finnegans permissions differ by account. A restricted account tested
on 2026-11-17 was denied 100 of 238 reports and 13 of 126 entities. Showing those to
that person only produces dead ends and confusing errors.

## 2. Goals

1. **No install, any device.** One connector URL that works in claude.ai, Claude
   Desktop and Claude mobile.
2. **Company sign-in.** People sign in with their company Google Workspace account.
   Only people an admin has added get in.
3. **Each person acts as themselves in Finnegans.** Every call uses that person's own
   Finnegans API keys, which an admin loads once. People never see or type keys.
4. **Adapted per person.** Search and `ver_endpoint` only show the endpoints that
   person's account can use. Permission refusals are explained in plain Spanish.
5. **Changes from day one.** `escribir` works online exactly as on desktop (save,
   then show the diff), limited by each person's Finnegans permissions.
6. **Who did what.** Every change is logged with who, when, which record and the
   diff. Reads are logged without their data.
7. **One program, two ways to run it.** The same Python server runs as the desktop
   extension and as the online version. Fixes reach both.

## 3. Non-goals

- **Narrow versions** (`/mcp/facturar`, `/mcp/compras`, …). Finnegans permissions
  already narrow what each person can do. Guidance for a specific job comes from
  skills each person writes in Claude. The design leaves room to add a guided
  version at its own URL later, but none is built now.
- **`exportar` online.** The online version has no export tool and no file storage.
  The desktop extension keeps `exportar` unchanged.
- **Probing write permissions up front.** There is no safe way to test a write
  without writing. Write permission is learned from real refusals only (§8.4).
- **Rewriting the server in TypeScript** or running it without containers.
- **Per-person instructions or tool sets** beyond the permission filter.
- **Moving the desktop extension to its own repo.** It stays here and keeps
  getting the same fixes (§12).

## 4. Anti-goals (failure even if it technically works)

- One person seeing another person's tables, results, keys or log entries.
- A Finnegans key, token, swagger key or docs key appearing in any tool output,
  admin page, log line, audit entry or committed file.
- Someone who isn't on the admin's list using the connector, or someone removed from
  the list still using it after their next request.
- A permission refusal reported as "your keys are wrong" or "a parameter is
  missing" (today's extension does this, see §8.5).
- The permission scan hammering Finnegans: it must stay gentle (§8.2).
- The desktop extension and the online version drifting into two programs.

## 5. Constraints and verified facts

**Cloudflare** (checked 2026-11-17)
- Containers have been generally available since 2026-04-13. They need the Workers
  Paid plan ($5/month). They run in Rodrigo Mateus's Cloudflare account, where Juan is
  already a member.
- A container is reached only through its Durable Object. One Durable Object per
  name means one container per person, addressed by the person's email.
- Cold start is about 1–3 s plus our own start-up work. Disk is ephemeral: a
  restarted container starts clean. An idle timeout (`setInactivityTimeout`, up to
  6 h) stops it. On stop it gets SIGTERM, then SIGKILL after up to 15 min.
- Per-person secrets reach the container as environment variables on `start()`
  (`env` option). `enableInternet: true` is needed for Finnegans calls.
- Instance types: `lite` 1/16 vCPU 256 MiB, `basic` 1/4 vCPU 1 GiB, `standard-1`
  1/2 vCPU 4 GiB, and larger. Memory and disk are billed while the container
  runs, CPU only when used. Included each month: 25 GiB-h of memory and
  375 vCPU-min. After that, $0.0000025 per GiB-s (about $0.009 per GiB-hour).
- `@cloudflare/workers-oauth-provider` implements the OAuth server side on a Worker:
  DCR, CIMD (`clientIdMetadataDocumentEnabled`, needs the
  `global_fetch_strictly_public` compatibility flag), and PKCE. It passes the
  signed-in user's props to the API handler, and its storage is a KV namespace
  bound as `OAUTH_KV`.

**Claude connectors** (checked 2026-11-17)
- claude.ai, Desktop and mobile share one OAuth client. The callback is
  `https://claude.ai/api/mcp/auth_callback`. Claude Code uses a loopback redirect
  on any port (`http://localhost/callback`, `http://127.0.0.1/callback`), and
  supporting it is cheap.
- Sign-in starts only on a **401** carrying
  `WWW-Authenticate: Bearer resource_metadata="…"`. The protected resource
  metadata's `resource` must equal the connector URL exactly. Claude uses only the
  first entry in `authorization_servers`.
- CIMD is used only if the authorization server metadata advertises
  `client_id_metadata_document_supported: true` **and** `"none"` in
  `token_endpoint_auth_methods_supported`. Otherwise Claude falls back to DCR.
  PKCE S256 is required. The token endpoint must accept form-urlencoded bodies,
  return `invalid_grant` for dead refresh tokens, and rotate refresh tokens for
  public clients. Claude allows 10 s for discovery, registration and token calls,
  and 30 s for refresh.
- Anthropic's outbound traffic comes from `160.79.104.0/21`.

**MCP Python SDK** (installed: `mcp` 2.3.0)
- `MCPServer.run(transport="streamable-http", host=…, port=…, stateless_http=…,
  json_response=…, transport_security=…)` exists. DNS-rebinding protection checks
  the Host header against `allowed_hosts`.

**Finnegans** (verified live 2026-11-17, read-only; see memory
`finnegans-permisos-por-cuenta`)
- swaggerGlobal works only with the company docs key. It returns the same 586 paths
  for everyone and rejects API tokens. There is no per-account swagger.
- No endpoint lists an account's permissions.
- **Reports:** a denied account gets `403 "Forbidden: Prestacion sin permiso"`
  *before* parameter validation. An allowed account's report actually **runs**,
  even without parameters.
- **Entities:** `GET /{entidad}/ZZ-NOEXISTE` answers 404 when allowed, or
  500 `"No tiene permisos para transacciones de la categoría…"` when denied.
- A full scan is about 364 calls and took about 2 minutes. Write refusals have not
  been observed yet.

**Repo rules that carry over**
- Never read, print or commit `.env` values. Tests use fake credentials only.
- Admin emails (Juan's, Rodrigo's) live in deployment settings, never in code,
  docs or the `.mcpb`.
- No production writes from tests or scripts without Juan's explicit go.
- The redactor rule stays: **redact first, then truncate**.
- User-facing text is in Spanish (Argentina).

## 6. Approaches considered

| Approach | Trade-off | Verdict |
|---|---|---|
| **A. One container per person** behind a Worker that handles sign-in, admin and keys | Server barely changes (it already assumes one person with one set of keys, read from env vars). Isolation by construction. Desktop and online stay one program. Cost: a cold start of a few seconds after idle, and each active person costs a little. | **Chosen by Juan** |
| B. One shared container for everyone | Always warm, cheaper at large scale. But the server would have to keep many people's keys, tokens, tables and redactors apart inside one process. One bug leaks data between people, and desktop and online drift apart. | Rejected |
| C. Rewrite on Workers without containers | Loses DuckDB and the proven search/vocabulary logic for no gain. | Rejected |

## 7. Architecture

```
Claude (web / desktop / mobile)
   │  HTTPS, OAuth bearer token
   ▼
Worker  "finnegans-remoto"  (TypeScript)
   ├─ OAuth server for Claude (workers-oauth-provider: CIMD + DCR + PKCE)
   ├─ Google sign-in (OIDC) for people and for the admin page
   ├─ /admin            admin page (Juan, Rodrigo)
   ├─ /mcp              → checks the person is active → their Durable Object
   ├─ D1                people, encrypted keys, permission maps, audit log
   └─ secrets           master key, Google client, swagger key, docs keys, admin emails
          │
          ▼
Durable Object "Persona" (one per email)
   ├─ starts/stops that person's container, passes keys as env vars
   ├─ forwards /mcp to the container
   ├─ writes the audit log from the traffic it forwards → D1
   ├─ receives permission corrections from the container → D1
   └─ alarm: weekly permission rescan
          │
          ▼
Container (Python, same server as the .mcpb, started in online mode)
   ├─ MCPServer over streamable HTTP, 7 tools (no exportar)
   ├─ DuckDB workspace in memory (this person only)
   └─ permission filter + scanner
          │
          ▼
api.finneg.com · swaggerGlobal · Finnegans docs MCP
```

### 7.1 Connector URL

At launch: `https://finnegans-remoto.<subdomain>.workers.dev/mcp`. A custom domain
on a company zone can come later. Changing the URL means everyone re-adds the
connector, so do it before the wide rollout if at all. *(Builder's call; noted.)*

### 7.2 Sign-in flow (people)

1. Claude calls `/mcp` without a token. The Worker answers **401** with
   `WWW-Authenticate: Bearer resource_metadata="https://…/.well-known/oauth-protected-resource"`.
   The metadata's `resource` is exactly the `/mcp` URL.
2. Claude registers (CIMD preferred, DCR fallback) and opens `/authorize`.
3. The Worker's `/authorize` sends the person to Google OIDC.
   - **Two company domains (SOUTEX and Formas), so the Google OAuth client is
     External**, with user type External and publishing status **In production**.
   - It asks only for `openid email profile`. Those scopes are non-sensitive, so
     Google doesn't require app verification. Production status also avoids
     testing mode's 100-user cap.
   - An Internal client is not used: it would only admit the Workspace org that
     owns the Cloud project.
   - No `hd` hint is passed, because there are two domains. Google's account
     chooser shows whatever account the person picks.
4. On return, the Worker verifies the ID token: issuer, audience, and
   `email_verified = true`.
   - The domain check is the `hd` claim **and** the email's domain, both in
     `ALLOWED_DOMAINS` (a comma-separated Worker var, not hard-coded). A personal
     `@gmail.com` account has no `hd` and is refused.
   - The real gate is the per-person list. It then looks up the email in
     `personas`:
   - **active** → `completeAuthorization()` with props `{ email }`, back to Claude.
   - **unknown or disabled** → a Spanish page: "Todavía no tenés acceso al
     asistente de Finnegans. Pedíselo a Juan o a Rodrigo." No token is issued.
5. **Every** `/mcp` request re-checks that the email is still active. A cached
   lookup of up to 60 s is fine. Removing someone takes effect on their next
   request, after which the Worker also asks their Durable Object to stop the
   container.

### 7.3 Admin page (`/admin`)

- Same Google sign-in, separate cookie session. Allowed only if the email is in the
  `ADMIN_EMAILS` secret (Juan and Rodrigo). Everyone else gets 403.
- Write actions carry a CSRF token. The session cookie is `HttpOnly`, `Secure` and
  `SameSite=Lax`, with a short lifetime (8 h).
- Screens (Spanish, plain, phone-friendly):
  - **Personas:** list (name, email, active, last use, permission summary such as
    "138 de 238 reportes · 113 de 126 entidades · escaneado hace 3 días"), with
    actions to add, disable/enable, remove, and rescan permissions now.
  - **Agregar / reemplazar claves:** email, name, Finnegans client ID, client
    secret. Saving runs a token check against Finnegans first and refuses keys
    that don't authenticate. Saved secrets are never shown again: the fields are
    write-only and show only "cargada el 17/11/2026".
  - **Registro:** the audit log, filterable by person, date, tool and "solo
    cambios".
- Saving new keys for a person stops their running container, so the next request
  starts with the new keys, and triggers a rescan.

### 7.4 Keys and secrets

- **Per person** (in D1): Finnegans `client_id` and `client_secret`, each encrypted
  with AES-256-GCM. The key is `MASTER_KEY` (a Worker secret), the nonce is random
  per value, and the AAD is the person's email, so a ciphertext copied to another
  row fails to decrypt. A `clave_version` column allows rotating `MASTER_KEY`
  later.
- **Shared** (Worker secrets only): `FINNEGANS_SWAGGER_KEY`,
  `FINNEGANS_DOCS_CLIENT_ID`, `FINNEGANS_DOCS_SECRET_KEY`, `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`, `MASTER_KEY`, `ADMIN_EMAILS`, `ALLOWED_DOMAINS`.
- The Durable Object decrypts only to start that person's container. Keys reach the
  container as the env vars the server already reads (`FINNEGANS_CLIENT_ID`,
  `FINNEGANS_CLIENT_SECRET`, `FINNEGANS_SWAGGER_KEY`, `FINNEGANS_DOCS_*`).
  `Settings.from_env` needs no change.
- Worker code never logs a request URL with a query string, an env var or a D1
  key column.

### 7.5 Durable Object ↔ container

- **Name:** the lower-cased email. **Instance type:** `basic` (1 GiB) at launch,
  with the DuckDB `memory_limit` lowered to fit (start at 512 MB). Move to
  `standard-1` only if real use hits memory errors. *(Builder's call; noted.)*
- **Idle timeout:** 30 minutes. Loaded tables are lost when the container stops,
  and Claude reloads what it needs.
- **Start:** pass the env vars, plus `FINNEGANS_MODO=remoto` and the
  control-channel settings (§7.6). Wait until `GET /salud` answers before
  forwarding. A container that fails to start yields a Spanish MCP error ("El
  asistente no pudo arrancar, probá de nuevo en un minuto"), never a raw 5xx page.
- **Forwarding:** only `/mcp` reaches the container. The container's internal paths
  (`/salud`, `/_interno/*`) are reachable only from the Durable Object, never from
  the public Worker route.
- **Transport:** the container runs `stateless_http=True, json_response=True`.
  Nothing in the tools depends on MCP session state, since the workspace belongs
  to the process. Stateless mode means a container restart never breaks a
  conversation with "unknown session". DNS-rebinding protection stays on, with
  `allowed_hosts` set to the host the Durable Object uses when forwarding.

### 7.6 Control channel (container → Worker)

The container must report permission changes and audit events. Its disk is
ephemeral, so nothing can stay only in the container. The builder picks one of
these, in this order of preference, and records the choice:

1. Outbound interception (`interceptOutboundHttp`): the container posts to a fixed
   internal hostname, and the Durable Object handles it.
2. An authenticated callback to a Worker route `/_interno/*`, using a per-start
   random token the Durable Object passes in env and checks.

The payloads are small JSON: `{tipo: "permiso", path, acceso, fuente}`. They're
sent fire-and-forget with a short timeout. A lost permission update costs nothing
lasting, because the next live call or scan corrects it again. The audit log does
**not** travel over this channel (§10).

## 8. Permissions per person

### 8.1 The map

One row per `(email, path)` in D1:

- `acceso`: `permitido` | `denegado` | `desconocido`
- `fuente`: `escaneo` | `uso` | `escritura`
- `escaneado_en`
- plus the person's `escaneo_estado` and `escaneo_fin`

Paths are the swagger's canonical paths: `/reports/{Nombre}`, or `/{entidad}`,
which covers its `/{codigo}` and `/list` too.

Write refusals are stored separately per entity (`escritura_denegada = true`),
because reading and writing are different permissions.

### 8.2 The scan

The scan runs **inside the person's container**, so it uses their own token, via
`POST /_interno/escanear` from the Durable Object. The Durable Object stores the
result.

- **Targets:** every viewer path and every entity in the swagger.
- **Reports:** `GET /api/reports/{Nombre}` with no params. A 403 that contains
  "Prestacion sin permiso" means `denegado`. **Anything else means `permitido`**,
  including 200, 500 (missing params) and timeouts. The denial comes back before
  any work starts, so a slow answer means the report is running, which means it's
  allowed.
- **Entities:** `GET /api/{entidad}/ZZ-NOEXISTE`. A 500 containing "No tiene
  permisos" means `denegado`. A 404 means `permitido`. Anything else means
  `desconocido`, which is treated as allowed (§8.3).
- **Gentle on the client side:** at most 4 requests in flight, a 10 s timeout per
  request, only the status line and the first 2 KB of the body read, then the
  connection is closed. One token for the whole scan. Expect about 2 minutes.
- **Load on Finnegans:** closing the connection doesn't stop a report that already
  started. A report probe on an allowed account really runs that report, possibly
  over its whole history. With about 15 people × about 140 allowed reports, that
  means roughly 2,000 production report runs per full sweep. So:
  - **First task of the plan, a read-only spike with Juan's account:** look for a
    report probe that is refused before the permission check when denied, and
    fails fast **after** it when allowed. Candidates: an invalid value for a
    required parameter, an impossible date range (`desde` after `hasta`), or a
    1-day range. Measure response times on 3–5 known-heavy reports. If one works,
    it becomes the report probe.
  - **Until a cheap probe is proven:**
    - reports are scanned only when a person is added, when their keys are
      replaced, and on "Reescanear", run off-hours where possible;
    - the **weekly** sweep covers entities only (a 404 on a fake code costs
      nothing);
    - report drift between sweeps is caught by live calls (§8.3).
- **When:** when a person is added, when their keys are replaced, on "Reescanear"
  in the admin page, and weekly by Durable Object alarm (staggered per person,
  scope as above). Only one scan per person at a time. A rescan replaces the `escaneo` rows but
  keeps `escritura_denegada` rows.
- A scan that fails partway keeps the previous map and shows "último escaneo
  falló" in the admin page.

### 8.3 How the map is used

Until a person's first scan finishes, everything is shown, and refusals are still
translated.

- **`buscar_endpoint`:** drops swagger and docs results whose path is `denegado`
  for this person. If everything that matched was dropped, it says so plainly:
  "Lo que buscás existe en Finnegans, pero tu usuario no tiene permiso. Si lo
  necesitás, pedíselo a quien administra Finnegans."
- **`ver_endpoint`:** for a `denegado` path, returns that message instead of the
  schema.
- **`leer`:** still **tries** a `denegado` path, because permissions can be granted
  after a scan. If the call succeeds, the map is corrected to `permitido`
  (`fuente: uso`). If it's refused, the message from §8.5 is shown.
- **`escribir`:** always listed. For an entity with `escritura_denegada`,
  `ver_endpoint` and `buscar_endpoint` tag it "solo lectura para vos". If `escribir`
  is attempted anyway, the call still goes out, for the same reason as `leer`.
- **Paths not in the map** (for example, new in the swagger since the last scan):
  treated as allowed.
- The container gets the map at start from the Durable Object via
  `POST /_interno/permisos` before the first forwarded request. It keeps the map in
  memory and reports every correction over the control channel.

### 8.4 Write permission

Writes can't be probed safely, so `escribir` is never hidden at launch. When a write
is refused for lack of permission, `escritura_denegada` is recorded for that entity
and reported. The refusal shape for writes hasn't been observed yet: classify any
403, and any 500 containing "permiso", on a write as a permission refusal. The
first real refusal seen in the audit log confirms the shape. *(Hiding `escribir`
entirely for people with no write rights at all can come later, once enough
refusals are known. Not built now.)*

### 8.5 Error translation (fixes a bug in the desktop extension too)

Today, `errores.traducir_error` turns a read **403 "Prestacion sin permiso"** into
"Finnegans rechazó las credenciales…". It turns a **500 "No tiene permisos…"** into
"falta un parámetro". And `FinnegansClient` retries every 403 with a fresh token,
which doubles each refused call. Change this in `finnegans_core`, so desktop and
online both benefit:

- Detect permission refusals by body text ("Prestacion sin permiso", "No tiene
  permisos"), not just by status code.
- The client does **not** re-authenticate on a 403 whose body says "sin permiso".
- New message, adapted to the mode:
  - Online: "Tu usuario de Finnegans no tiene permiso para {acción} en
    '{recurso}'. Si lo necesitás, pedíselo a quien administra Finnegans."
  - Desktop keeps a variant that mentions the extension's API user.
- Credential messages that say "configuración de la extensión en Claude Desktop"
  get an online variant: "avisale a Juan o a Rodrigo para que revisen tus claves".
  Admin names come from configuration (`FINNEGANS_CONTACTO_ADMIN`), not from code.

## 9. The server in online mode

`finnegans_mcp` gains a second entry point. The desktop entry point is unchanged.

- `crear_servidor(settings, modo="escritorio"|"remoto", permisos=…)`. Online mode
  registers **7 tools** (no `exportar`) and uses online instructions: the same five
  rules without the word "exportar" (rule 3 becomes "…trabajá con consultar
  (SQL); nunca pidas ni muestres todas las filas"). Guide topics that mention
  `exportar` (`clientes.md`, `parametros.md`) get mode-neutral wording or a
  per-mode line.
- Run with `transport="streamable-http"`, host `0.0.0.0`, port 8080, path `/mcp`,
  stateless with JSON responses. Add starlette routes for `/salud` and
  `/_interno/*`.
- `verificar_conexion` online: checks the token, swagger and docs as today, and
  also reports the permission scan state ("Permisos escaneados hace 3 días: 138
  reportes y 113 entidades disponibles").
- **Start-up time:** the swagger spec (586 paths) is downloaded on first use today.
  Measure the cold path (container start + first `buscar_endpoint`). If it goes
  over 10 s, the Durable Object warms it right after start by calling
  `/_interno/precalentar`. If that's still not enough, the Worker caches the spec
  in KV and passes it in. *(Builder measures and decides.)*
- **Limits:** responses keep today's cap, `RESPUESTA_MAX_CHARS` = 8,000 chars,
  far under Claude's per-result limit. Finnegans calls keep their 30 s timeout. The
  Durable Object's forward to the container allows up to 240 s per request. The
  scan's 10 s per-request timeout is separate.
- **Logging:** keep `_LOGGERS_HTTP` at WARNING. The container's stdout/stderr go to
  Cloudflare logs, so everything written there passes through the redactor.

## 10. Audit log ("who did what")

**Written by the Durable Object, from the traffic it forwards.** The container runs
with `json_response=True`, so the Durable Object sees every `tools/call` request
(tool name and arguments) and its complete JSON result, and it writes the audit
row itself:

- **`escribir`:** the row is **awaited before the response goes back to Claude**.
  If D1 fails, it retries once. If that also fails, the result goes back with an
  added line ("Ojo: el cambio se hizo, pero no quedó registrado en el historial;
  avisale a Juan o a Rodrigo") and the failure is logged. A change is never
  silently missing from the log.
- **Other tools:** the row is written with `waitUntil`, so it adds no delay.

A container crash or SIGKILL right after a write can therefore never lose its
record. The result text was already redacted by the server. The Durable Object
applies the same redact-then-truncate rule again, with the secrets it knows (the
person's keys, the swagger key, the docs keys), before storing anything.

D1 table `auditoria`:

`id`, `cuando` (UTC), `email`, `herramienta`, `metodo`, `path`, `codigo`,
`resultado` (`ok` | `denegado` | `error`), `filas` (reads), `detalle`.

- **`escribir`:** `detalle` holds the diff that `escribir` already produces, and
  the record code Finnegans assigned. Redacted first, then cut to 20,000 chars.
- **Reads** (`leer`, `consultar`, `ver_endpoint`, `buscar_endpoint`): tool, path,
  params (redacted), row count. **Never row data.** The SQL text of `consultar` is
  stored, cut to 2,000 chars after redaction.
- Sign-ins, admin actions (person added, keys replaced, rescan, removal) and scans
  are logged too, with `herramienta` set to `admin` or `acceso`.
- Kept 365 days. A daily Worker cron deletes older rows. *(My call.)*
- Only the admins can read it, on the admin page.

## 11. Isolation and cleanup

- One container per person: no shared DuckDB, token, redactor or memory.
- The Worker routes by the email from the **verified OAuth props**, never from
  anything the client sends.
- The container's disk is ephemeral, and the DuckDB workspace is in memory with
  `enable_external_access=false` (unchanged).
- Removing a person means: deny on the next request, stop the container, delete
  their keys, map and OAuth grants. Their audit rows are kept.

## 12. Repo layout and the desktop extension

```
src/finnegans_core/            shared (unchanged layout) + permisos.py (map, scan, classification)
src/finnegans_mcp/             server.py gains modo; __main__ stays desktop (stdio)
src/finnegans_mcp/remoto.py    online entry point (HTTP, internal routes, control channel)
remoto/                        Worker + Durable Object (TypeScript), wrangler config, D1 migrations, admin page
Dockerfile                     container image for the online server (uv, Python 3.12)
tests/                         Python tests (fakes only) incl. scan classification, filter, online tool list
remoto/test/                   Worker tests (vitest + Cloudflare's Workers test pool)
```

- The desktop extension stays here, is built from the same code, keeps all 8 tools,
  and gets every fix. Tag today's state as `v1.0.2` before the online work starts.
  The online version is the one announced to the team. The `.mcpb` stays on the
  GitHub releases page as a backup.
- `.mcpbignore` excludes `remoto/`, `Dockerfile` and online-only modules, so the
  desktop bundle doesn't grow.
- The repo is public: no secrets, emails, account IDs or the workers.dev subdomain
  in committed files. Deployment values live in Wrangler secrets and vars, or a
  local, git-ignored `wrangler` override.

## 13. Rollout

1. **Setup (Juan, in Rodrigo's Cloudflare account):** Workers Paid plan, D1
   database, KV namespace, Worker secrets. Then the Google Cloud OAuth client
   (External, In production, scopes `openid email profile`) with the redirect URI
   for the Worker's Google callback, created in either company's Google Cloud
   org.
2. **Juan alone:** add himself, scan, read-only checks from web, desktop and phone.
3. **Restricted account:** add the account used in the 2026-11-17 test, then
   confirm the filter hides what it should and that refusals read well.
4. **First live write:** only with Juan's explicit go, on a record he picks.
5. **Rodrigo, then the team.** If the company is on Claude Team/Enterprise, an
   Owner adds the connector once for the organization. Otherwise each person adds
   the URL under Settings → Connectors.

## 14. Cost (estimate, to verify after a month)

Memory is billed while a container runs, including its 30-minute idle tail.
Example: 15 people × 4 h/day × 22 days ≈ 1,320 container-hours.

- On `basic` (1 GiB): about 1,300 GiB-h after the free 25, which is roughly
  **$12/month**.
- On `standard-1` (4 GiB): about **$47/month**.

Plus the $5 plan. CPU, D1, KV and egress stay within included amounts at this scale.
Shortening the idle timeout is the main lever.

## 15. Testing

- **Python (fakes only):**
  - scan classification for every response shape in §8.2, including timeouts;
  - filter behaviour in `buscar_endpoint` and `ver_endpoint`;
  - `leer` self-correcting a stale `denegado`;
  - write-refusal recording;
  - the new error messages;
  - no 403 retry on "sin permiso";
  - online mode registers exactly 7 tools with no "exportar" in any tool
    description, instruction or guide text shown online;
  - the redactor on audit payloads (secret split by the cut → still masked);
  - desktop mode unchanged (all 413 current tests still pass).
- **Worker:**
  - 401 + `resource_metadata` on unauthenticated `/mcp`;
  - metadata fields required by Claude (§5);
  - unknown or disabled email gets no token;
  - disabled after sign-in → denied on next request;
  - admin routes reject non-admins and requests without CSRF;
  - encryption round-trip, and AAD mismatch fails;
  - internal routes unreachable from the public route.
- **Live (manual, step 13):** connect from claude.ai, Desktop and mobile, then run
  read-only checks. Writes only with Juan's go.

## 16. Decisions made in the conversation

- Company sign-in: **Google Workspace**. Everyone who'd use it has a company
  Google account. There are **two domains** (SOUTEX and Formas), so the Google
  client is External and sign-in accepts both domains.
- Each person acts with **their own Finnegans API keys**, loaded by an admin.
- **Admins: Juan and Rodrigo.** Hosting: **Rodrigo's Cloudflare account**, with Juan
  as a member.
- **Changes allowed from day one**, limited by Finnegans permissions, with an audit
  log.
- **Approach A:** one container per person.
- **No narrow versions.** Permissions narrow, and skills guide.
- **No `exportar` online.** The desktop keeps it.
- **Online is the main version.** The desktop extension stays in this repo and
  gets the same fixes.

## 17. Calls made by Claude (check these)

- Allow-list access: only people added on the admin page get in. Others see a
  "pedile acceso" page.
- 30-minute idle timeout. `basic` instance with DuckDB at 512 MB.
- Rescan plus self-correcting live calls. The weekly sweep covers entities only
  until a cheap report probe is proven (§8.2). Reports are scanned when a person
  is added, on key change and on demand.
- The audit log is written by the Durable Object from forwarded traffic. Change
  rows are awaited, so a change is never silently missing (§10).
- Stateless HTTP inside the container.
- Audit kept 365 days. Diffs up to 20,000 chars. No row data from reads.
- The admin page uses the same Google sign-in rather than Cloudflare Access.
- workers.dev URL at launch.
- Fixing permission-error translation in the shared core, so the desktop extension
  benefits too.

## 18. Left to the builder

- The control-channel mechanism (§7.6, in the stated order of preference).
- Whether to use the native Durable Object container API (`ctx.container`) or the
  `@cloudflare/containers` helper class. Pin versions at plan time.
- Whether the swagger needs warming or caching (§9, measure first).
- Admin page markup and styling (plain, Spanish, works on a phone).
- D1 schema details beyond the fields named here.
