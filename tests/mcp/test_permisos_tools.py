"""Las herramientas usan el mapa de permisos de la persona y lo corrigen con el uso."""
from __future__ import annotations

import threading

import pytest

from finnegans_core.almacen_permisos import AlmacenMemoria, carpeta_datos
from finnegans_core.catalogo.swagger import SwaggerError
from finnegans_core.client import FinnegansError
from finnegans_core.escaneo import REPORTES_EN_ESCANEO_AUTOMATICO
from finnegans_core.permisos import Permisos, mensaje_sin_permiso
from finnegans_mcp.contexto import Contexto
from finnegans_mcp.server import crear_servidor

from .conftest import SPEC, ClienteFalso, DocsFalso, ajustes, catalogo

pytestmark = pytest.mark.anyio

TODO_OCULTO = (
    "Lo que buscás existe en Finnegans, pero tu usuario no tiene permiso. Si lo "
    "necesitás, pedíselo a quien administra Finnegans y después pedime que revise tus "
    "permisos."
)
REPORTE = "reports/ACOrdenesCompraPendientes"
# La documentacion sugiere tambien la entidad cliente: la busqueda trae dos filas.
DOCS_CON_CLIENTE = [{"path": "cliente", "resumen": "Clientes de la empresa"}]


def permisos_con(resultado: dict, escritura_denegada: tuple[str, ...] = ()) -> Permisos:
    """Permisos en memoria con un escaneo ya aplicado."""
    almacen = AlmacenMemoria()
    mapa = almacen.cargar()
    mapa.aplicar_escaneo(resultado, "2026-11-17")
    for path in escritura_denegada:
        mapa.marcar_escritura_denegada(path)
    return Permisos(almacen)


# ------------------------------------------------------------ buscar_endpoint


async def test_buscar_oculta_lo_denegado(armar):
    p = permisos_con({"reports/acordenescomprapendientes": ("denegado", "reporte"),
                      "cliente": ("permitido", "entidad")})
    env = armar(permisos=p, docs=DocsFalso(DOCS_CON_CLIENTE))
    out = await env.llamar("buscar_endpoint", consulta="ordenes de compra pendientes")
    assert "ACOrdenesCompraPendientes" not in out
    assert "/cliente" in out
    assert out != TODO_OCULTO


async def test_buscar_todo_oculto_lo_dice(armar):
    p = permisos_con({"reports/acordenescomprapendientes": ("denegado", "reporte"),
                      "cliente": ("denegado", "entidad")})
    env = armar(permisos=p, docs=DocsFalso(DOCS_CON_CLIENTE))
    out = await env.llamar("buscar_endpoint", consulta="ordenes de compra pendientes")
    assert out == TODO_OCULTO


async def test_buscar_marca_solo_lectura(armar):
    p = permisos_con({"cliente": ("permitido", "entidad")}, escritura_denegada=("cliente",))
    env = armar(permisos=p)
    out = await env.llamar("buscar_endpoint", consulta="clientes")
    filas = [linea for linea in out.splitlines() if "/cliente" in linea]
    assert filas
    assert all("solo lectura para vos" in f for f in filas)
    reportes = [linea for linea in out.splitlines() if "/reports/" in linea]
    assert not any("solo lectura" in r for r in reportes)


async def test_buscar_cuenta_solo_lo_que_queda(armar):
    """El aviso de 'resultados más' no cuenta las filas ocultas."""
    docs = [{"path": f"reports/Oculto{i:02d}", "resumen": "x"} for i in range(20)]
    docs.append({"path": "reports/Visible", "resumen": "y"})
    p = permisos_con({f"reports/oculto{i:02d}": ("denegado", "reporte") for i in range(20)})
    env = armar(permisos=p, docs=DocsFalso(docs))
    out = await env.llamar("buscar_endpoint", consulta="ordenes de compra pendientes")
    assert "Oculto" not in out
    assert "reports/Visible" in out
    assert "resultados más" not in out


# --------------------------------------------------------------- ver_endpoint


async def test_ver_endpoint_denegado(armar):
    p = permisos_con({"reports/acordenescomprapendientes": ("denegado", "reporte")})
    env = armar(permisos=p)
    out = await env.llamar("ver_endpoint", path=REPORTE)
    assert out == mensaje_sin_permiso("GET", REPORTE)


async def test_ver_endpoint_solo_lectura(armar):
    p = permisos_con({"cliente": ("permitido", "entidad")}, escritura_denegada=("cliente",))
    env = armar(permisos=p)
    out = await env.llamar("ver_endpoint", path="cliente")
    assert out.splitlines()[0] == "(cliente: solo lectura para vos)"
    assert "PUT /cliente/{codigo}" in out


