#!/usr/bin/env python
"""Bild-Trainingsdaten: echte Konsolen-Screenshots mit bekanntem Inhalt.

Das Problem, das diese Datei loest: der bisherige Satz hatte **0** Bild-Zeilen,
also konnte kein Modell Bilddeutung lernen. Hier entstehen echte Screenshots
(gerendert von cmd.exe, aufgenommen per CopyFromScreen) mit Inhalt, den wir
selbst gedruckt haben — die Antwort ist damit belegbar, nicht erfunden.

Kontaminationsschutz: die Werte des eingefrorenen Pruefsatzes
(`testset_vision.json`) duerfen in den Trainingsbildern **nicht** vorkommen.
Deshalb andere Versionen, andere Fehlercodes, andere Pfade.

Aufruf:
    python tools/datagen_vision.py --count 40 --capture     # erzeugt Bilder + JSONL
    python tools/datagen_vision.py --rows-only              # nur Zeilen aus vorhandenen Bildern
"""
from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODELDIR = HERE.parent
IMGDIR = MODELDIR / "testdata" / "vision_train"
CASES = HERE / "vision_cases.json"
RENDER_PS1 = HERE / "vision_render.ps1"
RND = random.Random(20261118)

# Werte, die im Pruefsatz stehen — sie duerfen hier NICHT auftauchen.
# EINE Quelle: die Sollwerte des Vision-Pruefsatzes selbst. Vorher stand hier
# eine eigene Liste ("3.11.17"), waehrend die Schranke in build_dataset.py den
# kuerzeren Wert ("3.11") pruefte — so rutschte "3.11.9" durch und riss die
# Schranke (18.11.2026).
def _pruefwerte() -> list[str]:
    p = MODELDIR / "testset_vision.json"
    werte = {"2.54", "cde9d39", "deepseek", "314", "11001", "getaddrinfo",
             "config.yaml"}
    if p.is_file():
        for c in json.loads(p.read_text(encoding="utf-8")).get("cases", []):
            for v in (c.get("muss") or []):
                s = str(v).strip().lower()
                if len(s) >= 3:
                    werte.add(s)
    return sorted(werte)


FORBIDDEN = _pruefwerte()

PY_VERS = ["3.12.4", "3.10.14", "3.12.7", "3.13.1", "3.14.2"]
GIT_VERS = ["2.43.0", "2.47.1", "2.39.5", "2.51.2"]
HASHES = ["a7f3c21", "9b2e08d", "4c1a77e", "e83f5b0", "17d9ac4"]
MODELS = ["openamer-max-7b", "qwen2.5vl:7b", "openamer-max-tab", "llama3.2:3b"]
CODES = ["10060", "111", "404", "500", "EACCES", "ENOENT", "0x80070005"]
FILES = ["notizen.txt", "bericht_2026.pdf", "daten.csv", "start.sh", "verify.py"]
DIRS = ["C:\\Users\\amer7\\Dokumente", "/home/amer7/projekte", "D:\\Sicherung"]
COUNTS = ["42", "128", "7", "256", "19"]


def _case_version(i: int) -> tuple[list[str], str, str]:
    py = RND.choice(PY_VERS)
    git = RND.choice(GIT_VERS)
    lines = ["OpenAmer Installationspruefung", "--------------------------------",
             f"Python gefunden:  {py}", f"git gefunden:     {git}",
             "Ollama:           erreichbar", "Fertig."]
    q = "Welche Python-Version meldet die Pruefung? Antworte mit der Versionsnummer."
    return lines, q, py


def _case_git(i: int) -> tuple[list[str], str, str]:
    git = RND.choice(GIT_VERS)
    h = RND.choice(HASHES)
    lines = ["=== Werkzeuge ===", f"git version {git}", f"HEAD zeigt auf {h}",
             "Alle Werkzeuge gefunden."]
    q = "Welche Git-Version wird im Bild genannt?"
    return lines, q, git


def _case_hash(i: int) -> tuple[list[str], str, str]:
    h = RND.choice(HASHES)
    lines = ["Letzter Commit:", f"  commit {h}", "  Author: Amer Sacirovic",
             "  Message: Build korrigiert"]
    q = "Welcher Commit-Hash steht im Bild? Nenne nur den Hash."
    return lines, q, h


