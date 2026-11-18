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
import hashlib
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
PYLIBS = r"C:\Users\amer7\pylibs"
# Pakete, die der GGUF-Konverter braucht. sentencepiece fehlte am 18.11.2026 und
# liess die Umwandlung mit ModuleNotFoundError sterben — bei einem unbeaufsichtigten
# Kettenlauf waere das ein stiller Abbruch.
PAKETE = {"gguf": "gguf", "sentencepiece": "sentencepiece",
          "safetensors": "safetensors", "huggingface_hub": "huggingface_hub"}


def deps() -> int:
    """Fehlende Konverter-Pakete nachziehen. Rueckgabe: Anzahl installiert."""
    fehlend = []
    for modul, paket in PAKETE.items():
        try:
            __import__(modul)
        except Exception:
            fehlend.append(paket)
    if not fehlend:
        return 0
    sag(f"installiere fehlende Pakete: {', '.join(fehlend)}")
    r = lauf([sys.executable, "-m", "pip", "install", "--quiet", "--target", PYLIBS,
              *fehlend], timeout=1800)
    if r.returncode != 0:
        warn(f"Installation fehlgeschlagen: {(r.stderr or '')[-200:]}")
    if PYLIBS not in sys.path:
        sys.path.insert(0, PYLIBS)
    return len(fehlend)


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


def adapter_stempel(adapter: Path) -> str:
    """Kennung des Adapters (Groesse + Kopf-Hash) fuer den Zwischenspeicher.

    Ohne diese Kennung wuerde das Werkzeug eine vorhandene gemergte Basis
    wiederverwenden, auch wenn ein ANDERER Adapter vorliegt — beim ersten echten
    Lauf waere still das Testmodell erneut gebaut worden (Fund 18.11.2026).
    """
    datei = next((adapter / n for n in ADAPTER_KANDIDATEN if (adapter / n).is_file()), None)
    if datei is None:
        return "ohne-adapter"
    kopf = datei.open("rb").read(1 << 20)
    return f"{datei.stat().st_size}-{hashlib.sha256(kopf).hexdigest()[:16]}"


def zwischenspeicher_pruefen(adapter: Path) -> None:
    """Verwirft Zwischenstaende, wenn sie zu einem anderen Adapter gehoeren."""
    stempel_datei = WORK / "adapter.stempel"
    ist = adapter_stempel(adapter)
    war = stempel_datei.read_text(encoding="utf-8").strip() if stempel_datei.is_file() else ""
    if war and war != ist:
        sag(f"anderer Adapter ({war[:18]} -> {ist[:18]}) — Zwischenstaende werden neu gebaut")
        for pfad in (WORK / "merged",):
            shutil.rmtree(pfad, ignore_errors=True)
        for pfad in WORK.glob("merged-f16.gguf"):
            pfad.unlink(missing_ok=True)
        for pfad in WORK.glob("*-Q4_K_M.gguf"):
            pfad.unlink(missing_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    stempel_datei.write_text(ist, encoding="utf-8")
    ok_kurz = "Zwischenspeicher passt zum Adapter" if war == ist else "Zwischenspeicher markiert"
    sag(ok_kurz)


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
    if not da:
        LC.mkdir(parents=True, exist_ok=True)
        zip_datei = LC / "llama-cpp.zip"
        sag(f"lade llama.cpp {LLAMA_TAG} ...")
        urllib.request.urlretrieve(GGUF_URL, zip_datei)
        shutil.unpack_archive(str(zip_datei), str(LC))
        da = list(LC.glob("**/llama-quantize.exe"))
        if not da:
            raise RuntimeError("llama-quantize.exe nicht im Archiv")
    repo_laden()
    return da[0].parent


def repo_laden() -> Path:
    """Konverter-Repo. Die Binaries enthalten convert_hf_to_gguf.py NICHT —
    am 18.11.2026 mit NotADirectoryError aufgefallen."""
    repo = LC / "llama.cpp"
    if (repo / "convert_hf_to_gguf.py").is_file():
        return repo
    sag("hole Konverter-Repo (flach) ...")
    r = lauf(["git", "clone", "--depth", "1",
              "https://github.com/ggml-org/llama.cpp.git", str(repo)], timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"git clone fehlgeschlagen: {(r.stderr or '')[-200:]}")
    return repo


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
    deps()
    WORK.mkdir(parents=True, exist_ok=True)
    zwischenspeicher_pruefen(adapter)
    bin_dir = werkzeuge()
    basis = basis_laden()

    repo = repo_laden()
    # llama-export-lora gibt es im CPU-Build nicht, und ein Merge im Speicher
    # braucht ~20 GB RAM (nur 17 frei). Deshalb stromweise auf der Platte.
    sag("1/4 Adapter stromweise in die Basis rechnen ...")
    gemerged = WORK / "merged"
    if not (gemerged / "model.safetensors.index.json").is_file():
        r = lauf([sys.executable, str(REPO / "tools" / "merge_lora_stream.py"),
                  str(basis), str(adapter), str(gemerged)], timeout=7200)
        if r.returncode != 0:
            warn(f"Merge fehlgeschlagen: {(r.stderr or r.stdout or '')[-300:]}")
            return 2
    ok(f"gemergt: {gemerged}")

    sag("2/4 gemergte Basis nach GGUF (f16) ...")
    zusammengefuehrt = WORK / "merged-f16.gguf"
    if not zusammengefuehrt.is_file():
        r = lauf([sys.executable, str(repo / "convert_hf_to_gguf.py"), str(gemerged),
                  "--outfile", str(zusammengefuehrt), "--outtype", "f16"],
                 cwd=str(repo), timeout=7200)
        if r.returncode != 0:
            warn(f"Konvertierung fehlgeschlagen: {(r.stderr or '')[-300:]}")
            return 2
    ok(f"GGUF f16: {zusammengefuehrt.stat().st_size / 2**30:.1f} GB")

    sag("3/4 quantisieren ...")
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
