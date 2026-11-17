#!/usr/bin/env bash
# Startet das OpenAmer-OS-Image in QEMU und prueft den Kernel-Marker.
#
# Aufruf aus Windows:
#   wsl -d Ubuntu -- bash -s < scripts/boot-test.sh
#
# Wichtig: ein Timeout allein ist KEIN Erfolg. Gewertet wird nur, wenn der
# Kernel seine Bereitschaftsmeldung schreibt.
set -uo pipefail
export PATH="$HOME/.cargo/bin:$PATH"

IMG="${1:-/root/openamer-os-build/os/target/images/bios.img}"
SECS="${2:-40}"
LOG=/tmp/openamer-boot.log

if [ ! -f "$IMG" ]; then
  echo "FEHLER: Image fehlt: $IMG" >&2
  echo "Erst bauen: wsl -d Ubuntu -- bash -s < scripts/build-kernel.sh" >&2
  exit 2
fi

echo "Image: $IMG ($(du -h "$IMG" | cut -f1))"
echo "QEMU:  ${SECS}s, seriell, ohne Grafik"

timeout "$SECS" qemu-system-x86_64 \
  -drive format=raw,file="$IMG" \
  -display none -serial stdio -no-reboot > "$LOG" 2>&1 < /dev/null
# ^ < /dev/null ist PFLICHT: das Skript selbst kommt ueber stdin (bash -s).
#   Ohne die Umleitung erbt QEMU das Skript-stdin, frisst den Rest der Datei
#   und bash meldet danach einen "syntax error" mitten im Text.
RC=$?

LINES=$(wc -l "$LOG" | cut -d' ' -f1)
echo "Ausgabezeilen: $LINES  (QEMU rc=$RC, 124 = Timeout = erwartet)"

echo
echo "=== Bootloader-Phasen ==="
grep -c "^INFO" "$LOG" 2>/dev/null | sed 's/^/  INFO-Zeilen: /'

echo
echo "=== Kernel-Marker ==="
# -a ist Pflicht: der serielle Log enthaelt ANSI-/Framebuffer-Bytes und gilt
# grep sonst als Binaerdatei ("binary file matches" ohne Trefferzeile).
if grep -a -qi "kernel is running" "$LOG"; then
  grep -a -o -i -E ".{0,25}kernel is running.{0,25}" "$LOG" | head -2 | sed 's/^/  TREFFER: /'
  echo
  echo "[ok] Kernel laeuft."
  exit 0
else
  echo "  KEIN 'kernel is running' gefunden"
  echo
  echo "=== letzte 8 Zeilen ==="
  tail -c 1200 "$LOG" | strings | tail -8 | sed 's/^/  /'
  echo
  echo "[fail] Kernel-Marker fehlt."
  exit 1
fi
