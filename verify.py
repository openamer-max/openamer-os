#!/usr/bin/env python3
"""Kanonische Pruefung fuer OpenAmer Agent-Max.

Kein Test-Framework, keine Abhaengigkeiten — eine Datei, ein Befehl:

    python verify.py          # alle Pruefungen
    python verify.py -q       # nur Fehlschlaege und Summe

Prueft die Dinge, die hier schon einmal kaputt waren: Kontamination des
Trainingssatzes, kaputte Pruefsaetze, Manifest-Reparatur, Launcher, Image-Bauplan.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MDIR = ROOT / "model" / "openamer-max-one"
QUIET = "-q" in sys.argv
IS_WIN = sys.platform == "win32"
fails: list[str] = []
count = 0


def shell(cmd: str, timeout: int = 60) -> tuple[int, str]:
    """Fuehrt einen Shell-Befehl in der OpenAmer-OS-Umgebung aus.

    Auf Windows laeuft er in WSL, auf Linux direkt — so prueft dieselbe Datei
    beide Welten, ohne dass Pfade doppelt gepflegt werden.
    """
    argv = (["wsl", "-d", "Ubuntu", "--", "bash", "-c", cmd] if IS_WIN
            else ["bash", "-c", cmd])
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}"


def check(name: str, cond: bool, detail: str = "") -> None:
    global count
    count += 1
    if not cond:
        fails.append(name)
    if not cond or not QUIET:
        print(f"  {'PASS' if cond else 'FAIL'}  {name}{'  — ' + detail if detail else ''}")


def omx(*args: str, timeout: int = 120) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(ROOT / "omx.py"), *args],
                       capture_output=True, text=True, timeout=timeout, errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def section(title: str) -> None:
    if not QUIET:
        print(f"\n[{title}]")


def load(name: str):
    return json.loads((MDIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- CLI
section("CLI")
for cmd in (["--version"], ["doctor"], ["model", "status"], ["model", "health"],
            ["os", "status"], ["os", "pack"]):
    rc, out = omx(*cmd)
    check(f"omx {' '.join(cmd)}", rc in (0, 1, 2) and bool(out.strip()), f"rc={rc}")
rc, out = omx("doctor")
check("doctor meldet alle vier Bereiche",
      all(a in out for a in ("RUNTIME", "AGENT", "MODEL", "OS")))
check("doctor zaehlt Skills", "SKILL.md" in out)

# Messfehler-Hygiene: ein nicht existierendes Modell muss SOFORT abbrechen
# (rc=2), nicht 24x HTTP 404 als "Modellversagen" verbuchen.
rc, out = omx("model", "eval", "--set", "tasks", "--model", "gibt-es-nicht-xyz")
check("eval bricht bei unbekanntem Modell ab", rc == 2, f"rc={rc}")
check("eval nennt den Grund", "existiert nicht" in out or "nicht erreichbar" in out)

# ---------------------------------------------------------------- Launcher
section("Launcher")
# Beide Launcher werden wirklich ausgefuehrt, nicht nur auf Existenz geprueft.
# Windows-Falle: MSYS `cmd //c` startet cmd interaktiv — deshalb PowerShell.
def msys(p: Path) -> str:
    """Windows-Pfad in die Form, die MSYS-bash versteht (C:/x -> /c/x)."""
    s = p.as_posix()
    return f"/{s[0].lower()}{s[2:]}" if len(s) > 2 and s[1] == ":" else s


def msys_bash() -> str | None:
    """Findet den Git-bash. `bash` im PATH ist auf Windows oft WSL-bash,
    das /c/... nicht kennt — deshalb explizit suchen."""
    import os
    cands = [os.environ.get("OPENAMER_GIT_BASH_PATH", ""),
             r"C:\Users\amer7\AppData\Local\openamer\git\bin\bash.exe",
             r"C:\Program Files\Git\bin\bash.exe"]
    for c in cands:
        if c and Path(c).is_file():
            return c
    return None


bash_exe = msys_bash()
launcher_tests = []
if IS_WIN:
    if bash_exe:
        launcher_tests.append(
            ("omx (bash)", [bash_exe, "-c", f"cd '{msys(ROOT)}' && ./omx --version"]))
    else:
        print("  SKIP  omx (bash) — kein Git-bash gefunden")
    launcher_tests.append(
        ("omx.cmd (PowerShell)",
         ["powershell", "-NoProfile", "-Command", f"& '{ROOT / 'omx.cmd'}' --version"]))
else:
    # Linux/WSL: nur der POSIX-Launcher
    launcher_tests.append(
        ("omx (bash)", ["bash", "-c", f"cd '{ROOT}' && ./omx --version"]))
for label, cmd in launcher_tests:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=90, errors="replace")
        out = (p.stdout + p.stderr).replace("\r", "").strip()
        check(f"{label} startet", p.returncode == 0 and "0.1.0" in out,
              out.splitlines()[0] if out else f"rc={p.returncode}")
    except FileNotFoundError as exc:
        check(f"{label} startet", False, f"{type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- Pruefsaetze
section("Pruefsaetze")
for name, minimum in (("tasks", 24), ("vision", 10)):
    d = load(f"testset_{name}.json")
    cases = d["cases"]
    ids = [c["id"] for c in cases]
    check(f"{name}: >= {minimum} Faelle", len(cases) >= minimum, str(len(cases)))
    check(f"{name}: IDs eindeutig", len(ids) == len(set(ids)))
    check(f"{name}: frage+muss ueberall", all(c.get("frage") and c.get("muss") for c in cases))
    check(f"{name}: eingefroren datiert", bool(d.get("eingefroren")))

# ---------------------------------------------------------------- Wissen
section("Wissensbasis")
facts = load("facts.json")["facts"]
check("24 Fakten", len(facts) == 24, str(len(facts)))
check("Titel eindeutig", len({f["title"] for f in facts}) == len(facts))
check("Titel+Text ueberall", all(f.get("title") and f.get("text") for f in facts))

# ---------------------------------------------------------------- Datensatz
section("Trainingssatz")
DATA = MDIR / "data" / "max_one_sft.jsonl"
rows = None
if not DATA.is_file():
    # Ein frischer Klon ohne Trainingsdaten darf die Pruefung nicht abbrechen:
    # frueher warf das hier FileNotFoundError und der ganze Lauf starb an
    # Zeile 152 — Strukturpruefungen liefen nie.
    print(f"  SKIP  Trainingssatz fehlt ({DATA.name}) — Zeilen/Verteilung ungeprueft")
else:
    rows = [json.loads(l) for l in DATA.read_text(encoding="utf-8").splitlines() if l.strip()]

if rows is None:
    pass
else:
    check("Datensatz gefuellt", len(rows) > 150, f"{len(rows)} Zeilen")
    check("jede Zeile user->assistant mit Inhalt", all(
        len(r.get("messages", [])) == 2
        and r["messages"][0]["role"] == "user" and r["messages"][1]["role"] == "assistant"
        and r["messages"][0]["content"].strip() and r["messages"][1]["content"].strip()
        for r in rows))

    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r.get("kind", "?")] = kinds.get(r.get("kind", "?"), 0) + 1
    check("Skill-Anteil <= 25 % (kein FAQ-Automat)", kinds.get("skill", 0) / len(rows) <= 0.25,
          f"{kinds.get('skill', 0) / len(rows):.1%}")
    behaviour = sum(v for k, v in kinds.items() if k in (
        "werkzeug", "entscheidung", "form", "stopp", "identitaet", "produkt_grenze", "rechnen"))
    check("Verhaltensanteil >= 15 %", behaviour / len(rows) >= 0.15, f"{behaviour / len(rows):.1%}")

    # Kontamination: kein Prompt darf woertlich eine Pruefsatzfrage sein
    frozen = {c["frage"].strip().lower()
              for n in ("tasks", "vision") for c in load(f"testset_{n}.json")["cases"]}
    leaks = [r for r in rows if r["messages"][0]["content"].strip().lower() in frozen]
    check("keine Pruefsatz-Kontamination", not leaks, f"{len(leaks)} Treffer")

# ---------------------------------------------------------------- Manifest-Werkzeug
section("Manifest-Reparatur")
sys.path.insert(0, str(MDIR))
try:
    import rebuild_from_manifest as rfm

    # Portabel: irgendein vorhandenes Modell nehmen (Manifest mit Tag "latest")
    probe = None
    for root in rfm.MANIFEST_ROOTS:
        for ns in root.iterdir():
            for name in (ns.iterdir() if ns.is_dir() else []):
                if (name / "latest").is_file():
                    probe = name.name
                    break
            if probe:
                break
        if probe:
            break
    if not probe:
        check("Modelfile erzeugt", False, "kein Manifest in der Bau-Umgebung")
    else:
        mf = rfm.build(probe)
        txt = mf.read_text(encoding="utf-8")
        check("Modelfile erzeugt", mf.is_file(), f"{probe}: {mf.stat().st_size} B")
        check("FROM-Zeile vorhanden", "FROM " in txt.splitlines()[0])
        check("kein rohes JSON", '{"num_ctx"' not in txt)
        mf.unlink(missing_ok=True)
except Exception as exc:
    check("Modelfile erzeugt", False, f"{type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- OS
section("OS-Bauplan")
for f in ("Dockerfile", "Dockerfile.agent", "entrypoint.sh"):
    check(f"{f} vorhanden", (ROOT / "os" / "openamer-os" / f).is_file())
base = (ROOT / "os" / "openamer-os" / "Dockerfile").read_text(encoding="utf-8")
agent = (ROOT / "os" / "openamer-os" / "Dockerfile.agent").read_text(encoding="utf-8")
check("Basis-Image laeuft nicht als root", "USER openamer" in base)
check("Agent-Image nutzt editable install", "pip install --no-cache-dir -e" in agent)
check("Agent-Image behaelt Quellbaum", "/opt/openamer/src" in agent and "rm -rf /tmp/src" not in agent)

# Kernel-Bau: Skripte vorhanden und ohne Argument-Quoting (bash -s)
section("Kernel-Bau")
for f in ("install-kernel-toolchain.sh", "build-kernel.sh", "boot-test.sh"):
    check(f"scripts/{f} vorhanden", (ROOT / "scripts" / f).is_file())
rc, out = omx("os", "status")
check("os status meldet Toolchain-Zustand",
      "bereit" in out or "NICHT bereit" in out)
check("os status nennt den Bauweg", "build-kernel.sh" in out)

# Gebaute Kernel-Images liegen in der Bau-Umgebung, nicht im Repo.
# Achtung: /root ist als normaler Benutzer nicht lesbar — dann wird
# uebersprungen statt als Fehler gezaehlt (gemessener Fall: WSL laeuft als amer7).
rc, out = shell(
    "for d in /root/openamer-os-build $HOME/openamer-os-build; do "
    "ls $d/os/target/images/*.img 2>/dev/null; done | wc -l")
rc2, zugang = shell("ls /root/openamer-os-build >/dev/null 2>&1 && echo JA || echo NEIN")
try:
    n_imgs = int(out.strip().splitlines()[0]) if out.strip() else 0
except (ValueError, IndexError):
    n_imgs = 0
if n_imgs >= 2:
    check("Kernel-Images gebaut (bios+uefi)", True, f"{n_imgs} Images")
elif "NEIN" in zugang:
    print("  SKIP  Kernel-Images — Bau-Ordner unter /root nicht lesbar (kein root)")
else:
    check("Kernel-Images gebaut (bios+uefi)", False, f"{n_imgs} Images")

# ---------------------------------------------------------------- ISO
section("ISO")
isos = sorted((ROOT / "dist").glob("openamer-os-*.iso")) if (ROOT / "dist").is_dir() else []
if isos:
    check("ISO in dist/ vorhanden", True, f"{len(isos)} Datei(en)")
else:
    # Ein frischer Klon hat keine 2,0-GB-ISO im Repo (.gitignore) — sie liegt als
    # Release-Asset. Das ist kein Mangel des Klons, also dort nachsehen.
    rc, rel = shell("curl -s --max-time 15 https://api.github.com/repos/openamer-max/"
                    "openamer-os/releases/latest | grep -c 'openamer-os-.*[.]iso'")
    if rel.strip() not in ("", "0"):
        print("  SKIP  ISO nicht lokal — liegt im Release "
              "(https://github.com/openamer-max/openamer-os/releases/latest)")
    else:
        check("ISO in dist/ vorhanden", False, "0 Datei(en), auch kein Release-Asset")
if isos:
    biggest = max(isos, key=lambda p: p.stat().st_size)
    mb = biggest.stat().st_size / 1e6
    check("ISO plausibel gross (> 500 MB, Firmware drin)", mb > 500, f"{mb:.0f} MB")
    # Boot-Beweis: das Log des letzten QEMU-Laufs muss die Marker enthalten
    rc, out = shell("grep -a -c 'OPENAMER-OS-AGENT-OK' /root/openamer-iso/boot-test.log 2>/dev/null")
    rc2, zugang = shell("ls /root/openamer-iso >/dev/null 2>&1 && echo JA || echo NEIN")
    try:
        log_ok = int(out.strip().splitlines()[0] if out.strip() else 0) > 0
    except (ValueError, IndexError):
        log_ok = False
    if log_ok:
        check("Boot-Log zeigt OPENAMER-OS-AGENT-OK", True)
    elif "NEIN" in zugang:
        print("  SKIP  Boot-Log — /root nicht lesbar (kein root)")
    else:
        check("Boot-Log zeigt OPENAMER-OS-AGENT-OK", False)

# ---------------------------------------------------------------- Installation (Ebene 4)
section("OpenAmer-OS Installation")
# Agent liegt bevorzugt im Projektordner (agent/), sonst in einer Alt-Installation.
rc, out = shell(
    f"test -x '{ROOT}/agent/venv/bin/openamer' && echo ORDNER_OK; "
    "test -x $HOME/openamer-os/venv/bin/openamer && echo HOME_OK; "
    "test -e /dev/dxg && echo GPU_OK; "
    "curl -s --max-time 4 http://127.0.0.1:11434/api/tags | grep -c 'openamer-max-7b'")
_agent_ok = ("ORDNER_OK" in out) or ("HOME_OK" in out)
if _agent_ok:
    check("Agent installiert", True, "im Projektordner" if "ORDNER_OK" in out else "in $HOME")
elif (ROOT / "agent").is_dir() or not IS_WIN:
    # Frischer Klon: die Laufzeit entsteht erst durch scripts/install.sh.
    print("  SKIP  Agent nicht installiert — erst 'bash scripts/install.sh' (Windows: INSTALL.cmd)")
else:
    print("  SKIP  Agent-Installation — Quell-Ordner unter Windows (Laufzeit liegt im Ziel)")
check("GPU-Passthrough aktiv (/dev/dxg)", "GPU_OK" in out)
tail = out.strip().splitlines()[-1:] if out.strip() else []
check("Modell openamer-max-7b vorhanden", tail not in ([], ["0"]), f"{tail}")

# ---------------------------------------------------------------- Startbereit
section("Startbereit")
check("START.md vorhanden", (ROOT / "START.md").is_file())
check("start.sh (Linux/WSL) vorhanden", (ROOT / "start.sh").is_file())

starter_txt = (ROOT / "start.sh").read_text(encoding="utf-8") if (ROOT / "start.sh").is_file() else ""
check("start.sh heilt die Config", "config set model.default" in starter_txt)
check("start.sh synct Skills", "rsync" in starter_txt and "skills" in starter_txt)
check("start.sh hat Audit-Modus", "--audit" in starter_txt)

cmd_txt = (ROOT / "OpenAmer-OS.cmd").read_text(encoding="utf-8", errors="replace") if (ROOT / "OpenAmer-OS.cmd").is_file() else ""
check("Windows-Starter nutzt start.sh", "start.sh" in cmd_txt)

if IS_WIN:
    starter = ROOT / "OpenAmer-OS.cmd"
    check("Starter OpenAmer-OS.cmd vorhanden", starter.is_file())
    desktop_lnk = Path.home() / "Desktop" / "OpenAmer-OS.lnk"
    check("Desktop-Verknuepfung vorhanden", desktop_lnk.is_file(), str(desktop_lnk))
    # Starter wirklich ausfuehren (PowerShell, weil MSYS `cmd //c` interaktiv startet)
    try:
        p = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"& '{starter}' --version"],
            capture_output=True, text=True, timeout=120, errors="replace")
        out = (p.stdout or "") + (p.stderr or "")
        check("Starter startet den Agenten", "OpenAmer Agent v" in out,
              out.strip().splitlines()[-1] if out.strip() else "keine Ausgabe")
    except Exception as exc:
        check("Starter startet den Agenten", False, f"{type(exc).__name__}: {exc}")
else:
    if not _agent_ok:
        # start.sh beendet sich ohne Agent mit Code 2 ("Einrichten: install.sh").
        # Das ist auf einem frischen Klon korrekt und kein Fehlschlag.
        print("  SKIP  start.sh-Start — Agent noch nicht installiert (bash scripts/install.sh)")
    else:
        rc, out = shell(f"bash '{ROOT}/start.sh' --version", timeout=120)
        check("start.sh startet den Agenten", "OpenAmer Agent v" in out,
              out.strip().splitlines()[-1] if out.strip() else f"rc={rc}")

rc, out = shell("command -v openamer >/dev/null && echo PATH_OK")
check("Befehl openamer global im PATH", "PATH_OK" in out)

# ---------------------------------------------------------------- Selbsttragend
section("Selbsttragender Ordner")
# Der Ziel-Ordner muss ohne externe Installation funktionieren: Agent-Quellbaum,
# eigene Laufzeit und Modellrezept liegen unter agent/ und model/.
# Der Quell-Ordner unter Windows hat bewusst kein agent/ — dort wird uebersprungen.
if not (ROOT / "agent").is_dir():
    print("  SKIP  kein agent/ — dies ist der Quell-Ordner, nicht das Ziel")
else:
    agent_src = ROOT / "agent" / "src" / "pyproject.toml"
    agent_bin = ROOT / "agent" / "venv" / "bin" / "openamer"
    check("Agent-Quellbaum im Ordner", agent_src.is_file(), str(agent_src.parent.parent))
    check("Agent-Laufzeit im Ordner", agent_bin.is_file())

    if agent_bin.is_file():
        try:
            p = subprocess.run([str(agent_bin), "--version"], capture_output=True,
                               text=True, timeout=90, errors="replace")
            out = (p.stdout or "") + (p.stderr or "")
            check("Ordner-Agent startet", "OpenAmer Agent v" in out,
                  out.strip().splitlines()[0] if out.strip() else "keine Ausgabe")
            check("Ordner-Agent nutzt Ordner-Quellen", str(ROOT) in out,
                  "Install directory zeigt auf den Ordner")
        except Exception as exc:
            check("Ordner-Agent startet", False, f"{type(exc).__name__}: {exc}")

modelfile = MDIR / "Modelfile.max-7b"
check("Modellrezept im Ordner", modelfile.is_file(), str(modelfile))
if modelfile.is_file():
    mf = modelfile.read_text(encoding="utf-8")
    check("Rezept setzt num_ctx 65536", "PARAMETER num_ctx 65536" in mf)
    check("Rezept hat FROM + SYSTEM", "FROM " in mf and "SYSTEM" in mf)

check("Registrierungs-Skript vorhanden", (ROOT / "scripts" / "register-model.sh").is_file())

starter_txt = (ROOT / "start.sh").read_text(encoding="utf-8") if (ROOT / "start.sh").is_file() else ""
check("Starter nutzt Ordner-Agent", "agent/venv/bin/openamer" in starter_txt)
check("Starter prueft das Modell", "openamer-max-7b" in starter_txt)

# ---------------------------------------------------------------- Installierbar
section("Installierbar")
check("Windows-Installer INSTALL.cmd", (ROOT / "INSTALL.cmd").is_file())
check("Linux-Installer scripts/install.sh", (ROOT / "scripts" / "install.sh").is_file())

# Python und Laufzeit muessen im ZIEL-Ordner liegen, nicht im Home des Benutzers.
# Der Quell-Ordner unter Windows hat bewusst kein agent/ — dort wird uebersprungen.
if not (ROOT / "agent").is_dir():
    print("  SKIP  kein agent/ — Quell-Ordner, Python/Laufzeit im Ziel pruefen")
else:
    ordner_py = sorted((ROOT / "agent" / "python").glob("cpython-3.13*/bin/python3"))
    check("Python im Ordner", bool(ordner_py), str(ordner_py[0]) if ordner_py else "fehlt")

    venv_py = ROOT / "agent" / "venv" / "bin" / "python"
    if venv_py.exists():
        target = venv_py.resolve()
        check("Laufzeit zeigt in den Ordner", str(ROOT) in str(target), str(target))

    # Der Installer prueft sich selbst — das ist der staerkste Test hier.
    if not IS_WIN and (ROOT / "scripts" / "install.sh").is_file():
        rc, out = shell(f"cd '{ROOT}' && bash scripts/install.sh --check 2>&1 | tail -6", timeout=180)
        check("install.sh --check meldet 0 Fehler",
              "Fehler:    0" in out or "Fehler: 0" in out,
              out.strip().splitlines()[-1] if out.strip() else "keine Ausgabe")

# ---------------------------------------------------------------- Faehigkeiten
section("Faehigkeiten (Tools, Skills, Modelle)")
rc, out = shell("find $HOME/.openamer/skills -name SKILL.md 2>/dev/null | wc -l")
try:
    n_skills = int(out.strip().splitlines()[0]) if out.strip() else 0
except (ValueError, IndexError):
    n_skills = 0
check("Skills installiert (>= 300)", n_skills >= 300, f"{n_skills} Skills")

rc, out = shell("ls $HOME/.openamer/plugins 2>/dev/null | wc -l")
try:
    n_plugins = int(out.strip().splitlines()[0]) if out.strip() else 0
except (ValueError, IndexError):
    n_plugins = 0
check("Plugins installiert (>= 1)", n_plugins >= 1, f"{n_plugins} Plugins")

rc, out = shell("grep -q 'default: openamer-max-7b' $HOME/.openamer/config.yaml 2>/dev/null && echo MODELL_OK")
check("Config zeigt auf lokales Modell", "MODELL_OK" in out, "openamer-max-7b")

# grep -c liefert eine ZAHL, nicht den Treffer — deshalb -q + Marker
rc, out = shell("grep -q '127.0.0.1:11434' $HOME/.openamer/config.yaml 2>/dev/null && echo OLLAMA_OK")
check("Config nutzt lokales Ollama", "OLLAMA_OK" in out, "127.0.0.1:11434")

# Vision-Pruefsatz: Bilder muessen im Projekt liegen, sonst ist er nicht lauffaehig
vis_bilder = list((ROOT / "testdata" / "vision").glob("*.png")) if (ROOT / "testdata" / "vision").is_dir() else []
check("Vision-Bilder im Projekt (>= 6)", len(vis_bilder) >= 6, f"{len(vis_bilder)} Bilder")
check("Vision-Prüfsatz vorhanden", (MDIR / "testset_vision.json").is_file())
check("Vision-Messskript vorhanden", (MDIR / "vision_eval.py").is_file())

# ---------------------------------------------------------------- Summe
print(f"\n{'ALL PASS' if not fails else 'FAILED: ' + ', '.join(fails)}"
      f"  —  {count - len(fails)}/{count} Pruefungen\n")
sys.exit(1 if fails else 0)
