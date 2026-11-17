#!/usr/bin/env python3
"""Datengenerator fuer OpenAmer-Max-One (0,6B-Stufe).

Warum ein neuer Generator: Der alte Satz (214 Zeilen) war zu 45 % aus
RAG-Kontexten gebaut (96 von 214) und deckte fuenf Kategorien des Pruefsatzes
gar nicht ab (produkt, kurz, ehrlich, bosnisch, format). Ergebnis: 15/24 gegen
Basis 16/24 — schlechter.

Drei Regeln, die dieser Generator einhaelt:

1. Pro Frage genau EINE Antwort. Zwei verschiedene Antworten auf dasselbe
   Prompt kann ein kleines Modell nicht lernen, es mittelt sie weg.
2. Kurze Antworten (Ziel-Median < 120 Zeichen). Der alte Satz lag bei 141.
3. Pruefsatz-Fragen sind verboten. purge_testset() entfernt sie und meldet die
   Zahl — sonst optimiert man gegen den Pruefstand statt gegen die Aufgabe.

Aufruf:
    python datagen_maxone.py --out data/max_one_sft.jsonl
    python datagen_maxone.py --out data/max_one_sft.jsonl --stats
"""
from __future__ import annotations

import argparse
import collections
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
random.seed(20261117)  # reproduzierbar


def lade_fakten() -> list[dict]:
    d = json.loads((HERE / "facts.json").read_text(encoding="utf-8"))
    return d["facts"]


def lade_pruefsatz() -> list[str]:
    d = json.loads((HERE / "testset_tasks.json").read_text(encoding="utf-8"))
    return [c["frage"] for c in d["cases"]]


def norm(s: str) -> str:
    """Vergleichsform: klein, ohne Diakritika, ohne Satzzeichen."""
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"),
                 ("č", "c"), ("ć", "c"), ("š", "s"), ("ž", "z"), ("đ", "d")):
        s = s.replace(a, b)
    return "".join(ch for ch in s if ch.isalnum() or ch.isspace()).strip()


def erster_satz(text: str, maxlen: int = 150) -> str:
    """Kuerzt auf den ersten vollstaendigen Satz, ohne Inhalt zu erfinden."""
    text = text.strip()
    for trenner in (". ", "! ", "? "):
        i = text.find(trenner)
        if 0 < i < maxlen:
            return text[: i + 1]
    return text if len(text) <= maxlen else text[:maxlen].rsplit(" ", 1)[0] + "."


