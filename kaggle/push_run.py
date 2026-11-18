#!/usr/bin/env python
"""Startet einen Kaggle-Lauf aus einer einzigen Quelle (train.py).

Zwei Modi:
  smoke  — wenige Schritte, harte Abbruchbedingung (25 Schritte)
  full   — echte Epochen (Standard 3) ueber den ganzen Satz

Warum ein Generator statt zwei Kopien: die Kernel-Upload enthaelt nur Dateien
ihres eigenen Ordners. Zwei Kopien von train.py driften auseinander, sobald man
einen Fehler nur an einer Stelle korrigiert. Hier wird die eine Quelle gelesen,
der Epochen-Default ersetzt und nach `build/<modus>/` geschrieben.

Aufruf:
    python push_run.py --mode smoke
    python push_run.py --mode full --epochs 3
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

HERE = Path(__file__).resolve().parent
SRC = HERE / "vl-8b-qlora" / "train.py"
BUILD = HERE / "build"
OWNER = "amersacirovic"
SLUGS = {"smoke": "openamer-max-vl-8b-qlora",
         "full": "openamer-max-vl-8b-qlora-full"}
TITLES = {"smoke": "openamer-max-vl-8b-qlora",
          "full": "openamer-max-vl-8b-qlora-full"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--seq", type=int, default=1024)
    a = ap.parse_args()

    code = SRC.read_text(encoding="utf-8")
    # Defaults in der Quelle ersetzen — sonst muesste man zwei Dateien pflegen
    epochs = a.epochs if a.mode == "full" else 0
    code = re.sub(r'MAX_STEPS = int\(os\.environ\.get\("OM_STEPS", "\d+"\)\)',
                  f'MAX_STEPS = int(os.environ.get("OM_STEPS", "{a.steps}"))', code)
    code = re.sub(r'EPOCHS = float\(os\.environ\.get\("OM_EPOCHS", "[\d.]+"\)\)',
                  f'EPOCHS = float(os.environ.get("OM_EPOCHS", "{epochs}"))', code)
    code = re.sub(r'SEQ = int\(os\.environ\.get\("OM_SEQ", "\d+"\)\)',
                  f'SEQ = int(os.environ.get("OM_SEQ", "{a.seq}"))', code)
    if f'"{a.steps}"' not in code or f'"{epochs}"' not in code:
        print("ABBRUCH: Defaults konnten nicht ersetzt werden (Quelle geaendert?)")
        return 2

    out = BUILD / a.mode
    out.mkdir(parents=True, exist_ok=True)
    (out / "train.py").write_text(code, encoding="utf-8")
    meta = {
        "id": f"{OWNER}/{SLUGS[a.mode]}",
        "title": TITLES[a.mode],
        "code_file": "train.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": False,
        "enable_gpu": True,
        "enable_internet": True,
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (out / "kernel-metadata.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")

    modus = f"{epochs} Epochen" if epochs else f"{a.steps} Schritte"
    print(f"Quelle: {SRC.relative_to(HERE)} -> {out.relative_to(HERE)}  ({modus}, seq {a.seq})")
    api = KaggleApi()
    api.authenticate()
    res = api.kernels_push(str(out))
    print("PUSH:", json.dumps(res) if isinstance(res, dict) else res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
