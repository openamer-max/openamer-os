#!/usr/bin/env python
"""Etappe 19: den trainierten Adapter zu einem Ollama-Modell machen (8B-VL).

Warum dieses Werkzeug: der Shortcut startet automatisch das beste registrierte
Modell (start.sh: openamer-max-vl-8b vor openamer-max-7b). Damit das greift,
muss das Modell als Ollama-Modell existieren — dafuer ist diese Kette da:

    Basis laden -> GGUF(f16) -> Adapter als GGUF-LoRA -> zusammenrechnen
    -> Q4_K_M -> ollama create openamer-max-vl-8b -> Probe -> Audit

Aufruf:
    python tools/integrate_8b.py --preflight     # nur pruefen, nichts laden
    python tools/integrate_8b.py                 # volle Kette

VRAM-Hinweis (gemessen 8151 MiB, davon ~2 GB Desktop): Qwen3-VL-8B in Q4_K_M
wiegt ~5,2 GB, dazu Bildencoder und KV-Cache. 65536 Kontext wie beim 7B passt
NICHT; dieses Werkzeug setzt 16384.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORK = Path(r"C:\Users\amer7\omx-8b")
LC = Path(r"C:\Users\amer7\llama-cpp")
MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"
# Testlaeufe bekommen einen eigenen Namen, damit start.sh sie NICHT automatisch
# als Standard waehlt (dort steht openamer-max-vl-8b vor openamer-max-7b).
NAME = os.environ.get("OMX_8B_NAME", "openamer-max-vl-8b")
ADAPTER_OVERRIDE = os.environ.get("OMX_8B_ADAPTER", "")
CTX = 16384
LLAMA_TAG = "b12491"
GGUF_URL = (f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}/"
            f"llama-{LLAMA_TAG}-bin-win-cpu-x64.zip")
MIN_FREI_GB = 45           # Basis 17,5 + GGUF f16 17 + Q4 5 + Luft
ADAPTER_KANDIDATEN = ("adapter_model.safetensors", "adapter_model.bin")


def sag(msg: str) -> None:
    print(f"  {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"  [ok]    {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"  [warn]  {msg}", flush=True)


def lauf(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    sag("! " + " ".join(str(c) for c in cmd)[:150])
    return subprocess.run(cmd, capture_output=True, text=True, timeout=kw.pop("timeout", 3600), **kw)


def adapter_finden() -> Path | None:
    """Adapter im Ausgabeordner des Kaggle-Laufs suchen."""
    if ADAPTER_OVERRIDE:
        p = Path(ADAPTER_OVERRIDE)
        return p if p.is_dir() else None
    for basis in (Path(r"C:\Users\amer7\omx-kaggle"), WORK):
        if not basis.exists():
            continue
        for datei in ADAPTER_KANDIDATEN:
            treffer = list(basis.rglob(datei))
            if treffer:
                return treffer[0].parent
    return None


def preflight() -> int:
    probleme = 0
    print("=== Vorflugpruefung ===")

    frei = shutil.disk_usage(str(REPO.anchor or "C:\\")).free / 2**30
    if frei >= MIN_FREI_GB:
        ok(f"Festplatte: {frei:.0f} GB frei (noetig ~{MIN_FREI_GB} GB)")
    else:
        warn(f"Festplatte: nur {frei:.0f} GB frei (noetig ~{MIN_FREI_GB} GB)")
        probleme += 1

    try:
        version = json.load(urllib.request.urlopen("http://127.0.0.1:11434/api/version", timeout=5))
        ok(f"Ollama: {version.get('version')} erreichbar")
    except Exception as exc:
        warn(f"Ollama nicht erreichbar: {type(exc).__name__}")
        probleme += 1

    try:
        import torch
        ok(f"PyTorch: {torch.__version__}")
    except Exception:
        warn("PyTorch fehlt (PYTHONPATH=C:\\Users\\amer7\\pylibs setzen)")
        probleme += 1

    try:
        import gguf  # noqa: F401
        ok("gguf-Paket vorhanden")
    except Exception:
        warn("gguf-Paket fehlt — wird bei der Umwandlung installiert (pip install gguf)")

    adapter = adapter_finden()
    if adapter:
        ok(f"Adapter gefunden: {adapter}")
    else:
        warn("Adapter noch nicht da — Training/Auswertung laeuft (Kette bricht hier ab)")
        probleme += 1

    vorhanden = list(LC.glob("**/llama-quantize.exe")) or list(LC.glob("**/llama-export-lora.exe"))
    if vorhanden:
        ok(f"llama.cpp-Werkzeuge: {vorhanden[0].parent}")
    else:
        sag("llama.cpp-Werkzeuge: noch nicht geladen (holt das Werkzeug bei Bedarf)")

    print(f"\nVorflug: {probleme} offene(r) Punkt(e)")
    return 0 if probleme == 0 else 1


def werkzeuge() -> Path:
    """llama.cpp-Binaries holen (CPU reicht fuer Konvertieren/Mergen/Quantisieren)."""
    da = list(LC.glob("**/llama-quantize.exe"))
    if da:
        return da[0].parent
    LC.mkdir(parents=True, exist_ok=True)
    zip_datei = LC / "llama-cpp.zip"
    sag(f"lade llama.cpp {LLAMA_TAG} ...")
    urllib.request.urlretrieve(GGUF_URL, zip_datei)
    shutil.unpack_archive(str(zip_datei), str(LC))
    treffer = list(LC.glob("**/llama-quantize.exe"))
    if not treffer:
        raise RuntimeError("llama-quantize.exe nicht im Archiv")
    return treffer[0].parent


def basis_laden() -> Path:
    ziel = WORK / "base"
    if (ziel / "config.json").is_file():
        ok(f"Basis vorhanden: {ziel}")
        return ziel
    from huggingface_hub import snapshot_download
    sag(f"lade {MODEL_ID} (~17,5 GB) ...")
    snapshot_download(MODEL_ID, local_dir=str(ziel), allow_patterns=[
        "*.json", "*.safetensors", "*.txt", "*.model", "*.jinja"])
    return ziel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preflight", action="store_true")
    a = ap.parse_args()
    if a.preflight:
        return preflight()

    adapter = adapter_finden()
    if not adapter:
        warn("Kein Adapter gefunden — Training/Auswertung zuerst abschliessen.")
        return 1
    WORK.mkdir(parents=True, exist_ok=True)
    bin_dir = werkzeuge()
    basis = basis_laden()

    sag("1/4 Basis nach GGUF (f16) ...")
    basis_gguf = WORK / "base-f16.gguf"
    if not basis_gguf.is_file():
        r = lauf([sys.executable, "convert_hf_to_gguf.py", str(basis),
                  "--outfile", str(basis_gguf), "--outtype", "f16"],
                 cwd=str(LC / "llama.cpp"))
        if r.returncode != 0:
            warn(f"Konvertierung fehlgeschlagen: {(r.stderr or '')[-300:]}")
            return 2
    ok(f"Basis-GGUF: {basis_gguf.stat().st_size / 2**30:.1f} GB")

    sag("2/4 Adapter nach GGUF-LoRA ...")
    lora_gguf = WORK / "adapter-lora.gguf"
    if not lora_gguf.is_file():
        r = lauf([sys.executable, str(LC / "llama.cpp" / "convert_lora_to_gguf.py"),
                  "--base", str(basis), "--outfile", str(lora_gguf), str(adapter)])
        if r.returncode != 0:
            warn(f"LoRA-Konvertierung fehlgeschlagen: {(r.stderr or '')[-300:]}")
            return 2

    sag("3/4 zusammenrechnen und quantisieren ...")
    zusammengefuehrt = WORK / "merged-f16.gguf"
    if not zusammengefuehrt.is_file():
        r = lauf([str(bin_dir / "llama-export-lora.exe"), "-m", str(basis_gguf),
                  "-o", str(zusammengefuehrt), "--lora", str(lora_gguf)])
        if r.returncode != 0:
            warn(f"Mergen fehlgeschlagen: {(r.stderr or '')[-300:]}")
            return 2
    q4 = WORK / f"{NAME}-Q4_K_M.gguf"
    if not q4.is_file():
        r = lauf([str(bin_dir / "llama-quantize.exe"), str(zusammengefuehrt), str(q4), "Q4_K_M"])
        if r.returncode != 0:
            warn(f"Quantisierung fehlgeschlagen: {(r.stderr or '')[-300:]}")
            return 2
    ok(f"Q4_K_M: {q4.stat().st_size / 2**30:.1f} GB")

    sag("4/4 in Ollama registrieren ...")
    modelfile = WORK / "Modelfile"
    modelfile.write_text(
        f"FROM {q4}\n\n"
        f"# 8B-VL braucht weniger Kontext als das 7B: 8151 MiB VRAM, davon ~2 GB Desktop.\n"
        f"PARAMETER num_ctx {CTX}\n"
        f"PARAMETER temperature 0.3\n", encoding="utf-8")
    for cmd in (["ollama", "rm", NAME], ["ollama", "create", NAME, "-f", str(modelfile)]):
        lauf(cmd, timeout=1800)
    liste = subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout
    if NAME not in liste:
        warn("Modell nicht in 'ollama list' — Registrierung pruefen")
        return 3
    ok(f"{NAME} registriert")

    sag("Probe ...")
    probe = subprocess.run(["ollama", "run", NAME, "Antworte in einem Satz: Was ist OpenAmer?"],
                           capture_output=True, text=True, timeout=600).stdout.strip()
    ok(f"Antwort: {probe[:120]}")

    audit = subprocess.run(["wsl", "-d", "Ubuntu", "--cd", "/OpenAmer All in One", "--",
                            "bash", "./start.sh", "--audit"], capture_output=True, text=True)
    treffer = [l.strip() for l in (audit.stdout or "").splitlines() if "Modell:" in l]
    ok(f"Start-Audit: {treffer or 'keine Modellzeile'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
