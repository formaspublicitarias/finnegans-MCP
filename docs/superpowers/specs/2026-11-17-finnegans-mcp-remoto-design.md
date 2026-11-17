# Finnegans MCP — per person, then online (design)

Date: 2026-11-17 · Author: Juan Sbatella (with Claude)
Builds on: `2026-11-02-finnegans-mcp-extension-design.md` (the desktop extension, v1.0.2)

## 1. Intent

Today the Finnegans connector runs as a Claude Desktop extension
(`finnegans.mcpb`). The Claude organization distributes it, and each person types
API keys into its settings form. Two things are missing:

1. **It doesn't adapt to the person.** Finnegans permissions differ by account.
   A restricted account tested on 2026-11-17 was denied 100 of 238 reports and
   13 of 126 entities. Today the connector shows everyone the whole API, so a
   restricted person hits dead ends. On top of that, the connector reports
   those refusals as "your keys are wrong" or "a parameter is missing".
2. **It only works on a PC with Claude Desktop.** It doesn't work on the phone
   or on claude.ai in a browser.

The work happens in two phases, so each one delivers something usable and nothing
is thrown away:

- **Phase 1 — Per person, on the desktop, ready for a container.**
  - Each person uses their own Finnegans API keys.
  - The connector learns that person's permissions and only offers what they
    can use.
  - Refusals are explained correctly.
  - Distribution is unchanged: the `.mcpb` is uploaded to the Claude
    organization and updates reach everyone.
  - The code is shaped so it can run in a container with only the strictly
    necessary additions.
- **Phase 2 — Online (option A).** The same Python connector runs in one shared
  container on Cloudflare, behind a Worker that handles Google sign-in, an admin
  page and a shared change log. It works on the phone and in the browser with
  nothing installed. The desktop extension stays as a backup and gets the same
  fixes.

Phase 1 is planned and built first. Phase 2 is designed here so Phase 1 doesn't
paint it into a corner. It gets its own plan when Phase 1 is done.

## 2. Decisions made in the conversation

- **Roadmap:** Phase 1 (desktop, per person, ready for a container), then Phase 2
  (online, option A).
- **Distribution in Phase 1:** as today. The `.mcpb` is uploaded to the Claude
  organization and updates reach the whole team.
- **Keys:** each person acts with their own Finnegans API keys.
- **Option A for Phase 2:** the Python connector in one shared container on
  Cloudflare (the standard design for remote MCP servers). Rejected:
  - one container per person, for cost;
  - a TypeScript rewrite on Workers, because of the effort, the weaker analysis
    of big results, and the risk of re-implementing the write logic with no
    Finnegans test environment.
- **Phase 2 sign-in:** company Google accounts from two domains (SOUTEX and
  Formas).
- **Phase 2 admins:** Juan and Rodrigo. Hosting is Rodrigo's Cloudflare account,
  where Juan is a member.
- **Budget:** stay at or near the $5 Workers Paid plan. Phase 1 costs nothing.
- **Writes:** allowed from day one, limited by each person's Finnegans
  permissions.
- **No periodic permission scans:** an initial scan plus a manual rescan is
  enough, because permissions rarely change.
- **No narrow versions:** permissions narrow what each person sees, and people
  write their own skills for guidance.
- **No `exportar` online.** The desktop extension keeps it.
- **One program:** desktop and online run the same code and get the same fixes.
- **Repo:** `formaspublicitarias/finnegans-MCP`, public.

## 3. Goals, non-goals, anti-goals

**Goals**

1. Each person works in Finnegans as themselves, with their own API keys.
2. Search and `ver_endpoint` only offer what that person's account can use.
3. Every permission refusal is explained correctly, in plain Spanish.
4. Changes keep working exactly as today: save, then show the diff.
5. Phase 1 ships through the same channel as today, with no new infrastructure
   and $0 extra.
6. After Phase 1, going online is mostly new pieces around the connector, not a
   rework of it.
