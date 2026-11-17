# Architektur — OpenAmer Agent-Max

## Leitentscheidung

Es wird **nichts neu geschrieben, was schon gemessen funktioniert.** Der Agent,
die Trainingspipeline und der Kernel existieren. Max ist die Schicht, die sie zu
einem Produkt zusammenzieht und alles messbar macht.

```
                    omx  (eine Kontrollfläche)
                     │
     ┌───────────────┼────────────────┬──────────────────┐
     ▼               ▼                ▼                  ▼
  doctor         model             os                (später)
  Umgebung    Max-One           OpenAmer-OS         Release
     │               │                │
     ▼               ▼                ▼
┌─────────┐   ┌─────────────┐   ┌──────────────┐
│ Agent   │   │ facts.json  │   │ kernel/ Rust │
│ Kern    │◄──│ testset_*   │   │ image/ Debian│
│ (Repo)  │   │ data/*.jsonl│   │ entrypoint   │
└─────────┘   └─────────────┘   └──────────────┘
     │               │
     ▼               ▼
  Werkzeuge      Ollama
  Terminal       (Basismodell
  Dateien         + Adapter)
  Browser
```

## Datenfluss des Modells

```
facts.json ──┐
             ├─► omx model datagen ─► data/max_one_sft.jsonl ─► QLoRA ─► Adapter
skills/*.md ─┘                                   │                        │
                                                 │                        ▼
testset_tasks.json ──► omx model eval ◄──────────┘              merge → GGUF → Ollama
testset_vision.json ──►     │                                            │
                            ▼                                            ▼
                     reports/eval_*.json  ◄───────── Vergleich gegen Basis
```

**Der Prüfsatz wird nie trainiert.** Er ist eingefroren und trägt sein Datum.
Änderungen daran machen Vergleiche ungültig — deshalb steht das Datum im Report.

## Warum drei statt einer Säule

Der Agent kann heute mehr als das Modell, und das Modell mehr als das OS. Wer
alles in einen Topf wirft, kann nicht mehr sagen, was wo fehlt.

| Säule | Heute belastbar | Heute nicht belastbar |
|---|---|---|
| Agent | Werkzeuge, Skills, Gedächtnis, Messenger, Desktop | — |
| Modell | Prüfstand, Datensatz, Basis messbar | noch kein trainierter Max-One-Adapter |
| OS | Userspace-Image läuft | Kernel trägt keinen Userspace |

## Sicherheitsentscheidungen

1. **Kein root im Betrieb.** Das Image läuft als `uid=1000(openamer)`
   (`docker image inspect … {{.Config.User}}` bestätigt das).
2. **Agent-Code nicht eingebacken.** Er wird gemountet, damit ein Update kein
   neues Image braucht und das Image klein bleibt (258 MB statt >1 GB).
3. **Keine erfundenen Ergebnisse in der Pipeline.** Jeder `omx`-Befehl gibt
   Prozessausgaben und Exit-Codes weiter; `doctor` endet mit Code 2, wenn ein
   Pflicht-Prüfpunkt fehlt.

## Messregeln (verbindlich)

1. Erst messen, dann ändern. `omx doctor` vor jedem Bau.
2. Eine neue Modellfassung ersetzt die alte nur bei **+2 Fällen** im Prüfsatz,
   bei +1 nur ohne Regressionskategorie.
3. Quantisierung wird gegen die bf16-Referenz gemessen, nicht nach Bit-Zahl
   gewählt.
4. Ein Frischtest mit nie trainierten Fragen gehört zu „fertig" — 100 % auf dem
   eingefrorenen Satz ist kein Beweis.
5. Was nicht gemessen wurde, wird als „nicht gemessen" gemeldet, nicht geschätzt.

## Offene Punkte

- Max-One-Adapter trainieren (QLoRA, Basismodell ≤ Tab-Größe lokal möglich).
- Vision-Basismessung braucht ein multimodales Modell (`qwen3-vl`), lokal 8 GB.
- Kernel: Userspace fehlt; `omx os build` baut deshalb Ebene 2.
- RAG-Verdrahtung: `facts.json` → Retriever → Prompt (ohne Training).