# ----------------------------------------------------------- leer y escribir


async def test_leer_corrige_un_denegado_viejo(armar):
    p = permisos_con({"cliente": ("denegado", "entidad")})
    env = armar(lambda *a: [{"Codigo": "1"}], permisos=p)
    await env.llamar("leer", path="cliente/list")
    assert not p.denegado("cliente")


async def test_leer_rechazado_marca_denegado(armar):
    def rechazo(*a):
        raise FinnegansError("Error en GET reports/X (HTTP 403): Forbidden: Prestacion sin permiso")

    env = armar(rechazo)
    out = await env.llamar("leer", path="reports/X")
    assert env.permisos.denegado("reports/X")
    assert "no tiene permiso para ver" in out


async def test_leer_con_otro_error_no_marca_nada(armar):
    def falla(*a):
        raise FinnegansError("Error en GET reports/X (HTTP 500): Falta el parametro Fecha")

    env = armar(falla)
    await env.llamar("leer", path="reports/X")
    assert not env.permisos.denegado("reports/X")


async def test_escribir_rechazado_marca_solo_lectura(armar):
    def rechazo(metodo, *a):
        raise FinnegansError(f"Error en {metodo} cliente (HTTP 403): Forbidden")

    env = armar(rechazo)
    await env.llamar("escribir", metodo="PUT", path="cliente", id="1",
                     body={"Codigo": "1", "Nombre": "x"})
    assert env.permisos.solo_lectura("cliente")
    assert not env.permisos.denegado("cliente")


# ------------------------------------------------- estado y escaneos


async def test_sin_escaneo_no_oculta_nada(armar):
    env = armar(docs=DocsFalso(DOCS_CON_CLIENTE))
    out = await env.llamar("buscar_endpoint", consulta="ordenes de compra pendientes")
    assert "ACOrdenesCompraPendientes" in out and "/cliente" in out
    out = await env.llamar("verificar_conexion")
    assert "Permisos: todavía no se revisaron" in out


async def test_reescanear_arranca_y_no_duplica(armar):
    liberar = threading.Event()
    pedidos: list[bool] = []

    def escaneo(ctx, incluir_reportes):
        pedidos.append(incluir_reportes)
        assert liberar.wait(5)
        return {"cliente": ("permitido", "entidad")}

    env = armar(hacer_escaneo=escaneo)
    try:
        primero = await env.llamar("verificar_conexion", reescanear=True)
        segundo = await env.llamar("verificar_conexion", reescanear=True)
    finally:
        liberar.set()
    assert "Estoy revisando tus permisos, tarda unos 2 minutos." in primero
    assert "Ya estoy revisando tus permisos; en un par de minutos está listo." in segundo
    assert "Permisos: todavía revisando" in segundo
    assert "Ojo:" not in primero
    assert env.permisos.esperar_escaneo(5)
    assert pedidos == [REPORTES_EN_ESCANEO_AUTOMATICO]
    assert env.permisos.estado_texto().startswith("Permisos revisados el")


AVISO_REPORTES = (
    "Ojo: revisar los reportes los ejecuta en Finnegans (unos 140); conviene hacerlo "
    "fuera del horario de trabajo. Si igual querés hacerlo, pedímelo de nuevo confirmando."
)


async def test_reescanear_con_reportes_sin_confirmar_no_arranca_nada(armar):
    pedidos: list[bool] = []

    def escaneo(ctx, incluir_reportes):
        pedidos.append(incluir_reportes)
        return {}

    env = armar(hacer_escaneo=escaneo)
    out = await env.llamar("verificar_conexion", reescanear=True, incluir_reportes=True)
    assert env.permisos.esperar_escaneo(5)
    assert pedidos == []
    assert env.permisos.estado == "sin_escanear"
    assert AVISO_REPORTES in out
    assert "Estoy revisando" not in out and "Ya estoy revisando" not in out


async def test_reescanear_con_reportes_confirmado_arranca_con_reportes(armar):
    pedidos: list[bool] = []

    def escaneo(ctx, incluir_reportes):
        pedidos.append(incluir_reportes)
        return {"reports/acordenescomprapendientes": ("permitido", "reporte"),
                "cliente": ("permitido", "entidad")}

    env = armar(hacer_escaneo=escaneo)
    out = await env.llamar("verificar_conexion", reescanear=True, incluir_reportes=True,
                           confirmar=True)
    assert env.permisos.esperar_escaneo(5)
    assert pedidos == [True]
    assert "Estoy revisando tus permisos, tarda unos 2 minutos." in out
    assert "Ojo:" not in out
    assert "1 de 1 reportes y 1 de 1 entidades disponibles" in env.permisos.estado_texto()


