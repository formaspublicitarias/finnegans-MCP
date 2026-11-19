"""Fixtures compartidos de la suite."""


import pytest

from finnegans_core.catalogo.swagger import limpiar_caches


@pytest.fixture(autouse=True)
def _limpiar_caches_swagger():
    """Los caches del swagger son por proceso: cada test arranca limpio."""
    limpiar_caches()
    yield
    limpiar_caches()


@pytest.fixture(autouse=True)
def _datos_de_app_aislados(tmp_path, monkeypatch):
    """Ningun test escribe en la carpeta de datos real de la app."""
    datos = tmp_path / "datos-de-app"
    monkeypatch.setenv("LOCALAPPDATA", str(datos))
    monkeypatch.setenv("XDG_DATA_HOME", str(datos))
