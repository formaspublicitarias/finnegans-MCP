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