async def test_reescanear_con_reportes_confirmado_mientras_corre_otro(armar):
    liberar = threading.Event()
    pedidos: list[bool] = []

    def escaneo(ctx, incluir_reportes):
        pedidos.append(incluir_reportes)
        assert liberar.wait(5)
        return {}

    env = armar(hacer_escaneo=escaneo)
    try:
        await env.llamar("verificar_conexion", reescanear=True)
        out = await env.llamar("verificar_conexion", reescanear=True, incluir_reportes=True,
                               confirmar=True)
    finally:
        liberar.set()
    assert env.permisos.esperar_escaneo(5)
    assert "Ya estoy revisando tus permisos; en un par de minutos está listo." in out
    assert pedidos == [REPORTES_EN_ESCANEO_AUTOMATICO]


async def test_descripcion_de_verificar_conexion_y_manifest(armar):
    import json
    from pathlib import Path

    esperado = (
        "Revisa la configuración de la extensión: que estén todas las claves, que "
        "Finnegans dé un token, que cargue el swagger y que responda la documentación. "
        "Dice en castellano qué clave está mal. Con reescanear=True revisa de nuevo qué "
        "entidades puede usar tu usuario; los reportes solo si se pide "
        "incluir_reportes=True y confirmar=True."
    )
    env = armar()
    tools = {t.name: t for t in await env.server.list_tools()}
    assert tools["verificar_conexion"].description == esperado
    manifest = json.loads(
        (Path(__file__).parents[2] / "manifest.json").read_text(encoding="utf-8"))
    (decl,) = [t for t in manifest["tools"] if t["name"] == "verificar_conexion"]
    assert decl["description"] == esperado


# ------------------------------------------- lo aprendido por uso y los reescaneos


def permisos_con_lo_aprendido() -> Permisos:
    p = Permisos(AlmacenMemoria())
    p.registrar_lectura("reports/X", ok=False)
    p.registrar_escritura_denegada("cliente")
    return p


async def test_reescanear_olvida_lo_aprendido_por_uso(armar):
    p = permisos_con_lo_aprendido()
    env = armar(permisos=p, hacer_escaneo=lambda ctx, incl: {"cliente": ("permitido", "entidad")})
    await env.llamar("verificar_conexion", reescanear=True)
    assert p.esperar_escaneo(5)
    assert not p.denegado("reports/X")
    assert not p.solo_lectura("cliente")


async def test_escaneo_al_iniciar_conserva_lo_aprendido_por_uso(armar):
    p = permisos_con_lo_aprendido()
    env = armar(permisos=p, hacer_escaneo=lambda ctx, incl: {"cliente": ("permitido", "entidad")},
                escanear_al_iniciar=True)
    assert p.esperar_escaneo(5)
    assert env.permisos.estado == "listo"
    assert p.denegado("reports/X")
    assert p.solo_lectura("cliente")


async def test_escritura_aceptada_quita_solo_lectura(armar):
    def handler(metodo, path, id, params, body):
        return {} if metodo == "PUT" else {"Codigo": "1", "Nombre": "x"}

    p = permisos_con_lo_aprendido()
    env = armar(handler, permisos=p)
    out = await env.llamar("escribir", metodo="PUT", path="cliente", id="1",
                           body={"Codigo": "1", "Nombre": "x"})
    assert "listo, Finnegans aceptó la escritura" in out
    assert not p.solo_lectura("cliente")
    assert p.denegado("reports/X")


# ------------------------------------------- escaneo al iniciar y primer fallo


@pytest.mark.parametrize("falta", ["client_id", "client_secret"])
async def test_al_iniciar_no_escanea_sin_claves(armar, tmp_path, falta):
    pedidos: list[bool] = []

    def escaneo(ctx, incluir_reportes):
        pedidos.append(incluir_reportes)
        return {}

    env = armar(settings=ajustes(tmp_path, **{falta: ""}), hacer_escaneo=escaneo,
                escanear_al_iniciar=True)
    assert env.permisos.esperar_escaneo(5)
    assert pedidos == []
    assert env.permisos.estado == "sin_escanear"


async def test_primer_escaneo_fallido_lo_dice_en_verificar_conexion(armar):
    def escaneo(ctx, incluir_reportes):
        raise RuntimeError("se cayo la red")

    env = armar(hacer_escaneo=escaneo)
    await env.llamar("verificar_conexion", reescanear=True)
    assert env.permisos.esperar_escaneo(5)
    out = await env.llamar("verificar_conexion")
    assert (
        "Permisos: la revisión falló y todavía no hay una anterior; por ahora se muestra todo"
    ) in out


