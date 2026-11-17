# OpenAmer Agent-Max — All in One

Ein Projekt, ein Ordner: **Agent, eigenes Modell und eigenes Betriebssystem** —
aus vorhandenen Mitteln, ohne Cloud-Zwang, messbar statt behauptet.

```
OpenAmer All in One/
├── README.md              ← diese Datei
├── START.md               ← Startanleitung und Fehlerbehebung
├── ARCHITEKTUR.md         ← Aufbau, Datenfluss, Messregeln
├── CHANGELOG.md           ← was sich geändert hat
├── VERSION                ← 0.4.0
├── verify.py              ← kanonische Prüfung (62 Linux / 58 Windows Checks)
├── omx, omx.cmd, omx.py   ← Kommandozentrale
├── start.sh               ← Starter Linux/WSL (arbeitet aus diesem Ordner)
├── OpenAmer-OS.cmd        ← Starter Windows
├── agent/                 ← Agent: Quellbaum (src/) + eigene Laufzeit (venv/)
├── model/openamer-max-one/← Modell: Rezept, Fakten, Prüfsätze, Daten, Werkzeuge
├── os/openamer-os/        ← Betriebssystem: Kernel + Docker-Image
├── scripts/               ← Bau- und Betriebsskripte
├── config/                ← Konfigurationsvorlagen
├── docs/                  ← ergänzende Dokumentation (INDEX, MESSUNGEN)
└── dist/                  ← Artefakte (ISO, Icon) — nicht versioniert
```

## Der Ordner ist selbsttragend

Agent, Laufzeit und Modellrezept liegen **im** Ordner — kein Verweis nach außen:

| Teil | Ort | Prüfung |
|---|---|---|
| Agent-Quellbaum (1.173 Dateien) | `agent/src/` | `verify.py` |
| Agent-Laufzeit (Python 3.13) | `agent/venv/` | startet, `Install directory` zeigt auf den Ordner |
| Modellrezept (65.536 Kontext) | `model/openamer-max-one/Modelfile.max-7b` | `PARAMETER num_ctx 65536` |
| Registrierung | `scripts/register-model.sh` | legt `openamer-max-7b` in Ollama an |

Nur zwei Dinge bleiben außerhalb, weil sie dort hingehören: die
**Modellgewichte** (liegen im Ollama-Speicher, 4,7 GB — nicht dupliziert) und
das **Agent-Home** `~/.openamer` (Sitzungen, Gedächtnis, Konfiguration).

## Installieren

**Auf diesem PC ist alles fertig** — Doppelklick auf `OpenAmer-OS`.

**Auf einem neuen PC** (oder nach einer Neuinstallation):

```
INSTALL.cmd        (Windows: Doppelklick)
```

oder in Linux/WSL:

```bash
bash scripts/install.sh          # installiert / repariert
bash scripts/install.sh --check  # prüft nur, ändert nichts
```

Der Installer arbeitet in neun Schritten und ist **idempotent** — ein zweiter
Lauf ändert nichts. Er prüft: System, GPU, Ordner-Python, Laufzeit, Ollama,
Modell, Konfiguration, Befehl, Funktionstest. Ergebnis: `Fehler: 0 /
Warnungen: 0` = startbereit.

### Was der Installer nicht kann

| Hürde | Warum nicht | Was du tun musst |
|---|---|---|
| **WSL2 + Ubuntu** | braucht Administrator und einen Neustart | `wsl --install -d Ubuntu` als Admin, neu starten, Installer erneut |
| **NVIDIA-Treiber** | kommt vom Hersteller, nicht von uns | Windows-Treiber installieren; ohne ihn rechnet das Modell auf der CPU |
| **Modellgewichte** | 4,7 GB, liegen im Ollama-Speicher | `scripts/register-model.sh` baut sie aus dem Basismodell, notfalls aus den Blobs |

### Voraussetzungen

