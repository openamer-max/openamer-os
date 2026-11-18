# VL-8B — Stand, Messung, Grenzen

Kurzfassung: der erste 8B-Bau existiert, ist veroeffentlicht und **noch nicht**
besser als das laufende 7B. Er ist deshalb nicht Standard.

## Was gebaut wurde

| Schritt | Werkzeug | Ergebnis |
|---|---|---|
| Training | `kaggle/vl-8b-qlora/train.py` | QLoRA, r=16, lr 2e-4, 3 Epochen, **303 Schritte**, Loss **0,5957**, 807 Beispiele (657 Text, 150 Bild), VRAM-Spitze 11,42 GiB, 188,8 min |
| Auswertung | `kaggle/vl-8b-eval/eval.py` | 24 Textfaelle + 10 Bildfaelle, gleiche Bewertung wie im Projekt |
| Merge | `tools/merge_lora_stream.py` | Adapter stromweise in die Basis (W^T + (B@A)·α/r), ~2 GB RAM statt 20 GB |
| GGUF | llama.cpp `convert_hf_to_gguf.py` | f16, 15,3 GB |
| Quantisierung | `llama-quantize` | **Q4_K_M, 4,7 GB** |
| Registrierung | `ollama create` | `openamer-max-vl-8b-kandidat` inkl. Systemprompt aus `Modelfile.max-7b` |

## Messung (gleicher Harnisch, 24 Aufgabenfaelle)

| Modell | Treffer |
|---|---|
| `openamer-max-vl-8b-kandidat` | **17/24** |
| `openamer-max-7b` (Betrieb) | **22/24** |

Entscheidung nach `tools/vergleich.py`: **nicht uebernehmen**. 17 < 22, also bleibt
das 7B Standard — die Uebernahme ist an die Messung gebunden, nicht an die Absicht.

## Verteilung

| Kanal | Zustand |
|---|---|
| HuggingFace | **online**: `openamer-max/openamer-max-vl-8b`, GGUF **5.027.784.992 B** (per API und Range-Request geprueft, Kopf `GGUF`) |
| Lokal (Ollama) | **registriert** als `openamer-max-vl-8b`, antwortet ueber die API korrekt |
| GitHub | dieses Repository (Kernel, Werkzeuge, Installer) — 4,7 GB liegen nicht in Git |
| Website | **live**: Karte in der Modellfamilie mit HF-Link und Befehl |

### Lokal installieren

```bash
bash scripts/install-vl8b-local.sh     # laedt per curl, registriert in Ollama
```

Zwei Wege, die hier **nicht** funktionieren, mit Grund:

| Weg | Befund |
|---|---|
| `ollama run hf.co/openamer-max/openamer-max-vl-8b:Q4_K_M` | Ollamas Resolver findet `us.aws.cdn.hf.co` nicht (`no such host`), obwohl Windows den Namen aufloest und die Datei per curl erreichbar ist. Zweimal reproduziert. |
| `ollama run openamer-max-vl-8b` | CLI versucht zu pullen statt lokal zu starten: der Modellspeicher wurde auf `manifests-v2/ollama.com/library/…` umgestellt, `ollama list`, `ollama show` und die API sehen das Modell, die CLI sucht im alten Pfad. |

**Was funktioniert:** die HTTP-API (`/api/chat`) — genau der Weg, den die App und der Agent nutzen. Geprueft: „Wer hat OpenAmer entwickelt?" -> „OpenAmer wurde von Amer Sacirovic aus der Schweiz entwickelt."

### Nebenbefund: Windows-Modellspeicher

Im Windows-Speicher liegen nur noch die drei 8B-Eintraege; das 7B und 16 weitere
Modelle sind dort **nicht mehr sichtbar** (23 Blobs, 8,6 GB). Der WSL-Speicher ist
unberuehrt (11 Modelle), der Agent laeuft: `start.sh --audit` meldet
`Modell: openamer-max-7b registriert` und **0 Probleme**. Wiederherstellung des
Windows-Speichers ist offen (Neuziehen aus HF oder Kopie aus dem WSL-Speicher).

### Automatik-Schutz

`start.sh` waehlt nur noch `openamer-max-vl-8b-64k` vor dem 7B. Der Name ist Absicht:
der Agent verlangt 64k geladenen Kontext, und dieser Bau kann das auf 8 GB VRAM nicht
leisten. Ein 16k-Bau darf deshalb nie automatisch Standard werden — sonst startet der
Agent nicht mehr.

## Zwei harte Grenzen

**1. Kontext.** Der Agent verlangt einen **geladenen** Kontext von mindestens
64.000 Token (`start.sh` setzt `ollama_num_ctx 65536`). Bedarf eines 8B bei 64k:

| Kontext | KV-Cache | + Gewichte 4,7 GB + Bildencoder ~1,2 GB |
|---|---|---|
| 16.384 | 2,25 GB | **8,2 GB** |
| 32.768 | 4,50 GB | 10,4 GB |
| 65.536 | 9,00 GB | **14,9 GB** |

Die RTX 5060 Laptop hat **8.151 MiB**. 8B mit 64k passt nicht — unabhaengig von der
Qualitaet. Entweder laeuft der Agent mit kleinerem Kontext (dann greift seine
Pruefung nicht mehr) oder das 8B bleibt ein Zweitmodell fuer Einzelfragen.

**2. Qualitaet.** 17/24 ist schlechter als 22/24. Naechste Versuche in dieser
Reihenfolge: lernrate 1e-4 statt 2e-4, 2 Epochen statt 3 (Loss 0,60 zeigt
Memorieren), mehr Fakten-Zeilen statt Wiederholungen.

## Reproduzieren

```bash
# Adapter (Kaggle-Ausgabe) -> lokales Ollama-Modell
OMX_8B_NAME=openamer-max-vl-8b-kandidat \
OMX_8B_ADAPTER="C:\Users\amer7\omx-kaggle\openamer-max-vl-8b-qlora-full\adapter" \
python tools/integrate_8b.py

# Uebernahme messen (Exit 0 = besser, Exit 1 = schlechter)
python tools/vergleich.py --neu openamer-max-vl-8b-kandidat --alt openamer-max-7b
```
