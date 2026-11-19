"""Escaneo suave de permisos: sondea cada reporte y entidad con el token de la persona.

Un reporte sin permiso contesta 403 "Prestacion sin permiso"; una entidad sin
permiso contesta 500 "No tiene permisos ...". Para no tocar datos, las entidades
se piden con un codigo que no existe. Solo libreria estandar.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from .client import FinnegansAuthError
from .permisos import Acceso, TipoRecurso, clave_permiso, es_rechazo_permiso

# Salen de la nota docs/superpowers/notas/2026-11-sondeo-permisos.md; se
# actualizan cuando Juan corra el sondeo en vivo. Mientras tanto, conservador:
# los reportes no entran al escaneo automatico.
SONDA_REPORTE: dict[str, str] = {}
REPORTES_EN_ESCANEO_AUTOMATICO = False

ID_INEXISTENTE = "ZZ-NOEXISTE"


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


class Sonda(Protocol):
    def sondear(self, path: str, id: str | None = None, params: dict | None = None,
                timeout: float = 10.0) -> tuple[int | None, str]: ...


class Escaner:
    def __init__(self, sonda: Sonda, max_en_vuelo: int = 4, timeout: float = 10.0) -> None:
        self.sonda = sonda
        self.max_en_vuelo = max_en_vuelo
        self.timeout = timeout

    def _sondear(self, path: str, tipo: TipoRecurso) -> tuple[Acceso, TipoRecurso]:
        """Un fallo de autenticacion corta el escaneo; cualquier otro deja el objetivo desconocido."""
        try:
            return self._clasificar(path, tipo)
        except FinnegansAuthError:
            raise
        except Exception:
            return "desconocido", tipo

    def _clasificar(self, path: str, tipo: TipoRecurso) -> tuple[Acceso, TipoRecurso]:
        if tipo == "reporte":
            status, cuerpo = self.sonda.sondear(path, params=SONDA_REPORTE, timeout=self.timeout)
            return clasificar_reporte(status, cuerpo), tipo
        status, cuerpo = self.sonda.sondear(path, id=ID_INEXISTENTE, timeout=self.timeout)
        return clasificar_entidad(status, cuerpo), tipo

    def escanear(
        self, objetivos: list[tuple[str, TipoRecurso]], incluir_reportes: bool
    ) -> dict[str, tuple[Acceso, TipoRecurso]]:
        """Claves ya normalizadas con `clave_permiso`, listas para `aplicar_escaneo`.

        Propaga FinnegansAuthError: el escaneo entero falla y el llamador conserva el mapa anterior.
        """
        elegidos = [(p, t) for p, t in objetivos if incluir_reportes or t != "reporte"]
        with ThreadPoolExecutor(max_workers=self.max_en_vuelo) as pool:
            resultados = list(pool.map(lambda o: self._sondear(*o), elegidos))
        salida: dict[str, tuple[Acceso, TipoRecurso]] = {}
        for (path, _), res in zip(elegidos, resultados):
            clave = clave_permiso(path)
            if clave:
                salida[clave] = res
        return salida