7. Phase 2:
   - no install, on any device;
   - company sign-in;
   - an admin page;
   - a shared change log of who did what.

**Non-goals**

- Periodic permission scans.
- Probing write permissions up front. There's no safe way to test a write
  without writing, so write permission is learned from real refusals.
- Narrow versions (`/mcp/facturar`, …). The design leaves room for them later.
- A shared change log in Phase 1. Each PC only knows its own changes. First,
  check whether Finnegans already records which API user changed each record
  (§5.6).
- A TypeScript rewrite, or one container per person.
- Moving the desktop extension to its own repo.

**Anti-goals** (failure even if it technically works)

- A permission refusal reported as "your keys are wrong" or "a parameter is
  missing".
- A permission scan that puts real load on production Finnegans (§5.3).
- A Finnegans key, token, swagger key or docs key showing up in:
  - any tool output, log line or exported file;
  - the public repo.
- Phase 2: one person seeing another person's tables, results, keys or log
  entries.
- The desktop extension and the online version drifting into two programs.

## 4. Facts and constraints (verified 2026-11-17)

**Finnegans** (read-only checks; see memory `finnegans-permisos-por-cuenta`)

- swaggerGlobal works only with the company docs key and gives the same 586
  paths to everyone. It rejects API tokens, so there's no per-account swagger.
- No endpoint lists an account's permissions.
- **Reports:** a denied account gets `403 "Forbidden: Prestacion sin permiso"`
  *before* parameter validation. For an allowed account, the report actually
  **runs**, even without parameters.
- **Entities:** `GET /{entidad}/ZZ-NOEXISTE` answers 404 when allowed, or 500
  `"No tiene permisos para transacciones de la categoría…"` when denied.
- A full scan is about 364 calls and took about 2 minutes.
- Write refusals have not been observed yet.
- **There is no test environment.** Production already holds test records, so
  any write bug lands on real data.
- **The documentation keys** (`x-client-id`, `x-secret-key`) are personal, per
  Finnegans' own documentation: each user finds them in Finnegans GO under
  Modificar perfil → Datos personales.

**Current code**

- `Settings.from_env` reads every key from environment variables. The manifest
  fills them from the settings form: client ID, client secret, swagger key,
  docs client ID and docs secret key, all required today.
- `errores.traducir_error` turns a read 403 "Prestacion sin permiso" into
  "credenciales rechazadas", and a 500 "No tiene permisos" into "falta un
  parámetro".
- `FinnegansClient` re-authenticates and retries on every 403, which doubles
  each refused call.
- `crear_servidor` closes over a single client, workspace, `origen_tabla`,
  redactor and lock.
- Responses are capped at `RESPUESTA_MAX_CHARS` = 8,000 characters.
- Finnegans calls time out after 30 s.
- 413 tests.

**Claude, Cloudflare, MCP SDK** (relevant to Phase 2): see §6.1.

**Repo rules**

- Never read, print or commit `.env` values. Tests use fake credentials only.
- No admin emails, company domains or account IDs in committed files.
- No production writes from tests or scripts without Juan's explicit go.
- **Redact first, then truncate.**
- User-facing text is in Spanish (Argentina).

## 5. Phase 1 — per person on the desktop, ready for a container

### 5.1 The settings form

Each person enters only what is personal. The form changes as follows:

