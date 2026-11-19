"""El escaneo de produccion de punta a punta: FinnegansClient real sobre una red falsa.

Sin `hacer_escaneo` inyectado: corre el trabajo por defecto del servidor
(Escaner sobre el cliente de la persona y los recursos del swagger). Todas las
claves son falsas y no hay red.
"""
from __future__ import annotations

import copy
from datetime import date

import httpx2
import pytest

import finnegans_mcp.server as servidor
from finnegans_core.almacen_permisos import AlmacenMemoria
from finnegans_core.client import FinnegansAuthError, FinnegansClient
from finnegans_core.escaneo import ID_INEXISTENTE, EscaneoIncompleto, Escaner
from finnegans_core.permisos import Entrada, Permisos
from finnegans_core.workspace import Workspace
from finnegans_mcp.contexto import Contexto
from finnegans_mcp.server import crear_servidor

from .conftest import SPEC, DocsFalso, ajustes, catalogo

pytestmark = pytest.mark.anyio

TOKEN = "tok-falso-5p6q7r"
SIN_PERMISO_ENTIDAD = "No tiene permisos para transacciones de la categoría Clientes"
SIN_PERMISO_REPORTE = '{"error":"Forbidden: Prestacion sin permiso"}'


def es_token(req: httpx2.Request) -> bool:
    return req.url.path.endswith("/api/oauth/token")


@pytest.fixture
def espia(monkeypatch):
    """Registra la excepcion con la que termina cada escaneo del servidor."""
    errores: list[BaseException] = []

    class Espia(Escaner):
        def escanear(self, *a, **k):
            try:
                return super().escanear(*a, **k)
            except Exception as e:
                errores.append(e)
                raise

    monkeypatch.setattr(servidor, "Escaner", Espia)
    return errores


@pytest.fixture
def armar_real(tmp_path):
    creados: list[tuple[Contexto, httpx2.Client]] = []

    def _armar(red, almacen: AlmacenMemoria | None = None):
        s = ajustes(tmp_path)
        pedidos: list[httpx2.Request] = []

        def registrar(req: httpx2.Request) -> httpx2.Response:
            pedidos.append(req)
            return red(req)

        http = httpx2.Client(transport=httpx2.MockTransport(registrar))
        ctx = Contexto.desde_settings(
            s, client=FinnegansClient(s, http=http), docs=DocsFalso(), workspace=Workspace())
        almacen = almacen if almacen is not None else AlmacenMemoria()
        ctx.permisos = Permisos(almacen)
        server = crear_servidor(s, swagger=catalogo(s, SPEC), contexto=ctx)
        creados.append((ctx, http))
        return server, ctx, almacen, pedidos

    yield _armar
    for ctx, http in creados:
        assert ctx.permisos.esperar_escaneo(5), "quedo un escaneo de permisos corriendo"
        ctx.cerrar()
        http.close()


async def llamar(server, **argumentos) -> str:
    r = await server.call_tool("verificar_conexion", argumentos)
    assert not r.is_error, r
    return "".join(c.text for c in r.content)


def almacen_con_mapa_anterior() -> AlmacenMemoria:
    almacen = AlmacenMemoria()
    mapa = almacen.cargar()
    mapa.aplicar_escaneo({"cliente": ("denegado", "entidad")}, "2026-11-10")
    mapa.corregir("reports/X", "denegado")
    mapa.marcar_escritura_denegada("proveedor")
    return almacen


def sin_estado(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "estado"}


async def test_escaneo_real_feliz(armar_real, espia):
    def red(req):
        if es_token(req):
            return httpx2.Response(200, text=TOKEN)
        if req.url.path.endswith(f"/api/cliente/{ID_INEXISTENTE}"):
            return httpx2.Response(500, text=SIN_PERMISO_ENTIDAD)
        if req.url.path.endswith("/api/reports/ACOrdenesCompraPendientes"):
            return httpx2.Response(403, text=SIN_PERMISO_REPORTE)
        return httpx2.Response(404, text="no existe")

    server, ctx, almacen, pedidos = armar_real(red)
    hoy = date.today().isoformat()

    await llamar(server, reescanear=True)
    assert ctx.permisos.esperar_escaneo(5)
    assert espia == []
    assert ctx.permisos.estado == "listo"
    mapa = almacen.cargar()
    assert mapa.entradas == {"cliente": Entrada("denegado", "escaneo", "entidad", hoy)}
    assert mapa.reportes_escaneados is False
    sondas = [r for r in pedidos if not es_token(r)]
    assert [r.url.path for r in sondas] == [f"/api/cliente/{ID_INEXISTENTE}"]
    assert sondas[0].url.params["ACCESS_TOKEN"] == TOKEN
    assert ctx.permisos.denegado("cliente/list")

    # Con reportes, confirmado: tambien sondea el reporte.
    await llamar(server, reescanear=True, incluir_reportes=True, confirmar=True)
    assert ctx.permisos.esperar_escaneo(5)
    assert espia == []
    mapa = almacen.cargar()
    assert mapa.entradas == {
        "cliente": Entrada("denegado", "escaneo", "entidad", hoy),
        "reports/acordenescomprapendientes": Entrada("denegado", "escaneo", "reporte", hoy),
    }
    assert mapa.reportes_escaneados is True
    assert "0 de 1 reportes y 0 de 1 entidades disponibles" in ctx.permisos.estado_texto()


async def test_escaneo_real_con_claves_rechazadas_conserva_el_mapa(armar_real, espia):
    def red(req):
        if es_token(req):
            return httpx2.Response(401, text="invalid_client")
        raise AssertionError(f"no deberia sondear sin token: {req.url.path}")

    almacen = almacen_con_mapa_anterior()
    antes = copy.deepcopy(almacen.cargar().a_dict())
    server, ctx, almacen, pedidos = armar_real(red, almacen)

    out = await llamar(server, reescanear=True)
    assert ctx.permisos.esperar_escaneo(5)
    assert "- API de Finnegans (token): ERROR." in out
    assert len(espia) == 1 and isinstance(espia[0], FinnegansAuthError)
    assert ctx.permisos.estado == "fallo"
    assert sin_estado(almacen.cargar().a_dict()) == sin_estado(antes)
    assert ctx.permisos.denegado("cliente")
    assert ctx.permisos.denegado("reports/X")
    assert ctx.permisos.solo_lectura("proveedor")
    assert all(es_token(r) for r in pedidos)


async def test_escaneo_real_sin_red_en_las_entidades_conserva_el_mapa(armar_real, espia):
    def red(req):
        if es_token(req):
            return httpx2.Response(200, text=TOKEN)
        raise httpx2.ConnectError("se corto la red", request=req)

    almacen = almacen_con_mapa_anterior()
    antes = copy.deepcopy(almacen.cargar().a_dict())
    server, ctx, almacen, pedidos = armar_real(red, almacen)

    await llamar(server, reescanear=True)
    assert ctx.permisos.esperar_escaneo(5)
    assert len(espia) == 1 and isinstance(espia[0], EscaneoIncompleto)
    assert ctx.permisos.estado == "fallo"
    assert sin_estado(almacen.cargar().a_dict()) == sin_estado(antes)
    assert ctx.permisos.denegado("cliente")
    assert ctx.permisos.denegado("reports/X")
    assert ctx.permisos.solo_lectura("proveedor")
    assert ctx.permisos.estado_texto() == "Permisos: la última revisión falló; se usa la anterior"
    assert any(r.url.path == f"/api/cliente/{ID_INEXISTENTE}" for r in pedidos)
