"""omx os — OpenAmer-OS: Kernel-Prototyp und Userspace-Image.

Zwei Ebenen, ehrlich getrennt:
  kernel/   freestanding Rust-Kernel (bootet in QEMU, kein Linux)
  image/    Debian-Userspace mit OpenAmer-Daemon (via Docker in WSL2)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .paths import agent_repo, os_dir

WSL_DISTRO = "Ubuntu"


def _wsl(script: str, timeout: int = 120) -> tuple[int, str]:
    """Fuehrt ein Shell-Skript in WSL aus — ueber stdin, nicht als Argument.

    Gemessen (17.11.2026): `wsl.exe ... bash -lc "<skript>"` zerlegt lange
    Skripte an der Windows-Kommandozeile; `$HOME` und `$(...)` kommen leer an
    ("cargo: command not found", obwohl rustup es installiert hat).
    `bash -s` mit dem Skript auf stdin ist quoting-frei und laeuft zuverlaessig.
    """
    try:
        p = subprocess.run(["wsl", "-d", WSL_DISTRO, "--", "bash", "-s"],
                           input=script, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, "wsl nicht verfuegbar"
    except subprocess.TimeoutExpired:
        return 124, f"Zeitueberschreitung nach {timeout}s"


def _kernel_info() -> dict:
    src = agent_repo() / "os"
    info = {"source": str(src), "exists": src.is_dir()}
    if not src.is_dir():
        return info
    ksrc = src / "kernel"
    info["kernel_src"] = str(ksrc)
    info["rust_files"] = len(list(ksrc.rglob("*.rs"))) if ksrc.is_dir() else 0
    info["c_files"] = len(list(ksrc.rglob("*.c"))) if ksrc.is_dir() else 0
    tc = src / "rust-toolchain.toml"
    info["toolchain_pinned"] = tc.read_text(encoding="utf-8").strip() if tc.is_file() else None
    img = src / "os" / "target" / "images"
    info["images"] = sorted(p.name for p in img.glob("*")) if img.is_dir() else []
    return info


def _toolchain() -> dict:
    """Prueft die Bau-Toolchain in WSL — ehrlich, inklusive der Dinge, die fehlen.

    Gemessen (17.11.2026): rustup installiert cargo nach ~/.cargo/bin, das im
    nicht-interaktiven WSL-PATH fehlt. Ohne cc/make/qemu und ohne die Targets
    x86_64-unknown-none/-uefi laesst sich der Kernel nicht bauen.
    """
    script = (
        'export PATH="$HOME/.cargo/bin:$PATH"; '
        'printf "cargo=%s\\n" "$(cargo --version 2>/dev/null || echo MISSING)"; '
        'printf "targets=%s\\n" "$(rustup target list --installed --toolchain nightly 2>/dev/null | tr "\\n" "," )"; '
        'for t in cc make ld qemu-system-x86_64; do '
        '  printf "%s=%s\\n" "$t" "$(command -v $t 2>/dev/null || echo MISSING)"; '
        'done'
    )
    rc, out = _wsl(script)
    info: dict = {"rc": rc, "raw": out, "missing": [], "targets": []}
    for line in out.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k == "targets":
            info["targets"] = [x for x in v.split(",") if x]
        elif v == "MISSING":
            info["missing"].append(k)
        else:
            info[k] = v
    need = {"x86_64-unknown-none", "x86_64-unknown-uefi"}
    info["missing_targets"] = sorted(need - set(info["targets"]))
    info["ready"] = not info["missing"] and not info["missing_targets"]
    return info


def status(args) -> int:
    k = _kernel_info()
    t = _toolchain()
    imagedir = os_dir()
    blueprint = sorted(p.name for p in imagedir.glob("*")) if imagedir.is_dir() else []

    data = {"kernel": k, "toolchain": t, "image_blueprint": blueprint}
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    print("\nOpenAmer-OS — Zustand\n")
    print(f"  Kernel-Quelle      {k.get('source')}  ({'da' if k.get('exists') else 'FEHLT'})")
    print(f"  Rust-Dateien       {k.get('rust_files', 0)}  ·  C-Referenz {k.get('c_files', 0)}")
    print(f"  Toolchain-Pin      {(k.get('toolchain_pinned') or '-').replace(chr(10), ' ')[:70]}")
    print(f"  Gebaute Images     {', '.join(k.get('images', [])) or 'keine'}")

    if t.get("ready"):
        print(f"  WSL-Toolchain      bereit · {t.get('cargo', '?')}")
        print(f"  Ziele              {', '.join(t.get('targets', []))}")
    else:
        print("  WSL-Toolchain      NICHT bereit")
        if t.get("missing"):
            print(f"    fehlende Werkzeuge: {', '.join(t['missing'])}")
        if t.get("missing_targets"):
            print(f"    fehlende Ziele:     {', '.join(t['missing_targets'])}")
        if t.get("cargo") in (None, "MISSING"):
            print("    cargo fehlt:  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh")
        print("    Nachziehen:   wsl -d Ubuntu -- bash -s < scripts/install-kernel-toolchain.sh")

    print(f"  Image-Bauplan      {imagedir}  ({len(blueprint)} Dateien)")
    print("\n  Naechster Schritt: omx os build  (Userspace)  ·  "
          "Kernel: siehe scripts/build-kernel.sh\n")
    return 0


def pack(args) -> int:
    """Packt die Python-Teile des Agenten als Build-Kontext (ohne node_modules).

    Gemessen: das ganze Repo sind 270 MB Archiv (mit node_modules/Logs); die
    Python-Pakete allein sind 12 MB. Nur die braucht das Image.

    Reproduzierbar: Gzip-Zeitstempel 0 und sortierte Eintraege. Ohne das
    erzeugt jeder Lauf einen anderen Tarball (gleiche Groesse, anderer Hash)
    und `verify.py` — das `omx os pack` aufruft — macht das Repo bei jedem
    Prueflauf schmutzig.
    """
    import gzip
    import tarfile
    from .paths import agent_repo

    src = agent_repo()
    if not src.is_dir():
        print(f"  [fail] Quellbaum fehlt: {src}")
        return 2

    parts = [p for p in ("agent", "openamer_cli", "tools", "gateway",
                         "providers", "plugins", "tui_gateway") if (src / p).is_dir()]
    target = os_dir() / "om-src.tgz"
    count = 0
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(target, "wb"),
                       mtime=0, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tf:
            for part in parts:
                tf.add(src / part, arcname=part,
                       filter=lambda ti: None if "__pycache__" in ti.name else _stable(ti))
            for f in sorted(src.glob("*.py")):
                tf.add(f, arcname=f.name, filter=_stable)
                count += 1
            for f in ("pyproject.toml", "setup.py"):
                if (src / f).is_file():
                    tf.add(src / f, arcname=f, filter=_stable)

    mb = target.stat().st_size / 1e6
    print(f"  [ok]  {target}  {mb:.1f} MB  ({len(parts)} Pakete, {count} Module)")
    return 0


def _stable(ti):
    """Tar-Info auf Inhalt reduzieren: keine uid/gid/mtime-Unterschiede."""
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""
    ti.mtime = 0
    ti.mode = 0o755 if ti.isdir() else 0o644
    return ti


def build(args) -> int:
    """Baut das Userspace-Image. Nutzt Docker in WSL2 (Windows hat meist keins)."""
    tag = getattr(args, "tag", "openamer-os:0.1")
    with_agent = getattr(args, "with_agent", False)
    ctx = os_dir()
    dockerfile = "Dockerfile.agent" if with_agent else "Dockerfile"
    if with_agent:
        tag = tag if tag.endswith("-agent") else f"{tag}-agent"
        if not (ctx / "om-src.tgz").is_file():
            print("  [warn] om-src.tgz fehlt — packe zuerst:")
            pack(args)
    if not (ctx / dockerfile).is_file():
        print(f"  [fail] Kein {dockerfile} in {ctx}")
        return 2

    win_path = str(ctx).replace("\\", "/").replace("C:", "/mnt/c")
    script = f"cd {win_path} && docker build -f {dockerfile} -t {tag} . 2>&1 | tail -40"
    print(f"  Baue {tag} aus {ctx} ({dockerfile}) …")
    rc, out = _wsl(script, timeout=1800)
    print(out)
    if rc != 0:
        print(f"  [fail] Build fehlgeschlagen (rc={rc})")
        return rc

    rc2, size = _wsl(f"docker image inspect {tag} --format '{{{{.Size}}}}'")
    mb = int(size) / 1e6 if size.strip().isdigit() else 0
    print(f"  [ok]  {tag} gebaut — {mb:.1f} MB")
    return 0
