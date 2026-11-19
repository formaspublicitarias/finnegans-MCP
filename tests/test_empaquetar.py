"""El script que arma el paquete precarga la clave del swagger solo en la copia."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
CLAVE = "swkey-falsa-7g8h9i"


def _cargar():
    spec = importlib.util.spec_from_file_location("empaquetar", RAIZ / "scripts" / "empaquetar.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_armar_carpeta_precarga_la_clave_solo_en_la_copia(tmp_path):
    empaquetar = _cargar()
    antes = (RAIZ / "manifest.json").read_bytes()
    destino = empaquetar.armar_carpeta(RAIZ, tmp_path / "copia", CLAVE)
    copia = json.loads((destino / "manifest.json").read_text(encoding="utf-8"))
    assert copia["user_config"]["swagger_key"]["default"] == CLAVE
    assert copia["user_config"]["swagger_key"]["required"] is False
    assert (RAIZ / "manifest.json").read_bytes() == antes


def test_armar_carpeta_respeta_mcpbignore(tmp_path):
    empaquetar = _cargar()
    destino = empaquetar.armar_carpeta(RAIZ, tmp_path / "copia", CLAVE)
    for carpeta in ("tests", "docs", "scripts"):
        assert not (destino / carpeta).exists(), carpeta
    assert (destino / "src" / "finnegans_mcp" / "server.py").is_file()
    assert not list(destino.rglob("*.pyc"))


def test_main_sin_clave_se_niega(monkeypatch, capsys):
    empaquetar = _cargar()
    monkeypatch.delenv("FINNEGANS_SWAGGER_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["empaquetar.py"])
    with pytest.raises(SystemExit) as salida:
        empaquetar.main()
    assert salida.value.code not in (0, None)
    assert "Falta FINNEGANS_SWAGGER_KEY en el entorno." in (lambda c: c.out + c.err)(capsys.readouterr())
