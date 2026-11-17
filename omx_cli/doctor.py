"""omx doctor — Umgebung messen, Luecken benennen.

Jeder Wert kommt aus einem echten Aufruf (Dateisystem, git, HTTP, nvidia-smi).
Was nicht messbar ist, wird als "unbekannt" gemeldet — nie geschaetzt.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from .paths import ROOT, agent_repo, model_dir, openamer_home, os_dir, skills_dir

OK, WARN, FAIL = "ok", "warn", "fail"
SYM = {OK: "[ok]  ", WARN: "[warn]", FAIL: "[fail]"}


def _sh(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    """Fuehrt ein Kommando aus und gibt (rc, ausgabe) zurueck. Kein Shell=True."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           errors="replace")
        return p.returncode, (p.stdout or p.stderr).strip()
    except FileNotFoundError:
        return 127, "nicht installiert"
    except subprocess.TimeoutExpired:
        return 124, f"Zeitueberschreitung nach {timeout}s"
    except OSError as exc:  # pragma: no cover - plattformabhaengig
        return 1, f"{type(exc).__name__}: {exc}"


def _http_json(url: str, timeout: int = 4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _count_skills() -> tuple[int, int]:
    """(Anzahl SKILL.md, Anzahl Kategorien) unter dem Skills-Verzeichnis."""
    base = skills_dir()
    if not base.is_dir():
        return 0, 0
    files = list(base.rglob("SKILL.md"))
    cats = {f.parent.parent.name for f in files if f.parent.parent != base}
    return len(files), len(cats)


def collect() -> list[dict]:
    checks: list[dict] = []

    def add(area, name, state, value, hint=""):
        checks.append({"area": area, "name": name, "state": state,
                       "value": str(value), "hint": hint})

    # --- Laufzeit -------------------------------------------------------
    add("runtime", "Python", OK if sys.version_info >= (3, 10) else FAIL,
        platform.python_version(), "omx braucht >= 3.10")
    add("runtime", "Plattform", OK, f"{platform.system()} {platform.release()}")

    # --- Agent ----------------------------------------------------------
    home = openamer_home()
    add("agent", "OpenAmer-Home", OK if home.is_dir() else FAIL, home,
        "openamer setup ausfuehren")
    cfg = home / "config.yaml"
    add("agent", "config.yaml", OK if cfg.is_file() else FAIL,
        f"{cfg.stat().st_size} B" if cfg.is_file() else "fehlt")
    env = home / ".env"
    add("agent", ".env", OK if env.is_file() else WARN,
        f"{env.stat().st_size} B" if env.is_file() else "fehlt")

    repo = agent_repo()
    if repo.is_dir():
        rc, out = _sh(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"])
        add("agent", "Quellbaum", OK if rc == 0 else WARN, out.splitlines()[0] if out else "?")
        rc2, out2 = _sh(["git", "-C", str(repo), "status", "--porcelain"])
        dirty = len([l for l in out2.splitlines() if l.strip()]) if rc2 == 0 else -1
        add("agent", "Arbeitskopie", OK if dirty == 0 else WARN,
            f"{dirty} geaenderte Dateien" if dirty >= 0 else "unbekannt",
            "lokal modifiziert — vor Updates sichern")
    else:
        add("agent", "Quellbaum", FAIL, repo, "openamer installieren")

    n_skills, n_cats = _count_skills()
    add("agent", "Skills", OK if n_skills > 0 else WARN,
        f"{n_skills} SKILL.md in {n_cats} Kategorien")

    # --- Modell ---------------------------------------------------------
    tags = _http_json("http://127.0.0.1:11434/api/tags")
    if tags is None:
        add("model", "Ollama", FAIL, "nicht erreichbar", "ollama serve starten")
    else:
        models = tags.get("models", [])
        add("model", "Ollama", OK, f"{len(models)} Modelle")
        own = sorted(m["name"] for m in models if "openamer-max" in m["name"])
        add("model", "OpenAmer-Stufen", OK if own else WARN,
            f"{len(own)}: " + ", ".join(x.split("/")[-1].split(":")[0] for x in own))
        mdir = model_dir()
        add("model", "Max-One Rezept", OK if mdir.is_dir() else FAIL, mdir)

    # --- Hardware -------------------------------------------------------
    rc, out = _sh(["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
                   "--format=csv,noheader"])
    add("hardware", "GPU", OK if rc == 0 else WARN, out.splitlines()[0] if out else "keine")

    # --- OS-Bau ---------------------------------------------------------
    rc, out = _sh(["cargo", "--version"])
    add("os", "Rust (Windows)", OK if rc == 0 else WARN, out.splitlines()[0] if out else out,
        "Kernel-Bau laeuft in WSL (cargo fehlt im Windows-PATH ist normal)")
    rc, out = _sh(["wsl", "-d", "Ubuntu", "--", "bash", "-lc",
                   "cargo --version 2>/dev/null || echo MISSING", ])
    add("os", "Rust (WSL)", OK if "cargo" in out else WARN, out.splitlines()[-1] if out else "?",
        "rustup in WSL: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
    rc, out = _sh(["wsl", "-d", "Ubuntu", "--", "bash", "-lc", "docker --version"])
    add("os", "Docker (WSL)", OK if rc == 0 else WARN, out.splitlines()[0] if out else out)
    add("os", "Kernel-Quellen", OK if (agent_repo() / "os" / "kernel").is_dir() else FAIL,
        agent_repo() / "os" / "kernel")
    add("os", "Image-Bauplan", OK if os_dir().is_dir() else FAIL, os_dir())

    return checks


def run(args) -> int:
    checks = collect()
    if getattr(args, "json", False):
        print(json.dumps({"version": "0.1.0", "root": str(ROOT), "checks": checks},
                         indent=2, ensure_ascii=False))
        return 0

    print(f"\nomx doctor — OpenAmer Agent-Max  ({ROOT})\n")
    area = None
    counts = {OK: 0, WARN: 0, FAIL: 0}
    for c in checks:
        counts[c["state"]] += 1
        if c["area"] != area:
            area = c["area"]
            print(f"  {area.upper()}")
        print(f"    {SYM[c['state']]} {c['name']:<18} {c['value']}")
        if c["hint"] and c["state"] != OK:
            print(f"           -> {c['hint']}")

    print(f"\n  Ergebnis: {counts[OK]} ok · {counts[WARN]} warn · {counts[FAIL]} fail\n")
    return 0 if counts[FAIL] == 0 else 2
