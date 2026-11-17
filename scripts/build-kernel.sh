#!/usr/bin/env bash
# Baut den OpenAmer-OS-Kernel in WSL.
#
# Aufruf aus Windows:
#   wsl -d Ubuntu -- bash -s < scripts/build-kernel.sh
#
# Warum kopieren statt direkt bauen: der Quellbaum liegt auf /mnt/c (Windows-
# Dateisystem über 9p). Cargo macht pro Datei viele syscalls; ein Build dort
# dauert ein Vielfaches. Kopiert wird nur der Ordner os/ (wenige MB).
set -euo pipefail
export PATH="$HOME/.cargo/bin:$PATH"

SRC=/mnt/c/Users/amer7/AppData/Local/openamer/openamer-agent/os
WORK="$HOME/openamer-os-build"

if [ ! -d "$SRC" ]; then
  echo "FEHLER: Kernel-Quellen nicht gefunden: $SRC" >&2
  exit 2
fi

echo "== kopiere Quellen =="
rm -rf "$WORK"
mkdir -p "$WORK"
cp -a "$SRC"/. "$WORK"/
rm -rf "$WORK/target"          # alte Windows-Build-Artefakte nicht mitnehmen

cd "$WORK"
echo "== baue (nightly) =="
set +e
cargo +nightly build --release 2>&1 | tail -40
RC=${PIPESTATUS[0]}
set -e

echo
if [ "$RC" -eq 0 ]; then
  echo "[ok] Build erfolgreich"
else
  echo "[fail] Build fehlgeschlagen (rc=$RC)"
fi

echo
echo "== Artefakte =="
find "$WORK" -maxdepth 4 -type f \( -name "*.img" -o -name "*.bin" -o -name "*.elf" \) \
  2>/dev/null | sed "s|$WORK|~/openamer-os-build|" | head -10
ls -la "$WORK/target/x86_64-unknown-none/release" 2>/dev/null | head -5 || true
exit "$RC"