def _case_model(i: int) -> tuple[list[str], str, str]:
    m = RND.choice(MODELS)
    lines = ["OpenAmer Status", f"Modell:      {m}", "Provider:    ollama",
             "Kontext:     65536"]
    q = "Welches Modell ist laut Bild aktiv? Nenne den Modellnamen."
    return lines, q, m


def _case_count(i: int) -> tuple[list[str], str, str]:
    n = RND.choice(COUNTS)
    lines = ["Installation abgeschlossen", f"Skills installiert: {n}",
             f"Werkzeuge:          42", "Status:             bereit"]
    q = "Wie viele Skills meldet die Ausgabe? Nenne die Zahl."
    return lines, q, n


def _case_error(i: int) -> tuple[list[str], str, str]:
    code = RND.choice(CODES)
    lines = ["Verbindung fehlgeschlagen", f"Fehlercode: {code}",
             "Ziel: api.example.net:443", "Wiederhole mit --retry 3"]
    q = "Welcher Fehlercode steht im Bild?"
    return lines, q, code


def _case_missing(i: int) -> tuple[list[str], str, str]:
    fehlt = RND.sample(["kalender", "drucken", "musik", "csv-export", "sms"], 2)
    da = RND.sample(["terminal", "dateien", "browser", "git", "rechnen"], 3)
    lines = ["Werkzeugliste", "vorhanden: " + ", ".join(da),
             "fehlend:   " + ", ".join(fehlt)]
    q = "Welche Funktionen sind im Bild als fehlend markiert? Nenne beide."
    return lines, q, ", ".join(fehlt)


def _case_path(i: int) -> tuple[list[str], str, str]:
    f = RND.choice(FILES)
    d = RND.choice(DIRS)
    lines = ["Einstellungen", f"Ordner:  {d}", f"Datei:   {f}", "Groesse: 4,2 KB"]
    q = "Wie heisst die Datei, die im Bild genannt wird?"
    return lines, q, f


def _case_success(i: int) -> tuple[list[str], str, str]:
    # Wortwahl bewusst NICHT "erfolgreich/ok/ja/yes/success": genau diese Woerter
    # sind im Vision-Pruefsatz (V06) die Sollwerte. Wer sie ins Training gibt,
    # macht den Pruefsatz wertlos. Die Schranke in build_dataset.py prueft das.
    durch = RND.random() < 0.6
    lines = ["Build-Lauf",
             "Schritt 1: Quellen gelesen      " + ("durchgelaufen" if durch else "abgebrochen"),
             "Schritt 2: Tests                " + ("durchgelaufen" if durch else "abgebrochen"),
             "Schritt 3: Paket                "
             + ("durchgelaufen" if durch else "uebersprungen"),
             "Ergebnis: BUILD " + ("DURCHGELAUFEN" if durch else "ABGEBROCHEN")]
    q = "Lief dieser Build durch oder ist er abgebrochen? Antworte mit einem Wort."
    return lines, q, "durchgelaufen" if durch else "abgebrochen"


def _case_tabelle(i: int) -> tuple[list[str], str, str]:
    """Tabelle lesen und den Extremwert finden — nicht nur eine Zahl abmalen."""
    rows = [(name, round(RND.uniform(6, 20), 1), RND.randrange(380, 680, 4))
            for name in RND.sample(["A", "B", "C", "D", "E"], 3)]
    schnell = min(rows, key=lambda r: r[1])
    lines = ["Messwerte", "Durchlauf   Zeit s   Speicher MB"]
    lines += [f"{n:<11}{str(t).replace('.', ','):<9}{s}" for n, t, s in rows]
    lines += ["", f"Summe Speicher: {sum(s for _, _, s in rows)} MB"]
    q = "Welcher Durchlauf war am schnellsten? Antworte mit dem Buchstaben."
    return lines, q, schnell[0]


def _case_traceback(i: int) -> tuple[list[str], str, str]:
    """Ausnahmetyp aus einem echten Stacktrace-Aufbau ablesen."""
    exc = RND.choice(["ValueError", "KeyError", "FileNotFoundError", "TimeoutError"])
    zeile = RND.choice([17, 23, 42, 88, 101])
    detail = {"ValueError": "Expecting value: line 1 column 1 (char 0)",
              "KeyError": "'model_name'",
              "FileNotFoundError": "[Errno 2] No such file or directory",
              "TimeoutError": "timed out after 30 seconds"}[exc]
    lines = ["Traceback (most recent call last):",
             '  File "C:\\Users\\amer7\\run.py", line 64, in main',
             "    daten = lade(pfad)",
             f'  File "C:\\Users\\amer7\\lader.py", line {zeile}, in lade',
             "    return json.loads(text)",
             f"{exc}: {detail}"]
    q = "Welche Ausnahme nennt das Bild in der letzten Zeile?"
    return lines, q, exc


