import os
import sys

from finnegans_core.almacen_permisos import AlmacenLocal, AlmacenMemoria, carpeta_datos
from finnegans_core.permisos import MapaPermisos

CID = "cid-falso-1a2b3c"


def _mapa() -> MapaPermisos:
    m = MapaPermisos()
    m.aplicar_escaneo({"cliente": ("denegado", "entidad"), "reports/x": ("permitido", "reporte")}, "2026-11-17")
    m.marcar_escritura_denegada("articulo")
    return m


def test_guarda_y_carga(tmp_path):
    m = _mapa()
    AlmacenLocal(tmp_path, CID).guardar(m)
    assert AlmacenLocal(tmp_path, CID).cargar() == m


def test_archivo_sin_secretos_en_nombre_ni_contenido(tmp_path):
    AlmacenLocal(tmp_path, CID).guardar(_mapa())
    archivos = list(tmp_path.iterdir())
    assert archivos
    for a in archivos:
        assert CID not in a.name
        assert CID not in a.read_text(encoding="utf-8")


def test_otro_client_id_otro_mapa(tmp_path):
    AlmacenLocal(tmp_path, CID).guardar(_mapa())
    assert AlmacenLocal(tmp_path, "otro").cargar().entradas == {}


def test_client_id_con_espacios_usa_el_mismo_archivo(tmp_path):
    AlmacenLocal(tmp_path, CID).guardar(_mapa())
    assert AlmacenLocal(tmp_path, f"  {CID} ").cargar() == _mapa()


def test_archivo_faltante_da_mapa_vacio(tmp_path):
    assert AlmacenLocal(tmp_path, CID).cargar() == MapaPermisos()


def test_archivo_corrupto_da_mapa_vacio(tmp_path):
    al = AlmacenLocal(tmp_path, CID)
    al.guardar(_mapa())
    (archivo,) = tmp_path.iterdir()
    archivo.write_text("{no json", encoding="utf-8")
    assert al.cargar() == MapaPermisos()


def test_json_con_forma_invalida_da_mapa_vacio(tmp_path):
    al = AlmacenLocal(tmp_path, CID)
    al.guardar(_mapa())
    (archivo,) = tmp_path.iterdir()
    archivo.write_text('{"entradas": {"a": {"acceso": "x"}}}', encoding="utf-8")
    assert al.cargar() == MapaPermisos()


def test_carpeta_no_escribible_no_rompe(tmp_path, monkeypatch):
    def falla(*a, **k):
        raise PermissionError("denegado")

    monkeypatch.setattr(os, "replace", falla)
    al = AlmacenLocal(tmp_path, CID)
    al.guardar(_mapa())
    assert al.problema is not None and al.problema.startswith("No pude guardar")


def test_guardado_exitoso_limpia_el_problema(tmp_path, monkeypatch):
    al = AlmacenLocal(tmp_path, CID)
    with monkeypatch.context() as mc:
        mc.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        al.guardar(_mapa())
    assert al.problema
    al.guardar(_mapa())
    assert al.problema is None


def test_escritura_atomica_no_deja_tmp(tmp_path):
    AlmacenLocal(tmp_path, CID).guardar(_mapa())
    assert not list(tmp_path.glob("*.tmp"))


def test_almacen_memoria_guarda_y_carga():
    al = AlmacenMemoria()
    assert al.cargar() == MapaPermisos() and al.problema is None
    m = _mapa()
    al.guardar(m)
    assert al.cargar() == m


def test_carpeta_datos_nunca_es_la_real_en_tests(tmp_path):
    # El fixture autouse redirige LOCALAPPDATA y XDG_DATA_HOME a tmp_path.
    assert carpeta_datos().name in ("Finnegans", "finnegans")
    if sys.platform != "darwin":
        assert tmp_path in carpeta_datos().parents