async def test_falla_del_swagger_en_el_escaneo_conserva_el_mapa(armar):
    resultados = [{"cliente": ("denegado", "entidad")}, SwaggerError("clave del swagger invalida")]

    def escaneo(ctx, incluir_reportes):
        r = resultados.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    env = armar(hacer_escaneo=escaneo)
    await env.llamar("verificar_conexion", reescanear=True)
    assert env.permisos.esperar_escaneo(5)
    assert env.permisos.denegado("cliente")
    await env.llamar("verificar_conexion", reescanear=True)
    assert env.permisos.esperar_escaneo(5)
    assert env.permisos.denegado("cliente")
    texto = "Permisos: la última revisión falló; se usa la anterior"
    assert env.permisos.estado_texto() == texto
    assert texto in await env.llamar("verificar_conexion")
    out = await env.llamar("buscar_endpoint", consulta="ordenes de compra pendientes")
    assert "ACOrdenesCompraPendientes" in out


async def test_verificar_conexion_dice_si_no_pudo_guardar(armar):
    almacen = AlmacenMemoria()
    almacen.problema = "No pude guardar tus permisos en esta PC."
    env = armar(permisos=Permisos(almacen))
    out = await env.llamar("verificar_conexion")
    assert "No pude guardar tus permisos en esta PC." in out


async def test_al_iniciar_escanea_si_no_hay_mapa(armar):
    pedidos: list[bool] = []

    def escaneo(ctx, incluir_reportes):
        pedidos.append(incluir_reportes)
        return {"cliente": ("permitido", "entidad")}

    env = armar(hacer_escaneo=escaneo, escanear_al_iniciar=True)
    assert env.permisos.esperar_escaneo(5)
    assert pedidos == [REPORTES_EN_ESCANEO_AUTOMATICO]
    assert env.permisos.estado == "listo"


async def test_al_iniciar_no_escanea_si_ya_esta_listo(armar):
    pedidos: list[bool] = []

    def escaneo(ctx, incluir_reportes):
        pedidos.append(incluir_reportes)
        return {}

    env = armar(permisos=permisos_con({"cliente": ("permitido", "entidad")}),
                hacer_escaneo=escaneo, escanear_al_iniciar=True)
    assert env.permisos.esperar_escaneo(5)
    assert pedidos == []


async def test_al_iniciar_reintenta_un_escaneo_fallido(armar):
    def falla():
        raise RuntimeError("se cayo la red")

    p = permisos_con({"cliente": ("denegado", "entidad")})
    assert p.escanear_en_segundo_plano(falla)
    assert p.esperar_escaneo(5)
    assert p.estado == "fallo"
    env = armar(permisos=p, hacer_escaneo=lambda ctx, incl: {}, escanear_al_iniciar=True)
    assert env.permisos.esperar_escaneo(5)
    assert env.permisos.estado == "listo"


# ------------------------------------------------- permisos armados por el servidor


async def test_sin_permisos_inyectados_se_guardan_en_la_carpeta_de_datos(tmp_path):
    s = ajustes(tmp_path)

    def rechazo(*a):
        raise FinnegansError("Error en GET reports/X (HTTP 403): Forbidden: Prestacion sin permiso")

    ctx = Contexto.desde_settings(s, client=ClienteFalso(s, rechazo), docs=DocsFalso())
    try:
        server = crear_servidor(s, swagger=catalogo(s, SPEC), contexto=ctx)
        assert isinstance(ctx.permisos, Permisos)
        await server.call_tool("leer", {"path": "reports/X"})
        archivos = list(carpeta_datos().glob("permisos-*.json"))
        assert len(archivos) == 1
        assert s.client_id not in archivos[0].read_text(encoding="utf-8")
    finally:
        ctx.cerrar()


async def test_sin_client_id_los_permisos_viven_en_memoria(tmp_path):
    s = ajustes(tmp_path, client_id="")
    ctx = Contexto.desde_settings(s, client=ClienteFalso(s), docs=DocsFalso())
    try:
        crear_servidor(s, swagger=catalogo(s, SPEC), contexto=ctx)
        assert isinstance(ctx.permisos, Permisos)
        ctx.permisos.registrar_lectura("reports/X", ok=False)
        assert not carpeta_datos().exists() or not list(carpeta_datos().glob("permisos-*"))
    finally:
        ctx.cerrar()
