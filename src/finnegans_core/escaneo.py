"""Escaneo suave de permisos: sondea cada reporte y entidad con el token de la persona.

Un reporte sin permiso contesta 403 "Prestacion sin permiso"; una entidad sin
permiso contesta 500 "No tiene permisos ...". Para no tocar datos, las entidades
se piden con un codigo que no existe. Solo libreria estandar.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Mapping, Protocol

from .client import FinnegansAuthError
from .permisos import Acceso, TipoRecurso, clave_permiso, es_rechazo_permiso

if TYPE_CHECKING:
    from .catalogo.swagger import SwaggerCatalog

# Medido en vivo el 2026-11-19 (docs/superpowers/notas/2026-11-sondeo-permisos.md):
# - un reporte con un parametro requerido, llamado sin parametros, contesta
#   400 "is mandatory" al instante, sin ejecutarse;
# - uno sin requeridos pero con rango de fechas, con "desde" posterior a "hasta",
#   contesta [] en menos de un segundo y medio.
# Una cuenta sin permiso recibe 403 antes de cualquiera de las dos validaciones.
# Los que no tienen ni requeridos ni rango solo se pueden revisar ejecutandolos:
# esos no entran al escaneo automatico (hay que pedirlos y confirmar).
REPORTES_EN_ESCANEO_AUTOMATICO = False
DESDE_POSTERIOR = "2099-01-02"
HASTA_ANTERIOR = "2099-01-01"

ID_INEXISTENTE = "ZZ-NOEXISTE"

# Si mas de esta fraccion de las entidades no contesto, el escaneo no sirve:
# se descarta entero y queda el mapa anterior.
MAX_SIN_RESPUESTA = 0.25


class EscaneoIncompleto(Exception):
    """Finnegans no contesto a demasiadas sondas de entidades."""

    def __init__(self) -> None:
        super().__init__(
            "El escaneo no pudo completarse: Finnegans no respondió a muchas consultas."
        )


def clasificar_reporte(status: int | None, cuerpo: str) -> Acceso:
    """Solo un 403 con el texto de Finnegans es denegado; un timeout es que esta corriendo."""
    if status == 403 and es_rechazo_permiso(status, cuerpo):
        return "denegado"
    return "permitido"


def clasificar_entidad(status: int | None, cuerpo: str) -> Acceso:
    if es_rechazo_permiso(status, cuerpo):
        return "denegado"
    if status == 404:
        return "permitido"
    return "desconocido"


def sonda_de_reporte(parametros: list[dict]) -> dict[str, str] | None:
    """Parametros para revisar un reporte sin ejecutarlo, o None si no se puede.

    Con algun requerido: ninguno (Finnegans contesta 400 sin correr nada). Sin
    requeridos pero con fechas "desde" y "hasta": el rango invertido.
    """
    if any(p.get("requerido") for p in parametros):
        return {}
    fechas = [str(p.get("nombre", "")) for p in parametros
              if "fecha" in str(p.get("nombre", "")).lower()]
    desde = [n for n in fechas if "desde" in n.lower()]
    hasta = [n for n in fechas if "hasta" in n.lower()]
    if not desde or not hasta:
        return None
    return {**{n: DESDE_POSTERIOR for n in desde}, **{n: HASTA_ANTERIOR for n in hasta}}


def planificar_reportes(catalogo: "SwaggerCatalog") -> dict[str, dict[str, str] | None]:
    """Sonda de cada reporte del swagger, por clave de permiso. No llama a la API."""
    plan: dict[str, dict[str, str] | None] = {}
    for path, tipo in catalogo.recursos():
        if tipo != "reporte":
            continue
        clave = clave_permiso(path)
        if not clave:
            continue
        try:
            ops = [o for o in catalogo.ver(path) if o.metodo == "GET"]
        except Exception:  # noqa: BLE001 - un reporte raro queda para revisar al usarlo
            ops = []
        plan[clave] = sonda_de_reporte(ops[0].parametros) if ops else None
    return plan


class Sonda(Protocol):
    def sondear(self, path: str, id: str | None = None, params: dict | None = None,
                timeout: float = 10.0) -> tuple[int | None, str]: ...


class Escaner:
    def __init__(self, sonda: Sonda, max_en_vuelo: int = 4, timeout: float = 10.0,
                 sondas: Mapping[str, dict[str, str] | None] | None = None) -> None:
        self.sonda = sonda
        self.max_en_vuelo = max_en_vuelo
        self.timeout = timeout
        # Por clave de permiso: parametros para revisar el reporte sin
        # ejecutarlo, o None si no se puede (ver planificar_reportes).
        self.sondas = dict(sondas or {})

    def _sonda_de(self, path: str) -> dict[str, str] | None:
        return self.sondas.get(clave_permiso(path) or "")

    def _sondear(self, path: str, tipo: TipoRecurso) -> tuple[Acceso, bool]:
        """(acceso, contesto). Un fallo de autenticacion corta el escaneo;
        cualquier otro deja el objetivo desconocido."""
        try:
            return self._clasificar(path, tipo)
        except FinnegansAuthError:
            raise
        except Exception:
            return "desconocido", True

    def _clasificar(self, path: str, tipo: TipoRecurso) -> tuple[Acceso, bool]:
        if tipo == "reporte":
            params = self._sonda_de(path) or {}
            status, cuerpo = self.sonda.sondear(path, params=params, timeout=self.timeout)
            return clasificar_reporte(status, cuerpo), status is not None
        status, cuerpo = self.sonda.sondear(path, id=ID_INEXISTENTE, timeout=self.timeout)
        return clasificar_entidad(status, cuerpo), status is not None

    def escanear(
        self, objetivos: list[tuple[str, TipoRecurso]], incluir_reportes: bool
    ) -> dict[str, tuple[Acceso, TipoRecurso]]:
        """Claves ya normalizadas con `clave_permiso`, listas para `aplicar_escaneo`.

        Los reportes que se pueden revisar sin ejecutarlos (con sonda) entran
        siempre; los demas solo con `incluir_reportes`, y sin parametros.

        Propaga FinnegansAuthError y lanza EscaneoIncompleto si mas de un cuarto
        de las entidades no contesto (se corto la red): el escaneo entero falla
        y el llamador conserva el mapa anterior. Los reportes no cuentan: uno
        que no contesta esta corriendo.
        """
        elegidos = [
            (p, t) for p, t in objetivos
            if t != "reporte" or incluir_reportes or self._sonda_de(p) is not None
        ]
        with ThreadPoolExecutor(max_workers=self.max_en_vuelo) as pool:
            resultados = list(pool.map(lambda o: self._sondear(*o), elegidos))
        entidades = [contesto for (_, t), (_, contesto) in zip(elegidos, resultados)
                     if t == "entidad"]
        sin_respuesta = entidades.count(False)
        if entidades and sin_respuesta > MAX_SIN_RESPUESTA * len(entidades):
            raise EscaneoIncompleto()
        salida: dict[str, tuple[Acceso, TipoRecurso]] = {}
        for (path, tipo), (acceso, _) in zip(elegidos, resultados):
            clave = clave_permiso(path)
            if clave:
                salida[clave] = (acceso, tipo)
        return salida