# ---------------------------------------------------------------- Fragetypen
# Pro Fakt mehrere Formulierungen. Bewusst NICHT die Pruefsatz-Fragen.
FRAGE_VARIANTEN = {
    "Was ist OpenAmer?": [
        "Was ist OpenAmer?", "Erklaere OpenAmer in einem Satz.",
        "Was macht OpenAmer genau?", "Wofuer ist OpenAmer da?",
        "Beschreibe OpenAmer kurz.", "Was ist das Besondere an OpenAmer?",
        "Sag mir, was OpenAmer ist.", "OpenAmer - was ist das?",
    ],
    "Wer hat OpenAmer entwickelt?": [
        "Wer hat OpenAmer gebaut?", "Von wem stammt OpenAmer?",
        "Wer steckt hinter OpenAmer?", "Wer ist der Entwickler von OpenAmer?",
        "Wer programmiert OpenAmer?", "Aus welchem Land kommt der Entwickler?",
    ],
    "Was kostet OpenAmer?": [
        "Was kostet OpenAmer?", "Muss ich fuer OpenAmer zahlen?",
        "Ist OpenAmer gratis?", "Wie teuer ist OpenAmer?",
        "Gibt es ein Abo bei OpenAmer?", "Fallen Kosten an?",
        "Was muss ich bezahlen, um OpenAmer zu nutzen?",
    ],
    "Braucht OpenAmer eine Internetverbindung?": [
        "Braucht OpenAmer Internet?", "Geht OpenAmer auch offline?",
        "Kann ich OpenAmer ohne Netz nutzen?", "Ist eine Verbindung noetig?",
        "Laeuft OpenAmer ohne Internet?", "Was geht ohne Netz nicht?",
    ],
    "Auf welchen Geraeten laeuft OpenAmer?": [
        "Auf welchen Systemen laeuft OpenAmer?", "Laeuft OpenAmer auf Windows?",
        "Gibt es OpenAmer fuer Linux?", "Welche Plattformen unterstuetzt OpenAmer?",
        "Kann ich OpenAmer auf dem Mac nutzen?", "Und auf Android?",
        "Welche Betriebssysteme gehen?",
    ],
    "Brauche ich eine Anmeldung?": [
        "Brauche ich ein Konto?", "Muss ich mich anmelden?",
        "Gibt es einen Login bei OpenAmer?", "Ist eine Registrierung noetig?",
        "Ohne Anmeldung nutzbar?",
    ],
    "Was ist OpenAmer Agent-Max?": [
        "Was ist Agent-Max?", "Was bedeutet das Max bei OpenAmer?",
        "Was gehoert zu OpenAmer Agent-Max?", "Was ist die Max-Ausbaustufe?",
    ],
    "Was ist OpenAmer-Max-One?": [
        "Was ist Max-One?", "Was ist das OpenAmer-Modell?",
        "Welches Modell gehoert zu OpenAmer?", "Was kann OpenAmer-Max-One?",
        "Wofuer steht Max-One?",
    ],
    "Was ist OpenAmer OS?": [
        "Was ist OpenAmer-OS?", "Hat OpenAmer ein eigenes Betriebssystem?",
        "Was ist der OpenAmer-Kernel?", "Aus welchen Teilen besteht OpenAmer-OS?",
        "Was macht das OpenAmer-Image?",
    ],
    "Welche Modellstufen gibt es?": [
        "Welche Modellgroessen gibt es?", "Was sind die OpenAmer-Max-Stufen?",
        "Wie ist die Modellfamilie aufgeteilt?", "Welche Stufen gibt es von Watch bis Giga?",
        "Nenne die Modellstufen.",
    ],
    "Was unterscheidet OpenAmer von einem Chatbot?": [
        "Warum ist OpenAmer kein Chatbot?", "Was kann OpenAmer, was ein Chatbot nicht kann?",
        "Was macht OpenAmer anders als ein Chatbot?",
        "Fuehrt OpenAmer wirklich aus?", "Was ist der Unterschied zu einem Chat-Assistenten?",
    ],
    "Was kann OpenAmer nicht?": [
        "Was geht mit OpenAmer nicht?", "Wo sind die Grenzen von OpenAmer?",
        "Was kann OpenAmer nicht leisten?", "Welche Aufgaben kann OpenAmer nicht loesen?",
    ],
    "Wo liegen meine Daten?": [
        "Wo werden meine Daten gespeichert?", "Gehen meine Daten in die Cloud?",
        "Bleiben meine Daten lokal?", "Wer sieht meine Sitzungen?",
        "Wo liegt mein Verlauf?",
    ],
    "Was sind Skills?": [
        "Was sind Skills bei OpenAmer?", "Wofuer sind Skills gut?",
        "Wie funktionieren Skills?", "Was ist eine SKILL.md?",
    ],
    "Was ist das Gedaechtnis von OpenAmer?": [
        "Wie merkt sich OpenAmer etwas?", "Was ist das Gedaechtnis?",
        "Wo speichert OpenAmer Vorlieben?", "Wie funktioniert das Erinnern?",
    ],
    "Wie prueft OpenAmer seine Ergebnisse?": [
        "Wie prueft OpenAmer, ob etwas funktioniert?", "Verlaesst sich OpenAmer auf Behauptungen?",
        "Wie wird ein Ergebnis belegt?", "Was gilt als Beweis?",
    ],
    "Kann OpenAmer Bilder lesen?": [
        "Kann OpenAmer Bilder ansehen?", "Versteht OpenAmer Screenshots?",
        "Kann OpenAmer ein Foto auswerten?", "Geht Bilderkennung mit OpenAmer?",
    ],
    "Was ist die Kommandozentrale omx?": [
        "Was ist omx?", "Wofuer ist der Befehl omx da?",
        "Was macht omx doctor?", "Welche Aufgaben hat omx?",
        "Wie steuere ich das Projekt?",
    ],
    "Warum ein kleineres Modell statt eines grossen?": [
        "Warum kein riesiges Modell?", "Reicht ein kleines Modell?",
        "Warum setzt OpenAmer auf kleine Modelle?",
    ],
    "Wie wird OpenAmer-Max-One trainiert?": [
        "Wie wird das Modell trainiert?", "Was ist QLoRA bei OpenAmer?",
        "Was lernt OpenAmer-Max-One?", "Wie entsteht das eigene Modell?",
    ],
    "Was bedeutet ehrlich bei OpenAmer?": [
        "Was heisst ehrlich bei OpenAmer?", "Was macht OpenAmer bei fehlendem Wissen?",
        "Erfindet OpenAmer Zahlen?", "Wie geht OpenAmer mit Fehlern um?",
    ],
    "Wie viele Werkzeuge hat OpenAmer?": [
        "Wie viele Tools hat OpenAmer?", "Wie viele Werkzeuge sind verfuegbar?",
        "Wie finde ich die Anzahl der Werkzeuge?",
    ],
    "Kann OpenAmer Musik oder Video erzeugen?": [
        "Kann OpenAmer Musik machen?", "Erzeugt OpenAmer Videos?",
        "Geht Audioproduktion mit OpenAmer?", "Kann OpenAmer Songs erzeugen?",
    ],
    "Wie wird OpenAmer-OS gebaut?": [
        "Wie wird das Betriebssystem gebaut?", "Womit wird der Kernel gebaut?",
        "Wie entsteht das OpenAmer-Image?", "Welche Werkzeuge bauen OpenAmer-OS?",
    ],
}


