#!/usr/bin/env python3
"""Vision-Messung: laesst einen Bild-Pruefsatz gegen ein multimodales Ollama-Modell laufen.

    python vision_eval.py                       # alle Faelle, Modell qwen2.5vl:3b
    python vision_eval.py --id V01              # einzelner Fall
    python vision_eval.py --model <tag> --repeat 2

Warum ein eigenes Skript: Der Text-Prüfstand (omx model eval) kann keine Bilder.
Dieses Skript schickt den Screenshot base64 an /api/generate, wertet die Antwort
gegen die Pflicht-Begriffe und meldet pro Fall OK oder FAIL mit der echten
Modellantwort — damit ein Fehlschlag nachvollziehbar bleibt und nicht als
Modellfehler durchgeht, wenn in Wahrheit das Bild fehlt.

Bewertung: getroffen, wenn EINES der `muss`-Begriffe vorkommt (ODER, nicht UND —
gemessener Pruefer-Fehler aus frueheren Runden).
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "http://127.0.0.1:11434/api/generate"


def norm(s: str) -> str:
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"),
                 ("č", "c"), ("ć", "c"), ("š", "s"), ("ž", "z"), ("đ", "d")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s)


def frage_bild(model: str, bild: Path, frage: str, timeout: int = 300) -> tuple[bool, str]:
    """Schickt ein Bild und gibt (erfolgreich, Antwort) zurueck.

    Pfadauflösung: relative Pfade gelten ab dem Projektordner (zwei Ebenen über
    diesem Skript), damit der Pruefsatz portabel bleibt. Absolute Pfade aus
    aelteren Fassungen werden weiter akzeptiert.
    """
    if not bild.is_absolute():
        kandidat = HERE.parent.parent / bild
        if kandidat.is_file():
            bild = kandidat
        elif Path(str(bild)).is_file():
            pass
        else:
            return False, f"BILD FEHLT: {bild} (auch nicht unter {kandidat})"
    if not bild.is_file():
        return False, f"BILD FEHLT: {bild}"
    raw = base64.b64encode(bild.read_bytes()).decode()
    payload = json.dumps({
        "model": model,
        "prompt": frage,
        "images": [raw],
        "stream": False,
        "options": {"temperature": 0, "num_predict": 120},
    }).encode()
    req = urllib.request.Request(API, payload, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, (json.load(r).get("response") or "").strip()
    except Exception as exc:
        return False, f"FEHLER: {type(exc).__name__}: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen2.5vl:3b")
    ap.add_argument("--set", default=str(HERE / "testset_vision.json"))
    ap.add_argument("--id", default=None)
    ap.add_argument("--repeat", type=int, default=1)
    args = ap.parse_args()

    data = json.loads(Path(args.set).read_text(encoding="utf-8"))
    cases = data["cases"]
    if args.id:
        cases = [c for c in cases if c["id"] == args.id]
        if not cases:
            print(f"Kein Fall mit id={args.id}")
            return 2

    print(f"Vision-Pruefsatz: {len(cases)} Faelle · Modell {args.model} · {args.repeat} Lauf/Laeufe\n")
    ergebnisse, details = [], []
    for c in cases:
        treffer = []
        antworten = []
        for _ in range(args.repeat):
            ok, ant = frage_bild(args.model, Path(c["bild"]), c["frage"])
            antworten.append(ant)
            if ok:
                a = norm(ant)
                treffer.append(any(norm(m) in a for m in c["muss"]))
            else:
                treffer.append(False)
        bestanden = sum(treffer) > len(treffer) / 2
        ergebnisse.append(bestanden)
        mark = "OK  " if bestanden else "FAIL"
        kurz = antworten[0].replace("\n", " ")[:70]
        print(f"  [{mark}] {c['id']} ({c['kategorie']:<14}) {kurz}")
        details.append({"id": c["id"], "kategorie": c["kategorie"],
                        "bestanden": bestanden, "antworten": antworten,
                        "muss": c["muss"]})

    n_ok = sum(ergebnisse)
    print(f"\n  Ergebnis: {n_ok}/{len(ergebnisse)} ({n_ok / len(ergebnisse) * 100:.0f} %)")

    out = HERE / "reports" / f"eval_vision_{args.model.replace(':', '_').replace('/', '_')}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({
        "modell": args.model, "repeat": args.repeat,
        "ergebnis": f"{n_ok}/{len(ergebnisse)}",
        "faelle": details,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Bericht: {out}")
    return 0 if n_ok == len(ergebnisse) else 1


if __name__ == "__main__":
    raise SystemExit(main())
