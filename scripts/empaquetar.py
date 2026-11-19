"""Arma el instalable finnegans.mcpb con la clave del swagger ya cargada.

Uso:
    FINNEGANS_SWAGGER_KEY=... uv run python scripts/empaquetar.py [--salida finnegans.mcpb]

La clave sale SOLO de la variable de entorno (nunca de un archivo) y se escribe
solo en la copia temporal que se empaqueta: el manifest.json del repo no se toca
y el script nunca imprime la clave.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _leer_patrones(raiz: Path) -> list[str]:
    archivo = raiz / ".mcpbignore"
    if not archivo.is_file():
        return []
    patrones = []
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#"):
            patrones.append(linea)
    return patrones


def _ignorado(ruta: str, patrones: list[str]) -> bool:
    """Equivalente simple a gitignore: ruta relativa con '/', sin negaciones."""
    partes = ruta.split("/")
    for patron in patrones:
        solo_carpeta = patron.endswith("/")
        base = patron.rstrip("/")
        anclado = base.startswith("/") or "/" in base
        base = base.lstrip("/")
        if anclado:
            # Ancla a la raiz: coincide con la ruta o con alguna carpeta madre.
            hasta = len(partes) - 1 if solo_carpeta else len(partes)
            for n in range(1, hasta + 1):
                if fnmatch.fnmatchcase("/".join(partes[:n]), base):
                    return True
        else:
            # Sin barra: coincide con cualquier componente (carpetas, y el
            # archivo mismo salvo que el patron sea solo de carpeta).
            candidatos = partes[:-1] if solo_carpeta else partes
            if any(fnmatch.fnmatchcase(p, base) for p in candidatos):
                return True
    return False


def _archivos_versionados(raiz: Path) -> list[str]:
    salida = subprocess.run(
        ["git", "ls-files", "-z"], cwd=raiz, check=True, capture_output=True
    ).stdout.decode("utf-8")
    return [r for r in salida.split("\0") if r]


def armar_carpeta(raiz: Path, destino: Path, swagger_key: str) -> Path:
    """Copia a `destino` lo que va en el paquete y precarga la clave del swagger."""
    raiz, destino = Path(raiz), Path(destino)
    patrones = _leer_patrones(raiz)
    destino.mkdir(parents=True, exist_ok=True)
    for ruta in _archivos_versionados(raiz):
        origen = raiz / ruta
        if _ignorado(ruta, patrones) or not origen.is_file():
            continue
        salida = destino / ruta
        salida.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, salida)

    manifest = destino / "manifest.json"
    datos = json.loads(manifest.read_text(encoding="utf-8"))
    clave = datos["user_config"]["swagger_key"]
    clave["default"] = swagger_key
    clave["required"] = False
    manifest.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destino


def main() -> int:
    parser = argparse.ArgumentParser(description="Arma finnegans.mcpb con la clave del swagger precargada.")
    parser.add_argument("--salida", default="finnegans.mcpb", help="archivo a generar")
    args = parser.parse_args()

    swagger_key = os.environ.get("FINNEGANS_SWAGGER_KEY", "").strip()
    if not swagger_key:
        print("Falta FINNEGANS_SWAGGER_KEY en el entorno.", file=sys.stderr)
        raise SystemExit(1)

    with tempfile.TemporaryDirectory() as tmp:
        carpeta = armar_carpeta(RAIZ, Path(tmp) / "paquete", swagger_key)
        comando = ["npx", "@anthropic-ai/mcpb", "pack", str(carpeta), str(Path(args.salida).resolve())]
        # shell=True en Windows: npx es un .cmd.
        resultado = subprocess.run(comando, shell=(os.name == "nt"))
    if resultado.returncode != 0:
        print("No se pudo generar el paquete.", file=sys.stderr)
        return resultado.returncode
    print(f"Paquete generado: {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