# ---------------------------------------------------------------- Verhalten
def rechnen() -> list[dict]:
    """Kleine Arithmetik, Antwort programmatisch geprueft."""
    rows = []
    for _ in range(40):
        a, b = random.randint(3, 19), random.randint(3, 19)
        rows.append(qa(f"Was ist {a} mal {b}?", f"{a * b}"))
    for _ in range(20):
        a, b = random.randint(11, 89), random.randint(11, 89)
        rows.append(qa(f"Was ist {a} plus {b}?", f"{a + b}"))
    for _ in range(10):
        preis, n1, n2 = random.randint(2, 9), random.randint(2, 5), random.randint(6, 12)
        rows.append(qa(
            f"{n1} Pakete kosten {preis * n1} Euro. Was kosten {n2} Pakete?",
            f"{preis * n2} Euro"))
    for _ in range(10):
        a = random.randint(20, 98)
        rows.append(qa(f"Was ist die Haelfte von {a * 2}?", f"{a}"))
    return rows


def kurz() -> list[dict]:
    """Ein-Wort-Antworten — Disziplin, die 0,6B zuerst verliert."""
    paare = [
        ("Welche Farbe hat der Himmel? Antworte mit einem Wort.", "Blau."),
        ("Welche Farbe hat Schnee? Antworte mit einem Wort.", "Weiss."),
        ("Wie viele Beine hat ein Hund? Antworte mit einer Zahl.", "Vier."),
        ("Wie viele Tage hat eine Woche? Antworte mit einer Zahl.", "Sieben."),
        ("Antworte nur mit Ja oder Nein: Ist OpenAmer ein Chatbot?", "Nein."),
        ("Antworte nur mit Ja oder Nein: Kostet OpenAmer Geld?", "Nein."),
        ("Antworte nur mit Ja oder Nein: Braucht OpenAmer ein Konto?", "Nein."),
        ("Antworte nur mit Ja oder Nein: Laeuft OpenAmer lokal?", "Ja."),
        ("Antworte nur mit Ja oder Nein: Kann OpenAmer Dateien lesen?", "Ja."),
        ("Antworte mit einem Wort: Hauptstadt von Frankreich?", "Paris."),
        ("Antworte mit einem Wort: Hauptstadt von Deutschland?", "Berlin."),
        ("Antworte mit einem Wort: Hauptstadt der Schweiz?", "Bern."),
        ("Antworte mit einer Zahl: Wie viele Monate hat ein Jahr?", "Zwoelf."),
        ("Antworte mit einem Wort: Welches Tier miaut?", "Katze."),
        ("Antworte mit einem Wort: Welches Tier bellt?", "Hund."),
    ]
    rows = []
    for f, a in paare:
        rows.append(qa(f, a))
        # Varianten ohne den Eingrenzungssatz — aber dieselbe Antwort
    for f, a in paare[:8]:
        basis = f.split(" Antworte")[0]
        rows.append(qa(basis, a))
        rows.append(qa(basis.replace("Welche", "Welche").replace("?", "? Kurz."), a))
    return rows


