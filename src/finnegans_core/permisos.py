"""Permisos de Finnegans: deteccion de rechazos y mensaje para el usuario.

Finnegans no publica los permisos de cada cuenta: se los reconoce por la
respuesta. Un reporte sin permiso contesta 403 "Prestacion sin permiso" y una
entidad sin permiso contesta 500 "No tiene permisos ...". Solo libreria estandar.
"""
from __future__ import annotations

import re

from .vocabulario import sin_acentos

ACCIONES: dict[str, str] = {
    "GET": "ver",
    "POST": "crear",
    "PUT": "modificar",
    "PATCH": "modificar",
    "DELETE": "borrar",
}


def _normalizado(texto: str | None) -> str:
    return sin_acentos(texto or "").casefold()


def es_rechazo_permiso(status: int | None, cuerpo: str) -> bool:
    """La respuesta dice, con las palabras de Finnegans, que falta permiso."""
    t = _normalizado(cuerpo)
    return "prestacion sin permiso" in t or "no tiene permisos" in t


def es_rechazo_escritura(status: int | None, cuerpo: str) -> bool:
    """En una escritura, un 403 es siempre falta de permiso (las claves ya sirvieron)."""
    if es_rechazo_permiso(status, cuerpo):
        return True
    if status == 403:
        return True
    return status == 500 and "permiso" in _normalizado(cuerpo)


def rechazo_en_mensaje(mensaje: str, escritura: bool) -> bool:
    """Aplica la deteccion al texto de una FinnegansError ('... (HTTP nnn): cuerpo')."""
    msg = mensaje or ""
    m = re.search(r"HTTP (\d{3})", msg)
    status = int(m.group(1)) if m else None
    c = msg.find("):")
    cuerpo = msg[c + 2:] if c >= 0 else msg
    if escritura:
        return es_rechazo_escritura(status, cuerpo)
    return es_rechazo_permiso(status, cuerpo)


def mensaje_sin_permiso(metodo: str, recurso: str) -> str:
    accion = ACCIONES.get((metodo or "GET").upper(), "ver")
    return (
        f"Tu usuario de Finnegans no tiene permiso para {accion} en '{recurso}'. "
        "Si lo necesitás, pedíselo a quien administra Finnegans."
    )
