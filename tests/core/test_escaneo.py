import threading
import time

import pytest

from finnegans_core import escaneo
from finnegans_core.escaneo import (
    ID_INEXISTENTE, SONDA_REPORTE, Escaner, clasificar_entidad, clasificar_reporte,
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


def test_valores_conservadores_hasta_el_sondeo_en_vivo():
    assert SONDA_REPORTE == {}
    assert escaneo.REPORTES_EN_ESCANEO_AUTOMATICO is False


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
    assert por_path["reports/ACOrdenesCompraPendientes"] == (None, SONDA_REPORTE)
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
