#!/usr/bin/env python
"""Wartet auf den Kaggle-Kernel und holt das Ergebnis ab.

Laeuft als Hintergrundprozess: prueft alle 60 s den Status, laedt bei Ende die
Ausgabedateien nach C:\\Users\\amer7\\omx-kaggle\\<run> und schreibt eine
Zusammenfassung. Kein Klicken im Browser noetig.
"""
import json
import sys
import time
import traceback
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

REF = "amersacirovic/openamer-max-vl-8b-qlora"
OUT = Path(r"C:\Users\amer7\omx-kaggle")
TERMINAL = {"COMPLETE", "ERROR", "CANCEL_ACKNOWLEDGED", "CANCELED"}

api = KaggleApi()
api.authenticate()
OUT.mkdir(parents=True, exist_ok=True)
print(f"[{time.strftime('%H:%M:%S')}] beobachte {REF}", flush=True)

last = None
for i in range(180):                      # max. 3 Stunden
    try:
        s = json.loads(api.kernels_status(REF))
        st = s.get("status")
        if st != last:
            print(f"[{time.strftime('%H:%M:%S')}] Status: {st} "
                  f"{s.get('failureMessage') or ''}", flush=True)
            last = st
        if st in TERMINAL:
            break
    except Exception as exc:
        print(f"[{time.strftime('%H:%M:%S')}] Statusfehler: {type(exc).__name__} {exc}", flush=True)
    time.sleep(60)

print(f"[{time.strftime('%H:%M:%S')}] Endstatus: {last}", flush=True)
try:
    api.kernels_output(REF, path=str(OUT), force=True)
    print("Ausgabe geladen:", flush=True)
    total = 0
    for p in sorted(OUT.rglob("*")):
        if p.is_file():
            total += 1
            print(f"   {p.relative_to(OUT)}  {p.stat().st_size/1e6:.2f} MB", flush=True)
    print(f"{total} Dateien in {OUT}", flush=True)
except Exception:
    traceback.print_exc()
    print("Ausgabe konnte nicht geladen werden (Kernel evtl. abgebrochen)", flush=True)
sys.exit(0 if last == "COMPLETE" else 1)
