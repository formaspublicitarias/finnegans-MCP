"""Todo lo que es de una persona: sus claves, su cliente, su workspace y sus docs.

Las herramientas del servidor no guardan nada de una persona en su clausura:
al empezar cada llamada piden el contexto al proveedor y usan solo ese. Hoy
el proveedor devuelve siempre el mismo contexto (la persona de la extension);
la version en linea va a devolver el de quien llama.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable

from finnegans_core.catalogo.docs_mcp import DocsMcp
from finnegans_core.client import FinnegansClient
from finnegans_core.config import Settings
from finnegans_core.permisos import Permisos
from finnegans_core.secretos import Redactor
from finnegans_core.workspace import Workspace


@dataclass
class Contexto:
    settings: Settings
    client: FinnegansClient
    workspace: Workspace
    docs: DocsMcp
    # Lo que puede usar la persona en Finnegans. Si queda en None, crear_servidor
    # arma uno con su almacen local.
    permisos: Permisos | None = None
    # Path del que salio cada tabla: una fila de un /list o de un reporte no
    # es el registro completo y no sirve como base de un PUT.
    origen_tabla: dict[str, str] = field(default_factory=dict)
    # Las herramientas sincronicas corren en hilos: DuckDB no se comparte en paralelo.
    candado: threading.RLock = field(default_factory=threading.RLock)
    _redactor: Redactor = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._redactor = Redactor(self.settings.secretos())
        # Aca y no en desde_settings: todo Contexto redacta el workspace antes de cortar.
        self.workspace.usar_redactor(self.limpiar)

    def limpiar(self, texto: object) -> str:
        """Borra secretos: primero el redactor del cliente (conoce el token), despues las claves."""
        salida = str(texto)
        redactor = getattr(self.client, "redactor", None)
        if redactor is not None:
            salida = redactor.limpiar(salida)
        return self._redactor.limpiar(salida)

    def cerrar(self) -> None:
        """Cierra el workspace y borra su directorio temporal."""
        self.workspace.cerrar()

    @classmethod
    def desde_settings(
        cls,
        settings: Settings,
        client: FinnegansClient | None = None,
        docs: DocsMcp | None = None,
        workspace: Workspace | None = None,
    ) -> Contexto:
        """Contexto con lo que no se inyecte armado desde las claves."""
        return cls(
            settings=settings,
            client=client if client is not None else FinnegansClient(settings),
            workspace=workspace if workspace is not None else Workspace(),
            docs=docs if docs is not None else DocsMcp(settings),
        )


ProveedorContexto = Callable[[], Contexto]
