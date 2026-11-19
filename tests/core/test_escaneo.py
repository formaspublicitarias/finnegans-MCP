import threading
import time

import pytest

from finnegans_core import escaneo
from finnegans_core.escaneo import (
    ID_INEXISTENTE, Escaner, clasificar_entidad, clasificar_reporte, planificar_reportes,
    sonda_de_reporte,
)


@pytest.mark.parametrize("status,cuerpo,esperado", [
    (403, "Forbidden: Prestacion sin permiso", "denegado"),
    (500, "falta PARAM_Fechadesde", "permitido"),
    (200, "[]", "permitido"),
    (None, "", "permitido"),
    (403, "token invalido", "permitido"),
])
def test_clasificar_reporte(status, cuerpo, esperado):
    assert clasificar_reporte(status, cuerpo) == esperado


@pytest.mark.parametrize("status,cuerpo,esperado", [
    (404, "no existe", "permitido"),
    (500, "No tiene permisos para transacciones de la categoría Tareas", "denegado"),
    (500, "otra cosa", "desconocido"),
    (None, "", "desconocido"),
])
def test_clasificar_entidad(status, cuerpo, esperado):
    assert clasificar_entidad(status, cuerpo) == esperado


def test_los_reportes_caros_no_entran_solos():
    # Los que solo se pueden revisar ejecutandolos piden confirmacion.
    assert escaneo.REPORTES_EN_ESCANEO_AUTOMATICO is False


def _p(nombre, requerido=False):
    return {"nombre": nombre, "requerido": requerido}


def test_sonda_de_reporte_con_requerido_va_sin_parametros():
    assert sonda_de_reporte([_p("PARAM_Categoria", True), _p("PARAM_Fechadesde")]) == {}


def test_sonda_de_reporte_con_rango_invierte_las_fechas():
    assert sonda_de_reporte([_p("PARAM_Fechadesde"), _p("PARAM_Fechahasta"),
                             _p("PARAM_Sucursal")]) == {
        "PARAM_Fechadesde": "2099-01-02", "PARAM_Fechahasta": "2099-01-01"}


@pytest.mark.parametrize("parametros", [
    [], [_p("PARAM_Sucursal")], [_p("PARAM_Fechadesde")],
])
def test_sonda_de_reporte_sin_requeridos_ni_rango_es_none(parametros):
    assert sonda_de_reporte(parametros) is None


def test_planificar_reportes_lee_el_swagger(tmp_path):
    from tests.mcp.conftest import ajustes, catalogo, spec_grande

    plan = planificar_reportes(catalogo(ajustes(tmp_path), spec_grande(2)))
    # ACOrdenesCompraPendientes solo tiene una fecha opcional; los de spec_grande
    # tienen PARAM_Filtro0 requerido. Las entidades no aparecen.
    assert plan == {
        "reports/acordenescomprapendientes": None,
        "reports/reporteclientes0000": {},
        "reports/reporteclientes0001": {},
    }


def test_reportes_baratos_entran_sin_pedirlos_y_los_caros_no():
    sonda = SondaFalsa(respuesta=(200, "[]"))
    sondas = {"reports/barato": {}, "reports/rango": {"F_desde": "2099-01-02"},
              "reports/caro": None}
    objetivos = [("reports/Barato", "reporte"), ("reports/Rango", "reporte"),
                 ("reports/Caro", "reporte"), ("reports/SinPlan", "reporte")]
    res = Escaner(sonda, sondas=sondas).escanear(objetivos, incluir_reportes=False)
    assert sorted((p, pr) for p, _, pr in sonda.llamadas) == [
        ("reports/Barato", {}), ("reports/Rango", {"F_desde": "2099-01-02"})]
    assert sorted(res) == ["reports/barato", "reports/rango"]


def test_con_incluir_reportes_entran_tambien_los_caros_sin_parametros():
    sonda = SondaFalsa(respuesta=(200, "[]"))
    sondas = {"reports/barato": {}, "reports/caro": None}
    Escaner(sonda, sondas=sondas).escanear(
        [("reports/Barato", "reporte"), ("reports/Caro", "reporte")], incluir_reportes=True)
    assert sorted((p, pr) for p, _, pr in sonda.llamadas) == [
        ("reports/Barato", {}), ("reports/Caro", {})]


class SondaFalsa:
    def __init__(self, demora=0.0, respuesta=(404, "no existe")):
        self.demora = demora
        self.respuesta = respuesta
        self.llamadas = []
        self.lock = threading.Lock()
        self.en_vuelo = 0
        self.maximo = 0

    def sondear(self, path, id=None, params=None, timeout=10.0):
        with self.lock:
            self.llamadas.append((path, id, params))
            self.en_vuelo += 1
            self.maximo = max(self.maximo, self.en_vuelo)
        time.sleep(self.demora)
        with self.lock:
            self.en_vuelo -= 1
        return self.respuesta


