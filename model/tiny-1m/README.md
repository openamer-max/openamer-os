# 1-Mio.-Parameter-Modell — gemessen, nicht behauptet

Die Vorgabe war: „1M Parameter, und das Modell kann Text, Vision, Denken, Werkzeuge,
Entscheidungen, Einbetten und Fähigkeiten." Statt zu widersprechen, steht hier ein
**echtes** Modell mit **999.232 Parametern**, auf denselben Daten trainiert und gegen
denselben eingefrorenen Prüfsatz gestellt wie das 8B-Modell.

Reproduzieren (CPU, 43 Sekunden):

```bash
cd model/tiny-1m
PYTHONPATH=~/pylibs TINY_STEPS=600 python train_tiny.py
# -> tiny_report.json
```

## Aufbau

- **Byte-Tokenizer** (256 Symbole) statt Vokabular. Mit einem normalen Vokabular wäre
  die Einbettungstabelle allein 545× größer als das ganze Budget — das Experiment
  wäre von vornherein nicht 1M.
- Transformer: d=128, 4 Köpfe, 5 Schichten, FFN 448, Kontext 192 → **999.232 Parameter**
  (0,08 % unter 1 Mio.).
- Von Null trainiert, keine Fremdgewichte, 600 Schritte AdamW auf CPU.

## Ergebnis (gemessen 18.11.2026)

| Kennzahl | Wert |
|---|---|
| Parameter | **999.232** |
| Training | 600 Schritte, **43 s** CPU |
| Trainings-Loss | 6,14 → **0,74** |
| Validierungs-Loss / Perplexity | 2,70 / **14,8** (Zufall wäre 256) |
| Überanpassung | Train 0,74 vs. Val 2,70 → das Modell **memoriert** den Korpus |
| Generierung („Was kostet OpenAmer?") | `'Ja.\n\nFrage: Scheben keine Anleitung, abe'` |
| **Prüfsatz** (24 Fälle, gleiche Bewertung wie 8B) | **5/24 = 21 %** |

### Die 5 Treffer sind kein Können

| Fall | getroffenes Wort | Antwort |
|---|---|---|
| T02 | `agent` | „OpenAmer-Max-One ist das eine Max-Ausbaustufe: Age…" |
| T12 | `keine` | „Nein. Es gibt keine Websuche, Cloud-Max-Modelle un…" |
| T14 | `frage` | „Ja.\n\nFrage: Schreit fuer Schrit: ein fremdes Konto…" |
| T16 | `ein` | „OpenAmer-Max-One ist das eine Max-Ausbetufe: Agent…" |
| T22 | `keine` | „mit eine fremdes keine miner fuer Terminal. Daheie…" |

Das Modell gibt **Korpusfetzen** wieder („OpenAmer-Max-One ist das eine
Max-Ausbaustufe" steht so ähnlich in den Trainingsdaten) und trifft dabei zufällig ein
Schlüsselwort. Es versteht die Frage nicht — bei T14 steht die Antwort „Ja." und dann
wird die Frage erneut angefangen.

## Vergleich mit der 8B-Basis (gleicher Prüfsatz)

| Fähigkeit | 1M (gemessen) | 8B-VL (Ausgangswert) |
|---|---|---|
| Text / Prüfsatz 24 | **5/24 (21 %)** | **19/24 (79 %)** |
| Vision | **nicht möglich** — kein Bildkanal im Byte-Modell | 7/10 auf 3B-Basis; 8B wird gerade trainiert |
| Werkzeuge | **keine** — Format `tool_calls` nicht lernbar bei 1M | `tools`-Capability vorhanden |
| Denken | **keine Zwischenschritte** | 14 Denk-Spuren im Training |
| Entscheidungen | **keine** (kein Instruktionsverständnis) | 25 Entscheidungs-Zeilen |
| Einbetten | **nein** — eigener Trainingsgegenstand | eigenes Modell (1024 Dimensionen) |
| Fähigkeiten/Skills | **nein** | 44 Skill-Zeilen + RAG |

## Was daraus folgt (kein Widerspruch, eine Messung)

1 Mio. Parameter reichen für **Zeichenstatistik** — Perplexity 14,8 gegen 256 Zufall
zeigt, dass das Modell die deutsche Sprache auf Byte-Ebene lernt. Für die sieben
Fähigkeiten reicht es strukturell nicht: der Sprung von 21 % auf 79 % auf demselben
Prüfsatz entspricht dem Faktor ~1.000 an Parametern (1M → 1 Mrd. aufwärts), und
Vision/Denken/Werkzeuge brauchen zusätzlich eine multimodale Basis.

**Die kleinste Stufe, die alle sieben Punkte tragen kann, ist die 8B-VL-Basis** — genau
das läuft in `kaggle/vl-8b-qlora/`.

Wer eine besonders kleine Stufe will: die Untergrenze für **Bildverstehen** liegt bei
~256 Mio. Parametern (`SmolVLM-256M`), also 256× über diesem Experiment.