- Windows 10/11 mit WSL2 und einer Ubuntu-Distribution
- Internet beim ersten Lauf (Python-Pakete, Ollama)
- NVIDIA-Treiber für GPU-Betrieb (ohne: CPU, deutlich langsamer)

## Sofort starten

**Windows:** Doppelklick auf `OpenAmer-OS` (Desktop-Verknüpfung) oder
`OpenAmer-OS.cmd`.

**Linux / WSL:**

```bash
./start.sh
```

Beides startet den Agenten mit dem eigenen 7B-Modell auf der GPU.

## Die vier Ebenen

| Ebene | Was | Zustand |
|---|---|---|
| 1 | freestanding Rust-Kernel, bootet in QEMU | ✅ `OpenAmer OS kernel is running.` |
| 2 | Docker-Image mit Agent | ✅ `openamer-os:0.1-agent`, 1,37 GB |
| 3 | Live-ISO, BIOS + UEFI, mit Firmware | ✅ 890 MB, `AGENT-OK` im Boot-Log |
| 4 | **WSL + GPU — der Arbeitsplatz** | ✅ Agent + 7B, 51 tok/s, 91 % VRAM |

Ebene 4 ist der Weg, der heute produktiv läuft. Ebene 1 ist Forschung: der
eigene Kernel trägt noch keinen Userspace.

## Messwerte (17.11.2026)

| Punkt | Wert |
|---|---|
| System | Ubuntu 26.04.1 in WSL2, Kernel 6.18, 16 Kerne, 15 GB RAM |
| GPU | RTX 5060 8151 MiB, Windows-Treiber 621.14, `/dev/dxg` |
| Modell | `openamer-max-7b`, 7,6B, **65.536** Kontext |
| VRAM / Tempo | 6,26 von 6,84 GB (**91 %**), **51 Tokens/s** |
| Agent | OpenAmer v2026.11.17, Python 3.13.18 |
| Antwortzeit | 21–23 s pro Antwort (Kaltstart 30 s bis zur ersten) |
| Prüfstand | Tab-Stufe **19/24**, Watch **16/24** — je 4 Läufe stabil |
| Prüfungen | `verify.py` 52 (Linux) / 55 (Windows) |

## Prüfen

```bash
python3 verify.py        # alle Prüfungen, Exit-Code 0 = grün
python3 verify.py -q     # nur Fehlschläge und Summe
```

Kein Test-Framework, keine Abhängigkeiten. Geprüft wird, was schon einmal
kaputt war: Prüfsatz-Kontamination, Manifest-Reparatur, Launcher,
Kernel-Images, ISO-Inhalt, Starter, GPU-Passthrough.

## Kommandozentrale `omx`

```bash
./omx doctor                  # Umgebung messen
./omx model status            # Wissensbasis, Prüfsätze, Stufen
./omx model health            # unsichtbare Ollama-Modelle finden
./omx model eval --model <tag> --repeat 4
./omx os status               # Kernel-Toolchain, Images
./omx os build [--with-agent] # Userspace-Image
```

## Was ehrlich offen ist

- **Max-One-Adapter:** trainiert, aber 15/24 gegen Basis 16/24 → **schlechter**,
  deshalb nicht ausgeliefert. Es fehlen Daten, nicht Hardware (214 Zeilen gegen
  1.696 im bewährten Lauf).
- **Vision-Messung:** das VL-Modell im Cache ist unvollständig (331 MB).
- **NVIDIA im Live-ISO:** dort rechnet das Modell nur auf der CPU.
- **Installer fürs ISO:** es läuft live, es installiert sich nicht auf Platte.

## Herkunft

Basiert auf **OpenAmer Agent** (github.com/openamer/openamer). Der Ordner bündelt
dessen Laufzeit mit eigener Modell-, OS- und Prüfschicht. Lizenzhinweise des
Upstream-Projekts gelten weiter (siehe `LICENSE.md`).
