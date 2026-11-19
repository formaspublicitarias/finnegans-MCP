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
