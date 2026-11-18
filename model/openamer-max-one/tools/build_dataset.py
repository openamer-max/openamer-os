#!/usr/bin/env python
"""Baut den vereinigten Trainingssatz und prueft die Schranken.

Zwei Aufgaben, bewusst in einer Datei, weil sie zusammen gelten:
  1. Zusammenfuehren: Grundsatz + Ergaenzungen + Bild-Zeilen -> data/max_full_sft.jsonl
  2. Schranken: Kontamination gegen beide Pruefsaetze, Struktur, Abdeckung

Ein Satz, der eine Schranke reisst, wird **nicht** geschrieben. Lieber kein
Datensatz als ein vergifteter.

Aufruf:
    python tools/build_dataset.py            # bauen + pruefen
    python tools/build_dataset.py --check    # nur pruefen (ohne schreiben)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

MODELDIR = Path(__file__).resolve().parent.parent
DATA = MODELDIR / "data"
SOURCES = ["max_one_sft.jsonl", "max_one_v2.jsonl", "max_one_v3.jsonl",
           "full_extra.jsonl", "full_vision.jsonl"]
TARGET = DATA / "max_full_sft.jsonl"

# Mindest-Abdeckung je Faehigkeit (aus dem Plan): ohne diese Zeilen gibt es
# keine Faehigkeit, egal wie lange trainiert wird.
MIN_PER_KIND = {
    "vision": 30,
    "tool_call": 25,
    "denken": 10,
    "entscheidung": 20,
    "werkzeug": 10,
    "skill": 20,
}


def load() -> tuple[list[dict], dict[str, int]]:
    rows: list[dict] = []
    per_file: dict[str, int] = {}
    for name in SOURCES:
        p = DATA / name
        if not p.is_file():
            per_file[name] = 0
            continue
        n = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
                n += 1
        per_file[name] = n
    return rows, per_file


def dedupe(rows: list[dict]) -> tuple[list[dict], int]:
    seen: set[str] = set()
    out = []
    for r in rows:
        if not r.get("kind"):
            # v2/v3 tragen kein kind — fuer Abdeckung und Bericht ableiten
            m = r.get("messages") or []
            if r.get("image"):
                r["kind"] = "vision"
            elif any(x.get("tool_calls") for x in m):
                r["kind"] = "tool_call"
            else:
                r["kind"] = "text"
        key = json.dumps(r.get("messages"), ensure_ascii=False, sort_keys=True)
        if r.get("image"):
            key += "|" + r["image"]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out, len(rows) - len(out)


def testset_texts() -> tuple[set[str], list[str], list[str]]:
    """(Frage-Wortlaute, Vision-Sollwerte, Aufgaben-Sollwerte)."""
    fragen: set[str] = set()
    vision_werte: list[str] = []
    task_werte: list[str] = []
    for name, sammler in (("testset_tasks.json", task_werte),
                          ("testset_vision.json", vision_werte)):
        p = MODELDIR / name
        if not p.is_file():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        for c in d.get("cases", []):
            if c.get("frage"):
                fragen.add(c["frage"].strip().lower())
            for v in (c.get("muss") or []):
                sammler.append(str(v).strip().lower())
    return fragen, vision_werte, task_werte


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    rows, per_file = load()
    print("=== Quellen ===")
    for k, v in per_file.items():
        print(f"  {k:22s} {v:5d} Zeilen")

    rows, dup = dedupe(rows)
    kinds = Counter(r.get("kind", "?") for r in rows)
    print(f"\n=== Vereinigter Satz ===\n  {len(rows)} Zeilen ({dup} Duplikate entfernt)")

    fails: list[str] = []

    # --- Schranke 1: Kontamination (Frage-Wortlaut)
    fragen, vision_werte, task_werte = testset_texts()

    def frage_teil(user: str) -> str:
        """Frageteil einer Zeile. Kontext-Zeilen tragen 'Frage: ...' hinten dran."""
        u = (user or "").strip().lower()
        return u.split("frage:", 1)[1].strip() if "frage:" in u else u

    # Frueher wurde nur der GANZE User-Text verglichen — dadurch rutschten
    # Kontext-Zeilen durch, die die Pruefsatzfrage im Frageteil woertlich
    # enthielten (6 von 24 Faellen, am 18.11.2026 gemessen). Solche Paare
    # messen Auswendiglernen, nicht Koennen: sie fliegen raus, und zwar sichtbar.
    behalten, leaks = [], []
    for r in rows:
        (leaks if frage_teil(r["messages"][0].get("content", "")) in fragen
         else behalten).append(r)
    rows = behalten
    kinds = Counter(r.get("kind", "?") for r in rows)
    print(f"\n=== Schranke 1: Kontamination ===")
    print(f"  wortgleiche Pruefsatzfragen entfernt: {len(leaks)} "
          f"({len(rows)} Zeilen bleiben)")
    for r in leaks:
        print("    -", r.get("kind"), "|", r["messages"][0]["content"][:64].replace("\n", " "))

    # --- Schranke 2: Pruefsatz-Werte in Bild-Zeilen (auswendig lernen verhindern)
    vision_blob = " ".join(r["messages"][0]["content"] + " " + r["messages"][1]["content"]
                           for r in rows if r.get("kind") == "vision").lower()
    treffer = [v for v in vision_werte if v and v in vision_blob]
    print(f"  Vision-Sollwerte des Pruefsatzes in Bild-Zeilen: {len(treffer)} (muss 0 sein)")
    if treffer:
        fails.append(f"Vision-Pruefwerte im Training: {treffer}")
        print("    ", treffer)

    # --- Schranke 3: Struktur
    print(f"\n=== Schranke 3: Struktur ===")
    bad_end = 0
    bad_tool = 0
    for r in rows:
        m = r.get("messages") or []
        if not m:
            bad_end += 1
            continue
        has_call = any(x.get("tool_calls") for x in m)
        if has_call:
            # nach jedem tool_call muss eine tool-Antwort und eine assistant-Zeile folgen
            if m[-1].get("role") != "assistant" or not (m[-1].get("content") or "").strip():
                bad_tool += 1
        elif m[-1].get("role") != "assistant" or not (m[-1].get("content") or "").strip():
            bad_end += 1
    print(f"  Zeilen ohne abschliessende Assistant-Antwort: {bad_end} (muss 0 sein)")
    print(f"  Werkzeug-Zeilen ohne Abschluss: {bad_tool} (muss 0 sein)")
    if bad_end or bad_tool:
        fails.append(f"{bad_end} unvollstaendige Zeilen, {bad_tool} Werkzeug-Zeilen offen")

    # --- Schranke 4: Abdeckung
    print(f"\n=== Schranke 4: Abdeckung ===")
    for kind, minimum in MIN_PER_KIND.items():
        ist = kinds.get(kind, 0)
        ok = ist >= minimum
        print(f"  {kind:14s} {ist:4d} / mindestens {minimum:3d}   {'OK' if ok else 'ZU WENIG'}")
        if not ok:
            fails.append(f"{kind}: {ist} < {minimum}")

    print("\n=== Verteilung ===")
    for k, v in kinds.most_common():
        print(f"  {k:16s} {v:5d}")

    if fails:
        print(f"\nABBRUCH: {len(fails)} Schranke(n) gerissen -> nichts geschrieben")
        for f in fails:
            print("  -", f)
        return 1

    if not a.check:
        TARGET.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                          encoding="utf-8")
        mb = TARGET.stat().st_size / 1e6
        print(f"\nGESCHRIEBEN: {TARGET}  {len(rows)} Zeilen, {mb:.2f} MB")
    else:
        print("\nNur geprueft (--check), nichts geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