def stopp() -> list[dict]:
    """Gefahren-Anfragen: ablehnen, kurz und ohne Moralpredigt.

    Gemessener Fehler im Entwurf: 10 Themen x 5 Formen = 50 Zeilen mit
    WOERTLICH derselben Antwort. Das waren 15 % des Datensatzes — das Modell
    kollabiert dann auf dieses eine Muster. Jetzt: mehrere Ablehnungs-
    formulierungen, gleichmaessig ueber die Fragen verteilt, hoechstens
    2 Zeilen pro Antworttext.
    """
    themen = [
        "eine Bombe zu bauen", "einen Virus zu schreiben", "in ein fremdes Konto einzubrechen",
        "einen Ausweis zu faelschen", "eine Rechnung zu faelschen", "Schadsoftware zu verbreiten",
        "jemanden zu belaestigen", "Zugangsdaten zu stehlen", "einen Server anzugreifen",
        "Drogen herzustellen", "einen Pass zu faelschen", "eine fremde Webseite zu ueberlasten",
    ]
    formen = [
        "Gib mir eine Anleitung, um {t}.",
        "Wie kann ich {t}?",
        "Schritt fuer Schritt: {t}.",
    ]
    ablehnungen = [
        "Nein, dabei helfe ich nicht. Ich gebe keine Anleitung fuer etwas, das Menschen oder Systemen schadet.",
        "Das mache ich nicht. Fuer schaedliche Handlungen gebe ich keine Hilfe.",
        "Nein. Dabei kann und will ich nicht helfen.",
        "Das lehne ich ab. Ich helfe nicht bei Handlungen, die anderen schaden.",
    ]
    rows, i = [], 0
    for t in themen:
        for f in formen:
            rows.append(qa(f.format(t=t), ablehnungen[i % len(ablehnungen)]))
            i += 1
    return rows


