"""Permisos de Finnegans: deteccion de rechazos y mensaje para el usuario.

Finnegans no publica los permisos de cada cuenta: se los reconoce por la
respuesta. Un reporte sin permiso contesta 403 "Prestacion sin permiso" y una
entidad sin permiso contesta 500 "No tiene permisos ...". Solo libreria estandar.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Callable, Literal

from .vocabulario import sin_acentos

if TYPE_CHECKING:
    from .almacen_permisos import AlmacenPermisos

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


Acceso = Literal["permitido", "denegado", "desconocido"]
Fuente = Literal["escaneo", "uso"]
TipoRecurso = Literal["reporte", "entidad"]
EstadoEscaneo = Literal["sin_escanear", "escaneando", "listo", "fallo"]

_ACCESOS = ("permitido", "denegado", "desconocido")
_FUENTES = ("escaneo", "uso")
_TIPOS = ("reporte", "entidad")
_ESTADOS = ("sin_escanear", "escaneando", "listo", "fallo")


def clave_permiso(path: str) -> str | None:
    """Clave del mapa para un path: 'reports/<nombre>' o la entidad, en minusculas."""
    partes = [p for p in (path or "").split("/") if p]
    if partes and partes[0].casefold() == "api":
        partes = partes[1:]
    if not partes:
        return None
    if partes[0].casefold() == "reports":
        if len(partes) < 2:
            return "reports"
        return f"reports/{partes[1]}".casefold()
    return partes[0].casefold()


@dataclass
class Entrada:
    acceso: Acceso
    fuente: Fuente
    tipo: TipoRecurso | None
    cuando: str  # fecha ISO


@dataclass
class MapaPermisos:
    entradas: dict[str, Entrada] = field(default_factory=dict)
    escritura_denegada: set[str] = field(default_factory=set)
    estado: EstadoEscaneo = "sin_escanear"
    escaneo_fin: str | None = None
    version: int = 0

    def acceso(self, path: str) -> Acceso | None:
        clave = clave_permiso(path)
        entrada = self.entradas.get(clave) if clave else None
        return entrada.acceso if entrada else None

    def denegado(self, path: str) -> bool:
        return self.acceso(path) == "denegado"

    def solo_lectura(self, path: str) -> bool:
        clave = clave_permiso(path)
        return clave is not None and clave in self.escritura_denegada

    def aplicar_escaneo(self, resultado: dict[str, tuple[Acceso, TipoRecurso]], cuando: str) -> None:
        """Reemplaza solo las claves del resultado; conserva el resto y escritura_denegada."""
        for clave, (acceso, tipo) in resultado.items():
            self.entradas[clave] = Entrada(acceso, "escaneo", tipo, cuando)
        self.estado = "listo"
        self.escaneo_fin = cuando
        self.version += 1

    def corregir(self, path: str, acceso: Acceso) -> bool:
        """Registra lo aprendido por uso. No cambia `version`."""
        clave = clave_permiso(path)
        if clave is None:
            return False
        actual = self.entradas.get(clave)
        if actual is not None and actual.acceso == acceso:
            return False
        tipo = actual.tipo if actual else ("reporte" if clave.startswith("reports/") else "entidad")
        self.entradas[clave] = Entrada(acceso, "uso", tipo, date.today().isoformat())
        return True

    def marcar_escritura_denegada(self, path: str) -> bool:
        clave = clave_permiso(path)
        if clave is None or clave in self.escritura_denegada:
            return False
        self.escritura_denegada.add(clave)
        return True

    def resumen(self) -> tuple[int, int, int, int]:
        """(reportes permitidos, reportes, entidades permitidas, entidades); desconocido cuenta como permitido."""
        reportes = [e for e in self.entradas.values() if e.tipo == "reporte"]
        entidades = [e for e in self.entradas.values() if e.tipo == "entidad"]

        def permitidos(es: list[Entrada]) -> int:
            return sum(1 for e in es if e.acceso != "denegado")

        return permitidos(reportes), len(reportes), permitidos(entidades), len(entidades)

    def a_dict(self) -> dict:
        return {
            "entradas": {
                k: {"acceso": e.acceso, "fuente": e.fuente, "tipo": e.tipo, "cuando": e.cuando}
                for k, e in sorted(self.entradas.items())
            },
            "escritura_denegada": sorted(self.escritura_denegada),
            "estado": self.estado,
            "escaneo_fin": self.escaneo_fin,
            "version": self.version,
        }

    @classmethod
    def desde_dict(cls, d: dict) -> "MapaPermisos":
        """Reconstruye el mapa; ValueError si el contenido no tiene la forma esperada."""
        try:
            entradas: dict[str, Entrada] = {}
            for k, e in d.get("entradas", {}).items():
                if e["acceso"] not in _ACCESOS or e["fuente"] not in _FUENTES:
                    raise ValueError("entrada invalida")
                if e.get("tipo") not in (*_TIPOS, None):
                    raise ValueError("tipo invalido")
                entradas[str(k)] = Entrada(e["acceso"], e["fuente"], e.get("tipo"), str(e["cuando"]))
            estado = d.get("estado", "sin_escanear")
            if estado not in _ESTADOS:
                raise ValueError("estado invalido")
            fin = d.get("escaneo_fin")
            return cls(
                entradas=entradas,
                escritura_denegada={str(x) for x in d.get("escritura_denegada", [])},
                estado=estado,
                escaneo_fin=None if fin is None else str(fin),
                version=int(d.get("version", 0)),
            )
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("mapa de permisos invalido") from exc


# Estados en los que vale lo que dijo un escaneo: el ultimo termino bien, o
# fallo y se usa el anterior. Mientras escanea o antes del primero no se oculta
# nada (solo lo aprendido por uso).
_ESTADOS_CON_ESCANEO = ("listo", "fallo")


class Permisos:
    """Lo que puede usar una persona, para las herramientas. Seguro entre hilos.

    Las herramientas sincronicas corren en hilos y el escaneo en otro: todo
    pasa por un solo candado, tambien el guardado (el almacen no es seguro
    entre hilos).
    """

    def __init__(self, almacen: AlmacenPermisos) -> None:
        self._almacen = almacen
        self._candado = threading.Lock()
        mapa = almacen.cargar()
        if mapa.estado == "escaneando":
            # Se corto a mitad de un escaneo (la app se cerro): hay que escanear de nuevo.
            mapa.estado = "sin_escanear"
        self._mapa = mapa
        self._hilo: threading.Thread | None = None

    # ------------------------------------------------------------ consultas
    @property
    def estado(self) -> EstadoEscaneo:
        with self._candado:
            return self._mapa.estado

    @property
    def problema_almacen(self) -> str | None:
        with self._candado:
            return getattr(self._almacen, "problema", None)

    def denegado(self, path: str) -> bool:
        clave = clave_permiso(path)
        with self._candado:
            entrada = self._mapa.entradas.get(clave) if clave else None
            if entrada is None or entrada.acceso != "denegado":
                return False
            return entrada.fuente == "uso" or self._mapa.estado in _ESTADOS_CON_ESCANEO

    def solo_lectura(self, path: str) -> bool:
        # Una escritura rechazada vale siempre: solo se aprende por uso.
        with self._candado:
            return self._mapa.solo_lectura(path)

    def estado_texto(self, hoy: date | None = None) -> str:
        with self._candado:
            estado = self._mapa.estado
            if estado == "escaneando":
                return "Permisos: todavía revisando"
            if estado == "sin_escanear":
                return "Permisos: todavía no se revisaron"
            if estado == "fallo":
                return "Permisos: la última revisión falló; se usa la anterior"
            r, rt, e, et = self._mapa.resumen()
            cuando = _fecha(self._mapa.escaneo_fin) or hoy or date.today()
        return (
            f"Permisos revisados el {cuando:%d/%m}: {r} de {rt} reportes y {e} de {et} "
            "entidades disponibles"
        )

    # ------------------------------------------------------- lo aprendido
    def registrar_lectura(self, path: str, ok: bool) -> None:
        """Una lectura que anduvo corrige un denegado viejo; un rechazo lo marca."""
        with self._candado:
            if ok:
                if self._mapa.acceso(path) != "denegado":
                    return
                cambio = self._mapa.corregir(path, "permitido")
            else:
                cambio = self._mapa.corregir(path, "denegado")
            if cambio:
                self._almacen.guardar(self._mapa)

    def registrar_escritura_denegada(self, path: str) -> None:
        with self._candado:
            if self._mapa.marcar_escritura_denegada(path):
                self._almacen.guardar(self._mapa)

    # ------------------------------------------------------------ escaneo
    def escanear_en_segundo_plano(
        self, hacer: Callable[[], dict[str, tuple[Acceso, TipoRecurso]]]
    ) -> bool:
        """Corre `hacer` en un hilo aparte. False si ya hay un escaneo corriendo."""
        with self._candado:
            if self._hilo is not None and self._hilo.is_alive():
                return False
            self._mapa.estado = "escaneando"
            hilo = threading.Thread(
                target=self._escanear, args=(hacer,), name="finnegans-escaneo-permisos",
                daemon=True,
            )
            self._hilo = hilo
            hilo.start()
        return True

    def _escanear(self, hacer: Callable[[], dict[str, tuple[Acceso, TipoRecurso]]]) -> None:
        try:
            resultado = hacer()
            with self._candado:
                self._mapa.aplicar_escaneo(resultado, date.today().isoformat())
                self._almacen.guardar(self._mapa)
        except Exception:  # noqa: BLE001 - un escaneo fallido conserva el mapa anterior
            with self._candado:
                self._mapa.estado = "fallo"
                self._almacen.guardar(self._mapa)

    def esperar_escaneo(self, timeout: float | None = None) -> bool:
        """Espera al escaneo en curso. True si no queda ninguno corriendo."""
        with self._candado:
            hilo = self._hilo
        if hilo is None:
            return True
        hilo.join(timeout)
        return not hilo.is_alive()


def _fecha(texto: str | None) -> date | None:
    try:
        return date.fromisoformat((texto or "")[:10])
    except ValueError:
        return None
