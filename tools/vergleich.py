#!/usr/bin/env python
"""Zwei Ollama-Modelle auf denselben 24 Aufgabenfaellen vergleichen.

Warum als Werkzeug im Repo: "das neue Modell ist besser" ist eine Behauptung, bis
sie gemessen ist. Am 18.11.2026 war das frisch gebaute 8B (Adapter aus 25 Schritten)
mit 18/24 schlechter als das laufende 7B mit 22/24 — ohne diese Messung wäre ein
schlechteres Modell Standard geworden.

Aufruf:
    python tools/vergleich.py --neu openamer-max-vl-8b --alt openamer-max-7b
    python tools/vergleich.py --neu A --alt B --faelle 6      # schnelle Probe

Exit 0 = neu >= alt (Uebernahme vertretbar), Exit 1 = neu schlechter.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

EXP = Path(__file__).resolve().parent.parent / "model" / "openamer-max-one"
URL = "http://127.0.0.1:11434/api/chat"


def frage(modell: str, text: str, ctx: int) -> str:
    body = json.dumps({"model": modell, "stream": False,
                       "options": {"temperature": 0, "num_ctx": ctx},
                       "messages": [{"role": "user", "content": text}]}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=600))["message"]["content"]


def messen(modell: str, cases: list[dict], ctx: int) -> tuple[int, list[dict]]:
    treffer, details = 0, []
    for c in cases:
        try:
            antwort = frage(modell, c["frage"], ctx)
        except Exception as exc:
            antwort = f"FEHLER {type(exc).__name__}"
        ok = any(str(m).strip().lower() in antwort.lower() for m in (c.get("muss") or []))
        treffer += ok
        details.append({"id": c.get("id"), "treffer": ok, "laenge": len(antwort)})
    return treffer, details


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--neu", required=True)
    ap.add_argument("--alt", required=True)
    ap.add_argument("--faelle", type=int, default=24)
    ap.add_argument("--ctx", type=int, default=8192)
    ap.add_argument("--bericht", default="")
    a = ap.parse_args()

    cases = json.loads((EXP / "testset_tasks.json").read_text(encoding="utf-8"))["cases"][:a.faelle]
    ergebnis = {}
    for name, modell in (("neu", a.neu), ("alt", a.alt)):
        treffer, details = messen(modell, cases, a.ctx)
        ergebnis[name] = {"modell": modell, "getroffen": treffer,
                          "gesamt": len(cases), "details": details}
        print(f"{modell}: {treffer}/{len(cases)}", flush=True)

    delta = ergebnis["neu"]["getroffen"] - ergebnis["alt"]["getroffen"]
    urteil = ("BESSER" if delta > 0 else "GLEICH" if delta == 0 else "SCHLECHTER")
    print(f"\n{ergebnis['neu']['modell']} vs {ergebnis['alt']['modell']}: "
          f"{delta:+d} Faelle -> {urteil}")
    print("Empfehlung:", "uebernehmen" if delta >= 0 else
          "nicht uebernehmen (altes Modell bleibt Standard)")

    if a.bericht:
        Path(a.bericht).write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    return 0 if delta >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
