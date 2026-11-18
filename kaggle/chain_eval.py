#!/usr/bin/env python
"""Kette Etappe 3+7: auf das Training warten, dann den Adapter messen.

Warum als Kette: Kaggle erlaubt 2 GPU-Sitzungen, und die Auswertung braucht den
fertigen Adapter aus dem Trainings-Kernel. Manuelles Nachfassen kostet jedes Mal
eine Wartezeit — hier laeuft es in einem Zug durch.

Aufruf:  python chain_eval.py [--epochs N]     (ohne --epochs: kein neuer Trainingslauf)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from kaggle.api.kaggle_api_extended import KaggleApi

KAGGLE = Path(__file__).resolve().parent
REPO = KAGGLE.parent
OUT = Path(r"C:\Users\amer7\omx-kaggle")
TRAIN = "amersacirovic/openamer-max-vl-8b-qlora-full"
EVAL = "amersacirovic/openamer-max-vl-8b-eval"
KANDIDAT = "openamer-max-vl-8b-kandidat"     # Bauname: nicht in start.sh
ZIEL_NAME = "openamer-max-vl-8b"             # dieser Name wird Standard
BASIS_MODELL = "openamer-max-7b"             # laufender Standard
TERMINAL = {"COMPLETE", "ERROR", "CANCELED", "CANCEL_ACKNOWLEDGED"}

api = KaggleApi()
api.authenticate()


def st(ref: str) -> str:
    return str(getattr(api.kernels_status(ref), "status")).split(".")[-1]


def warte(ref: str, max_min: int) -> str:
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


def hole(ref: str) -> Path:
    ziel = OUT / ref.split("/")[-1]
    ziel.mkdir(parents=True, exist_ok=True)
    try:
        api.kernels_output(ref, path=str(ziel), force=True)
    except Exception as exc:
        print(f"  Ausgabe nicht abholbar: {type(exc).__name__} {exc}", flush=True)
    return ziel


def baue_und_entscheide(adapter: Path) -> bool:
    """Adapter zu Ollama-Modell bauen und nur bei besserem Ergebnis uebernehmen.

    Der Kandidat bekommt bewusst einen eigenen Namen: ein Modell, das auf dem
    Pruefsatz schlechter ist als das laufende, darf nicht Standard werden
    (gemessen 18.11.2026: 8B mit 25-Schritt-Adapter 18/24 gegen 7B 22/24).
    """
    env = {**os.environ, "PYTHONPATH": r"C:\Users\amer7\pylibs",
           "OMX_8B_NAME": KANDIDAT, "OMX_8B_ADAPTER": str(adapter)}
    print(f"\n=== 4. Modell bauen ({KANDIDAT}) ===", flush=True)
    p = subprocess.run([sys.executable, str(REPO / "tools" / "integrate_8b.py")],
                       cwd=str(REPO), capture_output=True, text=True, env=env, timeout=14400)
    print(((p.stdout or "") + (p.stderr or "")).strip()[-600:], flush=True)
    if p.returncode != 0:
        print("ABBRUCH: Bau fehlgeschlagen", flush=True)
        return False

    print("\n=== 5. Uebernahme messen ===", flush=True)
    v = subprocess.run([sys.executable, str(REPO / "tools" / "vergleich.py"),
                        "--neu", KANDIDAT, "--alt", BASIS_MODELL],
                       cwd=str(REPO), capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": r"C:\Users\amer7\pylibs"}, timeout=7200)
    print(((v.stdout or "") + (v.stderr or "")).strip()[-400:], flush=True)
    if v.returncode != 0:
        print(f"ENTSCHEID: {KANDIDAT} ist nicht besser — {BASIS_MODELL} bleibt Standard", flush=True)
        return False

    print(f"ENTSCHEID: {KANDIDAT} ist besser — wird als {ZIEL_NAME} uebernommen", flush=True)
    for cmd in (["ollama", "rm", ZIEL_NAME], ["ollama", "cp", KANDIDAT, ZIEL_NAME]):
        subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    liste = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
    print(f"  -> {ZIEL_NAME} registriert: {ZIEL_NAME in liste}", flush=True)
    return ZIEL_NAME in liste


def main() -> int:
    if "--epochs" in sys.argv:
        epochen = sys.argv[sys.argv.index("--epochs") + 1]
        p = subprocess.run([sys.executable, str(KAGGLE / "push_run.py"), "--mode", "full",
                            "--epochs", epochen], cwd=str(KAGGLE), capture_output=True,
                           text=True, env={**os.environ, "PYTHONPATH": r"C:\Users\amer7\pylibs"},
                           timeout=600)
        print((p.stdout or "").strip()[-200:], flush=True)
        time.sleep(30)

    print("=== 1. Training abwarten ===", flush=True)
    s = warte(TRAIN, 300)
    if s != "COMPLETE":
        print(f"ABBRUCH: Training endete mit {s} — keine Messung", flush=True)
        hole(TRAIN)
        return 1
    ziel = hole(TRAIN)
    reports = list(ziel.rglob("report.json"))
    if reports:
        r = json.loads(reports[0].read_text(encoding="utf-8"))
        print(f"  Training: {r.get('schritte')} Schritte · Loss {r.get('training_loss')} · "
              f"VRAM {r.get('vram_spitze_gib')} GiB · {r.get('dauer_min')} min", flush=True)

    print("\n=== 2. Auswertung starten ===", flush=True)
    for versuch in range(6):
        try:
            res = api.kernels_push(str(KAGGLE / "vl-8b-eval"))
            print(f"  PUSH: {str(res)[:160]}", flush=True)
            break
        except Exception as exc:
            print(f"  Versuch {versuch + 1}: {type(exc).__name__} {str(exc)[:90]}", flush=True)
            time.sleep(90)

    print("\n=== 3. Auswertung abwarten ===", flush=True)
    s = warte(EVAL, 180)
    ziel = hole(EVAL)
    for p in list(ziel.rglob("results.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for name, pr in d.get("pruefungen", {}).items():
            print(f"  {name}: {pr['getroffen']}/{pr['gesamt']}", flush=True)
        print(f"  Adapter: {d.get('adapter')} · VRAM {d.get('vram_spitze_gib')} GiB", flush=True)
        break
    else:
        print("  kein results.json im Ergebnis", flush=True)

    adapter = next((q.parent for q in ziel.rglob("adapter_config.json")), None)
    if s == "COMPLETE" and adapter:
        baue_und_entscheide(adapter)
    elif s == "COMPLETE":
        print("  kein Adapter in der Ausgabe — kein Bau", flush=True)

    print(f"\nENDE: Auswertung {s}", flush=True)
    return 0 if s == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
