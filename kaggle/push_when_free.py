#!/usr/bin/env python
"""Wartet auf einen freien GPU-Platz und pusht dann die korrigierten Laeufe.

Kaggle erlaubt 2 gleichzeitige GPU-Sitzungen. Die alten Versionen (ohne
pixel_values-Fix) sterben am ersten Bild; dieser Helfer wartet darauf und
startet dann Smoke v3 und Full v3.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

KAGGLE = Path(r"C:\Users\amer7\openamer-agent-max\kaggle")
REFS = ("amersacirovic/openamer-max-vl-8b-qlora",
        "amersacirovic/openamer-max-vl-8b-qlora-full")
ACTIVE = {"RUNNING", "QUEUED", "PENDING"}

api = KaggleApi()
api.authenticate()


def stati() -> dict[str, str]:
    out = {}
    for r in REFS:
        try:
            out[r] = str(getattr(api.kernels_status(r), "status")).split(".")[-1]
        except Exception as exc:
            out[r] = f"FEHLER:{type(exc).__name__}"
    return out


print(f"[{time.strftime('%H:%M:%S')}] warte auf freien GPU-Platz ...", flush=True)
frei = False
for _ in range(120):                      # max. 60 Minuten
    s = stati()
    aktiv = sum(1 for v in s.values() if v in ACTIVE)
    print(f"[{time.strftime('%H:%M:%S')}] aktiv={aktiv} {json.dumps(s)}", flush=True)
    if aktiv < 2:
        frei = True
        break
    time.sleep(30)

if not frei:
    print("ABBRUCH: nach 60 Minuten kein Platz frei", flush=True)
    sys.exit(1)

for mode, extra in (("smoke", []), ("full", ["--epochs", "3"])):
    cmd = [sys.executable, str(KAGGLE / "push_run.py"), "--mode", mode] + extra
    p = subprocess.run(cmd, cwd=str(KAGGLE), capture_output=True, text=True,
                       env={**__import__("os").environ, "PYTHONPATH": r"C:\Users\amer7\pylibs"},
                       timeout=600)
    out = (p.stdout or "") + (p.stderr or "")
    print(f"--- push {mode}: rc={p.returncode}", flush=True)
    print(out.strip()[-400:], flush=True)
    time.sleep(20)

print(f"[{time.strftime('%H:%M:%S')}] Endstand: {json.dumps(stati())}", flush=True)