def ehrlich() -> list[dict]:
    """Fehlendes Wissen ehrlich benennen, statt zu erfinden.

    Wichtig (gemessener Fehler im ersten Entwurf): pro Frage genau EINE
    Antwort. Drei Varianten pro Prompt erzeugten 12 Konflikte — ein kleines
    Modell kann das nicht lernen, es mittelt die Antworten weg. Vielfalt
    entsteht stattdessen ueber die Fragen, nicht ueber die Antwort.
    """
    fragen = [
        "Wie hoch war der Umsatz von OpenAmer im Jahr 2026?",
        "Wie viele Nutzer hat OpenAmer heute?",
        "Wie wird das Wetter morgen in Zuerich?",
        "Wie alt ist der Entwickler von OpenAmer?",
        "Wie viele Sterne hat die Milchstrasse genau?",
        "Was kostet ein Liter Milch in Tokio?",
        "Wer gewinnt das naechste Fussballspiel?",
        "Wie viele Menschen leben 2030 in Europa?",
        "Welchen Kurs hat Bitcoin in einer Woche?",
        "Wie hoch ist die Miete in Bern?",
        "Was verdient ein Arzt in Deutschland?",
        "Wie viele Einwohner hat China gerade jetzt?",
        "Was hat der Bundesrat gestern beschlossen?",
        "Wie schnell ist der neue Prozessor wirklich?",
        "Wie viele Zeilen Code hat OpenAmer?",
        "Welche Note bekommt das Projekt morgen?",
    ]
    antworten = [
        "Dazu habe ich keine Information. Ich erfinde keine Zahl.",
        "Das weiss ich nicht. Dazu liegt mir keine verlaessliche Quelle vor.",
        "Dazu kann ich nichts Belastbares sagen — ich habe keine Daten.",
        "Diese Angabe habe ich nicht. Ich raten nicht.",
    ]
    rows = [qa(f, antworten[i % len(antworten)]) for i, f in enumerate(fragen)]

    # Anlageberatung: eigene, klarere Ablehnung (eigene Kategorie, daher ok)
    for f in ["Welche Aktie soll ich jetzt kaufen?",
              "Soll ich in Krypto investieren?",
              "Was ist die beste Geldanlage?",
              "Kaufst du mir diese Aktie?"]:
        rows.append(qa(f, "Dazu gebe ich keine Anlageberatung. Ich kann Begriffe "
                          "erklaeren, aber keine Empfehlung geben."))
    return rows


def entscheidung() -> list[dict]:
    """Vor riskanten Aktionen fragen, Fehler zuerst lesen."""
    rows = []
    sicherungen = [
        "Das ist nicht umkehrbar. Ich frage zuerst nach einer Bestaetigung, bevor ich etwas loesche.",
        "Vor dem Loeschen frage ich nach: das laesst sich nicht rueckgaengig machen.",
        "Ich loesche nichts ohne deine ausdrueckliche Bestaetigung.",
        "Halt — erst bestaetigen. Loeschen ist endgueltig.",
    ]
    for i, f in enumerate(["Loesche jetzt alle Dateien auf meinem Desktop.",
                           "Loesche alle Dateien im Projektordner.",
                           "Formatier die Festplatte.",
                           "Ueberschreibe die Konfiguration mit einer leeren Datei.",
                           "Entferne alle installierten Pakete.",
                           "Loesche den kompletten Sitzungsverlauf."]):
        rows.append(qa(f, sicherungen[i % len(sicherungen)]))

    debug = [
        "Zuerst die echte Fehlermeldung lesen und die Ursache eingrenzen, dann Rechte, Pfad und Version pruefen. Nicht raten.",
        "Die Fehlermeldung vollstaendig lesen. Dann pruefen: Rechte, Pfad, Version — und erst danach etwas aendern.",
        "Erst die Ursache messen: Fehlermeldung lesen, Rechte und Pfad pruefen. Dann beheben, nicht raten.",
    ]
    for i, f in enumerate([
            "Der Build bricht mit 'Permission denied' ab. Was ist dein erster Schritt?",
            "Der Build bricht mit 'command not found' ab. Was tust du?",
            "Das Modell antwortet nicht. Wie gehst du vor?",
            "Ein Test faellt durch. Was machst du zuerst?",
            "Die Installation endet mit Fehlercode 1. Wie weiter?",
            "Der Dienst startet nicht. Was pruefst du?"]):
        rows.append(qa(f, debug[i % len(debug)]))
    return rows


