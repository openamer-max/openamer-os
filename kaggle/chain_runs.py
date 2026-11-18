#!/usr/bin/env python
"""Kette: Smoke pruefen -> Full starten -> Ergebnis abholen.

Kaggle erlaubt nur 2 GPU-Sitzungen. Statt manuell zu warten, verkettet dieses
Skript die Reihenfolge: erst den Smoke (25 Schritte, Bilder zuerst) bis zum Ende,
nur bei COMPLETE den echten Lauf starten, dann beide Ausgaben nach
C:\\Users\\amer7\\omx-kaggle\\<lauf> holen und report.json ausgeben.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

KAGGLE = Path(r"C:\Users\amer7\openamer-agent-max\kaggle")
OUT = Path(r"C:\Users\amer7\omx-kaggle")
SMOKE = "amersacirovic/openamer-max-vl-8b-qlora"
FULL = "amersacirovic/openamer-max-vl-8b-qlora-full"
TERMINAL = {"COMPLETE", "ERROR", "CANCELED", "CANCEL_ACKNOWLEDGED"}

api = KaggleApi()
api.authenticate()


def st(ref: str) -> str:
    return str(getattr(api.kernels_status(ref), "status")).split(".")[-1]


def weiter(smoke_status: str) -> bool:
    """Den echten Lauf nur starten, wenn der Smoke sauber durch ist.

    ERROR/TIMEOUT heisst: die Pipeline ist nicht bewiesen. Dann 3 Epochen auf einer
    Gratis-GPU zu verbrennen, waere teuer und wuerde nichts zeigen.
    """
    return smoke_status == "COMPLETE"


def warte(ref: str, max_min: int = 90) -> str:
    letzte = None
    for _ in range(max_min * 2):
        s = st(ref)
        if s != letzte:
            print(f"[{time.strftime('%H:%M:%S')}] {ref.split('/')[-1]}: {s}", flush=True)
            letzte = s
        if s in TERMINAL:
            return s
        time.sleep(30)
    return f"TIMEOUT:{letzte}"


def hole(ref: str) -> None:
    ziel = OUT / ref.split("/")[-1]
    ziel.mkdir(parents=True, exist_ok=True)
    try:
        api.kernels_output(ref, path=str(ziel), force=True)
        print(f"  Ausgabe -> {ziel}", flush=True)
    except Exception as exc:
        print(f"  Ausgabe nicht abholbar: {type(exc).__name__} {exc}", flush=True)
        return
    for rep in ziel.rglob("report.json"):
        print("  BERICHT:", rep.read_text(encoding="utf-8").replace("\n", " ")[:400], flush=True)
        return
    print("  kein report.json im Ergebnis", flush=True)


print("=== 1. Smoke bis Ende ===", flush=True)
s = warte(SMOKE)
hole(SMOKE)
if not weiter(s):
    print(f"ABBRUCH: Smoke endete mit {s} — kein Full-Lauf gestartet", flush=True)
    sys.exit(1)

print("\n=== 2. Full-Lauf starten ===", flush=True)
for versuch in range(10):
    p = subprocess.run([sys.executable, str(KAGGLE / "push_run.py"), "--mode", "full",
                        "--epochs", "3"], cwd=str(KAGGLE), capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": r"C:\Users\amer7\pylibs"}, timeout=600)
    out = (p.stdout or "") + (p.stderr or "")
    print(f"  Versuch {versuch + 1}: {out.strip().splitlines()[-1][:160]}", flush=True)
    if '"error": null' in out:
        break
    time.sleep(60)

print("\n=== 3. Full bis Ende ===", flush=True)
s = warte(FULL, max_min=300)          # 3 Epochen: bis 5 Stunden
hole(FULL)
print(f"\nENDE: Smoke+Full durch, Full-Status {s}", flush=True)
sys.exit(0 if s == "COMPLETE" else 1)
