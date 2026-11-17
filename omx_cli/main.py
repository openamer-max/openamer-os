#!/usr/bin/env python3
"""omx — Kommandozentrale fuer OpenAmer Agent-Max.

Drei Saeulen, ein Befehl:
  agent  — Laufzeit des Agenten (OpenAmer-Kern + Max-Schicht)
  model  — OpenAmer-Max-One (ein Modell: Text, Vision, Denken, Werkzeuge, Entscheidungen, Einbetten)
  os     — OpenAmer-OS (Kernel-Prototyp + Userspace-Image)

Grundsatz: omx misst, statt zu behaupten. Jeder Befehl liefert echte
Prozessausgaben, Dateipfade und Zaehlungen — keine geschaetzten Werte.
"""
from __future__ import annotations

import argparse
import sys

from . import doctor, model, osbuild

VERSION = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="omx",
        description="OpenAmer Agent-Max — Kommandozentrale",
        epilog="Beispiele: omx doctor | omx model status | omx os status",
    )
    p.add_argument("--version", action="version", version=f"omx {VERSION}")

    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="Umgebung messen und Luecken benennen")
    d.add_argument("--json", action="store_true", help="Maschinenlesbare Ausgabe")
    d.set_defaults(func=doctor.run)

    m = sub.add_parser("model", help="OpenAmer-Max-One")
    msub = m.add_subparsers(dest="mcmd", required=True)
    ms = msub.add_parser("status", help="Basis, Stufen, Pruefsaetze zaehlen")
    ms.add_argument("--json", action="store_true")
    ms.set_defaults(func=model.status)
    md = msub.add_parser("datagen", help="Trainingssatz aus Fakten + Skills bauen")
    md.add_argument("--out", default=None, help="Zieldatei (.jsonl)")
    md.add_argument("--limit", type=int, default=0, help="Max. Zeilen (0 = alle)")
    md.set_defaults(func=model.datagen)
    me = msub.add_parser("eval", help="Pruefsatz gegen ein Modell fahren")
    me.add_argument("--model", default="openamer-max-tab", help="Ollama-Tag")
    me.add_argument("--set", default="tasks", choices=["tasks", "vision"], help="Pruefsatz")
    me.add_argument("--repeat", type=int, default=1,
                    help="Wiederholungen fuer Streuungsmessung (temp 0 ist nicht deterministisch)")
    me.set_defaults(func=model.eval_run)
    mh = msub.add_parser("health", help="Unsichtbare Modelle finden (Manifeste vs. API)")
    mh.add_argument("--json", action="store_true")
    mh.set_defaults(func=model.health)

    o = sub.add_parser("os", help="OpenAmer-OS")
    osub = o.add_subparsers(dest="oscmd", required=True)
    ost = osub.add_parser("status", help="Kernel-Quellen, Toolchain, Image-Zustand")
    ost.add_argument("--json", action="store_true")
    ost.set_defaults(func=osbuild.status)
    ob = osub.add_parser("build", help="Userspace-Image bauen (Docker via WSL)")
    ob.add_argument("--tag", default="openamer-os:0.1")
    ob.add_argument("--with-agent", action="store_true",
                    help="Agent mit einbacken (Dockerfile.agent)")
    ob.set_defaults(func=osbuild.build)
    op = osub.add_parser("pack", help="Python-Teile des Agenten als Build-Kontext packen")
    op.set_defaults(func=osbuild.pack)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
