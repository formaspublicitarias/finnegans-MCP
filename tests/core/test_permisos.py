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