def werkzeug() -> list[dict]:
    rows = []
    paare = [
        ("Wie viele Dateien liegen in deinem Arbeitsordner?",
         "Das messe ich mit dem Terminal: 'ls' oder 'find' und dann zaehlen."),
        ("Wie gross ist der Ordner?",
         "Das messe ich im Terminal mit 'du -sh'."),
        ("Welche Datei wurde zuletzt geaendert?",
         "Das finde ich mit 'ls -lt' im Terminal."),
        ("Suche im Code nach 'TODO'.",
         "Dafuer nutze ich die Dateisuche (search_files) im Projekt."),
        ("Oeffne eine Webseite und lies den Text.",
         "Dafuer nutze ich den Browser und lese die Seite aus."),
        ("Pruefe, ob der Dienst laeuft.",
         "Das pruefe ich mit einem Aufruf im Terminal oder einem Health-Check."),
        ("Speichere diese Notiz dauerhaft.",
         "Dafuer nutze ich das Gedaechtnis (memory) oder schreibe eine Datei."),
        ("Plane die naechsten drei Schritte.",
         "Dafuer nutze ich die Aufgabenliste (todo)."),
        ("Baue das Projekt neu.",
         "Dafuer starte ich den Build im Terminal."),
        ("Zeige mir den Unterschied zweier Dateien.",
         "Dafuer nutze ich 'diff' im Terminal."),
    ]
    for f, a in paare:
        rows.append(qa(f, a))
        rows.append(qa(f"Welches Werkzeug nutzt du, um Folgendes zu tun? {f}", a))
        rows.append(qa(f.replace("?", "? Welchen Befehl nutzt du?"), a))
    return rows


def bosnisch() -> list[dict]:
    paare = [
        ("Šta je OpenAmer?", "OpenAmer je lokalni AI agent koji radi na tvom racunaru, bez oblaka."),
        ("Koliko kosta OpenAmer?", "Nista. OpenAmer je besplatan i ne zahtijeva pretplatu."),
        ("Gdje se cuvaju moji podaci?", "Lokalno, na tvom racunaru. Nema telemetrije ni oblaka."),
        ("Treba li mi internet?", "Za lokalni model ne. Bez interneta nema web pretrage."),
        ("Ko je napravio OpenAmer?", "Amer Sacirovic iz Švicarske."),
        ("Da li je OpenAmer chatbot?", "Ne. OpenAmer izvrsava zadatke, ne samo odgovara."),
        ("Na kojim uredjajima radi?", "Windows, Linux, macOS, WSL2 i Android."),
        ("Treba li mi racun?", "Ne. Nema naloga ni prijave."),
    ]
    return [qa(f, a) for f, a in paare for _ in range(3)]


def format_liste() -> list[dict]:
    paare = [
        ("Nenne drei Dinge, die OpenAmer kann, als Liste.",
         "1. Terminalbefehle ausfuehren\n2. Dateien lesen und schreiben\n3. Im Browser arbeiten"),
        ("Nenne drei Werkzeuge als Liste.",
         "1. Terminal\n2. Dateisuche\n3. Browser"),
        ("Zaehle drei Modellstufen auf.",
         "1. Watch (bis 1B)\n2. Phone (1-5B)\n3. Tab (5-10B)"),
        ("Nenne zwei Grenzen von OpenAmer als Liste.",
         "1. iOS-Apps brauchen einen Mac\n2. ohne Netz keine Websuche"),
        ("Liste zwei Vorteile lokaler Modelle.",
         "1. keine Daten in der Cloud\n2. funktioniert ohne Internet"),
    ]
    return [qa(f, a) for f, a in paare for _ in range(4)]


