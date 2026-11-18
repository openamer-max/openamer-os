#!/usr/bin/env python
"""Prueft Datengenerator und Trainingssatz gegen ihre Vertraege.

Aufruf:  python tools/check_data.py        (Exit 0 = alles gruen)

Warum als Datei im Repo und nicht als Wegwerf-Skript: die Vertraege (keine
Pruefsatzwerte in Bild-Zeilen, keine wortgleichen Pruefsatzfragen, 1 Quelle fuer
Sperrwerte) wurden am 18.11.2026 zweimal verletzt. Eine Pruefung, die man neu
schreiben muss, verschwindet irgendwann.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent
REPO = EXP.parent.parent
VISION = EXP / "data" / "full_vision.jsonl"
SFT = EXP / "data" / "max_full_sft.jsonl"
IMGDIR = EXP / "testdata" / "vision_train"
MIN_BILDER, MIN_ZEILEN = 150, 780

res: list[tuple[str, bool, str]] = []


def rec(n: str, ok: bool, d: str = "") -> None:
    res.append((n, ok, d))
    print(f"  {'PASS' if ok else 'FAIL'}  {n}" + (f"  — {d}" if d else ""))


def load(p: Path, name: str):
    s = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def sollwerte(datei: str) -> set[str]:
    """Sollwerte eines Pruefsatzes (>=3 Zeichen, sonst matcht alles)."""
    return {str(v).strip().lower()
            for c in json.loads((EXP / datei).read_text(encoding="utf-8"))["cases"]
            for v in (c.get("muss") or []) if len(str(v).strip()) >= 3}


# Nur die VISION-Sollwerte gehoeren in diese Pruefung: Bild-Zeilen duerfen sie nicht
# enthalten, sonst ist der Bild-Pruefsatz wertlos. Aufgaben-Antworten ("Windows,
# Linux", "0 EUR") sind dagegen Fakten, die im Training stehen MUESSEN — sie
# mitzupruefen hiesse, dem Modell das Wissen zu verbieten (Fehlannahme vom 18.11.).
VISION_WERTE = sollwerte("testset_vision.json")
TASK_WERTE = sollwerte("testset_tasks.json")


def frageteil(user: str) -> str:
    u = (user or "").strip().lower()
    return u.split("frage:", 1)[1].strip() if "frage:" in u else u


print("\n[1] Generator")
V = load(EXP / "tools" / "datagen_vision.py", "visiongen")
rec("Sperrliste deckt Vision-Sollwerte", VISION_WERTE <= set(V.FORBIDDEN),
    f"{len(VISION_WERTE)} Sollwerte / {len(V.FORBIDDEN)} Sperrwerte")
rec("durchgerutschter Wert 3.11 gesperrt", "3.11" in V.FORBIDDEN)
neu = V.build_cases(MIN_BILDER)
blob = json.dumps(neu, ensure_ascii=False).lower()
rec(f"{MIN_BILDER} Faelle ohne Sperrwert", len(neu) == MIN_BILDER
    and not any(f in blob for f in V.FORBIDDEN), f"{len(neu)} Faelle")
rec("neue Falltypen (Tabelle/Stacktrace/Diff)",
    all(k in blob for k in ("durchlauf", "traceback", "diff --git")))

print("\n[2] Trainingssatz")
rec("Bild-Zeilen vorhanden", VISION.is_file())
vis = [json.loads(l) for l in VISION.read_text(encoding="utf-8").splitlines()]
sft = [json.loads(l) for l in SFT.read_text(encoding="utf-8").splitlines()]
rec(f">= {MIN_BILDER} Bild-Zeilen", len(vis) >= MIN_BILDER, str(len(vis)))
rec(f">= {MIN_ZEILEN} Zeilen gesamt", len(sft) >= MIN_ZEILEN, str(len(sft)))
rec("kein Vision-Sollwert in Bild-Zeilen",
    not [f for f in VISION_WERTE if f in json.dumps(vis, ensure_ascii=False).lower()])
fragen = {frageteil_user for p in ("testset_vision.json", "testset_tasks.json")
          for c in json.loads((EXP / p).read_text(encoding="utf-8"))["cases"]
          if (frageteil_user := (c.get("frage") or "").strip().lower())}
rec("keine wortgleiche Pruefsatzfrage im Training",
    not [r for r in sft if frageteil(r["messages"][0]["content"]) in fragen])

print("\n[3] Bilder")
imgs = sorted(IMGDIR.glob("*.png"))
rec(f">= {MIN_BILDER} Bilddateien", len(imgs) >= MIN_BILDER, str(len(imgs)))
rec("keine Datei < 3 KB", all(p.stat().st_size >= 3000 for p in imgs))
rec("jede Bild-Zeile hat ihre Datei", all((EXP / r["image"]).is_file() for r in vis))

print("\n[4] Datensatzbau (idempotent)")
h0 = hashlib.sha256(SFT.read_bytes()).hexdigest()[:16]
p = subprocess.run([sys.executable, str(EXP / "tools" / "build_dataset.py")],
                   cwd=EXP, capture_output=True, text=True, timeout=600)
rec("build_dataset rc=0", p.returncode == 0, (p.stderr or "").strip()[-80:])
rec("keine gerissene Schranke", "ABBRUCH" not in p.stdout)
h1 = hashlib.sha256(SFT.read_bytes()).hexdigest()[:16]
rec("Neubau unveraendert (Hash)", h0 == h1, h1)

print("\n[5] Repo")
g = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True)
rec("Arbeitsbaum sauber", g.stdout.strip() == "", g.stdout.strip()[:70] or "leer")

print("\n[6] Denk-Spuren: Rechnung unabhaengig nachgerechnet")
# Form allein reicht nicht: ein Satz mit falscher Rechnung bringt dem Modell
# falsches Denken bei. Jede Fallfamilie wird hier neu berechnet.
G = load(EXP / "datagen_full.py", "fullgen")
FAKTOR = {("km", "m"): 1000, ("kg", "g"): 1000, ("min", "s"): 60,
          ("h", "min"): 60, ("l", "ml"): 1000}
faelle = G._rechenfaelle()
fehler: list[str] = []
zaehler: dict[str, int] = {}

for frage, schritte, antwort in faelle:
    if m := re.search(r"Wie viele (\w+) sind (\d+) (\w+)\?", frage):
        nach, wert, von = m.group(1), int(m.group(2)), m.group(3)
        soll, art = wert * FAKTOR[(von, nach)], "einheiten"
        ist = int(re.search(r"sind (\d+) ", antwort).group(1))
    elif m := re.search(r"Wie viel sind (\d+) Grad Celsius", frage):
        c, art = int(m.group(1)), "temperatur"
        soll = c * 9 / 5 + 32
        ist = float(re.search(r"sind ([\d.]+) Grad Fahrenheit", antwort).group(1))
    elif m := re.search(r"zwischen (\d+)\.(\d+)\.(\d+) und (\d+)\.(\d+)\.(\d+)", frage):
        a, b, c2, d, e, f = (int(m.group(i)) for i in range(1, 7))
        art = "datum"
        soll = (date(f, e, d) - date(c2, b, a)).days
        ist = int(re.search(r"Es sind (\d+) Tage", antwort).group(1))
    elif m := re.search(r"(\d+) cm lang und (\d+) cm breit", frage):
        laenge, breite, art = int(m.group(1)), int(m.group(2)), "rechteck"
        soll = (laenge * breite, 2 * (laenge + breite))
        ist = (int(re.search(r"Flaeche (\d+) cm2", antwort).group(1)),
               int(re.search(r"Umfang (\d+) cm", antwort).group(1)))
    elif m := re.search(r"Kapital von (\d+) bei ([\d.]+) % in (\d+) Jahren", frage):
        k, p, j, art = float(m.group(1)), float(m.group(2)), int(m.group(3)), "zins"
        soll = k * p / 100 * j
        ist = float(re.search(r"betraegt ([\d.]+)", antwort).group(1))
    elif m := re.search(r"kostet (\d+) Euro, es gibt (\d+) % Rabatt", frage):
        preis, rabatt, art = int(m.group(1)), int(m.group(2)), "rabatt"
        soll = preis * (100 - rabatt) / 100
        ist = float(re.search(r"danach ([\d.]+) Euro", antwort).group(1))
    else:
        continue
    zaehler[art] = zaehler.get(art, 0) + 1
    if soll != ist:
        fehler.append(f"{art}: {ist} statt {soll}")

for art in ("einheiten", "temperatur", "datum", "rechteck", "zins", "rabatt"):
    rec(f"{art} gerechnet", zaehler.get(art, 0) > 0, f"{zaehler.get(art, 0)} Faelle")
rec("keine Rechenfehler", not fehler, "; ".join(fehler[:3]))
rec("jeder Fall >=2 Schritte", all(len(s) >= 2 for _f, s, _a in faelle))
verboten = G.pruefsatz_fragen()
rec("keine Pruefsatzfrage aus dem Generator",
    not any(f.strip().lower() in verboten for f, _s, _a in faelle))

bad = [x for x in res if not x[1]]
print("\n" + "=" * 62)
print(f"CHECK: {len(res) - len(bad)}/{len(res)} Pruefungen gruen")
for n, _o, d in bad:
    print("  OFFEN:", n, "—", d[:100])
sys.exit(1 if bad else 0)
