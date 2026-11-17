#!/usr/bin/env bash
# Bootet das OpenAmer-OS-ISO in QEMU und prueft den Beweis-Marker.
#
#   wsl -d Ubuntu -- bash -s < scripts/iso-boot-test.sh
#
# Gewertet wird nur der Marker OPENAMER-OS-LIVE-READY plus die Agent-Version.
# Ein Timeout allein ist KEIN Erfolg.
set -uo pipefail

ISO=$(ls -t /root/openamer-iso/openamer-os-*.iso 2>/dev/null | head -1)
SECS="${1:-180}"
LOG=/root/openamer-iso/boot-test.log

if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
  echo "FEHLER: kein ISO gefunden in /root/openamer-iso/" >&2
  echo "Erst bauen: wsl -d Ubuntu -- bash -s < scripts/build-iso.sh" >&2
  exit 2
fi

echo "ISO:  $ISO ($(du -h "$ISO" | cut -f1))"
echo "QEMU: ${SECS}s, 2 GB RAM, seriell, ohne Grafik"

# < /dev/null ist Pflicht: dieses Skript kommt ueber stdin (bash -s) und QEMU
# wuerde sonst den Rest der Datei wegfressen.
timeout "$SECS" qemu-system-x86_64 \
  -cdrom "$ISO" \
  -m 2048 -smp 2 \
  -display none \
  -serial file:"$LOG" \
  -no-reboot < /dev/null
RC=$?

echo "QEMU rc=$RC  (124 = Timeout, normal bei einer Live-Session)"
echo "Log: $LOG ($(du -h "$LOG" 2>/dev/null | cut -f1))"

echo
echo "=== Kernel-Start ==="
grep -a -c -E "Linux version|Booting" "$LOG" 2>/dev/null | sed 's/^/  Treffer: /'

echo
echo "=== Systemstart ==="
for m in "Reached target" "getty" "login:"; do
  n=$(grep -a -c -i "$m" "$LOG" 2>/dev/null || echo 0)
  printf "  %-20s %s\n" "$m" "$n"
done

echo
echo "=== Beweis-Marker ==="
if grep -a -q "OPENAMER-OS-LIVE-READY" "$LOG"; then
  sed -n '/OPENAMER-OS-LIVE-READY/,/OPENAMER-OS-LIVE-DONE/p' "$LOG" | head -20 | sed 's/^/  /'
  echo
  if grep -a -q "OPENAMER-OS-AGENT-OK" "$LOG"; then
    echo "[ok] ISO bootet und der Agent ist installiert."
    exit 0
  else
    echo "[warn] ISO bootet, aber der Agent fehlt (OPENAMER-OS-AGENT-MISSING)."
    exit 1
  fi
else
  echo "  KEIN Marker gefunden."
  echo
  echo "=== letzte 15 Zeilen ==="
  tail -c 3000 "$LOG" 2>/dev/null | strings | tail -15 | sed 's/^/  /'
  echo
  echo "[fail] ISO bootet nicht bis zum Marker."
  exit 1
fi
