# Finnegans MCP Phase 1 — per person on the desktop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each person runs the desktop extension with their own Finnegans keys. The connector learns which reports and entities that person can use, only offers those, and explains refusals correctly. The code is shaped so Phase 2 can serve many people from one process.

**Architecture:** New core modules:
- `finnegans_core/permisos.py`: refusal detection, the permission map, and the `Permisos` facade.
- `finnegans_core/almacen_permisos.py`: a store interface, plus a local JSON file implementation.
- `finnegans_core/escaneo.py`: a gentle probe scanner.

`server.py` stops closing over single objects. Every tool gets the current per-person `Contexto` from a provider function. On the desktop that provider always returns one context. The manifest asks for four personal keys. A packing script pre-fills the company swagger key in the bundled copy only.

**Tech Stack:** Python ≥3.12, MCP Python SDK 2.3 (`MCPServer`), httpx2, DuckDB 2.x, pytest, uv, `npx @anthropic-ai/mcpb pack`.

**Spec:** `docs/superpowers/specs/2026-11-17-finnegans-mcp-remoto-design.md` (Phase 1 is §5; decisions in §2 and §9).

## Global Constraints

- **Base branch:** this branch, `claude/remote-mcp-design-1fa593`. It contains `feat/extension-desktop` (PR formaspublicitarias/finnegans-MCP#14, not yet in `master`). Do the work on a new branch from here.
- **Python and dependencies:** Python `>=3.12`. No new runtime dependencies. New modules use only the standard library plus what `pyproject.toml` already lists.
- **Language:** all user-facing text is Spanish (Argentina), with voseo ("pedíselo", "revisá").
- **Redaction:** redact first, then truncate, in every new place that cuts text.
- **Keys and secrets:**
  - Tests use fake credentials only, from `tests/mcp/conftest.py` (`CLIENT_ID`, `CLIENT_SECRET`, …).
  - Never read, print or commit `.env` values. Scripts take keys from environment variables only (repo rule, see `scripts/prueba_escritura_en_vivo.py`).
  - The permission map file never contains a key, a token or a client ID. Its name uses a hash.
- **Live calls:**
  - No writes against Finnegans from tests or scripts.
  - The only live calls in this plan are Task 1's read-only spike and Task 8's manual check. Both are run by Juan or with him present.
- **Size limits:** responses stay under `RESPUESTA_MAX_CHARS` = 8000 (`finnegans_core/presupuesto.py`).
- **Scan limits:** at most 4 requests in flight, a 10 s timeout per request, at most 2048 bytes of body read per probe, and one token per scan.
- **Copy (exact strings from the spec):**
  - Refusal: `Tu usuario de Finnegans no tiene permiso para {accion} en '{recurso}'. Si lo necesitás, pedíselo a quien administra Finnegans.`
    - `accion` is `ver` for GET, `crear` for POST, `modificar` for PUT/PATCH, `borrar` for DELETE.
  - Everything hidden: `Lo que buscás existe en Finnegans, pero tu usuario no tiene permiso. Si lo necesitás, pedíselo a quien administra Finnegans y después pedime que revise tus permisos.`
  - Read-only tag: `solo lectura para vos`
  - Rescan started: `Estoy revisando tus permisos, tarda unos 2 minutos.`
  - Rescan already running: `Ya estoy revisando tus permisos; en un par de minutos está listo.`
  - Permission state: `Permisos revisados el {dd/mm}: {r} de {R} reportes y {e} de {E} entidades disponibles`, or `Permisos: todavía revisando`, or `Permisos: todavía no se revisaron`, or `Permisos: la última revisión falló; se usa la anterior`.
- **Version:** 1.1.0 in `pyproject.toml`, `manifest.json` and `finnegans_mcp/__init__.py` (Task 7).

## Review Focus

1. **A corrupt or half-written map file** (power cut mid-write, a hand edit). The connector starts, shows everything, and rescans. It never crashes at start-up. *Test in Task 3.*
2. **An app-data folder that can't be written** (locked profile, `LOCALAPPDATA` missing). The map lives in memory for the session, and `verificar_conexion` says it couldn't be saved. *Test in Task 3.*
3. **The swagger failing during a background scan** (bad swagger key, network down). The scan state becomes `fallo`, the previous map stays, and every tool keeps working. *Test in Task 6.*
4. **A rescan requested while a scan is running.** No second scan starts, and the person gets the "ya estoy revisando" line. *Test in Task 6.*
5. **The same resource written in different ways** (`cliente/2956`, `/api/cliente/list`, `Cliente`, `reports/x` vs `/reports/X`). All of them resolve to the same map entry. *Test in Task 3.*

---

## File Structure

- `scripts/sondeo_permisos.py` (new, Task 1): live read-only spike. It times report probes and lists authorship fields. Not shipped (`scripts/` is in `.mcpbignore`).
- `docs/superpowers/notas/2026-11-sondeo-permisos.md` (new, Task 1): the spike's measured results and the decisions taken from them.
- `src/finnegans_core/permisos.py` (new, Tasks 2–3, 6): refusal detection, `MapaPermisos`, the `Permisos` facade.
- `src/finnegans_core/almacen_permisos.py` (new, Task 3): the `AlmacenPermisos` protocol, `AlmacenLocal`, `AlmacenMemoria`, `carpeta_datos()`.
- `src/finnegans_core/escaneo.py` (new, Task 4): the two classifiers, `Sonda` and `Escaner`.
- `src/finnegans_core/errores.py` (modify, Task 2): the permission branch.
- `src/finnegans_core/client.py` (modify, Tasks 2 and 4): no re-auth on "sin permiso", and `sondear()`.
- `src/finnegans_core/catalogo/swagger.py` (modify, Task 4): `recursos()`.
- `src/finnegans_mcp/contexto.py` (new, Task 5): `Contexto` and `ProveedorContexto`.
- `src/finnegans_mcp/server.py` (modify, Tasks 5–6): tools read the provider, plus permission wiring.
- `manifest.json`, `pyproject.toml`, `src/finnegans_mcp/__init__.py`, `README.md` (modify, Task 7).
- `scripts/empaquetar.py` (new, Task 7): builds `finnegans.mcpb` with the swagger key pre-filled.
- Tests: `tests/core/test_permisos.py`, `tests/core/test_almacen_permisos.py`, `tests/core/test_escaneo.py`, `tests/mcp/test_contexto.py`, `tests/mcp/test_permisos_tools.py`, `tests/test_empaquetar.py` (new). Existing tests in `tests/core/test_errores.py`, `tests/core/test_client.py`, `tests/core/test_swagger.py`, `tests/test_manifest.py` and `tests/mcp/test_tools.py` get updated where listed.

---

### Task 1: Live spike — cheap report probe and authorship fields (read-only, with Juan)

**Files:**
- Create: `scripts/sondeo_permisos.py`
- Create: `docs/superpowers/notas/2026-11-sondeo-permisos.md`

**Interfaces:**
- Produces two decisions that later tasks copy into `finnegans_core/escaneo.py` (Task 4) and the guide (Task 6):
  - `SONDA_REPORTE: dict[str, str]`: query params added to every report probe. `{}` if no cheap probe exists.
  - `REPORTES_EN_ESCANEO_AUTOMATICO: bool`.

  Plus one finding on authorship fields, for spec §5.6.

- [ ] **Step 1: Tag today's version.** Run `git tag v1.0.2 f796ea2`. Push the tag only after Juan says so.

- [ ] **Step 2: Write `scripts/sondeo_permisos.py`.**
  - Usage: `uv run python scripts/sondeo_permisos.py --reportes DETALLETRANSACCIONES,<2–4 more heavy reports Juan names>`.
  - Keys come from the environment through `Settings.from_env()`. The script refuses to run if `Settings.faltantes()` is non-empty. It never prints a key, a token or a URL with query params.
  - It uses `FinnegansClient` with a 60 s timeout, GET only.
  - **Probes:** for each report, it times each candidate probe:
    - (a) no params;
    - (b) every required date param set to `"no-es-fecha"`;
    - (c) `desde` after `hasta` (`2099-01-02` / `2099-01-01`) on the report's date params, named as the swagger spells them;
    - (d) a 1-day range on yesterday.

    It prints: report, candidate, HTTP status, seconds, and the first 120 characters of the body after redaction.
  - **Authorship:** it reads `cliente/list` and then one `cliente/{codigo}`. It prints only the **field names** of that record that match `(?i)usuario|modific|alta|creaci|autor`, never their values. It also prints the swagger paths whose name or summary matches `(?i)auditor|log|historial`.

- [ ] **Step 3: Juan runs it against production** (read-only). Paste the output, minus any values, into `docs/superpowers/notas/2026-11-sondeo-permisos.md`.

- [ ] **Step 4: Record the decisions in the same note.**
  - **The report probe:** pick the cheapest candidate that answers in under 3 s on every heavy report, still with a non-403 status for an allowed account. Set it as `SONDA_REPORTE`.
  - **Automatic report scans:** `REPORTES_EN_ESCANEO_AUTOMATICO = True` only if such a candidate exists. Otherwise `SONDA_REPORTE = {}` and `False`.
  - **Authorship:** whether records carry the editing user. If they do, Task 6 adds a paragraph to `guia/escrituras.md` on how to look it up.

- [ ] **Step 5: Commit.**
```bash
git add scripts/sondeo_permisos.py docs/superpowers/notas/2026-11-sondeo-permisos.md
git commit -m "chore(scripts): sondeo en vivo de permisos de reportes y autoria"
```

---

### Task 2: Detect permission refusals and say so correctly

**Files:**
- Create: `src/finnegans_core/permisos.py` (refusal-detection part only)
- Modify: `src/finnegans_core/errores.py` (new branch before the `codigo == 404` block)
- Modify: `src/finnegans_core/client.py:121-124` (the 401/403 retry)
- Test: `tests/core/test_permisos.py`, `tests/core/test_errores.py`, `tests/core/test_client.py`

**Interfaces:**
- Produces, in `finnegans_core/permisos.py`:
  - `es_rechazo_permiso(status: int | None, cuerpo: str) -> bool`: True when the body, casefolded and with accents stripped, contains `prestacion sin permiso` or `no tiene permisos`.
  - `es_rechazo_escritura(status: int | None, cuerpo: str) -> bool`: `es_rechazo_permiso(...)`, or `status == 403`, or (`status == 500` and `permiso` is in the body).
  - `rechazo_en_mensaje(mensaje: str, escritura: bool) -> bool`: parses `HTTP nnn` and the text after `):` from a `FinnegansError` message, then applies one of the two functions above.
  - `ACCIONES: dict[str, str] = {"GET": "ver", "POST": "crear", "PUT": "modificar", "PATCH": "modificar", "DELETE": "borrar"}`
  - `mensaje_sin_permiso(metodo: str, recurso: str) -> str`: the exact refusal copy from Global Constraints.
- `traducir_error` keeps its signature.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_permisos.py
from finnegans_core.permisos import (
    es_rechazo_escritura, es_rechazo_permiso, mensaje_sin_permiso, rechazo_en_mensaje,
)

def test_reporte_denegado_es_rechazo():
    assert es_rechazo_permiso(403, '{"error":"Forbidden: Prestacion sin permiso"}')

def test_entidad_denegada_es_rechazo():
    assert es_rechazo_permiso(500, "No tiene permisos para transacciones de la categoría X")

def test_403_de_credenciales_no_es_rechazo_de_permiso():
    assert not es_rechazo_permiso(403, "Forbidden: token invalido")

def test_escritura_403_cualquiera_es_rechazo():
    assert es_rechazo_escritura(403, "Forbidden")

def test_escritura_500_con_permiso_es_rechazo_y_sin_permiso_no():
    assert es_rechazo_escritura(500, "El usuario no tiene permiso para modificar")
    assert not es_rechazo_escritura(500, "Falta el campo Nombre")

def test_rechazo_en_mensaje_del_cliente():
    msg = "Error en GET reports/X (HTTP 403): Forbidden: Prestacion sin permiso"
    assert rechazo_en_mensaje(msg, escritura=False)

def test_mensaje_sin_permiso_textual():
    assert mensaje_sin_permiso("PUT", "cliente") == (
        "Tu usuario de Finnegans no tiene permiso para modificar en 'cliente'. "
        "Si lo necesitás, pedíselo a quien administra Finnegans."
    )
```

Add to `tests/core/test_errores.py`:
- `test_lectura_403_sin_permiso_no_culpa_a_las_credenciales`: `traducir_error("reports/X", "Error en GET reports/X (HTTP 403): Forbidden: Prestacion sin permiso")` equals `mensaje_sin_permiso("GET", "reports/X")`, and `"credenciales" not in` the result.
- `test_500_no_tiene_permisos_no_dice_falta_parametro`: `traducir_error("Tareas", "Error en GET Tareas (HTTP 500): No tiene permisos para transacciones de la categoría Tareas")` equals `mensaje_sin_permiso("GET", "Tareas")`.
- `test_escritura_403_usa_el_mensaje_nuevo`: a PUT 403 gives `mensaje_sin_permiso("PUT", "cliente")`.
- `test_403_sin_texto_de_permiso_sigue_siendo_credenciales`: a GET 403 "token invalido" still contains "credenciales".

Add to `tests/core/test_client.py`:
- `test_403_sin_permiso_no_reautentica`: with a MockTransport, the token endpoint is hit exactly once and the GET exactly once. `FinnegansError` is raised with "Prestacion sin permiso" in it.
- `test_403_comun_sigue_reintentando_una_vez`: the existing behaviour: 2 token calls and 2 GETs.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/core/test_permisos.py tests/core/test_errores.py tests/core/test_client.py -q`
Expected: FAIL. `ModuleNotFoundError: finnegans_core.permisos`, plus the new assertions in `test_errores` and `test_client`.

- [ ] **Step 3: Implement**
  - The functions listed in Interfaces, in `finnegans_core/permisos.py`. Strip accents with `finnegans_core.vocabulario.sin_acentos`.
  - In `errores.traducir_error`, right after `codigo` and `es_escritura` are computed: if `es_escritura` and `es_rechazo_escritura(codigo, msg)`, or not `es_escritura` and `es_rechazo_permiso(codigo, msg)`, return `mensaje_sin_permiso(metodo or "GET", recurso)`. Delete the old `codigo == 403 and es_escritura` block.
  - In `client._request`, retry on 401/403 only when `not es_rechazo_permiso(resp.status_code, resp.text)`.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS. Old assertions on the removed write-403 text (`grep -rn "no le da permiso a este conector" tests`) get updated to `mensaje_sin_permiso(...)`.

- [ ] **Step 5: Commit**
```bash
git add src/finnegans_core/permisos.py src/finnegans_core/errores.py src/finnegans_core/client.py tests/core
git commit -m "fix(errores): los rechazos por permiso ya no culpan a las claves ni reintentan"
```

---

### Task 3: The permission map and its local store

**Files:**
- Modify: `src/finnegans_core/permisos.py` (add map types)
- Create: `src/finnegans_core/almacen_permisos.py`
- Test: `tests/core/test_permisos.py`, `tests/core/test_almacen_permisos.py`

**Interfaces:**
- Produces, in `permisos.py`:
  - `Acceso = Literal["permitido", "denegado", "desconocido"]`, `Fuente = Literal["escaneo", "uso"]`, `TipoRecurso = Literal["reporte", "entidad"]`, `EstadoEscaneo = Literal["sin_escanear", "escaneando", "listo", "fallo"]`.
  - `clave_permiso(path: str) -> str | None`:
    - strip a leading `/api`, then slashes;
    - first segment `reports`, case-insensitive → `"reports/" + second segment`;
    - otherwise → the first segment;
    - casefold the result;
    - `None` for an empty path.
  - `@dataclass Entrada(acceso: Acceso, fuente: Fuente, tipo: TipoRecurso | None, cuando: str)`, where `cuando` is an ISO date.
  - `@dataclass MapaPermisos`:
    - fields: `entradas: dict[str, Entrada]`, `escritura_denegada: set[str]`, `estado: EstadoEscaneo = "sin_escanear"`, `escaneo_fin: str | None = None`, `version: int = 0`;
    - `acceso(path) -> Acceso | None`, `denegado(path) -> bool`, `solo_lectura(path) -> bool`;
    - `aplicar_escaneo(resultado: dict[str, tuple[Acceso, TipoRecurso]], cuando: str) -> None`: replaces only the keys it carries, keeps the rest and `escritura_denegada`, sets `estado="listo"` and `escaneo_fin`, increments `version`;
    - `corregir(path, acceso: Acceso) -> bool`: sets `fuente="uso"` and returns True if anything changed. Only `aplicar_escaneo` changes `version`; `corregir` and `marcar_escritura_denegada` don't;
    - `marcar_escritura_denegada(path) -> bool`;
    - `resumen() -> tuple[int, int, int, int]`: allowed reports, total reports, allowed entities, total entities. `desconocido` counts as allowed;
    - `a_dict() -> dict` and `MapaPermisos.desde_dict(d) -> MapaPermisos`.
- Produces, in `almacen_permisos.py`:
  - `class AlmacenPermisos(Protocol)`: `cargar() -> MapaPermisos`, `guardar(mapa: MapaPermisos) -> None`, `problema: str | None` (the last save error, in Spanish, or None).
  - `AlmacenMemoria()`: keeps the map in memory, for tests and as a fallback.
  - `AlmacenLocal(carpeta: Path, client_id: str)`:
    - file `carpeta / f"permisos-{sha256(client_id.strip()).hexdigest()[:16]}.json"`;
    - `cargar()` returns an empty `MapaPermisos()` on a missing, unreadable or invalid file;
    - `guardar()` writes `<file>.tmp` then `os.replace`. On `OSError` it keeps the map in memory and sets `problema = "No pude guardar tus permisos en esta PC; se van a revisar de nuevo la próxima vez."`
  - `carpeta_datos() -> Path`:
    - `%LOCALAPPDATA%\Finnegans` on Windows;
    - `~/Library/Application Support/Finnegans` on macOS;
    - else `$XDG_DATA_HOME/finnegans`, or `~/.local/share/finnegans`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/core/test_permisos.py (add)
import pytest
from finnegans_core.permisos import MapaPermisos, clave_permiso

@pytest.mark.parametrize("path", ["cliente", "/cliente/2956", "api/cliente/list", "/api/Cliente"])
def test_clave_de_entidad(path):
    assert clave_permiso(path) == "cliente"

@pytest.mark.parametrize("path", ["reports/ACOrdenes", "/api/Reports/acordenes", "/reports/ACOrdenes/"])
def test_clave_de_reporte(path):
    assert clave_permiso(path) == "reports/acordenes"

def test_escaneo_reemplaza_lo_suyo_y_conserva_lo_demas():
    m = MapaPermisos()
    m.aplicar_escaneo({"cliente": ("permitido", "entidad"), "reports/x": ("denegado", "reporte")}, "2026-11-17")
    m.corregir("reports/y", "denegado")
    m.marcar_escritura_denegada("cliente")
    m.aplicar_escaneo({"cliente": ("permitido", "entidad")}, "2026-11-18")
    assert m.denegado("reports/x") and m.denegado("reports/y")
    assert m.solo_lectura("cliente/1") and m.estado == "listo" and m.version == 2

def test_resumen_cuenta_desconocido_como_permitido():
    m = MapaPermisos()
    m.aplicar_escaneo({"a": ("permitido", "entidad"), "b": ("desconocido", "entidad"),
                       "reports/r": ("denegado", "reporte")}, "2026-11-17")
    assert m.resumen() == (0, 1, 2, 2)

def test_ida_y_vuelta_a_dict():
    m = MapaPermisos()
    m.aplicar_escaneo({"cliente": ("denegado", "entidad")}, "2026-11-17")
    assert MapaPermisos.desde_dict(m.a_dict()) == m
```

```python
# tests/core/test_almacen_permisos.py
from finnegans_core.almacen_permisos import AlmacenLocal
from finnegans_core.permisos import MapaPermisos

CID = "cid-falso-1a2b3c"

def test_guarda_y_carga(tmp_path): ...            # aplicar_escaneo, guardar, a fresh AlmacenLocal carga ==
def test_archivo_sin_secretos_en_nombre_ni_contenido(tmp_path): ...
                                                  # CID not in any file name nor in any file's text
def test_otro_client_id_otro_mapa(tmp_path): ...  # AlmacenLocal(tmp, "otro").cargar().entradas == {}
def test_archivo_corrupto_da_mapa_vacio(tmp_path): ...
                                                  # write "{no json" to the expected file -> cargar() == MapaPermisos()
def test_carpeta_no_escribible_no_rompe(tmp_path, monkeypatch): ...
                                                  # monkeypatch os.replace to raise PermissionError ->
                                                  # guardar() doesn't raise, problema startswith "No pude guardar"
def test_escritura_atomica_no_deja_tmp(tmp_path): ...  # after guardar, no *.tmp left
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/core/test_permisos.py tests/core/test_almacen_permisos.py -q`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement** the types and functions in Interfaces. Serialize `escritura_denegada` as a sorted list.

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest tests/core -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/finnegans_core/permisos.py src/finnegans_core/almacen_permisos.py tests/core
git commit -m "feat(permisos): mapa de permisos por persona y almacen local"
```

---

### Task 4: The probe scanner

**Files:**
- Modify: `src/finnegans_core/catalogo/swagger.py` (add `recursos()`)
- Modify: `src/finnegans_core/client.py` (add `sondear()`)
- Create: `src/finnegans_core/escaneo.py`
- Test: `tests/core/test_swagger.py`, `tests/core/test_client.py`, `tests/core/test_escaneo.py`

**Interfaces:**
- Consumes: `clave_permiso`, `Acceso`, `TipoRecurso`, `es_rechazo_permiso` (Tasks 2–3), and the Task 1 decisions.
- Produces:
  - `SwaggerCatalog.recursos() -> list[tuple[str, TipoRecurso]]`:
    - one entry per tagged resource;
    - viewers as `"reports/{Nombre}"`, taken from their `/reports/...` path;
    - entities as their first path segment;
    - deduplicated by `clave_permiso`, keeping the swagger's spelling;
    - untagged paths and `otro` are left out.
  - `FinnegansClient.sondear(path: str, id: str | None = None, params: dict | None = None, timeout: float = 10.0) -> tuple[int | None, str]`:
    - a GET with `ACCESS_TOKEN`, streamed;
    - reads at most 2048 bytes, then closes;
    - returns `(status, redacted text)`;
    - `(None, "")` on a timeout or transport error;
    - never retries and never raises `FinnegansError`.
  - In `escaneo.py`:
    - `SONDA_REPORTE: dict[str, str]` and `REPORTES_EN_ESCANEO_AUTOMATICO: bool`, with the values from Task 1;
    - `ID_INEXISTENTE = "ZZ-NOEXISTE"`;
    - `clasificar_reporte(status, cuerpo) -> Acceso`: `denegado` iff `status == 403` and `es_rechazo_permiso`, else `permitido`;
    - `clasificar_entidad(status, cuerpo) -> Acceso`: `denegado` iff `es_rechazo_permiso`; `permitido` iff `status == 404`; else `desconocido`;
    - `class Sonda(Protocol): def sondear(self, path, id=None, params=None, timeout=10.0) -> tuple[int | None, str]`;
    - `Escaner(sonda: Sonda, max_en_vuelo: int = 4, timeout: float = 10.0)`, with `escanear(objetivos: list[tuple[str, TipoRecurso]], incluir_reportes: bool) -> dict[str, tuple[Acceso, TipoRecurso]]`:
      - uses `concurrent.futures.ThreadPoolExecutor(max_workers=max_en_vuelo)`;
      - report probe: `sonda.sondear(path, params=SONDA_REPORTE)`;
      - entity probe: `sonda.sondear(entidad, id=ID_INEXISTENTE)`;
      - result keys are `clave_permiso(path)`;
      - reports are skipped when `incluir_reportes` is False.

- [ ] **Step 1: Write the failing tests**
  - `test_swagger.py::test_recursos_lista_reportes_y_entidades`: with the `SPEC` from `tests/mcp/conftest.py`, the result is `[("cliente", "entidad"), ("reports/ACOrdenesCompraPendientes", "reporte")]`, in any order.
  - `test_client.py::test_sondear_devuelve_status_y_corta_el_cuerpo`:
    - a 5000-char body → `len(texto) <= 2048`;
    - a body containing `CLIENT_SECRET` comes back masked;
    - a 403 does **not** trigger a second token call.
  - `test_client.py::test_sondear_timeout_da_none`: a MockTransport raising `httpx2.ReadTimeout` → `(None, "")`.
  - `test_escaneo.py`:

```python
@pytest.mark.parametrize("status,cuerpo,esperado", [
    (403, "Forbidden: Prestacion sin permiso", "denegado"),
    (500, "falta PARAM_Fechadesde", "permitido"),
    (200, "[]", "permitido"),
    (None, "", "permitido"),        # timeout: el reporte esta corriendo
    (403, "token invalido", "permitido"),
])
def test_clasificar_reporte(status, cuerpo, esperado): ...

@pytest.mark.parametrize("status,cuerpo,esperado", [
    (404, "no existe", "permitido"),
    (500, "No tiene permisos para transacciones de la categoría Tareas", "denegado"),
    (500, "otra cosa", "desconocido"),
    (None, "", "desconocido"),
])
def test_clasificar_entidad(status, cuerpo, esperado): ...

def test_nunca_mas_de_cuatro_en_vuelo(): ...
    # SondaFalsa sleeps 0.05 s per call and tracks max concurrency with a lock; 40 targets -> max <= 4
def test_entidades_usan_codigo_inexistente_y_reportes_la_sonda(): ...
    # records calls: entity -> id == "ZZ-NOEXISTE"; report -> params == SONDA_REPORTE
def test_sin_reportes_no_sondea_reportes(): ...
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/core -q`
Expected: FAIL on the new tests.

- [ ] **Step 3: Implement** the Interfaces. `sondear` uses `self.http.stream("GET", ...)` with `timeout=timeout`. It reads `iter_bytes()` until 2048 bytes, decodes with `errors="replace"`, and passes the text through `self._detalle(texto, 2048)` (redact, then cut).

- [ ] **Step 4: Run them to verify they pass**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/finnegans_core tests/core
git commit -m "feat(escaneo): sondeo suave de reportes y entidades con el token de la persona"
```

---

### Task 5: Per-person context seam (no behaviour change)

**Files:**
- Create: `src/finnegans_mcp/contexto.py`
- Modify: `src/finnegans_mcp/server.py` (`crear_servidor` and every tool body)
- Modify: `tests/mcp/conftest.py` (the `armar` fixture builds a `Contexto`)
- Test: `tests/mcp/test_contexto.py`

**Interfaces:**
- Produces, in `contexto.py`:
  - `@dataclass Contexto`:
    - fields: `settings: Settings`, `client: FinnegansClient`, `workspace: Workspace`, `docs: DocsMcp`, `permisos: Permisos | None = None` (filled in Task 6), `origen_tabla: dict[str, str] = field(default_factory=dict)`, `candado: threading.RLock = field(default_factory=threading.RLock)`;
    - `limpiar(texto: object) -> str`: the client's redactor first, then `Redactor(settings.secretos())`. This is exactly today's `limpiar` closure in `server.py`;
    - `cerrar() -> None`: closes the workspace.
  - `Contexto.desde_settings(settings: Settings, client=None, docs=None, workspace=None) -> Contexto`: builds the defaults the way `crear_servidor` does today, and calls `workspace.usar_redactor(ctx.limpiar)`.
  - `ProveedorContexto = Callable[[], Contexto]`
- `crear_servidor(settings: Settings, client=None, swagger=None, docs=None, workspace=None, *, contexto: Contexto | ProveedorContexto | None = None, modo: Literal["escritorio", "remoto"] = "escritorio", escanear_al_iniciar: bool = False) -> MCPServer`:
  - With no `contexto`, it builds one with `Contexto.desde_settings(settings, client, docs, workspace)`, so every existing call site and test keeps working.
  - With a `Contexto` instance, the provider returns it.
  - With a callable, that is the provider.
  - `swagger` stays process-wide.
  - `modo` is stored but unused until Phase 2. Only `"escritorio"` is accepted for now: `ValueError` otherwise.
  - `escanear_al_iniciar` is used in Task 6.
- **Rule:** every tool body starts with `ctx = proveedor()` and uses `ctx.client`, `ctx.workspace`, `ctx.docs`, `ctx.origen_tabla`, `ctx.candado` and `ctx.limpiar`. Nothing person-specific stays in a closure. `verificar_conexion` uses `ctx.settings`.

- [ ] **Step 1: Write the failing test**

```python
# tests/mcp/test_contexto.py
async def test_cada_contexto_ve_solo_sus_tablas(tmp_path):
    sa = ajustes(tmp_path)
    sb = ajustes(tmp_path, client_id="cid-b-falso", client_secret="sec-b-falso")
    a = Contexto.desde_settings(sa, client=ClienteFalso(sa, lambda *x: [{"x": 1}]), docs=DocsFalso())
    b = Contexto.desde_settings(sb, client=ClienteFalso(sb), docs=DocsFalso())
    actual = {"ctx": a}
    server = crear_servidor(a.settings, swagger=catalogo(a.settings, SPEC), contexto=lambda: actual["ctx"])
    await llamar(server, "leer", path="cliente/list", tabla="clientes_a")
    actual["ctx"] = b
    texto = await llamar(server, "consultar", sql="SHOW TABLES")
    assert "clientes_a" not in texto
    actual["ctx"] = a
    assert "clientes_a" in await llamar(server, "consultar", sql="SHOW TABLES")

async def test_secretos_de_cada_contexto_se_enmascaran_en_el_suyo(tmp_path): ...
    # handler of b raises error_con_secreto(b.settings); output under b has no b secrets

def test_modo_remoto_todavia_no_existe(tmp_path):
    with pytest.raises(ValueError):
        crear_servidor(ajustes(tmp_path), modo="remoto")
```

`llamar(server, nombre, **args)` is a small helper in this test file, mirroring `Entorno.llamar`.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/mcp/test_contexto.py -q`
Expected: FAIL (`ModuleNotFoundError: finnegans_mcp.contexto`).

- [ ] **Step 3: Implement.** Create `contexto.py` and move the per-person state in `server.py` behind the provider. In `tests/mcp/conftest.py`, `armar` keeps its signature and its `Entorno` fields, and passes `client`, `docs` and `workspace` as today.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS, including the 3 new tests.

- [ ] **Step 5: Commit**
```bash
git add src/finnegans_mcp tests/mcp
git commit -m "refactor(server): las herramientas leen el contexto de la persona actual"
```

---

### Task 6: Use the map in the tools, the background scan and rescans

**Files:**
- Modify: `src/finnegans_core/permisos.py` (add `Permisos`)
- Modify: `src/finnegans_mcp/server.py` (`buscar_endpoint`, `ver_endpoint`, `leer`, `escribir`, `verificar_conexion`, `main`)
- Modify: `src/finnegans_core/guia/escrituras.md` (only if Task 1 found authorship fields)
- Test: `tests/core/test_permisos.py`, `tests/mcp/test_permisos_tools.py`

**Interfaces:**
- Consumes: `MapaPermisos`, `AlmacenPermisos`, `AlmacenLocal`, `carpeta_datos`, `Escaner`, `objetivos` via `SwaggerCatalog.recursos()`, `REPORTES_EN_ESCANEO_AUTOMATICO`, `rechazo_en_mensaje`, `mensaje_sin_permiso`, `Contexto`.
- Produces, in `permisos.py`, `class Permisos`:
  - `__init__(almacen: AlmacenPermisos)`: loads the map. A map saved in state `escaneando` loads as `sin_escanear`.
  - `denegado(path) -> bool` and `solo_lectura(path) -> bool`: both False while `estado != "listo"`, except entries learned from `uso` and every `escritura_denegada`, which always count.
  - `registrar_lectura(path, ok: bool) -> None`: on `ok`, if the entry is `denegado`, correct it to `permitido`. On a refusal, set it to `denegado`. Saves only when something changed.
  - `registrar_escritura_denegada(path) -> None`
  - `escanear_en_segundo_plano(hacer: Callable[[], dict[str, tuple[Acceso, TipoRecurso]]]) -> bool`:
    - returns False if a scan is already running;
    - otherwise sets `estado="escaneando"`, runs `hacer` on a daemon `threading.Thread`, and returns True;
    - on success, `aplicar_escaneo` and save;
    - on any exception, `estado="fallo"`, the entries are kept, and it saves.
  - `estado_texto(hoy: date | None = None) -> str`: one of the four permission-state strings in Global Constraints.
  - `problema_almacen -> str | None`: forwarded from the store.
  - All methods are thread-safe, behind one `threading.Lock`.
- In `server.py`:
  - **Building `Permisos`:** when the `Contexto` has `permisos is None`, `crear_servidor` builds `Permisos(AlmacenLocal(carpeta_datos(), settings.client_id))`, or `Permisos(AlmacenMemoria())` when `settings.client_id` is empty. Tests inject `Permisos(AlmacenMemoria())` through the `armar` fixture.
  - **The scan job:** a new keyword on `crear_servidor`,
    `hacer_escaneo: Callable[[Contexto, bool], dict[str, tuple[Acceso, TipoRecurso]]] | None = None`.
    - The default is `lambda ctx, incluir_reportes: Escaner(ctx.client).escanear(swagger.recursos(), incluir_reportes)`.
    - Tests inject their own, since `ClienteFalso` has no `sondear`.
    - The server wraps it as `lambda: hacer_escaneo(ctx, incluir_reportes)` for `escanear_en_segundo_plano`.
    - `incluir_reportes` is `REPORTES_EN_ESCANEO_AUTOMATICO` for automatic scans, and the rule under `verificar_conexion` below for explicit ones.
  - **`buscar_endpoint`:**
    - drops rows where `ctx.permisos.denegado(fila.path)`;
    - appends ` · solo lectura para vos` to the `resumen` of rows where `solo_lectura`;
    - if rows existed and all were dropped, returns the exact "Lo que buscás existe…" copy;
    - the "Hay N resultados más" counter counts only rows that weren't dropped.
  - **`ver_endpoint`:** a `denegado` path returns `mensaje_sin_permiso("GET", path)`. A `solo_lectura` path gets a first line `({path}: solo lectura para vos)`.
  - **`leer`:**
    - success → `registrar_lectura(path, ok=True)`;
    - a `FinnegansError` where `rechazo_en_mensaje(str(e), escritura=False)` → `registrar_lectura(path, ok=False)`;
    - the message comes from Task 2's translation either way.
  - **`escribir`:** a `FinnegansError` where `rechazo_en_mensaje(str(e), escritura=True)` → `registrar_escritura_denegada(path)`.
  - **`verificar_conexion(reescanear: bool = False, incluir_reportes: bool = False)`:**
    - It always appends `ctx.permisos.estado_texto()`, plus `problema_almacen` when set.
    - With `reescanear=True`:
      - it starts a scan with `incluir_reportes or REPORTES_EN_ESCANEO_AUTOMATICO`;
      - it appends the "Estoy revisando…" line, or the "Ya estoy revisando…" line;
      - when `incluir_reportes=True` and `not REPORTES_EN_ESCANEO_AUTOMATICO`, it also appends: `Ojo: revisar los reportes los ejecuta en Finnegans (unos 140); conviene hacerlo fuera del horario de trabajo.`
    - The tool description gains: `Con reescanear=True revisa de nuevo qué reportes y entidades puede usar tu usuario.`
  - **Start-up:** `crear_servidor(..., escanear_al_iniciar=True)` starts a background scan when the map's `estado` is `sin_escanear` or `fallo`. `main()` passes `escanear_al_iniciar=True`.

- [ ] **Step 1: Write the failing tests** in `tests/mcp/test_permisos_tools.py`. Use `armar` with a `Permisos(AlmacenMemoria())` pre-loaded through `aplicar_escaneo`.
  - `test_buscar_oculta_lo_denegado`: `reports/ACOrdenesCompraPendientes` is `denegado`. A search for "ordenes de compra pendientes" doesn't list it.
  - `test_buscar_todo_oculto_lo_dice`: every hit is denied. The output equals the exact "Lo que buscás existe…" copy.
  - `test_buscar_marca_solo_lectura`: `cliente` has write denied. The row contains `solo lectura para vos`.
  - `test_ver_endpoint_denegado`: the output equals `mensaje_sin_permiso("GET", "reports/ACOrdenesCompraPendientes")`.
  - `test_leer_corrige_un_denegado_viejo`: `cliente` is `denegado`, and the handler returns `[{"Codigo": "1"}]`. After `leer("cliente/list")`, `permisos.denegado("cliente")` is False.
  - `test_leer_rechazado_marca_denegado`: the handler raises `FinnegansError("Error en GET reports/X (HTTP 403): Forbidden: Prestacion sin permiso")`. After that, `denegado("reports/X")` is True.
  - `test_escribir_rechazado_marca_solo_lectura`: a PUT to `cliente` raises a 403. After that, `solo_lectura("cliente")` is True.
  - `test_sin_escaneo_no_oculta_nada`: with a fresh `Permisos`, `buscar_endpoint` lists everything, and `verificar_conexion` contains `Permisos: todavía no se revisaron`.
  - `test_reescanear_arranca_y_no_duplica`: with a scan job that waits on a `threading.Event`, the first call contains "Estoy revisando tus permisos" and the second contains "Ya estoy revisando". Set the event, join, and check that `estado_texto()` starts with `Permisos revisados el`.
  - `test_falla_del_swagger_en_el_escaneo_conserva_el_mapa` (Review Focus 3):
    - the first scan succeeds and denies `cliente`;
    - the second scan job raises `SwaggerError`;
    - after that, `denegado("cliente")` is still True, the state text is `Permisos: la última revisión falló; se usa la anterior`, and `buscar_endpoint` still answers.
  - `test_estado_texto_con_numeros` (in `tests/core/test_permisos.py`): a map with 2 of 3 reports and 1 of 2 entities, plus `hoy=date(2026, 11, 17)` → `Permisos revisados el 17/11: 2 de 3 reportes y 1 de 2 entidades disponibles`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/mcp/test_permisos_tools.py tests/core/test_permisos.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** the Interfaces.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS. `test_registro_tiene_las_ocho_tools` still sees 8 tools.

- [ ] **Step 5: Commit**
```bash
git add src tests
git commit -m "feat(permisos): busqueda y herramientas segun los permisos de cada persona"
```

---

### Task 7: Personal keys in the form, pre-filled swagger key, version 1.1.0

**Files:**
- Modify: `manifest.json` (the `user_config` texts and `version`), `pyproject.toml` (`version`), `src/finnegans_mcp/__init__.py` (`__version__`), `README.md` (the packing section)
- Create: `scripts/empaquetar.py`
- Test: `tests/test_manifest.py`, `tests/test_empaquetar.py`

**Interfaces:**
- `scripts/empaquetar.py`:
  - **Usage:** `FINNEGANS_SWAGGER_KEY=... uv run python scripts/empaquetar.py [--salida finnegans.mcpb]`.
  - **`armar_carpeta(raiz: Path, destino: Path, swagger_key: str) -> Path`:**
    - copies the files `git ls-files` lists, minus `.mcpbignore` patterns, into `destino`;
    - rewrites `destino/manifest.json` with `user_config.swagger_key.default = swagger_key` and `user_config.swagger_key.required = False`;
    - returns `destino`.
  - **`main()`:**
    - refuses with `Falta FINNEGANS_SWAGGER_KEY en el entorno.` when the variable is empty;
    - calls `armar_carpeta` into a `tempfile.TemporaryDirectory`;
    - runs `npx @anthropic-ai/mcpb pack <tmp> <salida>`;
    - never prints the key.
- **Manifest texts** (Spanish, generic, with no person's name on personal keys):
  - `client_id` / `client_secret`: `Tu Client ID de la API de Finnegans (te lo da quien administra Finnegans).` and `Tu Client secret de la API de Finnegans (te lo da quien administra Finnegans).`
  - `docs_client_id` / `docs_secret_key`: `Tu Client ID de la documentación: en Finnegans GO, Modificar perfil → Datos personales, al final del formulario.` and `Tu Secret key de la documentación: en Finnegans GO, Modificar perfil → Datos personales, al final del formulario.`
  - `swagger_key`: title `Clave del swagger (avanzado)`, description `Clave de la empresa para el catálogo de endpoints. Si ya viene cargada, no la cambies.`
  - The committed manifest keeps `swagger_key.required: true` and **no** `default`.
- **The `verificar_conexion` tool description** in `manifest.json`'s `tools` list matches the new description from Task 6.

- [ ] **Step 1: Write the failing tests**
  - `tests/test_manifest.py`:
    - in `test_manifest_y_settings_coinciden`, the required set is unchanged;
    - new `test_textos_de_claves_personales_sin_nombres`: no `user_config` description contains `Juan`, and the two docs descriptions contain `Modificar perfil`;
    - new `test_manifest_versionado_no_trae_clave_del_swagger`: `"default" not in user_config["swagger_key"]`;
    - `test_version_igual_en_manifest_pyproject_y_servidor` also asserts `__version__ == "1.1.0"`.
  - `tests/test_empaquetar.py`:
    - `test_armar_carpeta_precarga_la_clave_solo_en_la_copia(tmp_path)`: the copy's manifest has `default == "swkey-falsa-7g8h9i"` and `required is False`, and the repo's `manifest.json` is byte-identical before and after;
    - `test_armar_carpeta_respeta_mcpbignore(tmp_path)`: `tests/`, `docs/` and `scripts/` are absent from the copy, and `src/finnegans_mcp/server.py` is present;
    - `test_main_sin_clave_se_niega(monkeypatch, capsys)`: `FINNEGANS_SWAGGER_KEY` unset → exit code ≠ 0 and the refusal text is printed.

    Load the script with `importlib.util.spec_from_file_location`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_manifest.py tests/test_empaquetar.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement** the manifest edits, the version bump, the script, and a README packing section that replaces the bare `npx @anthropic-ai/mcpb pack` line with the script's usage. Note in the README that the key comes from the environment, never from a file.

- [ ] **Step 4: Run the whole suite**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add manifest.json pyproject.toml src/finnegans_mcp/__init__.py README.md scripts/empaquetar.py tests
git commit -m "feat(extension): claves personales en el formulario y clave del swagger precargada (v1.1.0)"
```

---

### Task 8: Pack, install and check (with Juan)

**Files:** none changed, unless a bug turns up. A fix then goes through its own test first.

- [ ] **Step 1:** Run `uv run pytest -q`. Expected: all pass, with 413 plus the new tests.

- [ ] **Step 2: Juan packs it.** Juan runs `FINNEGANS_SWAGGER_KEY=<company key> uv run python scripts/empaquetar.py`. Expected: `finnegans.mcpb` is created, and the console never shows the key.

- [ ] **Step 3: Juan installs the `.mcpb` on his PC** and enters his four personal keys. In Claude Desktop, he runs:
  - `verificar_conexion`: all OK, then `Permisos: todavía revisando`, then about 2 minutes later `Permisos revisados el …`;
  - a search for something his account has.

- [ ] **Step 4: Juan installs on a second PC with the restricted account** used on 2026-11-17. This also covers the pending "pasar a tester" step. Then:
  - search for a report that account was denied: it's hidden, or the "Lo que buscás existe…" line shows;
  - `leer` on a denied entity gives the new refusal copy, not "credenciales".

- [ ] **Step 5: Juan uploads the `.mcpb`** to the Claude organization. The team gets 1.1.0.

- [ ] **Step 6: Push and PR.** Push the branch and open a PR to `master`. This needs Juan's ok, and PR #14 should be merged first or be part of this PR. The PR body lists the spike's decisions from `docs/superpowers/notas/2026-11-sondeo-permisos.md`.
