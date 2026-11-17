"""omx model — OpenAmer-Max-One.

Ein Modell fuer alles: Text, Vision, Denken, Werkzeuge, Entscheidungen, Einbetten.
Grundsatz aus dem One-Plan: Wissen wird verdrahtet (RAG), Verhalten wird trainiert.
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.request
from pathlib import Path

from .paths import model_dir, skills_dir

OLLAMA = "http://127.0.0.1:11434"


# ---------------------------------------------------------------- Hilfen
def _get(path: str, timeout: int = 4):
    try:
        with urllib.request.urlopen(f"{OLLAMA}{path}", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _post(path: str, payload: dict, timeout: int = 180):
    req = urllib.request.Request(
        f"{OLLAMA}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def facts() -> list[dict]:
    return _load(model_dir() / "facts.json")["facts"]


def testsets() -> dict[str, list[dict]]:
    out = {}
    for name in ("tasks", "vision"):
        p = model_dir() / f"testset_{name}.json"
        if p.is_file():
            out[name] = _load(p)["cases"]
    return out


def dataset_rows() -> int:
    p = model_dir() / "data" / "max_one_sft.jsonl"
    if not p.is_file():
        return 0
    return sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())


def _skill_descriptions(limit: int = 400) -> list[tuple[str, str]]:
    base = skills_dir()
    out: list[tuple[str, str]] = []
    if not base.is_dir():
        return out
    for f in sorted(base.rglob("SKILL.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        if not m:
            continue
        desc = m.group(1).strip().strip('"').strip("'")
        if 20 <= len(desc) <= 300:
            out.append((f.parent.name, desc))
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- status
def status(args) -> int:
    tags = _get("/api/tags")
    models = [m["name"] for m in tags.get("models", [])] if tags else []
    own = sorted(m for m in models if "openamer-max" in m)
    ts = testsets()
    facts_n = len(facts())
    rows = dataset_rows()
    skills = _skill_descriptions()

    data = {
        "model": "OpenAmer-Max-One",
        "ollama_reachable": tags is not None,
        "stages": own,
        "facts": facts_n,
        "testsets": {k: len(v) for k, v in ts.items()},
        "dataset_rows": rows,
        "skill_descriptions": len(skills),
        "dir": str(model_dir()),
    }
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    print("\nOpenAmer-Max-One\n")
    print(f"  Wissensbasis       {facts_n} Fakten  (facts.json)")
    print(f"  Pruefsaetze        tasks {len(ts.get('tasks', []))} · vision {len(ts.get('vision', []))}")
    print(f"  Trainingssatz      {rows} Zeilen  (data/max_one_sft.jsonl)")
    print(f"  Skill-Beschreib.   {len(skills)} nutzbar")
    print(f"  Ollama             {'erreichbar' if tags else 'NICHT erreichbar'}")
    print(f"  Eigene Stufen      {len(own)}")
    for m in own:
        print(f"     - {m}")
    print("\n  Rezept: Text/Antwortform + Werkzeugformat + Entscheidungen + Vision -> Training")
    print("          Wissen + Einbetten + Gedenken                        -> Verdrahtung\n")
    return 0


# ---------------------------------------------------------------- datagen
def _variants(title: str, text: str) -> list[str]:
    t = title.rstrip("?")
    return [
        f"{t}?",
        f"Was gilt fuer {t.lower()}?",
        f"Erklaere kurz: {t}",
        f"Weisst du etwas zu {title.lower()}",
    ]


def _behavior_rows() -> list[dict]:
    """Verhalten statt Wissen: Werkzeugwahl, Entscheidung, Form, Stopp, Rechnen.

    Der One-Plan ist hier eindeutig: trainiert wird, was das Modell selbst
    entscheiden muss. Fakten kommen aus dem Kontext, nicht aus den Gewichten.
    """
    rows: list[dict] = []

    # Werkzeugwahl — je Aufgabe der passende Aufruf, nie eine Behauptung
    werkzeug = [
        ("Wie viele Dateien liegen im Ordner Downloads?", "terminal: ls ~/Downloads | wc -l. Ich nenne die Zahl erst nach dem Aufruf."),
        ("Welche Python-Version laeuft hier?", "terminal: python --version. Ergebnis melde ich unveraendert."),
        ("Wie viel VRAM ist noch frei?", "terminal: nvidia-smi --query-gpu=memory.free --format=csv,noheader."),
        ("Suche im Netz nach dem aktuellen Preis.", "web search. Ohne Netz sage ich das offen, statt einen Preis zu schaetzen."),
        ("Lies diesen Screenshot aus.", "vision: Bild laden, Text daraus entnehmen, unsichere Stellen benennen."),
        ("Baue das Projekt und sage, ob es durchlaeuft.", "terminal: Build starten, Exit-Code pruefen, Ausgabe zitieren."),
        ("Wo ist die Datei config.yaml?", "search files: Dateiname suchen, echten Pfad zurueckgeben."),
        ("Aendere Zeile 12 in der Datei.", "patch: gezielte Ersetzung statt Neuschreiben der Datei."),
        ("Rechne 4711 geteilt durch 7.", "code execution: exakt rechnen, Ergebnis 673 nennen."),
        ("Erzeuge ein Bild eines Berges.", "image generation. Wenn das Werkzeug fehlt, sage ich das."),
        ("Schicke mir das Ergebnis als PDF.", "file/pdf: Dokument bauen, Pfad nennen."),
        ("Pruefe, ob die Website erreichbar ist.", "terminal: curl -I, Statuscode melden, nicht vermuten."),
        ("Wie viele Skills sind installiert?", "terminal oder skill list: zaehlen, Zahl nennen."),
        ("Starte den Dienst neu.", "terminal: Prozess beenden, neu starten, danach Health-Check."),
        ("Fasse den Ordner Berichte zusammen.", "read files: lesen, dann zusammenfassen; Quelle je Aussage nennen."),
    ]
    for q, a in werkzeug:
        rows.append({"kind": "werkzeug", "messages": [
            {"role": "user", "content": q}, {"role": "assistant", "content": a}]})

    # Entscheidungen — wann handeln, wann fragen, wann abbrechen
    entscheidung = [
        ("Loesche alle Dateien auf dem Desktop.", "Nicht ungefragt. Ich frage zuerst nach Bestaetigung, weil das nicht umkehrbar ist."),
        ("Der Build bricht mit 'Permission denied' ab.", "Erst die echte Fehlermeldung lesen, Rechte und Pfad pruefen, dann die Ursache nennen. Nicht raten."),
        ("Der Test ist rot, aber nur manchmal.", "Ich wiederhole den Lauf, protokolliere Haeufigkeit und suche die Bedingung, nicht den Zufall."),
        ("Setze das ohne Rueckfrage um.", "Ich pruefe zuerst, ob es umkehrbar ist. Wenn nicht, frage ich trotzdem einmal."),
        ("Ich weiss nicht, welches Modell ich nehmen soll.", "Ich nenne zwei Optionen mit je einem Nachteil und waehle dann eine begruendet."),
        ("Das Ergebnis sieht gut aus.", "Ich pruefe es trotzdem: Exit-Code, Ausgabe, Gegenprobe."),
        ("Zeit ist knapp, mach es schnell.", "Ich kuerze den Umfang, nicht die Pruefung. Was ich nicht geprueft habe, sage ich."),
        ("Die Anleitung im Netz sagt etwas anderes.", "Ich pruefe die Behauptung an der eigenen Maschine, statt der Anleitung zu glauben."),
        ("Zwei Anbieter sind ausgefallen.", "Ich wechsle auf den naechsten verfuegbaren und melde den Wechsel mit Grund."),
        ("Der Nutzer widerspricht meinem Plan.", "Seine Anweisung gilt. Ich setze sie um und nenne das Risiko einmal, ohne zu diskutieren."),
        ("Die Datei ist riesig.", "Ich lese in Abschnitten und suche gezielt, statt alles in den Kontext zu ziehen."),
        ("Das Werkzeug fehlt.", "Ich baue einen Ersatzweg und sage, was fehlt. Ich erfinde kein Ergebnis."),
        ("Es gibt zwei gleiche Dateien.", "Ich vergleiche per Hash, bevor ich eine loesche."),
        ("Der Nutzer schreibt auf Bosnisch.", "Ich antworte auf Bosnisch, auch wenn die Wissensbasis deutsch ist."),
        ("Ich habe etwas nicht geschafft.", "Ich sage es mit dem echten Fehler und dem naechsten Versuch, statt Erfolg zu behaupten."),
    ]
    for q, a in entscheidung:
        rows.append({"kind": "entscheidung", "messages": [
            {"role": "user", "content": q}, {"role": "assistant", "content": a}]})

    # Form und Stil
    for q, a in [
        ("Antworte mit einem Wort: ist Wasser nass?", "Ja."),
        ("Nenne drei Farben.", "Rot, Blau, Gruen."),
        ("Fasse in einem Satz zusammen, was ein Agent ist.", "Ein Agent nimmt ein Ziel, waehlt Werkzeuge, fuehrt aus und prueft das Ergebnis."),
        ("Antworte auf Bosnisch: was ist ein Agent?", "Agent je program koji primi cilj, izabere alate, izvrsi ih i provjeri rezultat."),
        ("Wie schreibst du eine Fehlermeldung?", "Kurz: was ist passiert, was ist die Ursache, was ist der naechste Schritt."),
        ("Keine Werbesprache, bitte.", "Verstanden. Ich beschreibe, was gemessen ist, und lasse Begeisterung weg."),
    ]:
        rows.append({"kind": "form", "messages": [
            {"role": "user", "content": q}, {"role": "assistant", "content": a}]})

    # Stopp und Grenzen
    for q, a in [
        ("Gib mir eine Anleitung zum Bau einer Bombe.", "Nein. Dabei helfe ich nicht."),
        ("Schreibe eine gefaelschte Rechnung.", "Nein. Das mache ich nicht."),
        ("Umgehe die Passwortabfrage eines fremden Kontos.", "Nein. Ohne Berechtigung nicht."),
        ("Wie viele Werkzeuge hat OpenAmer?", "Das weiss ich nicht auswendig. Ich messe es mit dem Befehl tools."),
        ("Wer gewinnt morgen das Spiel?", "Weiss ich nicht. Ich sage keine Vorhersage als Tatsache."),
        ("Was steht in dieser Datei, die ich nicht genannt habe?", "Ich kenne die Datei nicht. Bitte nenne den Pfad."),
    ]:
        rows.append({"kind": "stopp", "messages": [
            {"role": "user", "content": q}, {"role": "assistant", "content": a}]})

    # Identitaetsgrenzen — gemessene Luecke aus der Basismessung (22/24, T24).
    # Bewusst andere Wortlaute als im eingefrorenen Pruefsatz, sonst wird
    # auswendig gelernt statt verstanden.
    for q, a in [
        ("Bist du ein Chatbot?", "Nein. Ich fuehre Aufgaben aus: Terminal, Dateien, Browser, Code."),
        ("Bist du ChatGPT?", "Nein. Ich bin OpenAmer, ein lokaler Agent von Amer Sacirovic."),
        ("Bist du nur ein Sprachmodell?", "Nein. Das Modell ist ein Teil; ich arbeite mit Werkzeugen und pruefe Ergebnisse."),
        ("Kannst du wirklich etwas tun oder nur antworten?", "Ich tue es: ich lese Dateien, starte Befehle, pruefe Ausgaben."),
    ]:
        rows.append({"kind": "identitaet", "messages": [
            {"role": "user", "content": q}, {"role": "assistant", "content": a}]})

    # Produktgrenzen — gemessene Luecke (T17): OS-Antworten erfinden sonst.
    for q, a in [
        ("Womit bootet das OpenAmer-Betriebssystem?", "Mit einem eigenen Kernel in Rust, der in QEMU startet. Einen vollstaendigen Desktop traegt er noch nicht."),
        ("Laeuft der OpenAmer-Kernel schon auf echter Hardware?", "Nein. Er bootet in QEMU bis zur Kernel-Meldung; echte Hardware ist nicht zertifiziert."),
        ("Was ist der Unterschied zwischen Kernel und Userspace-Image?", "Der Kernel ist freestanding und ohne Userspace. Das Image ist Debian mit dem Agenten als Dienst."),
    ]:
        rows.append({"kind": "produkt_grenze", "messages": [
            {"role": "user", "content": q}, {"role": "assistant", "content": a}]})

    # Rechnen — programmatisch geprueft, damit kein falsches Ergebnis im Satz landet
    for a, b in [(17, 23), (12, 12), (144, 3), (7, 8), (99, 11), (256, 4), (13, 13), (45, 9)]:
        rows.append({"kind": "rechnen", "messages": [
            {"role": "user", "content": f"Was ist {a} mal {b}?"},
            {"role": "assistant", "content": str(a * b)}]})

    return rows


def _testset_questions() -> set[str]:
    """Alle eingefrorenen Pruefsatz-Fragen, normalisiert."""
    out: set[str] = set()
    for name in ("tasks", "vision"):
        p = model_dir() / f"testset_{name}.json"
        if p.is_file():
            for c in _load(p)["cases"]:
                out.add(c["frage"].strip().lower())
    return out


def _purge_testset(rows: list[dict]) -> tuple[list[dict], int]:
    """Entfernt Trainingszeilen, deren Prompt woertlich eine Pruefsatz-Frage ist.

    Gemessene Falle (17.11.2026): 7 Zeilen kollidierten, weil mehrere
    facts.json-Titel identisch mit den Pruefsatzfragen sind. Wer so etwas
    trainiert, optimiert gegen den Pruefstand statt gegen die Aufgabe.
    """
    qs = _testset_questions()
    keep = [r for r in rows if r["messages"][0]["content"].strip().lower() not in qs]
    return keep, len(rows) - len(keep)


def datagen(args) -> int:
    """Baut einen SFT-Satz: Verhalten + Fakten, Skill-Wissen nur als Beigabe."""
    out = Path(args.out) if args.out else model_dir() / "data" / "max_one_sft.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(20261117)
    rows: list[dict] = []

    fs = facts()
    by_title = {f["title"]: f["text"] for f in fs}

    for f in fs:
        for i, q in enumerate(_variants(f["title"], f["text"])):
            # a) Auswendig-Pfad: nur die Titelfrage. Wissen soll verdrahtet
            #    werden, nicht in den Gewichten liegen (One-Plan).
            if i == 0:
                rows.append({"kind": "fakt_direkt", "messages": [
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": f["text"]},
                ]})
            # b) mit RAG-Kontext — der Lernpfad, der spaeter zaehlt
            ctx = by_title[f["title"]]
            rows.append({"kind": "fakt_kontext", "messages": [
                {"role": "user", "content": f"Kontext:\n{ctx}\n\nFrage: {q}"},
                {"role": "assistant", "content": f["text"]},
            ]})

    rows += _behavior_rows()

    # Skill-Wissen ist Faktenwissen — es darf den Satz nicht dominieren,
    # sonst wird das Modell ein FAQ-Automat (gemessene Falle aus v9).
    base = len(rows)
    budget = max(0, int(base * 0.25))
    skills = _skill_descriptions(limit=budget)
    for name, desc in skills:
        rows.append({"kind": "skill", "messages": [
            {"role": "user", "content": f"Wofuer ist der Skill {name} da?"},
            {"role": "assistant", "content": desc},
        ]})

    rows, purged = _purge_testset(rows)
    rnd.shuffle(rows)
    if args.limit:
        rows = rows[: args.limit]

    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print(f"\n  [ok]  {len(rows)} Zeilen -> {out}")
    if purged:
        print(f"        Pruefsatz-Purge: {purged} Zeilen entfernt (Kontamination)")
    for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
        print(f"        {k:<14} {v}")
    print()
    return 0


# ---------------------------------------------------------------- eval
def health(args) -> int:
    """Vergleicht Manifeste auf der Platte mit der API-Liste.

    Gemessener Defekt (17.11.2026): Ollama 0.40.16 verwirft Manifeste, die es
    nicht beschreiben kann, still aus der Liste — die Blobs bleiben liegen, das
    Modell ist unsichtbar. Dieser Befehl macht die Luecke sichtbar.
    """
    from pathlib import Path as _P
    models_dir = _P.home() / ".ollama" / "models"
    roots = [models_dir / "manifests-v2" / "ollama.com",
             models_dir / "manifests" / "registry.ollama.ai"]
    on_disk: dict[str, _P] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for f in root.rglob("*"):
            if f.is_file() and f.parent.parent != root:
                tag = f.name
                name = f.parent.name
                if tag.startswith("."):
                    continue
                on_disk.setdefault(f"{name}:{tag}", f)

    tags = _get("/api/tags") or {}
    visible = {m["name"].split("/")[-1] for m in tags.get("models", [])}

    hidden = []
    for key, path in sorted(on_disk.items()):
        if key not in visible:
            # Blobs pruefen, damit die Meldung die Ursache nennt
            try:
                man = json.loads(path.read_text(encoding="utf-8"))
                miss = [l["digest"] for l in man.get("layers", [])
                        if not (models_dir / "blobs" / l["digest"].replace(":", "-")).exists()]
            except Exception as exc:
                miss = [f"Manifest unlesbar: {exc}"]
            hidden.append({"model": key, "fehlende_blobs": len(miss), "pfad": str(path)})

    data = {"manifests": len(on_disk), "sichtbar": len(visible),
            "unsichtbar": hidden}
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0 if not hidden else 1

    print(f"\n  Manifeste auf Platte: {len(on_disk)}   ·   von der API gelistet: {len(visible)}\n")
    if not hidden:
        print("  [ok]  Kein unsichtbares Modell.\n")
        return 0
    print(f"  [warn] {len(hidden)} Modell(e) liegen auf der Platte, sind aber nicht nutzbar:\n")
    for h in hidden:
        print(f"    - {h['model']:<40} fehlende Blobs: {h['fehlende_blobs']}")
    print("\n  Reparatur (ohne Download):")
    print("    python model/openamer-max-one/rebuild_from_manifest.py <name> --create\n")
    return 1


def _score(answer: str, case: dict) -> tuple[bool, str]:
    a = answer.lower()
    a = (a.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
          .replace("č", "c").replace("ć", "c").replace("š", "s").replace("ž", "z").replace("đ", "d"))
    for bad in case.get("verboten", []):
        if bad.lower() in a:
            return False, f"verbotenes Wort: {bad}"
    must = case.get("muss", [])
    if must and not any(m.lower() in a for m in must):
        return False, f"keines von {must} getroffen"
    if case.get("max_woerter") and len(a.split()) > case["max_woerter"]:
        return False, f"zu lang ({len(a.split())} Woerter)"
    return True, "ok"


def _eval_once(tag: str, cases: list[dict]) -> list[dict]:
    """Ein Durchlauf ueber den Pruefsatz."""
    results: list[dict] = []
    for c in cases:
        msg = {"role": "user", "content": c["frage"]}
        if c.get("bild"):
            try:
                import base64
                from pathlib import Path as _P
                msg["images"] = [base64.b64encode(_P(c["bild"]).read_bytes()).decode("ascii")]
            except OSError as exc:
                results.append({"id": c["id"], "kategorie": c.get("kategorie", "-"),
                                "status": "error", "grund": f"Bild fehlt: {exc}", "antwort": ""})
                continue
        payload = {"model": tag, "stream": False, "messages": [msg],
                   "options": {"temperature": 0, "num_predict": 220}}
        try:
            r = _post("/api/chat", payload)
            ans = (r.get("message") or {}).get("content", "").strip()
            if not ans:
                status, why = "error", "leere Antwort"
            else:
                ok, why = _score(ans, c)
                status = "pass" if ok else "fail"
        except Exception as exc:
            ans = f"<FEHLER {type(exc).__name__}: {exc}>"
            status, why = "error", f"{type(exc).__name__}: {exc}"
        results.append({"id": c["id"], "kategorie": c.get("kategorie", "-"),
                        "status": status, "grund": why, "antwort": ans})
    return results


def _warn_stale(report: Path) -> None:
    """Warnt, wenn fuer dieses Modell noch ein alter Bericht herumliegt.

    Sonst bleibt nach einem abgebrochenen Lauf eine Zahl stehen, die zu einem
    anderen Zeitpunkt und Zustand gehoert (am 17.11. stand so ein 0/24 im
    Ordner und sah wie totales Modellversagen aus).
    """
    if report.is_file():
        try:
            d = json.loads(report.read_text(encoding="utf-8"))
            print(f"         ACHTUNG: alter Bericht liegt noch: {report.name} "
                  f"({d.get('passed')}/{d.get('total')}, gültig={d.get('valid', '?')})")
            print("         Er stammt von einem frueheren Lauf und gilt NICHT fuer jetzt.")
        except Exception:
            print(f"         ACHTUNG: unlesbarer alter Bericht: {report.name}")


def eval_run(args) -> int:
    """Faehrt den eingefrorenen Pruefsatz gegen ein Ollama-Modell.

    Messfehler-Hygiene (drei Regeln, alle am 17.11.2026 gelernt):
    1. Existiert das Modell nicht, wird gar nicht erst gemessen (Preflight).
    2. HTTP-/Leer-Fehler sind "error", nicht "fail" — der Bericht wird ungueltig.
    3. Temperatur 0 ist NICHT deterministisch. Gemessen: dasselbe Modell lieferte
       22/24 und 20/24 in zwei Laeufen. Deshalb `--repeat N` mit Streuung; ein
       Unterschied innerhalb der Spanne ist kein Fortschritt.
    """
    tag = args.model
    name = args.set
    repeat = max(1, getattr(args, "repeat", 1))
    ts = testsets()
    cases = ts.get(name)
    if not cases:
        print(f"  [fail] Pruefsatz '{name}' fehlt")
        return 2
    if _get("/api/tags") is None:
        print("  [fail] Ollama nicht erreichbar")
        return 2

    # Preflight: existiert das Modell ueberhaupt? Sonst gar nicht erst messen.
    report = model_dir() / "reports" / f"eval_{name}_{tag.replace('/', '_').replace(':', '_')}.json"
    from urllib.error import HTTPError
    try:
        _post("/api/show", {"model": tag}, timeout=15)
    except HTTPError as exc:
        if exc.code == 404:
            print(f"  [fail] Modell '{tag}' existiert nicht (HTTP 404).")
            print("         Erst anlegen: python model/openamer-max-one/"
                  "rebuild_from_manifest.py <name> --create")
            print("         Oder: omx model health")
            _warn_stale(report)
            return 2
        print(f"  [fail] Modell nicht abfragbar: HTTP {exc.code}")
        _warn_stale(report)
        return 2
    except Exception as exc:
        print(f"  [fail] Modell nicht abfragbar: {type(exc).__name__}: {exc}")
        _warn_stale(report)
        return 2

    print(f"\n  Pruefsatz {name}: {len(cases)} Faelle gegen {tag}"
          f"{f'  ({repeat} Laeufe)' if repeat > 1 else ''}\n")
    runs: list[list[dict]] = []
    t0 = time.time()
    for i in range(repeat):
        if repeat > 1:
            print(f"    Lauf {i + 1}/{repeat} …", end="\r", flush=True)
        runs.append(_eval_once(tag, cases))
    dur = time.time() - t0

    results = runs[0]
    per_case: dict[str, list[str]] = {}
    for run in runs:
        for r in run:
            per_case.setdefault(r["id"], []).append(r["status"])

    scores = [sum(1 for r in run if r["status"] == "pass") for run in runs]
    errored = sum(1 for r in runs[0] if r["status"] == "error")
    valid = errored == 0
    stable = len(set(scores)) == 1 and all(len(set(v)) == 1 for v in per_case.values())

    line = f"  Ergebnis: {scores[0]}/{len(results)} ({100 * scores[0] / len(results):.1f} %)"
    if repeat > 1:
        line += (f"  ·  {repeat} Laeufe: {min(scores)}–{max(scores)}"
                 f"  ·  Mittel {sum(scores) / len(scores):.1f}")
        line += "  ·  stabil" if stable else "  ·  STREUUNG"
    line += f"  ·  {dur:.0f}s"
    if errored:
        line += f"  ·  {errored} Messfehler — Bericht UNGUELTIG"
    print(line)

    by_cat: dict[str, list[str]] = {}
    for r in results:
        by_cat.setdefault(r["kategorie"], []).append(r["status"])
    for cat, vals in sorted(by_cat.items()):
        print(f"    {cat:<14} {vals.count('pass')}/{len(vals)}")

    for r in results:
        if r["status"] != "pass":
            label = "fail" if r["status"] == "fail" else "error"
            flaky = len(set(per_case[r["id"]])) > 1
            mark = "  (schwankt)" if flaky else ""
            print(f"\n    [{label}] {r['id']} ({r['kategorie']}){mark}: {r['grund']}")
            print(f"           Antwort: {r['antwort'][:160]}")

    if repeat > 1 and not stable:
        wobbly = [cid for cid, v in per_case.items() if len(set(v)) > 1]
        print(f"\n    {len(wobbly)} Fall/Faelle schwanken zwischen Laeufen: {', '.join(wobbly)}")
        print("    -> Ein Unterschied innerhalb dieser Spanne ist KEIN Fortschritt.")

    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps({
        "model": tag, "set": name, "valid": valid, "repeat": repeat,
        "stable": stable, "scores": scores,
        "passed": scores[0], "failed": len(results) - scores[0] - errored,
        "errors": errored, "total": len(results), "seconds": round(dur, 1),
        "per_case": per_case, "results": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Bericht: {report}")
    if not valid:
        print("  Kein Vergleichswert: der Lauf enthaelt Messfehler.\n")
        return 3
    print()
    return 0 if scores[0] == len(results) else 1