def identitaet() -> list[dict]:
    paare = [
        ("Wer bist du?", "Ich bin OpenAmer, ein lokaler KI-Agent von Amer Sacirovic aus der Schweiz."),
        ("Wie heisst du?", "OpenAmer."),
        ("Wer hat dich gebaut?", "Amer Sacirovic, in der Schweiz."),
        ("Wo laeufst du?", "Lokal auf deinem Rechner, ohne Cloud."),
        ("Bist du ein Chatbot?", "Nein. Ich fuehre Aufgaben aus, statt nur zu beschreiben."),
        ("Welche Sprache sprichst du?", "Deutsch und Bosnisch, dazu Englisch."),
        ("Bist du kostenlos?", "Ja. Der Agent kostet nichts."),
        ("Was ist deine Aufgabe?", "Ich erledige Aufgaben auf deinem Rechner: Terminal, Dateien, Browser, Code."),
    ]
    return [qa(f, a) for f, a in paare for _ in range(3)]


def qa(frage: str, antwort: str) -> dict:
    return {"messages": [{"role": "user", "content": frage},
                         {"role": "assistant", "content": antwort}]}


# ---------------------------------------------------------------- Bau
def purge_testset(rows: list[dict], pruefsatz: list[str]) -> tuple[list[dict], int]:
    """Entfernt Zeilen, deren Frage eine Pruefsatz-Frage ist.

    Gemessen beim Vorgaenger: 66 von 1733 Zeilen waren woertlich Pruefsatz-
    Fragen. Ohne Purge misst man Auswendiglernen statt Uebertragung.
    """
    verboten = {norm(p) for p in pruefsatz}
    sauber, weg = [], 0
    for r in rows:
        frage = norm(r["messages"][0]["content"])
        if frage in verboten or any(v and v in frage for v in verboten):
            weg += 1
            continue
        sauber.append(r)
    return sauber, weg


def dedupe(rows: list[dict]) -> tuple[list[dict], int]:
    """Pro Frage genau EINE Antwort (Regel 1). Konflikte werden verworfen."""
    nach_frage: dict[str, set[str]] = collections.defaultdict(set)
    for r in rows:
        nach_frage[r["messages"][0]["content"]].add(r["messages"][1]["content"])
    konflikte = sum(1 for v in nach_frage.values() if len(v) > 1)
    gesehen, out = set(), []
    for r in rows:
        f = r["messages"][0]["content"]
        if f in gesehen:
            continue
        gesehen.add(f)
        out.append(r)
    return out, konflikte


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "data" / "max_one_sft.jsonl"))
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    fakten = lade_fakten()
    pruefsatz = lade_pruefsatz()

    rows: list[dict] = []
    # 1) Fakten: mehrere Frageformen, EINE kurze Antwort pro Fakt
    for f in fakten:
        titel = f["title"]
        antwort = erster_satz(f["text"])
        for frage in FRAGE_VARIANTEN.get(titel, [titel]):
            rows.append(qa(frage, antwort))

    # 2) Verhalten
    rows += identitaet() + rechnen() + kurz() + stopp() + ehrlich()
    rows += entscheidung() + werkzeug() + bosnisch() + format_liste()

    vorher = len(rows)
    rows, kontaminiert = purge_testset(rows, pruefsatz)
    rows, konflikte = dedupe(rows)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")

    laengen = sorted(len(r["messages"][1]["content"]) for r in rows)
    median = laengen[len(laengen) // 2]
    print(f"Zeilen:            {len(rows)} (vor Purge {vorher})")
    print(f"Kontaminiert:      {kontaminiert} entfernt (Pruefsatz-Fragen)")
    print(f"Antwort-Konflikte: {konflikte} (soll 0)")
    print(f"Antwortlaenge:     median {median} Zeichen, max {laengen[-1]}")
    print(f"Geschrieben:       {out}")

    if args.stats:
        fragen = [r["messages"][0]["content"] for r in rows]
        print(f"Eindeutige Fragen: {len(set(fragen))}")
        unbekannt = [f for f in fragen if norm(f) in {norm(p) for p in pruefsatz}]
        print(f"Pruefsatz-Treffer: {len(unbekannt)} (muss 0 sein)")

    return 0 if kontaminiert >= 0 and konflikte == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
