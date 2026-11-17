# Messungen — alle Reihen mit Streuung

Jede Zahl hier stammt aus einem echten Lauf. Wo eine Streuung existiert, steht
sie dabei; wo eine Aussage schwach ist, steht das ebenfalls.

## Modell-Prüfstand (24 Aufgaben, eingefroren 2026-11-17)

| Modell | Ergebnis | Läufe | Streuung | Aussagekraft |
|---|---|---|---|---|
| `amersacirovic/openamer-max-tab` (7,6B) | **19/24 (79,2 %)** | 4 | 19·19·19·19 | belastbar |
| `openamer-max-tab-rebuild` (gleicher Blob) | **20/24 (83,3 %)** | 4 | 20·20·20·20 | belastbar |
| `amersacirovic/openamer-max-watch` (0,6B) | **16/24 (66,7 %)** | 3 | 16·16·16 | belastbar |
| `openamer-max-one-test` (0,6B, Lauf 1) | **15/24 (62,5 %)** | 3 | 15·15·15 | belastbar |
| `openamer-max-one-v3` (0,6B, Lauf 3) | **13/24 (54,2 %)** | 3 | 13·13·13 | belastbar |
| `openamer-max-one-v3b/v3p` (ChatML / `{{ .Prompt }}`) | **10/24 (41,7 %)** | 3 | 10·10·10 | belastbar |
| `openamer-max-one-v4` (0,6B, Lauf 4, 175 Schritte) | **13/24 (54,2 %)** | 3 | 13·13·13 | belastbar |

**Verworfen:** eine frühere Einzelmessung von 22/24. Bei `--repeat 4` ergab
dasselbe Modell 20/24. Temperatur 0 ist bei Ollama **nicht** deterministisch.

### Feinjustierung auf 0,6B: fünf Läufe, alle unter der Basis
| Lauf | Daten | Schritte | train_loss | eval_loss | Ergebnis |
|---|---|---|---|---|---|
| out_maxone1 | 214 | 20 | 2,75 | 2,03 → 1,96 | 15/24 |
| out_maxone2 | 214 | 60 | 1,16 | 0,626 | 15/24 |
| out_maxone3 | 330 | 50 | 1,47 | 0,562 | 13/24 |
| out_maxone3 (ChatML) | 330 | 50 | — | — | 10/24 |
| out_maxone3 (`{{ .Prompt }}`) | 330 | 50 | — | — | 10/24 |
| out_maxone4 | 317 | 175 | 0,880 | 0,745 | 13/24 |

**Befund: Jeder trainierte Adapter liegt unter der Basis (16/24).**
Ursachen, jede einzeln gemessen:

1. **Denkmodus war an.** Ohne TEMPLATE nutzt Ollama Qwen3s Standard-Template mit
   ` thinking`. Gemessen: „17 mal 23" → ` thinking 421` statt `391`. Mit ChatML ohne
   Denkblock → `391` richtig. Das verfälschte alle früheren 0,6B-Messungen.
2. **Antwortmuster-Kollaps.** Der erste Datensatz hatte 50 von 330 Zeilen
   (15 %) mit wörtlich derselben Ablehnung. Nach der Reparatur: max. 2,8 %.