| Field | Today | Phase 1 |
|---|---|---|
| Client ID de Finnegans | required | required, personal |
| Client secret de Finnegans | required | required, personal |
| Clave del swagger | required | **pre-filled** in the build uploaded to the organization (see below); hidden under "avanzado" |
| Docs client ID / secret | required | required, **personal** (each person's own, from Finnegans GO → Modificar perfil → Datos personales) |
| Carpeta de exportación | optional | unchanged |

**Pre-filling the swagger key.** It's a company-wide, read-only documentation
key that already appears inside every `$ref` of the spec, so it isn't a personal
secret. It still must never be in the public repo.

- The packing script reads `FINNEGANS_SWAGGER_KEY` from the local `.env` at
  build time.
- It writes the key as the field's `default` into the manifest copy that goes
  inside the `.mcpb`.
- The committed `manifest.json` keeps no default.
- The `.mcpb` uploaded to the organization is not published anywhere public.
  *(Claude's call; Juan can choose to keep the field typed by hand instead.)*

**Form texts.** They stop saying "Te lo pasa Juan Sbatella" for personal keys.
They say where the person gets them, or that an admin hands them over, using
generic wording.

### 5.2 One per-person context (the container seam)

`server.py` stops closing over single objects. Everything that belongs to one
person moves into a `Contexto`:

```
Contexto
  client        FinnegansClient (this person's keys and token)
  workspace     Workspace (in-memory DuckDB, private temp dir)
  origen_tabla  where each table came from
  candado       RLock for DuckDB
  permisos      Permisos (the map, see 5.3–5.4)
  docs          DocsMcp (this person's docs keys)
```

- A `contextvars.ContextVar` holds the current `Contexto`. Every tool reads it at
  the start of each call, never at registration time.
- On the desktop there is exactly one `Contexto`, built at start-up from
  `Settings.from_env()`. Behaviour is identical to today.
- **Phase 2 adds** a registry that finds or creates the `Contexto` per signed-in
  person (§6.4). Nothing in the tools changes.
- `SwaggerCatalog` stays shared at process level: it uses the company swagger
  key and holds company-wide metadata, not results.
- `DocsMcp` uses each person's own docs keys (§9), so it lives in the
  `Contexto`. Its search results are company-wide documentation, so caching
  them across people is allowed if it's ever needed.
- The mode (`escritorio` | `remoto`) is a parameter of `crear_servidor`. It
  decides:
  - the tool set (`exportar` only on the desktop);
  - the instructions text;
  - how messages refer to "who to ask": on the desktop, the extension's
    settings; online, `FINNEGANS_CONTACTO_ADMIN`.
- **Rule for the builder:** no tool may depend on MCP session state, and nothing
  person-specific may be stored outside the `Contexto`. Both are needed for
  Phase 2.

### 5.3 The permission scan

New module `finnegans_core/permisos.py`. It runs with that person's own token.

- **Targets:** every report (viewer) and every entity in the swagger.
- **Entities:** `GET /api/{entidad}/ZZ-NOEXISTE`.
  - 500 containing "No tiene permisos" → `denegado`.
  - 404 → `permitido`.
  - Anything else → `desconocido`, which is treated as allowed.
- **Reports:** `GET /api/reports/{Nombre}`.
  - 403 containing "Prestacion sin permiso" → `denegado`.
  - Anything else → `permitido`, including 200, 500 and timeouts. The denial
    comes back before any work starts, so a slow answer means the report is
    running, which means it's allowed.
- **Load on Finnegans.** For an allowed account, a report probe without params
  really runs the report. Closing the connection doesn't stop it, and about 140
  allowed reports per person means about 140 real report runs per scan.
  1. **First task of Phase 1: a read-only spike with Juan's account.** Find a
     report probe that, when allowed, fails fast **after** the permission check.
     Candidates: an invalid value for a required parameter, `desde` after
     `hasta`, or a 1-day range. Measure 3–5 known-heavy reports and pick the
     cheapest probe that keeps both outcomes distinguishable.
  2. **If no cheap probe exists:**
     - the automatic scan covers **entities only**;
     - reports are learned from use (§5.4);
     - a full scan that includes reports runs only when the person asks for it
       explicitly, with a warning that it runs about 140 reports on Finnegans.
- **Gentle on the client side:**
  - at most 4 requests in flight;
  - a 10 s timeout per request;
  - read only the status line and the first 2 KB of the body;
  - one token for the whole scan.
- **When:**
  - automatically in the background, at the first start of the connector, or
    when the client ID changes;
  - on request: `verificar_conexion(reescanear=True)`. It starts the scan in the
    background and answers right away: "Estoy revisando tus permisos, tarda unos
    2 minutos". *(Claude's call: a parameter on an existing tool, not a new
    tool.)*

  There are no periodic scans. While a scan runs or before the first one, nothing
  is hidden.
- **A failed scan** keeps the previous map. `verificar_conexion` reports it.

### 5.4 The permission map and how it's used

- **Shape:** one entry per canonical path (`/reports/{Nombre}`, or `/{entidad}`,
  which covers its `/{codigo}` and `/list`). Each entry has:
  - `acceso`: `permitido` | `denegado` | `desconocido`;
  - `fuente`: `escaneo` | `uso`;
  - `escaneado_en`.
- **Write refusals** are kept separately per entity (`escritura_denegada`), since
  reading and writing are different permissions.
- **Storage behind an interface.** `AlmacenPermisos` has `cargar()`,
  `guardar_escaneo()` and `corregir(path, acceso, fuente)`.
  - **Phase 1: `AlmacenLocal`.** One JSON file in the user's app-data folder
    (`%LOCALAPPDATA%\Finnegans\` on Windows, the platform equivalent elsewhere).
    It's named by a hash of the client ID, so new keys mean a new map, and no
    key appears in the file name or contents. Writes are atomic: write a
    temporary file, then rename.
  - **Phase 2: `AlmacenRemoto`** (§6.5).
- **How the tools use it:**
  - **`buscar_endpoint`:** drops `denegado` results from the swagger and the
    docs. If everything matched was dropped, it says: "Lo que buscás existe en
    Finnegans, pero tu usuario no tiene permiso. Si lo necesitás, pedíselo a
    quien administra Finnegans y después pedime que revise tus permisos."
    Entities with `escritura_denegada` are tagged "solo lectura para vos".
  - **`ver_endpoint`:** for a `denegado` path, returns that message instead of
    the schema. It carries the same "solo lectura" tag.
  - **`leer`:** still **tries** a `denegado` path, because the permission may
    have been granted after the scan.
    - Success → corrected to `permitido` (`fuente: uso`).
    - Refusal → the message from §5.5, and the path is marked `denegado`.
  - **`escribir`:** always available. A write refused for lack of permission
    marks `escritura_denegada`.
    - The shape of a write refusal hasn't been observed yet. Until it is, treat
      any 403, and any 500 whose body contains "permiso", as a permission
      refusal.
  - **Paths not in the map** (for example, new in the swagger) are treated as
    allowed.

### 5.5 Correct refusal messages

The fix goes in `finnegans_core`, so both phases get it.

- Detect permission refusals by body text ("Prestacion sin permiso", "No tiene
  permisos"), not only by status code.
- `FinnegansClient` does **not** re-authenticate on a 403 whose body says "sin
  permiso". The retry on other 401/403 responses stays.
- New message: "Tu usuario de Finnegans no tiene permiso para {acción} en
  '{recurso}'. Si lo necesitás, pedíselo a quien administra Finnegans."
- The existing write-403 message keeps its meaning but uses the same wording.
- Credential messages ("revisá el Client ID… en la configuración de la
  extensión") stay for real 401s. Their "who to ask" part comes from the mode
  (§5.2).

### 5.6 Who did what (investigation only)

Now that everyone uses their own keys, Finnegans itself may already record which
API user created or changed each record. Check this read-only on one recently
changed record: look for fields like `UsuarioModificacion` or similar, or for an
audit report in the swagger.

- **If it does:** the guide (`guia escrituras`) explains how to look it up, and
  Phase 1 needs no change log of its own.
- **If it doesn't:** the shared change log arrives with Phase 2 (§6.7).

### 5.7 Also in Phase 1

- Tag the current state as `v1.0.2` before starting.
- Bump the version to 1.1.0 and upload the new `.mcpb` to the organization.
- `verificar_conexion` reports the permission state: "Permisos revisados el
  17/11: 138 de 238 reportes y 113 de 126 entidades disponibles", or "todavía
  revisando".

### 5.8 Phase 1 testing (fakes only)

- **Scan:**
  - the classification for every response shape in §5.3, including timeouts;
  - at most 4 requests in flight;
  - a failed scan keeps the old map.
- **Map:**
  - `AlmacenLocal` round-trips, writes atomically, uses a hash-named file, and
    never contains a secret;
  - a new client ID means a new map.
- **Filter:**
  - `buscar_endpoint` and `ver_endpoint` hide `denegado` paths;
  - the "everything was hidden" message;
  - `leer` self-corrects a stale `denegado`;
  - write refusals get recorded;
  - unknown paths are allowed.
- **Errors:**
  - the new permission messages for both refusal shapes;
  - no re-authentication on "sin permiso".
- **Context:**
  - every tool reads the current `Contexto`;
  - a test with two contexts set in turn proves each tool uses whichever one is
    current, which is the groundwork for Phase 2.
- **Manifest:**
  - the committed `manifest.json` has no swagger-key default;
  - the packing script injects it only into the bundled copy.
- **Regression:** all 413 current tests still pass, adjusted only where the old
  wrong messages were asserted.

## 6. Phase 2 — online (option A)

Built after Phase 1, with its own plan. What Phase 2 adds: an HTTP entry point, a
registry of contexts, a Worker, and a container image. The tools themselves don't
change.

### 6.1 Facts that apply to Phase 2

**Cloudflare**

- Containers have been generally available since 2026-04-13 and need the Workers
  Paid plan.
- A container is reached through a Durable Object.
- Cold start takes about 1–3 s plus our own start-up work.
- Disk is ephemeral.
- `setInactivityTimeout` controls idle sleep (up to 6 h). On stop, the container
  gets SIGTERM, then SIGKILL after up to 15 min.
- Env vars are passed via `start({env})`, and `enableInternet: true` is needed.
- The `basic` instance has 1/4 vCPU, 1 GiB memory and 4 GB disk.
- Included per month: 25 GiB-h memory, 375 vCPU-min and 200 GB-h disk. After
  that, about $0.009 per GiB-hour of memory.

**`@cloudflare/workers-oauth-provider`**

- Client registration through DCR and through CIMD (needs
  `global_fetch_strictly_public`).
- PKCE.
- User props are passed to the API handler.
- The KV binding is `OAUTH_KV`.

**Claude connectors** (claude.ai, Desktop and mobile share them)

- **Callback:** `https://claude.ai/api/mcp/auth_callback`. Claude Code uses a
  loopback on any port.
- **Starting sign-in:** sign-in starts only on a **401** with
  `WWW-Authenticate: Bearer resource_metadata="…"`.
  - `resource` must equal the URL exactly.
  - Only the first entry of `authorization_servers` is used.
- **CIMD:** used only if the metadata advertises
  `client_id_metadata_document_supported: true` **and** `"none"` in
  `token_endpoint_auth_methods_supported`. Otherwise Claude falls back to DCR.
- **PKCE:** S256 is required.
- **Token endpoint:**
  - must accept form-urlencoded bodies;
  - must return `invalid_grant` for a dead refresh token;
  - must rotate refresh tokens for public clients.
- **Timeouts:** 10 s for discovery, registration and token; 30 s for refresh.
- **Egress:** `160.79.104.0/21`.

**MCP SDK 2.3.0**

- `run(transport="streamable-http", stateless_http=…, json_response=…,
  transport_security=…)`.
- Sync tools run in threads through `anyio.to_thread.run_sync`, which copies
  `contextvars`.

### 6.2 Architecture

```
Claude (web / desktop / mobile)
   │  HTTPS, OAuth bearer token
   ▼
Worker "finnegans-remoto" (TypeScript)
   ├─ OAuth server for Claude (workers-oauth-provider: CIMD + DCR + PKCE)
   ├─ Google sign-in (OIDC) for people and for /admin
   ├─ /admin        Juan and Rodrigo
   ├─ /mcp          checks the person is active → forwards with signed internal headers
   ├─ /_interno/*   callbacks from the container (shared secret)
   ├─ audit log     written from the traffic it forwards
   └─ D1            people, encrypted keys, permission maps, audit log
          ▼
Durable Object "Servidor" (one) → starts/stops the one container, forwards
          ▼
Container: the same Python connector, mode "remoto", stateless HTTP, 7 tools,
           one Contexto per person (registry), AlmacenRemoto for permission maps
          ▼
api.finneg.com · swaggerGlobal · Finnegans docs MCP
```

The URL at launch is `https://finnegans-remoto.<subdomain>.workers.dev/mcp`. A
custom domain, if any, comes before the team rollout. *(Builder's call.)*

### 6.3 Sign-in, admin, keys

- **Sign-in:**
  1. Claude gets a 401 with `resource_metadata` and registers through CIMD or
     DCR.
  2. The Worker's `/authorize` sends the person to Google, using an **External**
     OAuth client in production with scopes `openid email profile`. This works
     with two domains, and the scopes don't need Google's app verification.
  3. The Worker checks the ID token: `email_verified`, and the `hd` claim plus
     the email's domain in `ALLOWED_DOMAINS` (a Worker variable, never
     committed).
  4. It looks up the email in `personas`:
     - active → `completeAuthorization({email})`;
     - otherwise → a Spanish "pedile acceso a {CONTACTO_ADMIN}" page, and no
       token.
- **Every `/mcp` request** re-checks that the person is active, with a cache of
  up to 60 s. Removing someone takes effect on their next request and drops their
  context.
- **Admin page** (`/admin`):
  - **Access:**
    - same Google sign-in;
    - only emails in the `ADMIN_EMAILS` secret;
    - a CSRF token on write actions;
    - an `HttpOnly`, `Secure`, `SameSite=Lax` session cookie that lasts 8 h.
  - **Personas:** the list with a permission summary, and actions to add,
    disable, remove and rescan.
  - **Agregar / reemplazar claves:** keys are checked against Finnegans before
    saving. Fields are write-only and never shown again.
  - **Registro:** the change log, with filters.
  - **Month's container hours,** to check the cost.
- **Per-person keys:** stored in D1, encrypted with AES-256-GCM.
  - The key is `MASTER_KEY`, with a random nonce per value.
  - The AAD is the email.
  - A `clave_version` column allows rotation.
- **Shared secrets:** Worker secrets only. The container receives the shared
  Finnegans keys and `INTERNAL_SECRET` as env vars at start.
- **Docs keys are personal** (§9). They're stored encrypted per person, like the
  API keys. `DocsMcp` becomes part of the per-person `Contexto` instead of being
  shared, and only `SwaggerCatalog` stays process-wide.

### 6.4 Worker → container

- **One Durable Object, one `basic` container**, with a 15-minute idle timeout.
  - It sleeps nights and weekends, so the first request after that waits a few
    seconds.
  - Before forwarding, the Durable Object waits for `/salud`.
  - If the container fails to start, Claude gets a Spanish MCP error, never a
    raw 5xx.
- **Headers on `/mcp`:**
  - The Worker **strips** incoming `X-Finnegans-*` headers.
  - It adds `X-Finnegans-Persona` (from the verified OAuth props only), the
    person's decrypted keys, `X-Finnegans-Clave-Version` and
    `X-Finnegans-Permisos-Version`.
  - It adds `X-Finnegans-Firma`: an HMAC-SHA256 with `INTERNAL_SECRET` over the
    email, the versions and a timestamp.
  - Neither side ever logs these headers.
- **The container's ASGI middleware:**
  - rejects requests with a missing, wrong or stale (over 60 s) signature;
  - finds or creates the person's `Contexto`, rebuilding it when the key version
    changes;
  - sets the ContextVar.
- **Registry limits:**
  - at most 6 live contexts, with the least recently used closed first;
  - each context closes after 30 minutes idle;
  - DuckDB is limited to 128 MB per person.

  These are start values; the builder measures them.
- **Redaction:** the redactor masks that person's secrets, the shared secrets,
  **and every other live context's keys and tokens.**
- **Transport:**
  - `stateless_http=True, json_response=True`;
  - DNS-rebinding protection is on, with the forwarding host in
    `allowed_hosts`;
  - the forward allows 240 s per request.
- **Internal routes:** `/salud` and `/_interno/*` are not reachable through the
  public `/mcp` route.

### 6.5 Permissions online

- **`AlmacenRemoto`** implements the same interface as `AlmacenLocal`:
  - `GET /_interno/permisos?email=…` loads the map.
  - `POST /_interno/permisos` sends corrections, fire-and-forget.
  - `POST /_interno/escaneo` delivers a finished scan.
  - Each call carries `Authorization: Bearer <INTERNAL_SECRET>`.
- **Reloading:** a context reloads its map when `X-Finnegans-Permisos-Version` is
  newer than the version it holds.
- **Scans:**
  - run in the container with the person's token, using the same module as
    Phase 1;
  - start when a person is added, when their keys change, or on "Reescanear" in
    the admin page;
  - the Durable Object holds the request open so the container doesn't sleep
    mid-scan;
  - the report probe follows whatever the Phase 1 spike settled.

### 6.6 Tools online

- 7 tools: no `exportar`.
- The instructions are the same five rules without "exportar". Rule 3 ends:
  "…trabajá con consultar (SQL); nunca pidas ni muestres todas las filas".
- The guide topics that mention `exportar` get wording that works in both modes.
- **Start-up:** measure container start plus the first `buscar_endpoint`.
  - Over 10 s: warm the swagger in the background at process start.
  - Still too slow: cache it in KV.
- **Logging:** HTTP loggers stay at WARNING, the middleware never logs headers,
  and everything printed goes through the redactor.

### 6.7 Shared change log

The **Worker writes it from the traffic it forwards.** The container returns
JSON, so the Worker sees every `tools/call` request and its result.

- **`escribir`:** the row is awaited before the response goes back.
  - If D1 fails, it retries once.
  - If that also fails, the response gets the line "Ojo: el cambio se hizo, pero
    no quedó registrado en el historial; avisale a {contacto}".
- **Other tools:** the row is written with `waitUntil`.
- **Columns:** `cuando`, `email`, `herramienta`, `metodo`, `path`, `codigo`,
  `resultado`, `filas`, `detalle`.
  - Writes: the diff plus the assigned code, up to 20,000 chars.
  - Reads: the path, the params and the row count, **never row data**. The SQL
    text is kept, up to 2,000 chars.
  - Everything is redacted first, then cut.
- **Also logged:** sign-ins, admin actions and scans.
- **Retention:** 365 days, cleaned up by a daily cron.
- **Access:** only the admins can read it.

### 6.8 Rollout

1. **Setup in Rodrigo's account:** D1, KV, Worker secrets and variables. Then
   the Google OAuth client: External, In production, with the redirect URI for
   the Worker's callback.
2. **Juan alone:** checks from the web, Desktop and the phone, read-only.
3. **The restricted account:** check the filter, the refusal messages, and the
   **isolation**: two people at the same time each see only their own tables in
   `SHOW TABLES`.
4. **First live write:** only with Juan's explicit go.
5. **Rodrigo, then the team.** If the plan is Team or Enterprise, an Owner adds
   the connector for the organization.

### 6.9 Cost

This assumes one `basic` container, awake about 240 h a month (working hours
plus the idle tails), for about 15 people.

| Item | Extra on top of the $5 plan |
|---|---|
| Memory | ≈ $1.95 |
| Disk | ≈ $0.20 |
| CPU | within the included amount |
| Worker, Durable Object, D1, KV, logs, egress | within the included amounts |
| **Total** | **≈ $2–3/month** |

Each extra hour awake costs about $0.01. `standard-1` would be about $8 extra.

### 6.10 Phase 2 testing

**Python:**

- **Isolation:**
  - two contexts with different tables never see each other through
    `SHOW TABLES`, `consultar` or an `escribir` base;
  - concurrent threaded requests keep the right context;
  - another person's secrets are masked.
- **Signature middleware:** a missing, wrong or stale signature never reaches a
  tool.
- **Registry:** LRU and idle close free the DuckDB and its temp dir, and a
  key-version change rebuilds the context.
- **`AlmacenRemoto`:** against a fake Worker.
- **Online mode:**
  - exactly 7 tools;
  - no "exportar" in any text shown online.

**Worker:**

- **Sign-in:**
  - a 401 with `resource_metadata`;
  - the metadata fields Claude requires;
  - domain and list checks;
  - someone disabled after signing in is denied.
- **Headers:** client `X-Finnegans-*` headers are stripped, and the signature is
  added.
- **Admin:** admin auth and CSRF.
- **Keys:** the encryption round-trips, and an AAD mismatch fails.
- **Callbacks:** `/_interno/*` requires the bearer.
- **Audit:** the awaited audit row, and its fallback line.

**Live:** manual, per §6.8.

## 7. Approaches considered

| Approach | Trade-off | Verdict |
|---|---|---|
| **Desktop per person first, then the Python connector in one shared container** | Ships value now at $0, with low risk. Phase 1's permission work and context seam are reused online. Phone access only arrives in Phase 2. | **Chosen** |
| Straight to online (shared container) | Phone access sooner, but everything lands at once and nothing is usable until the whole Worker, admin and container stack works. | Superseded by the phased roadmap |
| One container per person | Isolation comes from the design itself, with little refactoring. Costs about $15/month on top for 15 people. | Rejected (cost) |
| TypeScript rewrite on Workers | $0 extra and no cold start. But it means rewriting about 3,100 lines and 413 tests, analysis of big results gets weaker (SQLite instead of DuckDB), and the write rules have to be re-implemented with no Finnegans test environment. | Rejected |
| Desktop only, forever | $0 and already exists. No phone or browser, no shared change log, and a manual install per PC. | Kept as Phase 1 and as a backup, not as the end state |

## 8. Calls made by Claude (check these)

**Phase 1**

- The swagger key is pre-filled in the bundled `.mcpb` from the local `.env` at
  pack time, and never committed.
- Rescanning is `verificar_conexion(reescanear=True)`, not a new tool.
- The permission map lives in a hash-named JSON file in the user's app-data
  folder.
- Reports are learned from use if no cheap probe exists. Full report scans
  happen only on explicit request, with a warning.
- Who-did-what is an investigation first: Finnegans may already record it.

**Phase 2**

- **Access:** only people on the admin page's list get in.
- **The container:**
  - one `basic` container with a 15-minute idle timeout;
  - at most 6 live contexts, closed after 30 minutes idle;
  - DuckDB at 128 MB per person.
- **Keys** travel per request in signed internal headers.
- **Change log:** written by the Worker, with change rows awaited. Kept 365 days.
  Diffs up to 20,000 chars. No row data from reads.
- **Admin page sign-in:** the same Google sign-in, not Cloudflare Access.
- **URL:** a workers.dev URL at launch.

## 9. Decided after the reorganization

- **Documentation keys are personal.** Each person enters their own docs client
  ID and secret key, from Finnegans GO → Modificar perfil → Datos personales.
  That makes four personal keys in the form, plus the pre-filled swagger key.
  The form's help text tells people exactly where to find each key. In Phase 2,
  the docs keys are stored and encrypted per person, like the API keys, and
  passed per request alongside them.

## 10. Left to the builder

- **Phase 1:** the exact app-data path on each platform.
- **Phase 2:**
  - whether to use `ctx.container` or the `@cloudflare/containers` helper (pin
    versions at plan time);
  - whether the swagger needs warming or caching;
  - the final per-person DuckDB limit and the context cap;
  - the admin page's markup;
  - D1 schema details.
