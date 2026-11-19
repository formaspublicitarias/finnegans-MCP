from finnegans_core.permisos import (
    es_rechazo_escritura, es_rechazo_permiso, mensaje_sin_permiso, rechazo_en_mensaje,
)


def test_reporte_denegado_es_rechazo():
    assert es_rechazo_permiso(403, '{"error":"Forbidden: Prestacion sin permiso"}')


def test_entidad_denegada_es_rechazo():
    assert es_rechazo_permiso(500, "No tiene permisos para transacciones de la categoría X")


def test_403_de_credenciales_no_es_rechazo_de_permiso():
    assert not es_rechazo_permiso(403, "Forbidden: token invalido")


def test_escritura_403_cualquiera_es_rechazo():
    assert es_rechazo_escritura(403, "Forbidden")


def test_escritura_500_con_permiso_es_rechazo_y_sin_permiso_no():
    assert es_rechazo_escritura(500, "El usuario no tiene permiso para modificar")
    assert not es_rechazo_escritura(500, "Falta el campo Nombre")


def test_rechazo_en_mensaje_del_cliente():
    msg = "Error en GET reports/X (HTTP 403): Forbidden: Prestacion sin permiso"
    assert rechazo_en_mensaje(msg, escritura=False)


def test_mensaje_sin_permiso_textual():
    assert mensaje_sin_permiso("PUT", "cliente") == (
        "Tu usuario de Finnegans no tiene permiso para modificar en 'cliente'. "
        "Si lo necesitás, pedíselo a quien administra Finnegans."
    )


import pytest

from finnegans_core.permisos import MapaPermisos, clave_permiso


@pytest.mark.parametrize("path", ["cliente", "/cliente/2956", "api/cliente/list", "/api/Cliente"])
def test_clave_de_entidad(path):
    assert clave_permiso(path) == "cliente"


@pytest.mark.parametrize("path", ["reports/ACOrdenes", "/api/Reports/acordenes", "/reports/ACOrdenes/"])
def test_clave_de_reporte(path):
    assert clave_permiso(path) == "reports/acordenes"


@pytest.mark.parametrize("path", ["", "/", "/api", "/api/"])
def test_clave_de_path_vacio(path):
    assert clave_permiso(path) is None


def test_escaneo_reemplaza_lo_suyo_y_conserva_lo_demas():
    m = MapaPermisos()
    m.aplicar_escaneo({"cliente": ("permitido", "entidad"), "reports/x": ("denegado", "reporte")}, "2026-11-17")
    m.corregir("reports/y", "denegado")
    m.marcar_escritura_denegada("cliente")
    m.aplicar_escaneo({"cliente": ("permitido", "entidad")}, "2026-11-18")
    assert m.denegado("reports/x") and m.denegado("reports/y")
    assert m.solo_lectura("cliente/1") and m.estado == "listo" and m.version == 2
    assert m.escaneo_fin == "2026-11-18"


def test_corregir_marca_uso_y_no_cambia_version():
    m = MapaPermisos()
    m.aplicar_escaneo({"cliente": ("permitido", "entidad")}, "2026-11-17")
    assert m.corregir("/cliente/5", "denegado") is True
    assert m.entradas["cliente"].fuente == "uso"
    assert m.acceso("cliente") == "denegado"
    assert m.version == 1
    assert m.corregir("cliente", "denegado") is False
    assert m.corregir("", "denegado") is False


def test_marcar_escritura_denegada_no_cambia_version():
    m = MapaPermisos()
    assert m.marcar_escritura_denegada("cliente/1") is True
    assert m.marcar_escritura_denegada("cliente") is False
    assert m.version == 0 and m.solo_lectura("cliente")


def test_acceso_de_lo_no_mapeado_es_none():
    m = MapaPermisos()
    assert m.acceso("cliente") is None and m.acceso("") is None
    assert not m.denegado("cliente") and not m.solo_lectura("cliente")


def test_resumen_cuenta_desconocido_como_permitido():
    m = MapaPermisos()
    m.aplicar_escaneo({"a": ("permitido", "entidad"), "b": ("desconocido", "entidad"),
                       "reports/r": ("denegado", "reporte")}, "2026-11-17")
    assert m.resumen() == (0, 1, 2, 2)


def test_ida_y_vuelta_a_dict():
    m = MapaPermisos()
    m.aplicar_escaneo({"cliente": ("denegado", "entidad")}, "2026-11-17")
    m.marcar_escritura_denegada("x")
    d = m.a_dict()
    assert d["escritura_denegada"] == ["x"]
    assert MapaPermisos.desde_dict(d) == m


# ------------------------------------------------------------ fachada Permisos

import threading
from datetime import date

from finnegans_core.almacen_permisos import AlmacenMemoria
from finnegans_core.permisos import Permisos


class AlmacenContador(AlmacenMemoria):
    """AlmacenMemoria que cuenta los guardados."""

    def __init__(self) -> None:
        super().__init__()
        self.guardados = 0

    def guardar(self, mapa: MapaPermisos) -> None:
        self.guardados += 1
        super().guardar(mapa)


