#!/usr/bin/env python3
"""Baut aus einem Ollama-Manifest ein gueltiges Modelfile.

Hintergrund (gemessen am 17.11.2026): Ollama 0.40.16 verwirft Manifeste, die es
nicht beschreiben kann, still aus der Modellliste ("failed to describe model").
Die Blobs bleiben liegen, das Modell ist aber unsichtbar. `ollama create` aus
dem vorhandenen GGUF-Blob erzeugt ein frisches Manifest im erwarteten Format —
ohne Download, ohne Neuantwort.

Benutzung:
    python rebuild_from_manifest.py <name>            # Modelfile schreiben
    python rebuild_from_manifest.py <name> --create   # zusaetzlich ollama create

Beispiel:
    python rebuild_from_manifest.py openamer-max-tab --create
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Ollama-Speicher: OLLAMA_MODELS hat Vorrang. In WSL zeigt der Dienst oft auf
# den Windows-Pfad (/mnt/c/...), deshalb werden beide Orte geprueft.
MODELS = Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama" / "models"))
_EXTRA = [Path(p) for p in (
    "/mnt/c/Users/amer7/.ollama/models",
    "/mnt/c/Users/amer7/manifests-v2",
) if Path(p).is_dir()]

MANIFEST_ROOTS = []
for _m in [MODELS, *_EXTRA]:
    MANIFEST_ROOTS += [
        _m / "manifests-v2" / "ollama.com",
        _m / "manifests" / "registry.ollama.ai",
        _m / "manifests-v2",
        _m / "manifests",
    ]
MANIFEST_ROOTS = [p for p in MANIFEST_ROOTS if p.is_dir()]
OUT = Path(__file__).resolve().parent


def find_manifest(name: str, tag: str = "latest") -> Path:
    for root in MANIFEST_ROOTS:
        for ns in root.iterdir() if root.is_dir() else []:
            cand = ns / name / tag
            if cand.is_file():
                return cand
    raise FileNotFoundError(f"Manifest fuer {name}:{tag} nicht gefunden in {MANIFEST_ROOTS}")


def _blobs_for(man: Path) -> Path:
    """Findet den Blob-Ordner, der zu diesem Manifest gehoert.

    Gemessen (17.11.2026): Manifest und Blobs muessen zusammenpassen. In WSL
    zeigte der Dienst auf /mnt/c/.../models — die Blobs lagen dort, waehrend
    MODELS auf ~/.ollama/models zeigte. Ergebnis: FileNotFoundError.
    """
    for parent in man.parents:
        if (parent / "blobs").is_dir():
            return parent / "blobs"
    return MODELS / "blobs"


def build(name: str, tag: str = "latest") -> Path:
    man = find_manifest(name, tag)
    d = json.loads(man.read_text(encoding="utf-8"))
    blobs = _blobs_for(man)
    model = system = params = template = None
    license_txt = None
    for layer in d.get("layers", []):
        p = blobs / layer["digest"].replace(":", "-")
        kind = layer["mediaType"].split(".")[-1]
        if kind == "model":
            model = p
        elif kind == "system":
            system = p.read_text(encoding="utf-8")
        elif kind == "params":
            params = p.read_text(encoding="utf-8")
        elif kind == "template":
            template = p.read_text(encoding="utf-8")
        elif kind == "license":
            license_txt = p.read_text(encoding="utf-8", errors="replace")

    if model is None:
        raise ValueError("kein Modell-Layer im Manifest")

    out: list[str] = [f"FROM {model}", ""]
    if license_txt:
        out += ['LICENSE """' + license_txt + '"""', ""]
    if template:
        out += ['TEMPLATE """' + template + '"""', ""]
    if system:
        out += ['SYSTEM """' + system + '"""', ""]

    if params:
        try:
            obj = json.loads(params)
        except json.JSONDecodeError:
            out += [params.strip(), ""]
        else:
            for k, v in obj.items():
                if isinstance(v, list):
                    for item in v:
                        if k == "stop":
                            out.append(f'PARAMETER stop "{item}"')
                        else:
                            out.append(f"PARAMETER {k} {item}")
                else:
                    out.append(f"PARAMETER {k} {v}")
            out.append("")

    mf = OUT / f"Modelfile.{name}"
    mf.write_text("\n".join(out), encoding="utf-8")
    return mf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="Modellname ohne Namespace, z. B. openamer-max-tab")
    ap.add_argument("--tag", default="latest")
    ap.add_argument("--create", action="store_true", help="ollama create ausfuehren")
    ap.add_argument("--as", dest="as_name", default=None, help="Zielname beim Anlegen")
    a = ap.parse_args()

    mf = build(a.name, a.tag)
    print(f"Modelfile: {mf} ({mf.stat().st_size} B)")
    if not a.create:
        return 0
    target = a.as_name or a.name
    r = subprocess.run(["ollama", "create", target, "-f", str(mf)],
                       capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0:
        return r.returncode
    print(f"[ok] {target} neu angelegt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
