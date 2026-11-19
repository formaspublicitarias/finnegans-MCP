"""Sondeo EN VIVO (solo lectura) de permisos de reportes y campos de autoria.

Solo hace GET contra Finnegans; no escribe nada. Sirve para decidir dos cosas:

  1. Que parametros baratos ("sonda") se le pueden mandar a un reporte pesado para
     saber si la cuenta tiene permiso sin esperar el reporte completo (un 403
     "Prestacion sin permiso" llega rapido; un reporte real puede tardar minutos).
  2. Si los registros de Finnegans traen el usuario que los creo o modifico.

Por cada reporte prueba cuatro candidatos y mide cuanto tarda cada uno:
  (a) sin parametros;
  (b) cada parametro de fecha requerido en "no-es-fecha";
  (c) desde posterior a hasta (2099-01-02 / 2099-01-01);
  (d) un rango de 1 dia sobre ayer.
Imprime reporte, candidato, estado HTTP, segundos y los primeros 120 caracteres de
la respuesta ya redactada. Nunca imprime claves, tokens ni URLs con parametros.
Ojo: ante un 401/403 el cliente renueva el token y reintenta una vez, salvo que
la respuesta diga que falta permiso ("Prestacion sin permiso" o "No tiene
permisos"): ese 403 vuelve sin reintento, asi que su tiempo es el de una sola
llamada. Un 401/403 por otra causa si incluye el reintento.

Para autoria lee cliente/list y un cliente: imprime solo los NOMBRES de los campos
que parecen de usuario/modificacion (nunca sus valores) y los paths del swagger que
parecen de auditoria o historial.

Ademas hace un censo de los reportes del swagger (sin llamar a la API): cuantos
tienen algun parametro requerido (sondearlos sin parametros es barato: Finnegans
contesta 400 "is mandatory" sin ejecutar nada), cuantos no tienen requeridos pero
si un rango de fechas, y cuantos no tienen ninguna de las dos cosas. En los
primeros N sin requeridos con rango prueba solo (c) y (d): nunca los llama sin
parametros, porque eso podria ejecutar el reporte entero.

Uso (las claves van por variables de entorno, nunca desde un archivo .env):

    python scripts/sondeo_permisos.py
    python scripts/sondeo_permisos.py --reportes DETALLETRANSACCIONES --sin-requeridos 4

Sale con codigo distinto de cero si faltan variables de entorno.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Mapping

import httpx2

from finnegans_core.catalogo.swagger import SwaggerCatalog
from finnegans_core.client import FinnegansClient, FinnegansError
from finnegans_core.config import Settings

TIMEOUT_SEGUNDOS = 60
LARGO_CUERPO = 120
FECHA_INVALIDA = "no-es-fecha"
DESDE_POSTERIOR = "2099-01-02"
HASTA_ANTERIOR = "2099-01-01"

_CAMPO_AUTORIA = re.compile(r"usuario|modific|alta|creaci|autor", re.IGNORECASE)
_PATH_AUDITORIA = re.compile(r"auditor|log|historial", re.IGNORECASE)
_RE_ESTADO = re.compile(r"\(HTTP (\d{3})\)")


# ------------------------------------------------------------ helpers puros


def parametros_de_fecha(parametros: list[dict]) -> list[dict]:
    """Los parametros cuyo nombre contiene 'fecha' (sin importar mayusculas)."""
    return [p for p in parametros if "fecha" in str(p.get("nombre", "")).lower()]


def candidatos(parametros: list[dict], hoy: date | None = None) -> dict[str, dict[str, str]]:
    """Juegos de parametros candidatos, por etiqueta, para un reporte.

    (a) sin parametros; (b) fechas requeridas en un texto que no es fecha; (c) desde
    posterior a hasta; (d) un dia, ayer. (c) y (d) usan los nombres tal como los
    escribe el swagger; si el reporte no tiene parametros de fecha quedan vacios.
    """
    hoy = hoy or date.today()
    ayer = (hoy - timedelta(days=1)).isoformat()
    fechas = parametros_de_fecha(parametros)
    nombres = [p["nombre"] for p in fechas]
    requeridas = [p["nombre"] for p in fechas if p.get("requerido")]
    desde = [n for n in nombres if "desde" in n.lower()]
    hasta = [n for n in nombres if "hasta" in n.lower()]
    invertido = {**{n: DESDE_POSTERIOR for n in desde}, **{n: HASTA_ANTERIOR for n in hasta}}
    un_dia = {n: ayer for n in desde + hasta}
    return {
        "a) sin parametros": {},
        "b) fechas requeridas invalidas": {n: FECHA_INVALIDA for n in requeridas},
        "c) desde posterior a hasta": invertido,
        "d) rango de 1 dia (ayer)": un_dia,
    }


def tiene_rango(parametros: list[dict]) -> bool:
    """True si el reporte tiene un parametro de fecha 'desde' y otro 'hasta'."""
    nombres = [str(p.get("nombre", "")).lower() for p in parametros_de_fecha(parametros)]
    return any("desde" in n for n in nombres) and any("hasta" in n for n in nombres)


@dataclass
class Censo:
    """Nombres de reportes del swagger, separados por como se pueden sondear."""

    con_requeridos: list[str] = field(default_factory=list)
    sin_requeridos_con_rango: list[str] = field(default_factory=list)
    sin_requeridos_sin_rango: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (len(self.con_requeridos) + len(self.sin_requeridos_con_rango)
                + len(self.sin_requeridos_sin_rango))


def censar_reportes(reportes: list[tuple[str, list[dict]]]) -> Censo:
    """Clasifica (path, parametros) de cada reporte.

    Con un parametro requerido, llamarlo sin parametros es barato: Finnegans
    contesta 400 "is mandatory" sin ejecutar nada (o 403 si no hay permiso).
    Sin requeridos, una llamada sin parametros puede ejecutar el reporte entero.
    """
    censo = Censo()
    for path, parametros in reportes:
        nombre = path.strip("/").split("/", 1)[-1]
        if any(p.get("requerido") for p in parametros):
            censo.con_requeridos.append(nombre)
        elif tiene_rango(parametros):
            censo.sin_requeridos_con_rango.append(nombre)
        else:
            censo.sin_requeridos_sin_rango.append(nombre)
    for lista in (censo.con_requeridos, censo.sin_requeridos_con_rango,
                  censo.sin_requeridos_sin_rango):
        lista.sort(key=str.casefold)
    return censo


def candidatos_baratos(parametros: list[dict], hoy: date | None = None) -> dict[str, dict[str, str]]:
    """Solo los candidatos (c) y (d): nunca se llama al reporte sin parametros."""
    todos = candidatos(parametros, hoy)
    return {k: todos[k] for k in ("c) desde posterior a hasta", "d) rango de 1 dia (ayer)")}


def elegir_para_probar(censo: Censo, n: int) -> list[str]:
    """Los primeros n reportes sin requeridos que tienen rango de fechas."""
    return sorted(censo.sin_requeridos_con_rango, key=str.casefold)[:max(n, 0)]


def campos_de_autoria(registro: Any) -> list[str]:
    """Nombres (nunca valores) de los campos de primer nivel que parecen de autoria."""
    if isinstance(registro, list) and len(registro) == 1:
        registro = registro[0]
    if not isinstance(registro, dict):
        return []
    return sorted(str(k) for k in registro if _CAMPO_AUTORIA.search(str(k)))


def paths_de_auditoria(spec: Mapping[str, Any]) -> list[str]:
    """Paths del swagger cuyo nombre o resumen parece de auditoria o historial."""
    encontrados = []
    for path, ops in (spec.get("paths") or {}).items():
        textos = [str(path)]
        if isinstance(ops, dict):
            textos += [str(d.get("summary", "")) for d in ops.values() if isinstance(d, dict)]
        if any(_PATH_AUDITORIA.search(t) for t in textos):
            encontrados.append(str(path))
    return sorted(encontrados)


def primer_codigo(lista: Any) -> str | None:
    """Codigo del primer registro de un listado (lista o dict con una lista)."""
    if isinstance(lista, dict):
        lista = next((v for v in lista.values() if isinstance(v, list)), [])
    if not isinstance(lista, list):
        return None
    for fila in lista:
        if isinstance(fila, dict):
            for k, v in fila.items():
                if str(k).lower() == "codigo" and v not in (None, ""):
                    return str(v)
    return None


def recortar(texto: object, redactor: Any, largo: int = LARGO_CUERPO) -> str:
    """Redacta el texto entero y recien despues lo corta, en una sola linea."""
    limpio = redactor.limpiar("" if texto is None else str(texto))
    return " ".join(limpio.split())[:largo]


# ----------------------------------------------------------------- en vivo


def _sondear(client: FinnegansClient, path: str, params: dict[str, str]) -> tuple[str, float, str]:
    """(estado, segundos, cuerpo redactado) de un GET. Nunca levanta por HTTP."""
    t0 = time.monotonic()
    try:
        cuerpo = client.request("GET", path, params=params or None)
        estado, texto = "200", str(cuerpo)
    except FinnegansError as e:
        m = _RE_ESTADO.search(str(e))
        estado, texto = (m.group(1) if m else "error"), str(e)
    return estado, time.monotonic() - t0, recortar(texto, client.redactor)


def sondear_reporte(client: FinnegansClient, catalogo: SwaggerCatalog, nombre: str,
                    salida: Callable[[str], None]) -> None:
    path = f"reports/{nombre}"
    ops = [o for o in catalogo.ver(path) if o.metodo == "GET"]
    if not ops:
        salida(f"{nombre}: no hay GET en el swagger para {path}; lo salteo.")
        return
    params = ops[0].parametros
    fechas = [p["nombre"] + ("*" if p["requerido"] else "") for p in parametros_de_fecha(params)]
    requeridos = [p["nombre"] for p in params if p.get("requerido")]
    salida(f"\n--- {nombre} (parametros de fecha: {fechas or 'ninguno'}; "
           f"requeridos segun el swagger: {requeridos or 'ninguno'}) ---")
    for etiqueta, juego in candidatos(params).items():
        estado, seg, cuerpo = _sondear(client, path, juego)
        salida(f"{nombre} | {etiqueta} | HTTP {estado} | {seg:.1f} s | {cuerpo}")


def _parametros_get(catalogo: SwaggerCatalog, path: str) -> list[dict] | None:
    ops = [o for o in catalogo.ver(path) if o.metodo == "GET"]
    return ops[0].parametros if ops else None


def censar(catalogo: SwaggerCatalog, salida: Callable[[str], None]) -> Censo:
    """Cuenta los reportes del swagger por como se pueden sondear. No llama a la API."""
    reportes = []
    for path, tipo in catalogo.recursos():
        if tipo != "reporte":
            continue
        parametros = _parametros_get(catalogo, path)
        if parametros is not None:
            reportes.append((path, parametros))
    censo = censar_reportes(reportes)
    salida(f"\n--- Censo de reportes del swagger ({censo.total}) ---")
    salida(f"Con algun parametro requerido (sondeo sin parametros, barato): "
           f"{len(censo.con_requeridos)}")
    salida(f"Sin requeridos, con rango de fechas (se prueba el truco de fechas): "
           f"{len(censo.sin_requeridos_con_rango)}")
    salida(f"Sin requeridos ni rango de fechas (se aprenden al usarlos): "
           f"{len(censo.sin_requeridos_sin_rango)}")
    salida("Sin requeridos ni rango: " + (", ".join(censo.sin_requeridos_sin_rango) or "ninguno"))
    return censo


def sondear_sin_requeridos(client: FinnegansClient, catalogo: SwaggerCatalog,
                           nombres: list[str], salida: Callable[[str], None]) -> None:
    """Prueba solo (c) y (d) en reportes sin requeridos: nunca los llama sin parametros."""
    for nombre in nombres:
        path = f"reports/{nombre}"
        parametros = _parametros_get(catalogo, path) or []
        salida(f"\n--- {nombre} (sin requeridos; solo candidatos con fechas) ---")
        for etiqueta, juego in candidatos_baratos(parametros).items():
            estado, seg, cuerpo = _sondear(client, path, juego)
            salida(f"{nombre} | {etiqueta} | HTTP {estado} | {seg:.1f} s | {cuerpo}")


def sondear_autoria(client: FinnegansClient, catalogo: SwaggerCatalog,
                    salida: Callable[[str], None]) -> None:
    salida("\n--- Autoria: campos de cliente (solo nombres) ---")
    codigo = primer_codigo(client.request("GET", "cliente/list"))
    if codigo is None:
        salida("cliente/list no devolvio ningun codigo: no pude leer un cliente.")
    else:
        campos = campos_de_autoria(client.request("GET", "cliente", id=codigo))
        salida(f"Campos que parecen de usuario o modificacion: {campos or 'ninguno'}")
    salida("\n--- Autoria: paths del swagger que parecen de auditoria o historial ---")
    for path in paths_de_auditoria(catalogo.spec()) or ["(ninguno)"]:
        salida(path)


# -------------------------------------------------------------------- main


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Sondeo de solo lectura de permisos de reportes y campos de autoria.")
    p.add_argument("--reportes", default="", metavar="A,B,C",
                   help="opcional: reportes puntuales para probar los cuatro candidatos, "
                        "por ejemplo DETALLETRANSACCIONES,OTRO")
    p.add_argument("--sin-requeridos", type=int, default=4, metavar="N",
                   help="cuantos reportes sin parametros requeridos (y con rango de "
                        "fechas) probar con el truco de fechas (por defecto 4; 0 = ninguno)")
    p.add_argument("--sin-autoria", action="store_true",
                   help="no repetir la parte de autoria")
    return p


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None, *,
         salida: Callable[[str], None] = print) -> int:
    args = _parser().parse_args(argv)
    reportes = [r.strip() for r in args.reportes.split(",") if r.strip()]
    settings = Settings.from_env() if env is None else Settings.from_env(env)
    sin_cargar = settings.faltantes()
    if sin_cargar:
        print(
            "Faltan variables de entorno de la configuración: " + ", ".join(sin_cargar)
            + ". Cargalas en la terminal (FINNEGANS_CLIENT_ID, FINNEGANS_CLIENT_SECRET, "
            "FINNEGANS_SWAGGER_KEY, FINNEGANS_DOCS_CLIENT_ID, FINNEGANS_DOCS_SECRET_KEY). "
            "No se hizo nada.",
            file=sys.stderr,
        )
        return 2
    client = FinnegansClient(settings, http=httpx2.Client(timeout=TIMEOUT_SEGUNDOS))
    catalogo = SwaggerCatalog(settings)
    salida("SONDEO DE SOLO LECTURA (solo GET). No se escribe nada en Finnegans.")
    try:
        for nombre in reportes:
            sondear_reporte(client, catalogo, nombre, salida)
        censo = censar(catalogo, salida)
        sondear_sin_requeridos(
            client, catalogo, elegir_para_probar(censo, args.sin_requeridos), salida)
        if not args.sin_autoria:
            sondear_autoria(client, catalogo, salida)
    except Exception as e:  # noqa: BLE001
        print(f"\nSONDEO FALLIDO ({type(e).__name__}): {client.redactor.limpiar(str(e))[:300]}",
              file=sys.stderr)
        return 1
    salida("\nListo. Pegá esta salida (sin valores) en docs/superpowers/notas/"
           "2026-11-sondeo-permisos.md.")
    return 0


if __name__ == "__main__":
    # La consola de Windows no siempre es UTF-8: que los acentos no salgan rotos.
    for _flujo in (sys.stdout, sys.stderr):
        if hasattr(_flujo, "reconfigure"):
            _flujo.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
