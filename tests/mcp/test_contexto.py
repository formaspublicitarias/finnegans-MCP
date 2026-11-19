"""Contexto por persona: cada llamada usa el contexto que da el proveedor."""
from __future__ import annotations

import pytest

from finnegans_mcp.contexto import Contexto
from finnegans_mcp.server import crear_servidor

from .conftest import (
    SPEC,
    ClienteFalso,
    DocsFalso,
    ajustes,
    catalogo,
    error_con_secreto,
)

pytestmark = pytest.mark.anyio

CID_B = "cid-b-falso"
SECRETO_B = "sec-b-falso"


async def llamar(server, nombre: str, **argumentos) -> str:
    r = await server.call_tool(nombre, argumentos)
    assert not r.is_error, r
    return "".join(c.text for c in r.content)


async def test_cada_contexto_ve_solo_sus_tablas(tmp_path):
    sa = ajustes(tmp_path)
    sb = ajustes(tmp_path, client_id=CID_B, client_secret=SECRETO_B)
    a = Contexto.desde_settings(sa, client=ClienteFalso(sa, lambda *x: [{"x": 1}]),
                                docs=DocsFalso())
    b = Contexto.desde_settings(sb, client=ClienteFalso(sb), docs=DocsFalso())
    try:
        actual = {"ctx": a}
        server = crear_servidor(a.settings, swagger=catalogo(a.settings, SPEC),
                                contexto=lambda: actual["ctx"])
        await llamar(server, "leer", path="cliente/list", tabla="clientes_a")
        actual["ctx"] = b
        texto = await llamar(server, "consultar", sql="SHOW TABLES")
        assert "clientes_a" not in texto
        actual["ctx"] = a
        assert "clientes_a" in await llamar(server, "consultar", sql="SHOW TABLES")
    finally:
        a.cerrar()
        b.cerrar()


async def test_secretos_de_cada_contexto_se_enmascaran_en_el_suyo(tmp_path):
    sa = ajustes(tmp_path)
    sb = ajustes(tmp_path, client_id=CID_B, client_secret=SECRETO_B)

    def falla_b(*x):
        raise error_con_secreto(sb)

    a = Contexto.desde_settings(sa, client=ClienteFalso(sa, lambda *x: {"Codigo": "X"}),
                                docs=DocsFalso())
    b = Contexto.desde_settings(sb, client=ClienteFalso(sb, falla_b), docs=DocsFalso())
    try:
        actual = {"ctx": a}
        server = crear_servidor(a.settings, swagger=catalogo(a.settings, SPEC),
                                contexto=lambda: actual["ctx"])
        # Primero una llamada con a: si algo quedara atado al contexto de
        # arranque, la siguiente con b lo usaria.
        await llamar(server, "leer", path="cliente", id="X")
        actual["ctx"] = b
        out_leer = await llamar(server, "leer", path="cliente", id="X")
        out_escribir = await llamar(server, "escribir", metodo="PUT", path="cliente",
                                    id="X", body={"Codigo": "X"})
        for out in (out_leer, out_escribir):
            assert SECRETO_B not in out and CID_B not in out
            assert "Finnegans no pudo procesar" in out
        assert len(b.client.llamadas) == 2
    finally:
        a.cerrar()
        b.cerrar()


def test_modo_remoto_todavia_no_existe(tmp_path):
    with pytest.raises(ValueError):
        crear_servidor(ajustes(tmp_path), modo="remoto")


def test_contexto_armado_a_mano_redacta_el_workspace(tmp_path):
    """El redactor del workspace se conecta al crear el Contexto, no solo en desde_settings."""
    from finnegans_core.workspace import Workspace

    from .conftest import CLIENT_SECRET

    s = ajustes(tmp_path)
    ctx = Contexto(settings=s, client=ClienteFalso(s), workspace=Workspace(), docs=DocsFalso())
    try:
        resumen = ctx.workspace.cargar("t", f"respuesta con {CLIENT_SECRET} adentro")
        assert resumen.nota
        assert CLIENT_SECRET not in resumen.nota
    finally:
        ctx.cerrar()
