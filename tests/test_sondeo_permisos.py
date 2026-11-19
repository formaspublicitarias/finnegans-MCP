"""Helpers puros del sondeo en vivo (sin red, valores falsos)."""
import importlib.util
from datetime import date
from pathlib import Path

_RUTA = Path(__file__).resolve().parents[1] / "scripts" / "sondeo_permisos.py"
_spec = importlib.util.spec_from_file_location("sondeo_permisos", _RUTA)
sondeo = importlib.util.module_from_spec(_spec)
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