def _case_diff(i: int) -> tuple[list[str], str, str]:
    """Geaenderte Datei aus einem Diff-Kopf ablesen."""
    datei, alt, neu = RND.choice([
        ("omx_cli/build.py", "mtime = time.time()", "mtime = 0"),
        ("omx_cli/status.py", "return 1", "return 0"),
        ("agent/start.sh", "reasoning_effort=medium", "reasoning_effort=false"),
        ("tools/vision.py", "RND.seed()", "RND.seed(20261118)"),
    ])
    lines = [f"diff --git a/{datei} b/{datei}", f"--- a/{datei}", f"+++ b/{datei}",
             "@@ -12,7 +12,7 @@", f"-    {alt}", f"+    {neu}", " ",
             f"1 Datei geaendert, 1 Einfuegung(+), 1 Loeschung(-)"]
    q = "In welcher Datei wurde etwas geaendert? Antworte mit dem Pfad."
    return lines, q, datei


GENERATORS = [_case_version, _case_git, _case_hash, _case_model, _case_count,
              _case_error, _case_missing, _case_path, _case_success,
              _case_tabelle, _case_traceback, _case_diff]


def build_cases(count: int) -> list[dict]:
    out = []
    i = 0
    while len(out) < count:
        lines, q, a = GENERATORS[i % len(GENERATORS)](i)
        blob = "\n".join(lines).lower()
        if any(f.lower() in blob for f in FORBIDDEN):
            i += 1
            continue          # Pruefsatz-Wert getroffen -> verwerfen
        out.append({"id": f"VT{len(out)+1:03d}", "lines": lines,
                    "frage": q, "antwort": a})
        i += 1
    return out


def capture(cases: list[dict]) -> None:
    """Rendert die Abbilder. Bewusst gerendert, nicht fotografiert: cmd.exe bekommt
    unter Windows Terminal keinen eigenen Fenster-Handle, ein Bildschirmfoto des
    Fensters ist damit nicht moeglich (gemessen 18.11.2026, Handle blieb 0)."""
    IMGDIR.mkdir(parents=True, exist_ok=True)
    CASES.write_text(json.dumps(cases, ensure_ascii=False, indent=1), encoding="utf-8")
    ps = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
          str(RENDER_PS1), "-Cases", str(CASES), "-OutDir", str(IMGDIR)]
    p = subprocess.run(ps, capture_output=True, text=True, timeout=1800, errors="replace")
    print((p.stdout or "").strip()[-800:])
    if p.returncode != 0:
        print("Render-Fehler:", (p.stderr or "").strip()[-400:], file=sys.stderr)


def rows(cases: list[dict]) -> list[dict]:
    out = []
    for c in cases:
        img = IMGDIR / f"{c['id']}.png"
        if not img.is_file() or img.stat().st_size < 3000:
            continue
        out.append({"kind": "vision", "image": str(img.relative_to(MODELDIR)).replace("\\", "/"),
                    "messages": [{"role": "user", "content": c["frage"]},
                                 {"role": "assistant", "content": c["antwort"]}]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--rows-only", action="store_true")
    ap.add_argument("--out", default=str(MODELDIR / "data" / "full_vision.jsonl"))
    a = ap.parse_args()

    if a.rows_only and CASES.is_file():
        cases = json.loads(CASES.read_text(encoding="utf-8"))
    else:
        cases = build_cases(a.count)
    if a.capture:
        capture(cases)
    rws = rows(cases)
    Path(a.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rws),
                           encoding="utf-8")
    blob = json.dumps(cases, ensure_ascii=False).lower()
    leaked = [f for f in FORBIDDEN if f.lower() in blob]
    print(f"{len(rws)} Bild-Zeilen -> {a.out}")
    print("Pruefsatz-Werte in Trainingsdaten:", leaked or "keine")
    return 0 if len(rws) else 1


if __name__ == "__main__":
    sys.exit(main())
