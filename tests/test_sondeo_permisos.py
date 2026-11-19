"""Helpers puros del sondeo en vivo (sin red, valores falsos)."""
import importlib.util
import sys
from datetime import date
from pathlib import Path

_RUTA = Path(__file__).resolve().parents[1] / "scripts" / "sondeo_permisos.py"
_spec = importlib.util.spec_from_file_location("sondeo_permisos", _RUTA)
sondeo = importlib.util.module_from_spec(_spec)
# dataclasses busca el modulo en sys.modules mientras se carga.
sys.modules["sondeo_permisos"] = sondeo
_spec.loader.exec_module(sondeo)

PARAMS = [
    {"nombre": "PARAMWEBREPORT_FechaDesde", "requerido": True},
    {"nombre": "PARAMWEBREPORT_FechaHasta", "requerido": True},
    {"nombre": "PARAM_Sucursal", "requerido": True},
    {"nombre": "PARAM_fechaOpcional", "requerido": False},
]


def test_parametros_de_fecha_por_nombre():
    nombres = [p["nombre"] for p in sondeo.parametros_de_fecha(PARAMS)]
    assert nombres == ["PARAMWEBREPORT_FechaDesde", "PARAMWEBREPORT_FechaHasta",
                       "PARAM_fechaOpcional"]


def test_candidatos():
    c = sondeo.candidatos(PARAMS, hoy=date(2026, 11, 19))
    assert list(c) == ["a) sin parametros", "b) fechas requeridas invalidas",
                       "c) desde posterior a hasta", "d) rango de 1 dia (ayer)"]
    assert c["a) sin parametros"] == {}
    assert c["b) fechas requeridas invalidas"] == {
        "PARAMWEBREPORT_FechaDesde": "no-es-fecha", "PARAMWEBREPORT_FechaHasta": "no-es-fecha"}
    assert c["c) desde posterior a hasta"] == {
        "PARAMWEBREPORT_FechaDesde": "2099-01-02", "PARAMWEBREPORT_FechaHasta": "2099-01-01"}
    assert c["d) rango de 1 dia (ayer)"] == {
        "PARAMWEBREPORT_FechaDesde": "2026-11-18", "PARAMWEBREPORT_FechaHasta": "2026-11-18"}


def test_candidatos_sin_fechas():
    c = sondeo.candidatos([{"nombre": "X", "requerido": True}])
    assert c["b) fechas requeridas invalidas"] == {}
    assert c["c) desde posterior a hasta"] == {}


def test_tiene_rango_pide_desde_y_hasta():
    assert sondeo.tiene_rango(PARAMS)
    assert not sondeo.tiene_rango([{"nombre": "PARAM_FechaDesde", "requerido": False}])
    assert not sondeo.tiene_rango([{"nombre": "PARAM_Sucursal", "requerido": False}])


def test_censar_reportes_separa_por_requeridos_y_rango():
    reportes = [
        ("reports/ConRequerido", [{"nombre": "PARAM_Categoria", "requerido": True}]),
        ("reports/SinRequeridosConRango", [
            {"nombre": "PARAM_Fechadesde", "requerido": False},
            {"nombre": "PARAM_Fechahasta", "requerido": False}]),
        ("reports/SinNada", []),
        ("reports/SoloOpcional", [{"nombre": "PARAM_Sucursal", "requerido": False}]),
    ]
    c = sondeo.censar_reportes(reportes)
    assert c.con_requeridos == ["ConRequerido"]
    assert c.sin_requeridos_con_rango == ["SinRequeridosConRango"]
    assert c.sin_requeridos_sin_rango == ["SinNada", "SoloOpcional"]
    assert c.total == 4


def test_candidatos_baratos_nunca_sin_parametros():
    c = sondeo.candidatos_baratos(PARAMS, hoy=date(2026, 11, 19))
    assert list(c) == ["c) desde posterior a hasta", "d) rango de 1 dia (ayer)"]
    assert all(c.values())  # ninguno vacio: nunca se llama al reporte sin parametros


def test_elegir_para_probar_toma_los_primeros_n():
    c = sondeo.Censo(con_requeridos=[], sin_requeridos_con_rango=["B", "A", "C"],
                     sin_requeridos_sin_rango=["Z"])
    assert sondeo.elegir_para_probar(c, 2) == ["A", "B"]
    assert sondeo.elegir_para_probar(c, 0) == []


def test_censar_lee_solo_el_swagger(tmp_path):
    from tests.mcp.conftest import SPEC, ajustes, catalogo

    lineas: list[str] = []
    censo = sondeo.censar(catalogo(ajustes(tmp_path), SPEC), lineas.append)
    # El reporte de prueba solo tiene PARAM_Fechadesde opcional: sin requeridos ni rango.
    assert censo.sin_requeridos_sin_rango == ["ACOrdenesCompraPendientes"]
    assert censo.total == 1
    assert any("Censo de reportes del swagger (1)" in l for l in lineas)


def test_main_sin_claves_no_hace_nada(capsys):
    assert sondeo.main([], env={}) == 2
    assert "Faltan variables de entorno" in capsys.readouterr().err


def test_campos_de_autoria_solo_nombres():
    registro = {"Codigo": "1", "UsuarioModificacion": "x", "FechaAlta": "y",
                "Nombre": "n", "Creacion": "z", "Autor": "a"}
    assert sondeo.campos_de_autoria(registro) == [
        "Autor", "Creacion", "FechaAlta", "UsuarioModificacion"]
    assert sondeo.campos_de_autoria([registro])[0] == "Autor"
    assert sondeo.campos_de_autoria("nada") == []


def test_paths_de_auditoria():
    spec = {"paths": {"/cliente": {"get": {"summary": "Clientes"}},
                      "/auditoria/x": {"get": {}},
                      "/otro": {"get": {"summary": "Historial de cambios"}}}}
    assert sondeo.paths_de_auditoria(spec) == ["/auditoria/x", "/otro"]


def test_primer_codigo():
    assert sondeo.primer_codigo([{"Codigo": "C1"}, {"Codigo": "C2"}]) == "C1"
    assert sondeo.primer_codigo({"data": [{"codigo": 7}]}) == "7"
    assert sondeo.primer_codigo([]) is None


def test_recortar_redacta_antes_de_cortar():
    class R:
        def limpiar(self, t):
            return t.replace("SECRETO-FALSO", "***")
    texto = "x" * 110 + "SECRETO-FALSO" + "\n y"
    out = sondeo.recortar(texto, R())
    assert "SECRETO" not in out and out.endswith("*** y") and len(out) == 115
    assert len(sondeo.recortar("y" * 500, R())) == 120