3. **Katastrophales Vergessen.** T05 („Braucht OpenAmer Internet?") war in der
   Basis richtig und nach dem Training falsch. Das Modell verliert allgemeine
   Fähigkeiten, weil 317 enge Beispiele sie überschreiben.
4. **Kapazität.** Der Prüfstand verlangt Produkt-Definitionen (T16–T18), Rechnen
   (T09/T10) und Bosnisch (T19/T20). Ein 0,6B trägt das nicht — die Basis selbst
   erreicht nur 16/24.
5. **Halluzination als Nebenwirkung.** Auf „Koliko kosta OpenAmer?" antwortete
   ein Lauf **„Zwei Euro pro Befehl."** — frei erfunden. Das ist der gefährlichste
   Fehler und der Grund, warum nichts davon ausgeliefert wird.

**Konsequenz:** Ausgeliefert bleibt die Tab-Stufe (19/24). Der Adapter braucht
eine größere Basis (3B lokal ab 4,06 GB VRAM, 7B nur auf gemieteter GPU mit
gemessenen 10,24 GB) und deutlich mehr Daten — nicht mehr Trainingszeit auf 0,6B.

### Was Training verschoben hat (0,6B, 214 Zeilen, 60 Schritte)

| | Fälle |
|---|---|
| verbessert (+3) | T03 Kosten · T12 Stopp · T23 Chatbot-Unterschied |
| verschlechtert (−4) | T09 17×23 · T14 Löschen bestätigen · T18 `omx doctor` · T24 Chatbot |
| unverändert | T10, T11, T15, T17, T19 |

Nach der Release-Regel („+2 Fälle oder mehr") → **nicht ausgeliefert**.

### Training-Rohdaten

| Lauf | Epochen | Schritte | train_loss | eval_loss | Dauer | VRAM |
|---|---|---|---|---|---|---|
| `out_maxone1` | 4 | 20 | 2,75 | 2,03 → 1,96 | 73,8 s | 3,29 GB |
| `out_maxone2` | 24 (Stop bei 12) | 60 | 1,16 | **0,626** | 161,1 s | 3,29 GB |
| Referenz `out_watch9` (1667 Zeilen) | 3 Etappen | 208 | — | **0,19** | 11,4 min | 2,77 GB |

Der Vergleich zeigt: **Datenmenge, nicht Rechenzeit** war der Engpass.

## Vision-Prüfsatz (10 Fälle, echte eigene Screenshots)

Quelle: 6 Screenshots vom 17.11.2026 (Installer-Log, TUI, Tool-Liste, Login-Fehler).
Kein gekauftes Testmaterial. Skript: `vision_eval.py`, Bilder unter `testdata/vision/`.

| Modell | Ergebnis | Läufe | Anmerkung |
|---|---|---|---|
| `qwen2.5vl:3b` | **7/10 (70 %)** | 2 | Log + TUI perfekt, kleine Schrift schwach |
| `qwen2.5vl:7b` | **8/10 (80 %)** | 2 | besser, aber 12+ min Laufzeit (CPU-Auslagerung) |

### Was das Modell kann — und was nicht

| Kategorie | Fälle | 3B | 7B |
|---|---|---|---|
| `log_lesen` (Versionen, Hashes) | V01–V03 | **3/3** | **3/3** |
| `tui_lesen` (Modellname, Zahlen) | V04–V05 | **2/2** | **2/2** |
| `pfad_lesen` (Dateinamen) | V09 | **1/1** | **1/1** |
| `status` (ja/nein) | V10 | **1/1** | **1/1** |
| `fehler_finden` (markierte Fehler) | V06–V08 | 0/3 | **1/3** |

**Kernaussage: Text aus Screenshots lesen funktioniert (8 von 8 in Log/TUI/Pfad/Status).
Als „fehlend" markierte Einträge erkennen funktioniert nicht** — V07 (✕ vor
`Web Search`, `Browser Automation`, `Skills Hub`) wurde von keinem Modell erkannt,
V08 (`[Errno 11001] getaddrinfo failed`) ebenfalls nicht.

### Drei Messfehler, die ich korrigiert habe

1. **V06 war ein Prüfer-Fehler.** Das Modell antwortete „Yes" — richtig, aber meine
   `muss`-Liste kannte nur `ja`. Ergänzt um `yes`/`success`.
2. **V07 war zuerst ein Timeout, kein Modellfehler.** Mein Skript wertete
   `TimeoutError` als FAIL. Nach Einzeltest mit mehr Zeit: echter Modellfehler.
   Getrennt gehalten, weil `error` ≠ `fail`.
3. **Prompt zählt.** Mit „Lies den Text Zeile für Zeile" wurde V06 aus „Fehlerrichter"
   ein klares „Yes" — aber V07/V08 blieben falsch. Prompt verbessert das Lesen,
   nicht das Verstehen von Symbolen.

### Laufzeit (wichtig für den Einsatz)

| Modell | VRAM | Dauer für 10 Fälle × 2 |
|---|---|---|
| `qwen2.5vl:3b` | passt vollständig | ~3 min |
| `qwen2.5vl:7b` | **wird ausgelagert** | **12–15 min** (CPU) |

Auf 8 GB VRAM ist 7B-VL nicht praktikabel: Es läufz zwar, aber mit CPU-Auslagerung.
Für den Agenten heißt das: **3B-VL für schnelle Bildprüfung, 7B nur wenn Zeit keine Rolle spielt.**

## Stufenvergleich: der Prüfstand braucht 7B

Dieselben 24 Aufgaben, drei Stufen, je 3 Läufe:

| Stufe | Parameter | Modell | Ergebnis |
|---|---|---|---|
| Watch | 0,6B | `amersacirovic/openamer-max-watch` | **16/24 (66,7 %)** |
| Phone | 3B | `amersacirovic/openamer-max-phone` | **16/24 (66,7 %)** |
| Tab | 7,6B | `amersacirovic/openamer-max-tab` | **19/24 (79,2 %)** |

**Der Prüfstand unterscheidet 0,6B und 3B nicht.** Er verlangt Fähigkeiten, die
erst ab etwa 7B vorhanden sind (Produkt-Definitionen, mehrstufiges Rechnen,
Bosnisch). Ein 3B-Training ist damit kein sinnvoller nächster Schritt — die
Kapazität fehlt, nicht die Anpassung.

Die acht Fehlschläge der 3B-Stufe sind aufschlussreich: T08 (Anlageberatung),
T10 (Rechnen), T13 (Werkzeugwahl), T14/T15 (Entscheidung), T17 (Produkt), T22
(Stopp), T24 (Ein-Wort-Antwort) — also genau die Kategorien, die Kontext-
Verständnis und Instruktions-Treue brauchen.

**Folge:** Ein besserer eigener Adapter ist auf 8 GB VRAM nicht erreichbar.
Der einzige gemessene Weg ist 7B-Training auf gemieteter GPU (Kaggle T4 16 GB,
VRAM-Spitze 10,24 GB, historisch 56/61 = 91,8 %).

## Modell-Performance auf der GPU (WSL)

| Modell | Kontext | VRAM | Tokens/s |
|---|---|---|---|
| 7B (`openamer-max-tab-rebuild`) | 16.384 | 5,47/5,47 GB (100 %) | 38,9 |
| 7B (`om7b64k` → `openamer-max-7b`) | **65.536** | 6,26/6,84 GB (**91 %**) | **51,0** |

Beide vollständig auf der RTX 5060. 65.536 Kontext passt, obwohl der KV-Cache
rechnerisch ~3,7 GB bräuchte — Ollama legt 9 % auf die CPU.

## Betriebssystem

| Ebene | Messwert |
|---|---|
| Kernel-Bau | 50,9 s (`cargo build --release`), Fehlversuch vorher: `failed to get llvm tools` |
| Kernel-Boot | Marker `OpenAmer OS kernel is running.` nach GDT/Framebuffer/Memory-Map |
| Kernel-Images | `bios.img` 2,5 MB · `uefi.img` 2,1 MB |
| Docker `openamer-os:0.1` | 983 MB, uid=1000(openamer), Python 3.11.2 |
| Docker `openamer-os:0.1-agent` | 1,37 GB, `OpenAmer Agent v2026.11.17` startbar |
| Live-ISO (mit NVIDIA) | **2,0 GB (2.100.226.048 B)**, BIOS + UEFI, bootet |
| Squashfs | 1,9 GB, 43.000+ Dateien, **6.105 NVIDIA-Dateien** |
| NVIDIA-Treiber | **620.70.06** per DKMS gegen Kernel 6.1.0-50 gebaut (`nvidia.ko` 21 MB) |
| ISO-Firmware | iwlwifi 58 · amdgpu 531 · SOF 338 · Intel-Microcode 127 · AMD 6 |
| ISO-Boot | `OPENAMER-OS-LIVE-READY` → `AGENT-OK` → `LIVE-DONE` |

### Warum NVIDIA aus dem Hersteller-Repo kommen musste

Debian 12 (bookworm) liefert `nvidia-driver 535.309.01` — **zu alt für die
RTX 5060** (Blackwell, sm_120 braucht ≥ 550; gemessen am fehlenden Kernel-Modul).
Das NVIDIA-Repo für Debian 12 bietet bis **620.70.06** und baut per DKMS gegen
den ISO-Kernel:

```
Installing /lib/modules/6.1.0-50-amd64/updates/dkms/nvidia.ko
Installing .../nvidia-uvm.ko   .../nvidia-peermem.ko
Setting up nvidia-kernel-dkms (620.70.06-1)
```

**Ehrliche Einschränkung:** Ob das Modell im Live-ISO die GPU nutzt, ist **nicht
gemessen** — QEMU hat keine NVIDIA-Karte. Belegt ist: Das Modul ist gebaut, im
Image vorhanden (6.105 Dateien), und das ISO bootet mit laufendem Agent. Der
Beweis auf echter Hardware (USB-Stick, Laptop) steht aus.

## Zeit bis zur ersten Antwort

| Weg | Dauer |
|---|---|
| Kaltstart (WSL aus) bis Antwort | **30,1 s** |
| Warmer Start bis Antwort | 21–23 s |
| Modell-Ladezeit allein (7B, 64k) | 7 s |

## Ollama-Bestand

| | Anzahl |
|---|---|
| Manifeste auf der Platte | 29 |
| von der API gelistet (vor der Reparatur) | 7 |
| nach Reparatur + Neustart | 10 |
| Modelle mit fehlenden Blobs (Library) | 19 |

Die fehlenden Blobs der Library-Modelle liegen in `C:\Users\amer7\blobs` (19 GB),
nicht im erwarteten `models\blobs`. Nicht repariert — nur dokumentiert.
