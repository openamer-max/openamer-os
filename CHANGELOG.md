# Changelog — OpenAmer Agent-Max

Alle Änderungen mit Datum und **gemessenen** Werten. Was nicht gemessen wurde,
steht als „nicht gemessen" dabei.

## 0.4.1 — 2026-11-17 (Modell-Runde)

### Hinzugefügt
- `datagen_maxone.py` — neuer Datensatz-Generator: kategorien­deckend
  (identitaet, fakt, produkt, ehrlich, rechnen, kurz, stopp, entscheidung,
  werkzeug, bosnisch, format), kurze Antworten (Median 42 statt 141 Zeichen),
  `purge_testset()` gegen Prüfsatz-Kontamination, `dedupe()` gegen
  Antwort-Konflikte.
- 5 Trainingsläufe (0,6B) und 4 ausgelieferte Prüfläufe, alle in
  `docs/MESSUNGEN.md` mit Streuung.

### Gefunden (wichtiger als jede Punktzahl)
- **Denkmodus war aktiv.** Ohne `TEMPLATE` nutzt Ollama Qwen3s Standard-Template
  mit ` thinking`. Gemessen: „17 mal 23" → ` thinking 421` statt `391`. Das hat
  **alle** früheren 0,6B-Messungen verfälscht. Mit ChatML ohne Denkblock: `391`.
- **Antwortmuster-Kollaps.** Der erste Datensatz hatte 50 von 330 Zeilen (15 %)
  mit identischer Ablehnung → Modell kollabiert auf ein Muster. Nach Reparatur:
  max. 2,8 %.
- **Halluzination durch Training.** Ein Lauf antwortete auf „Koliko kosta
  OpenAmer?" mit „Zwei Euro pro Befehl." — frei erfunden.

### Behoben
- 26 fehlende Blobs aus `C:\Users\amer7\blobs` (19 GB) in den Ollama-Modellordner
  zusammengeführt; `openamer-max-tab` neu angelegt, `openamer-max-ultra` folgt.
- `omx model health` findet Modelle, die als Manifest vorliegen, aber wegen
  fehlender Blobs nicht gelistet werden.

### Ergebnis der Modell-Runde
**Kein Adapter wird ausgeliefert.** Fünf Läufe auf 0,6B, alle unter der Basis:

| Lauf | Daten | Schritte | Ergebnis |
|---|---|---|---|
| Basis Watch | — | — | **16/24** |
| Lauf 1 | 214 | 20 | 15/24 |
| Lauf 2 | 214 | 60 | 15/24 |
| Lauf 3 | 330 | 50 | 13/24 |
| Lauf 4 | 317 | 175 | 13/24 |

Der Grund ist Kapazität, nicht Trainingszeit: Der Prüfstand verlangt
Produkt-Definitionen, Rechnen und Bosnisch — die Basis selbst erreicht nur
16/24. Nächster Weg: 3B lokal (4,06 GB VRAM gemessen) oder 7B auf gemieteter
GPU (10,24 GB gemessen).

### Nicht gemessen
- Vision-Prüfsatz (VL-Modell im Cache unvollständig, 331 MB)
- GPU im Live-ISO (kein NVIDIA-Treiber eingebaut)
- 3B- und 7B-Training (nicht begonnen — bewusste Entscheidung nach fünf Fehlschlägen)

## 0.4.0 — 2026-11-17

### Hinzugefügt
- **All-in-One-Struktur** `/OpenAmer All in One`: Agent, Modell, OS, Skripte,
  Doku und Artefakte an einem Ort (891 MB, 49 Dateien).
- **Ebene 4: WSL + GPU.** Agent + eigenes 7B-Modell auf der RTX 5060.
  Gemessen: 6,26/6,84 GB VRAM (91 %), 51 Tokens/s, Antwort in 22 s.
- `scripts/wsl-install.sh` — reproduzierbarer Aufbau in einem Befehl.
- `start.sh` (Linux/WSL) und `OpenAmer-OS.cmd` (Windows) als Ein-Klick-Starter.
- Desktop-Verknüpfung `OpenAmer-OS.lnk`.
- `omx model eval --repeat N` — Wiederholungsmessung mit Streuungsausgabe.
- `omx model health` — findet Modelle, die auf der Platte liegen, aber von
  Ollama nicht gelistet werden.
- `rebuild_from_manifest.py` — baut ein Ollama-Modell ohne Download aus seinen
  Blobs neu.
- `CHANGELOG.md`, `VERSION`, `.gitignore`, `LICENSE.md`.

### Behoben
- **Drei Modellstufen unsichtbar** (tab, phone, ultra): Ollama 0.40 verwarf die
  Manifeste (`bad manifest` / `failed to describe model`). Reparatur ohne
  Download über `rebuild_from_manifest.py`.
- **Messfehler als Modellfehler:** ein Lauf gegen ein fehlendes Modell schrieb
  0/24. Jetzt Preflight (`/api/show`), `error` ≠ `fail`, Bericht `valid: false`.
- **Einzelmessungen logen:** dasselbe Modell ergab 22/24 und 20/24. Ursache:
  Temperatur 0 ist nicht deterministisch. Jetzt `--repeat 4` als Standard für
  Vergleiche.
- **Prüfsatz-Kontamination:** 7 von 221 Trainingszeilen waren wörtlich
  Prüfsatzfragen. `_purge_testset()` entfernt sie und meldet die Zahl.
- **Launcher:** MSYS-Pfad (`/c/...` → `C:\c\...`), Windows-`python`-Alias ins
  Leere, Linux `python3` statt `python` — alle drei plattformabhängig gelöst.
- **Kernel-Bau:** `failed to get llvm tools` → `llvm-tools-preview` fehlte.
- **Docker-Image:** Wheel-Bau ist im Projekt gesperrt → editable install.
- **ISO:** getty hielt `/dev/ttyS0`, Beweis-Dienst blockierte → `/dev/console`;
  QEMU fraß das Skript-stdin → `< /dev/null`.

### Gemessen (Baselines)
- Watch-Stufe (0,6B): **16/24** (3 Läufe, stabil)
- Tab-Stufe (7,6B): **19/24** (4 Läufe, stabil)
- Max-One-Adapter 0,6B (214 Zeilen, 60 Schritte, `eval_loss` 0,626):
  **15/24** → schlechter als die Basis, **nicht ausgeliefert**
- Kernel-Bau: 50,9 s; Images `bios.img` 2,5 MB / `uefi.img` 2,1 MB
- Live-ISO: 890 MB, 43.143 Dateien, Firmware + NetworkManager enthalten
- `verify.py`: 52 Prüfungen (Linux) / 55 (Windows), alle grün

### Nicht gemessen
- Vision-Prüfsatz (VL-Modell im HF-Cache unvollständig, 331 MB)
- GPU im Live-ISO (kein NVIDIA-Treiber eingebaut)
- Verhalten auf physischer Hardware (nur QEMU)
