"""Almacen local del mapa de permisos de cada persona. Solo libreria estandar.

El archivo se nombra con el hash del client_id: nunca contiene ni nombra una clave.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Protocol

from .permisos import MapaPermisos

PROBLEMA_GUARDADO = "No pude guardar tus permisos en esta PC; se van a revisar de nuevo la próxima vez."


class AlmacenPermisos(Protocol):
    problema: str | None

    def cargar(self) -> MapaPermisos: ...

    def guardar(self, mapa: MapaPermisos) -> None: ...


class AlmacenMemoria:
    """Guarda el mapa en memoria: para tests y como respaldo."""

    def __init__(self) -> None:
        self._mapa = MapaPermisos()
        self.problema: str | None = None

    def cargar(self) -> MapaPermisos:
        return self._mapa

    def guardar(self, mapa: MapaPermisos) -> None:
        self._mapa = mapa


class AlmacenLocal:
    def __init__(self, carpeta: Path, client_id: str) -> None:
        huella = hashlib.sha256(client_id.strip().encode("utf-8")).hexdigest()[:16]
        self.archivo = Path(carpeta) / f"permisos-{huella}.json"
        self.problema: str | None = None
        self._mapa: MapaPermisos | None = None

    def cargar(self) -> MapaPermisos:
        if self._mapa is not None:
            # Un guardado fallo: lo ultimo conocido manda sobre el archivo viejo.
            return self._mapa
        try:
            datos = json.loads(self.archivo.read_text(encoding="utf-8"))
            return MapaPermisos.desde_dict(datos)
        except Exception:  # noqa: BLE001 - un archivo roto (p. ej. version 1e999) no frena el arranque
            return MapaPermisos()

    def guardar(self, mapa: MapaPermisos) -> None:
        tmp = self.archivo.with_name(self.archivo.name + ".tmp")
        try:
            self.archivo.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(mapa.a_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.archivo)
            self.problema = None
            self._mapa = None
        except OSError:
            self._mapa = mapa  # no se pudo escribir: queda en memoria
            self.problema = PROBLEMA_GUARDADO
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass


def carpeta_datos() -> Path:
    """Carpeta de datos de la app en esta PC (Windows, macOS u otros)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Finnegans"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Finnegans"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "finnegans"
