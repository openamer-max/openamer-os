# Startbereit — OpenAmer Agent-Max

Ein Klick, und der Agent läuft mit dem eigenen 7B-Modell auf der GPU.
Keine Pfade, keine Kommandos, keine Cloud.

---

## Starten

**Doppelklick auf dem Desktop: `OpenAmer-OS`**

Das war es. Es öffnet sich ein Fenster mit dem Agenten. Der Starter prüft vorher,
ob WSL und der Ollama-Dienst laufen, und startet sie bei Bedarf.

Einzelauftrag ohne Chat-Fenster:

```cmd
OpenAmer-OS.cmd chat -q "Fasse mir den Ordner Berichte zusammen"
```

In WSL direkt (wenn du schon in einem Linux-Terminal bist):

```bash
openamer
```

---

## Was dabei läuft

| Schicht | Wert | geprüft am 17.11.2026 |
|---|---|---|
| System | Ubuntu 26.04.1 in WSL2, Kernel 6.18, 16 Kerne, 15 GB RAM | `uname -a` |
| GPU | RTX 5060 8151 MiB, Windows-Treiber 621.14, `/dev/dxg` | `nvidia-smi` |
| Modell | **openamer-max-7b**, 7,6B Parameter, 65.536 Kontext | 6,26/6,84 GB VRAM (91 %) |
| Tempo | **51 Tokens/s** | gemessen |
| Agent | OpenAmer v2026.11.17 auf Python 3.13.18 | `openamer --version` |
| Antwortzeit | 22–23 s für einen Satz | Session-Log |

---

## Warum WSL und keine Linux-Treiber

WSL nutzt den Windows-Treiber über `/dev/dxg`. Die GPU rechnet mit 91 % im VRAM,
ohne dass im Linux irgendein Treiber installiert werden muss. Das ist der
einzige Weg auf diesem Laptop, bei dem Hardware und Modell ohne Treiberjagd
zusammenkommen.

---

## Wenn etwas nicht startet

| Symptom | Ursache | Lösung |
|---|---|---|
| `openamer: command not found` | in Windows-cmd getippt | `OpenAmer-OS.cmd` nutzen oder in WSL `openamer` |
| Agent startet, antwortet nicht | Ollama-Dienst aus | `wsl -d Ubuntu -- sudo systemctl start ollama` |
| „context too small" | Modell ohne 64k geladen | `openamer-max-7b` verwenden (nicht `openamer-max-tab`) |
| GPU nicht genutzt | `/dev/dxg` fehlt | Windows neu starten; `wsl --shutdown` |
| Alles prüfen | — | `python verify.py` (50 Prüfungen) |

---

## Was noch nicht fertig ist — ehrlich

**Der Max-One-Adapter.** Der heute trainierte Adapter (0,6B, 214 Zeilen) erreicht
15/24 im Prüfstand, die Basis 16/24 — er ist **schlechter** und wird nicht
ausgeliefert. Das laufende 7B-Modell ist die bewährte Tab-Stufe (19/24).

Was fehlt, ist mehr Training, nicht mehr Hardware: Der Datensatz hat 214 Zeilen,
der bewährte Watch-Lauf hatte 1.696.

**Nicht startbereit, weil nicht fertig:**

- Vision-Messung (das VL-Modell im HF-Cache ist unvollständig, 331 MB)
- NVIDIA-Treiber im Live-ISO (dort rechnet das Modell nur auf der CPU)
- Installer für das ISO (es läuft live, es installiert sich nicht auf die Platte)

---

## Die anderen Ebenen (falls du sie brauchst)

| Ebene | Was | Befehl |
|---|---|---|
| 1 | eigener Rust-Kernel, bootet in QEMU | `wsl -d Ubuntu -- bash -s < scripts/boot-test.sh` |
| 2 | Docker-Image mit Agent | `wsl -d Ubuntu -- docker run --rm -it openamer-os:0.1-agent` |
| 3 | Live-ISO, 890 MB, BIOS+UEFI | `dist/openamer-os-20261117.iso` |
| **4** | **WSL + GPU — dieser Weg** | **`OpenAmer-OS.cmd`** |

Alle Skripte liegen in `scripts/`. Prüfung: `python verify.py`.
