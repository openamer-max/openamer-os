#!/usr/bin/env python
"""Volltraining-Daten: Werkzeug-Spuren, Denk-Spuren, Entscheidungen.

Warum diese Datei existiert: der bisherige Satz hatte 15 Werkzeug- und 15
Entscheidungs-Zeilen und **0** Denk-Spuren. Fähigkeiten entstehen nicht aus
Gewichtsoptimierung allein, sondern aus Spuren im Trainingssatz.

Zwei Regeln, die hier gelten:
  * Jede Zeile ist programmatisch richtig — Zahlen werden gerechnet, nicht
    behauptet; Werkzeug-Ergebnisse stehen im Text, damit die Antwort ableitbar ist.
  * Kein Prüfsatz-Wortlaut. `check_dataset.py` prüft das danach.

Aufruf:
    python datagen_full.py tools      > ausgabe_tools.jsonl
    python datagen_full.py think      > ausgabe_think.jsonl
    python datagen_full.py decision   > ausgabe_decision.jsonl
    python datagen_full.py all        > data/full_extra.jsonl
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

RND = random.Random(20261118)
MODELDIR = Path(__file__).resolve().parent


def pruefsatz_fragen() -> set[str]:
    """Fragen der eingefrorenen Pruefsaetze — sie duerfen im Training nicht vorkommen.

    Am 18.11.2026 genau hier passiert: (17, 23) erzeugte 'Was ist 17 mal 23?',
    und das ist eine Pruefsatzfrage. Die Schranke in build_dataset.py fing es.
    """
    out: set[str] = set()
    for name in ("testset_tasks.json", "testset_vision.json"):
        p = MODELDIR / name
        if p.is_file():
            for c in json.loads(p.read_text(encoding="utf-8")).get("cases", []):
                if c.get("frage"):
                    out.add(c["frage"].strip().lower())
    return out


def qa(kind: str, frage: str, antwort: str) -> dict:
    return {"kind": kind,
            "messages": [{"role": "user", "content": frage},
                         {"role": "assistant", "content": antwort}]}


# ---------------------------------------------------------------- Werkzeuge
# (Frage, Werkzeug, Argumente, Ergebnis, Antwort) — das Ergebnis steht woertlich
# im Werkzeug-Output, damit die Antwort daraus ableitbar und pruefbar ist.
TOOL_CASES = [
    # terminal
    ("Nenne mir die Python-Version auf diesem Rechner.", "terminal",
     {"command": "python --version"}, "Python 3.11.17",
     "Auf diesem Rechner laeuft Python 3.11.17."),
    ("Wie viel freier Speicher ist auf C:?", "terminal",
     {"command": "df -h /c"}, "Dateisystem C: 268G frei von 500G",
     "Auf C: sind 268 GB frei."),
    ("Laeuft Ollama gerade?", "terminal",
     {"command": "curl -s http://127.0.0.1:11434/api/tags | head -c 40"},
     '{"models":[{"name":"openamer-max-7b',
     "Ja, Ollama antwortet auf Port 11434 und listet openamer-max-7b."),
    ("Zeig mir die letzten Zeilen des Agenten-Logs.", "terminal",
     {"command": "tail -5 ~/.openamer/logs/agent.log"},
     "2026-11-18 01:02:11 INFO agent.session: turn 4\n2026-11-18 01:02:12 INFO agent.tools: terminal ok",
     "Die letzten Log-Zeilen zeigen einen laufenden Turn 4 und einen erfolgreichen "
     "terminal-Aufruf."),
    ("Welche Version hat der OpenAmer-Agent?", "terminal",
     {"command": "openamer --version"}, "OpenAmer Agent v2026.11.17 (2026.11.17)",
     "Installiert ist OpenAmer Agent v2026.11.17."),
    # read_file
    ("Was steht in der Datei VERSION?", "read_file",
     {"path": "VERSION"}, "0.4.0",
     "In VERSION steht 0.4.0."),
    ("Lies mir die ersten Zeilen von README.md vor.", "read_file",
     {"path": "README.md", "limit": 2},
     "# OpenAmer Agent-Max — All in One\n\nEin Projekt, ein Ordner",
     "Die README beginnt mit „OpenAmer Agent-Max — All in One\" und dem Satz "
     "„Ein Projekt, ein Ordner\"."),
    ("Wie viele Zeilen hat verify.py?", "read_file",
     {"path": "verify.py"}, "410 Zeilen",
     "verify.py hat 410 Zeilen."),
    # write_file
    ("Lege eine Datei notiz.txt mit dem Inhalt „Termin am Freitag\" an.", "write_file",
     {"path": "notiz.txt", "content": "Termin am Freitag"}, "geschrieben: notiz.txt (18 B)",
     "Erledigt: notiz.txt ist angelegt, Inhalt „Termin am Freitag\" (18 Byte)."),
    ("Schreib die Uhrzeit in zeit.txt.", "write_file",
     {"path": "zeit.txt", "content": "01:14"}, "geschrieben: zeit.txt (5 B)",
     "zeit.txt enthaelt jetzt 01:14."),
    # web_search
    ("Such mir die aktuelle Ollama-Version.", "web_search",
     {"query": "ollama latest release version"}, "ollama 0.40.16 (Release-Seite)",
     "Die aktuelle Ollama-Version ist 0.40.16."),
    ("Was ist der Unterschied zwischen QLoRA und LoRA?", "web_search",
     {"query": "QLoRA vs LoRA difference"}, "QLoRA quantisiert die Basis auf 4 Bit, LoRA nicht",
     "QLoRA quantisiert die Basisgewichte auf 4 Bit und trainiert darauf Adapter; "
     "LoRA trainiert Adapter auf unquantisierten Gewichten."),
    # skill_view
    ("Zeig mir die Anleitung für GitHub-Pull-Requests.", "skill_view",
     {"name": "github-pr-workflow"}, "Skill geladen: github-pr-workflow (Branch, Commit, PR, CI)",
     "Die Skill github-pr-workflow beschreibt Branch, Commit, PR und CI-Reihenfolge."),
    ("Wie starte ich OpenAmer-OS?", "skill_view",
     {"name": "openamer-agent-max"}, "Skill geladen: openamer-agent-max (omx, Modell, OS)",
     "Die Skill openamer-agent-max beschreibt omx, Modell und OS-Start."),
    # browser
    ("Öffne die Seite openamer-max.github.io.", "browser_navigate",
     {"url": "https://openamer-max.github.io/"}, "HTTP 200, Titel: OpenAmer — Dein persoenlicher KI-Assistent",
     "Die Seite ist erreichbar (HTTP 200) und traegt den Titel „OpenAmer — Dein "
     "persoenlicher KI-Assistent\"."),
    ("Lies den Preis auf der Seite example.com/pricing.", "browser_navigate",
     {"url": "https://example.com/pricing"}, "HTTP 200, Text: Professional 19 USD pro Monat",
     "Auf der Seite steht: Professional 19 USD pro Monat."),
    # memory
    ("Merk dir, dass ich Antworten auf Deutsch will.", "memory",
     {"action": "add", "target": "user", "content": "Antwortet auf Deutsch"},
     "ok: 1 Eintrag gespeichert",
     "Gemerkt: du willst Antworten auf Deutsch."),
    ("Was hast du dir über meine Sprache gemerkt?", "memory",
     {"action": "list", "target": "user"}, "user: Antwortet auf Deutsch",
     "Bei dir ist gespeichert: Antworten auf Deutsch."),
    # computer_use
    ("Mach einen Screenshot vom Desktop.", "computer_use",
     {"action": "capture", "app": "screen", "mode": "vision"},
     "Bild 1456x910 gespeichert: screen.png",
     "Screenshot erstellt: 1456x910 Pixel, liegt als screen.png."),
    ("Klick im Browser auf Anmelden.", "computer_use",
     {"action": "click", "element": 14}, "effect=confirmed, verified=true",
     "Der Klick wurde ausgefuehrt und bestaetigt (effect=confirmed)."),
    # kanban
    ("Lege eine Kanban-Aufgabe „README pruefen\" an.", "kanban_create",
     {"title": "README pruefen", "assignee": "reviewer"}, "id=42, status=todo",
     "Aufgabe angelegt: id 42, Status todo, zugewiesen an reviewer."),
    ("Zeig mir meine offenen Kanban-Aufgaben.", "kanban_list",
     {"status": "ready"}, "3 Aufgaben: 41, 42, 43",
     "Es sind drei Aufgaben im Status ready: 41, 42 und 43."),
]

# Frage-Varianten, damit dieselbe Spur nicht 3x identisch klingt
TOOL_VARIANTS = {
    "terminal": ["{f}", "Bitte: {f}", "Kurz: {f}"],
    "read_file": ["{f}", "Schau nach: {f}"],
}


def tools() -> list[dict]:
    rows = []
    for i, (frage, name, args, result, antwort) in enumerate(TOOL_CASES, start=1):
        variants = TOOL_VARIANTS.get(name, ["{f}"])
        for v in variants:
            call_id = f"call_{i:03d}"
            row = {"kind": "tool_call", "messages": [
                {"role": "user", "content": v.format(f=frage)},
                {"role": "assistant", "content": None, "tool_calls": [
                    {"id": call_id, "type": "function",
                     "function": {"name": name,
                                  "arguments": json.dumps(args, ensure_ascii=False)}}]},
                {"role": "tool", "tool_call_id": call_id, "name": name, "content": result},
                {"role": "assistant", "content": antwort}]}
            rows.append(row)
    return rows


# ---------------------------------------------------------------- Denken
def _rechenfaelle() -> list[tuple[str, list[str], str]]:
    """(Frage, Schritte, Antwort) — jede Zahl wird hier gerechnet, nicht getippt."""
    faelle = []
    for a, b in [(17, 23), (128, 47), (306, 19), (94, 86), (451, 129), (68, 74)]:
        p = a * b
        schritte = [f"Ich zerlege {b} in {b//10*10} + {b%10}.",
                    f"{a} x {b//10*10} = {a*(b//10*10)}, {a} x {b%10} = {a*(b%10)}.",
                    f"{a*(b//10*10)} + {a*(b%10)} = {p}."]
        faelle.append((f"Was ist {a} mal {b}?", schritte, f"{a} mal {b} ist {p}."))
    for gesamt, prozent in [(240, 15), (1800, 7), (64, 25), (1250, 3)]:
        teil = gesamt * prozent // 100
        schritte = [f"{prozent} % von {gesamt}:",
                    f"{gesamt} x {prozent} = {gesamt * prozent}.",
                    f"{gesamt * prozent} / 100 = {teil}."]
        faelle.append((f"Wie viel sind {prozent} Prozent von {gesamt}?",
                       schritte, f"{prozent} % von {gesamt} sind {teil}."))
    for km, tempo in [(210, 70), (45, 15), (12, 4)]:
        h = km // tempo
        schritte = [f"Zeit = Strecke / Geschwindigkeit.",
                    f"{km} km / {tempo} km/h = {h} h.",
                    f"Das sind {h} Stunden."]
        faelle.append((f"Ich fahre {km} km mit {tempo} km/h. Wie lange dauert das?",
                       schritte, f"Das dauert {h} Stunden."))

    # Einheiten umrechnen — Faktor wird gerechnet, nicht behauptet
    for wert, von, nach, faktor in [(3, "km", "m", 1000), (2, "kg", "g", 1000),
                                    (90, "min", "s", 60), (4, "h", "min", 60),
                                    (2, "l", "ml", 1000)]:
        ergebnis = wert * faktor
        schritte = [f"1 {von} sind {faktor} {nach}.",
                    f"{wert} x {faktor} = {ergebnis}."]
        faelle.append((f"Wie viele {nach} sind {wert} {von}?",
                       schritte, f"{wert} {von} sind {ergebnis} {nach}."))

    # Grad Celsius in Fahrenheit
    for c in [0, 21, 37, 100]:
        f = c * 9 / 5 + 32
        schritte = [f"Formel: F = C x 9/5 + 32.",
                    f"{c} x 9/5 = {c * 9 / 5:g}.",
                    f"{c * 9 / 5:g} + 32 = {f:g}."]
        faelle.append((f"Wie viel sind {c} Grad Celsius in Fahrenheit?",
                       schritte, f"{c} Grad Celsius sind {f:g} Grad Fahrenheit."))

    # Tage zwischen zwei Daten
    for d1, d2 in [((2026, 1, 10), (2026, 3, 15)), ((2026, 6, 1), (2026, 6, 30)),
                   ((2025, 12, 20), (2026, 1, 5))]:
        from datetime import date
        tage = (date(*d2) - date(*d1)).days
        schritte = [f"Erstes Datum: {d1[2]}.{d1[1]}.{d1[0]}.",
                    f"Zweites Datum: {d2[2]}.{d2[1]}.{d2[0]}.",
                    f"Differenz in Tagen: {tage}."]
        faelle.append((f"Wie viele Tage liegen zwischen {d1[2]}.{d1[1]}.{d1[0]} "
                       f"und {d2[2]}.{d2[1]}.{d2[0]}?",
                       schritte, f"Es sind {tage} Tage."))

    # Rechteck: Flaeche und Umfang
    for laenge, breite in [(7, 4), (12, 5), (3, 9)]:
        flaeche, umfang = laenge * breite, 2 * (laenge + breite)
        schritte = [f"Flaeche = Laenge x Breite = {laenge} x {breite} = {flaeche}.",
                    f"Umfang = 2 x (Laenge + Breite) = 2 x ({laenge} + {breite}) "
                    f"= {umfang}."]
        faelle.append((f"Ein Rechteck ist {laenge} cm lang und {breite} cm breit. "
                       f"Wie gross sind Flaeche und Umfang?",
                       schritte, f"Flaeche {flaeche} cm2, Umfang {umfang} cm."))

    # Zinsrechnung (einfach)
    for kapital, prozent, jahre in [(1000, 3, 2), (2500, 1.5, 4), (800, 5, 3)]:
        zins = kapital * prozent / 100 * jahre
        schritte = [f"Zins = Kapital x Zinssatz x Jahre.",
                    f"{kapital} x {prozent}/100 = {kapital * prozent / 100:g} pro Jahr.",
                    f"{kapital * prozent / 100:g} x {jahre} = {zins:g}."]
        faelle.append((f"Wie viel Zins bringt ein Kapital von {kapital} bei {prozent} % "
                       f"in {jahre} Jahren?",
                       schritte, f"Der Zins betraegt {zins:g}."))

    # Rabatt
    for preis, rabatt in [(240, 15), (89, 20), (1250, 10)]:
        neu = preis * (100 - rabatt) / 100
        schritte = [f"Rabatt in Geld: {preis} x {rabatt}/100 = {preis * rabatt / 100:g}.",
                    f"Neuer Preis: {preis} - {preis * rabatt / 100:g} = {neu:g}."]
        faelle.append((f"Ein Artikel kostet {preis} Euro, es gibt {rabatt} % Rabatt. "
                       f"Was kostet er danach?",
                       schritte, f"Er kostet danach {neu:g} Euro."))
    return faelle


def think() -> list[dict]:
    rows = []
    verboten = pruefsatz_fragen()
    for frage, schritte, antwort in _rechenfaelle():
        if frage.strip().lower() in verboten:
            continue          # Pruefsatzfrage — nicht ins Training
        kopf = "Ich pruefe das in drei Schritten, statt zu raten:"
        inhalt = (f"{kopf}\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(schritte, 1))
                  + f"\n\nAntwort: {antwort}")
        rows.append(qa("denken", frage, inhalt))
    # Entscheidungs-Denken: Werkzeug noetig oder nicht?
    entscheidungen = [
        ("Wie spaet ist es?", "Die Uhrzeit kann ich nicht aus dem Kopf wissen — ich lese sie "
                              "vom System.", "terminal", {"command": "date +%H:%M"},
                              "Es ist die Zeit aus dem Systemaufruf."),
        ("Was steht im CHANGELOG unter 0.4.0?", "Der Text liegt in einer Datei, nicht in "
                                                "meinem Wissen.", "read_file",
         {"path": "CHANGELOG.md"}, "Die Zeilen unter 0.4.0 stehen in der Datei."),
        ("Wie heisst die Hauptstadt von Frankreich?", "Das ist Allgemeinwissen, dafuer "
                                                      "brauche ich kein Werkzeug.", None, None,
         "Paris."),
        ("Addiere 19 und 23.", "Rechnen kann ich selbst, ein Werkzeug waere Umweg.", None,
         None, "19 plus 23 ist 42."),
    ]
    for frage, begruendung, name, args, antwort in entscheidungen:
        if name:
            call_id = "call_plan"
            row = {"kind": "denken_tool", "messages": [
                {"role": "user", "content": frage},
                {"role": "assistant", "content": f"Pruefung: {begruendung} Ich nutze {name}.",
                 "tool_calls": [{"id": call_id, "type": "function",
                                 "function": {"name": name,
                                              "arguments": json.dumps(args, ensure_ascii=False)}}]},
                {"role": "tool", "tool_call_id": call_id, "name": name, "content": "ok"},
                {"role": "assistant", "content": antwort}]}
        else:
            row = qa("denken", frage, f"Pruefung: {begruendung}\n\nAntwort: {antwort}")
        rows.append(row)
    return rows


# ---------------------------------------------------------------- Entscheidungen
DECISIONS = [
    ("Loesche alle Dateien im Ordner Downloads.", "stopp",
     "Das loescht Nutzerdaten unwiderruflich. Ich mache das nicht ohne ausdrueckliche "
     "Bestaetigung. Sag „ja, loeschen\" und nenne den Ordner, dann frage ich vor jedem "
     "Schritt nach."),
    ("Wie viele Skills sind installiert?", "werkzeug",
     "Das messe ich, statt zu schaetzen:",
     {"name": "terminal", "args": {"command": "ls ~/.openamer/skills/*/ | wc -l"}},
     "Nach dem Zaehlen nenne ich die Zahl mit dem Befehl dazu."),
    ("Ist das Wetter morgen gut?", "grenze",
     "Wetter kann ich nicht messen — ich habe keinen Zugriff auf Wetterdaten. Ich sage "
     "das offen, statt eine Zahl zu erfinden; mit web_search koennte ich nachsehen, wenn "
     "du willst."),
    ("Schick eine E-Mail an meinen Chef.", "stopp",
     "E-Mail-Versand nach aussen ist eine irreversible Handlung mit Aussenwirkung. Dafuer "
     "brauche ich Adresse, Text und dein ausdrueckliches Go."),
    ("Erklaer mir kurz, was ein LoRA ist.", "antwort",
     "Ein LoRA trainiert kleine Zusatzmatrizen auf ein bestehendes Modell, statt alle "
     "Gewichte zu aendern — dadurch reicht wenig Speicher und der Adapter bleibt klein."),
    ("Optimiere den Code, ohne die Tests zu verlieren.", "werkzeug",
     "Erst messen, dann aendern:", {"name": "terminal", "args": {"command": "pytest -q"}},
     "Ich lasse zuerst die Tests laufen und aendere danach nur, was rot ist."),
    ("Wie viele Einwohner hat Bosnien genau?", "grenze",
     "Eine exakte Einwohnerzahl kann ich nicht garantieren; Schaetzungen schwanken je "
     "nach Quelle und Jahr. Ich nenne die Groessenordnung mit Quellenhinweis, nicht eine "
     "Scheingenauigkeit."),
    ("Was ist 2 hoch 10?", "antwort", "2 hoch 10 ist 1024."),
    ("Starte den Server und deploye in die Produktion.", "stopp",
     "Deploy ist eine Aenderung an einem laufenden System. Ich zeige erst den Diff und "
     "den Health-Check, dann starte ich — mit deiner Freigabe."),
    ("Fasse den Ordner zusammen, auch wenn 500 Dateien drin sind.", "werkzeug",
     "Bei 500 Dateien lese ich nicht blind alles, sondern messe zuerst:",
     {"name": "terminal", "args": {"command": "ls | wc -l"}},
     "Danach entscheide ich, was ich lese, und sage, was ich ausgelassen habe."),
]


def decision() -> list[dict]:
    rows = []
    for frage, art, *rest in DECISIONS:
        if art == "werkzeug":
            text, call, abschluss = rest
            row = {"kind": "entscheidung", "messages": [
                {"role": "user", "content": frage},
                {"role": "assistant", "content": text, "tool_calls": [
                    {"id": "call_d", "type": "function",
                     "function": {"name": call["name"],
                                  "arguments": json.dumps(call["args"], ensure_ascii=False)}}]},
                {"role": "tool", "tool_call_id": "call_d", "name": call["name"], "content": "ok"},
                {"role": "assistant", "content": abschluss}]}
        else:
            (antwort,) = rest
            row = qa("entscheidung", frage, antwort)
        rows.append(row)
    return rows


def main() -> int:
    was = sys.argv[1] if len(sys.argv) > 1 else "all"
    builder = {"tools": tools, "think": think, "decision": decision}
    if was == "all":
        rows = []
        for fn in builder.values():
            rows.extend(fn())
    elif was in builder:
        rows = builder[was]()
    else:
        print(f"unbekannt: {was} (tools|think|decision|all)", file=sys.stderr)
        return 2
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    print(f"# {len(rows)} Zeilen", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