def test_nunca_mas_de_cuatro_en_vuelo():
    sonda = SondaFalsa(demora=0.05)
    objetivos = [(f"ent{i}", "entidad") for i in range(40)]
    res = Escaner(sonda).escanear(objetivos, incluir_reportes=True)
    assert len(res) == 40
    assert 1 < sonda.maximo <= 4


def test_entidades_usan_codigo_inexistente_y_reportes_la_sonda():
    sonda = SondaFalsa(respuesta=(200, "[]"))
    res = Escaner(sonda).escanear(
        [("cliente", "entidad"), ("reports/ACOrdenesCompraPendientes", "reporte")],
        incluir_reportes=True)
    por_path = {p: (i, pr) for p, i, pr in sonda.llamadas}
    assert por_path["cliente"][0] == ID_INEXISTENTE
    assert por_path["reports/ACOrdenesCompraPendientes"] == (None, {})
    # las claves salen normalizadas, no con la grafia del swagger
    assert res == {
        "cliente": ("desconocido", "entidad"),
        "reports/acordenescomprapendientes": ("permitido", "reporte"),
    }


def test_sin_reportes_no_sondea_reportes():
    sonda = SondaFalsa()
    res = Escaner(sonda).escanear(
        [("cliente", "entidad"), ("reports/X", "reporte")], incluir_reportes=False)
    assert [c[0] for c in sonda.llamadas] == ["cliente"]
    assert list(res) == ["cliente"]
    assert res["cliente"] == ("permitido", "entidad")


def test_un_fallo_de_autenticacion_corta_el_escaneo():
    from finnegans_core.client import FinnegansAuthError

    class Mala:
        def sondear(self, path, id=None, params=None, timeout=10.0):
            raise FinnegansAuthError("claves malas")

    with pytest.raises(FinnegansAuthError):
        Escaner(Mala()).escanear([("cliente", "entidad"), ("reports/X", "reporte")], True)


def test_una_excepcion_en_un_objetivo_lo_deja_desconocido_y_sigue():
    class Rota:
        def sondear(self, path, id=None, params=None, timeout=10.0):
            if path in ("malo", "reports/Malo"):
                raise RuntimeError("boom")
            return 404, "no existe"

    res = Escaner(Rota()).escanear(
        [("a", "entidad"), ("malo", "entidad"), ("b", "entidad"), ("reports/Malo", "reporte")],
        incluir_reportes=True)
    assert res == {
        "a": ("permitido", "entidad"),
        "malo": ("desconocido", "entidad"),
        "b": ("permitido", "entidad"),
        "reports/malo": ("desconocido", "reporte"),
    }


# ------------------------------------------- final review: escaneo incompleto


class SondaPorPath:
    """Responde segun el path; None simula que Finnegans no contesto."""

    def __init__(self, respuestas):
        self.respuestas = respuestas

    def sondear(self, path, id=None, params=None, timeout=10.0):
        return self.respuestas.get(path, (404, "no existe"))


def _entidades(n):
    return [(f"ent{i}", "entidad") for i in range(n)]


def test_muchas_entidades_sin_respuesta_cortan_el_escaneo():
    from finnegans_core.escaneo import EscaneoIncompleto

    # 2 de 7 sin respuesta: mas del 25%.
    sonda = SondaPorPath({"ent0": (None, ""), "ent1": (None, "")})
    with pytest.raises(EscaneoIncompleto) as exc:
        Escaner(sonda).escanear(_entidades(7), incluir_reportes=False)
    assert str(exc.value) == (
        "El escaneo no pudo completarse: Finnegans no respondió a muchas consultas."
    )


def test_hasta_un_cuarto_sin_respuesta_sigue():
    # 1 de 4 sin respuesta: justo el 25%, no mas.
    sonda = SondaPorPath({"ent0": (None, "")})
    res = Escaner(sonda).escanear(_entidades(4), incluir_reportes=False)
    assert res["ent0"] == ("desconocido", "entidad")
    assert res["ent1"] == ("permitido", "entidad")


def test_los_reportes_sin_respuesta_no_cuentan():
    # Un reporte que no contesta esta corriendo: no es un escaneo incompleto.
    respuestas = {f"reports/R{i}": (None, "") for i in range(10)}
    sonda = SondaPorPath(respuestas)
    objetivos = _entidades(2) + [(p, "reporte") for p in respuestas]
    res = Escaner(sonda).escanear(objetivos, incluir_reportes=True)
    assert res["reports/r0"] == ("permitido", "reporte")
    assert res["ent0"] == ("permitido", "entidad")


def test_escaneo_incompleto_es_un_error_propio():
    from finnegans_core.client import FinnegansAuthError
    from finnegans_core.escaneo import EscaneoIncompleto

    assert issubclass(EscaneoIncompleto, Exception)
    assert not issubclass(EscaneoIncompleto, FinnegansAuthError)