def _almacen_con(resultado, estado=None, cuando="2026-11-17") -> AlmacenContador:
    almacen = AlmacenContador()
    mapa = almacen.cargar()
    mapa.aplicar_escaneo(resultado, cuando)
    if estado is not None:
        mapa.estado = estado
    return almacen


def test_estado_texto_con_numeros():
    almacen = _almacen_con({
        "reports/a": ("permitido", "reporte"),
        "reports/b": ("desconocido", "reporte"),
        "reports/c": ("denegado", "reporte"),
        "cliente": ("permitido", "entidad"),
        "proveedor": ("denegado", "entidad"),
    })
    p = Permisos(almacen)
    assert p.estado_texto(hoy=date(2026, 11, 17)) == (
        "Permisos revisados el 17/11: 2 de 3 reportes y 1 de 2 entidades disponibles"
    )


def test_estado_texto_de_cada_estado():
    assert Permisos(AlmacenMemoria()).estado_texto() == "Permisos: todavía no se revisaron"
    fallo = Permisos(_almacen_con({"cliente": ("denegado", "entidad")}, estado="fallo"))
    assert fallo.estado_texto() == "Permisos: la última revisión falló; se usa la anterior"


def test_mapa_guardado_escaneando_carga_sin_escanear_y_no_oculta():
    p = Permisos(_almacen_con({"cliente": ("denegado", "entidad")}, estado="escaneando"))
    assert p.estado == "sin_escanear"
    assert p.estado_texto() == "Permisos: todavía no se revisaron"
    assert not p.denegado("cliente")


def test_listo_y_fallo_usan_el_escaneo():
    assert Permisos(_almacen_con({"cliente": ("denegado", "entidad")})).denegado("cliente/list")
    p = Permisos(_almacen_con({"cliente": ("denegado", "entidad")}, estado="fallo"))
    assert p.denegado("/api/Cliente/2956")


def test_lo_aprendido_por_uso_cuenta_sin_escaneo():
    p = Permisos(AlmacenMemoria())
    p.registrar_lectura("reports/X", ok=False)
    p.registrar_escritura_denegada("cliente/2956")
    assert p.estado == "sin_escanear"
    assert p.denegado("/reports/x")
    assert p.solo_lectura("Cliente")
    assert not p.solo_lectura("proveedor")


def test_registrar_lectura_corrige_y_guarda_solo_si_cambia():
    almacen = _almacen_con({"cliente": ("denegado", "entidad"),
                            "proveedor": ("permitido", "entidad")})
    p = Permisos(almacen)
    p.registrar_lectura("proveedor/list", ok=True)  # ya permitido
    p.registrar_lectura("pedido", ok=True)  # no mapeado: no se agrega
    assert almacen.guardados == 0
    p.registrar_lectura("cliente/list", ok=True)
    assert not p.denegado("cliente")
    assert almacen.guardados == 1
    p.registrar_lectura("cliente", ok=False)
    p.registrar_lectura("cliente", ok=False)
    assert p.denegado("cliente")
    assert almacen.guardados == 2
    p.registrar_escritura_denegada("cliente")
    p.registrar_escritura_denegada("cliente")
    assert almacen.guardados == 3


def test_escaneo_en_segundo_plano_no_se_duplica_y_aplica():
    almacen = AlmacenContador()
    p = Permisos(almacen)
    liberar = threading.Event()

    def hacer():
        assert liberar.wait(5)
        return {"cliente": ("denegado", "entidad")}

    assert p.escanear_en_segundo_plano(hacer)
    try:
        assert p.estado == "escaneando"
        assert p.estado_texto() == "Permisos: todavía revisando"
        assert not p.escanear_en_segundo_plano(hacer)
    finally:
        liberar.set()
    assert p.esperar_escaneo(5)
    assert p.estado == "listo"
    assert p.denegado("cliente")
    assert almacen.guardados == 1
    assert p.estado_texto().startswith("Permisos revisados el ")


def test_escaneo_que_falla_conserva_el_mapa():
    almacen = _almacen_con({"cliente": ("denegado", "entidad")})
    p = Permisos(almacen)

    def hacer():
        raise RuntimeError("se cayo la red")

    assert p.escanear_en_segundo_plano(hacer)
    assert p.esperar_escaneo(5)
    assert p.estado == "fallo"
    assert p.denegado("cliente")
    assert almacen.guardados == 1
    assert almacen.cargar().estado == "fallo"
    # Despues de un fallo se puede volver a escanear.
    assert p.escanear_en_segundo_plano(lambda: {"cliente": ("permitido", "entidad")})
    assert p.esperar_escaneo(5)
    assert not p.denegado("cliente")


def test_problema_almacen_se_reenvia():
    almacen = AlmacenMemoria()
    p = Permisos(almacen)
    assert p.problema_almacen is None
    almacen.problema = "No pude guardar"
    assert p.problema_almacen == "No pude guardar"


def test_esperar_escaneo_sin_escaneo_es_inmediato():
    assert Permisos(AlmacenMemoria()).esperar_escaneo(0)
