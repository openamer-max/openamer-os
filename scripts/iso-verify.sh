#!/usr/bin/env bash
# Prueft ein gebautes OpenAmer-OS-ISO auf Inhalt und Brauchbarkeit.
#   wsl -d Ubuntu -- bash -s < scripts/iso-verify.sh
#
# Prueft nicht nur, dass die Datei existiert, sondern was drin ist:
# Agent, Firmware, Netzwerkverwaltung, Kernel, Bootloader.
set -uo pipefail

ISO=$(ls -t /root/openamer-iso/openamer-os-*.iso 2>/dev/null | head -1)
SQ=/root/openamer-iso/iso/live/filesystem.squashfs

if [ -z "$ISO" ] || [ ! -f "$ISO" ]; then
  echo "FEHLER: kein ISO gefunden" >&2
  exit 2
fi

echo "ISO:   $(basename "$ISO")  ($(du -h "$ISO" | cut -f1))"
echo "Groesse in Bytes: $(stat -c%s "$ISO")"
echo

echo "=== Bootloader ==="
if file -b "$ISO" | grep -qi "boot sector"; then
  echo "  [ok]  ISO 9660 mit Bootsektor (BIOS)"
else
  echo "  [warn] kein Bootsektor erkannt"
fi
if command -v isoinfo >/dev/null 2>&1; then
  isoinfo -d -i "$ISO" 2>/dev/null | grep -i "volume id" | sed 's/^/  /'
fi

echo
echo "=== Kernel + initrd ==="
ls -lh /root/openamer-iso/iso/live/vmlinuz /root/openamer-iso/iso/live/initrd.img 2>/dev/null \
  | awk '{printf "  %-12s %s\n", $9, $5}'

echo
echo "=== Inhalt (Squashfs) ==="
if [ ! -f "$SQ" ]; then
  echo "  FEHLER: $SQ fehlt"
  exit 1
fi
LIST=/root/openamer-iso/.sqlist
unsquashfs -l "$SQ" 2>/dev/null > "$LIST"
echo "  Dateien gesamt: $(wc -l < "$LIST")"

check() {
  local label="$1" pattern="$2" want="${3:-1}"
  local n
  n=$(grep -c -- "$pattern" "$LIST" 2>/dev/null || echo 0)
  if [ "$n" -ge "$want" ]; then
    printf "  [ok]   %-34s %s\n" "$label" "$n"
  else
    printf "  [warn] %-34s %s (erwartet >= %s)\n" "$label" "$n" "$want"
  fi
}

echo
echo "=== Agent ==="
check "Agent-Binary" "opt/openamer/venv/bin/openamer" 1
check "venv-Python" "opt/openamer/venv/bin/python" 1
check "Quellbaum (editable)" "opt/openamer/src/pyproject.toml" 1
check "Python-Pakete" "opt/openamer/venv/lib/python3.11/site-packages" 5

echo
echo "=== Treiber / Firmware ==="
check "WLAN-Firmware (iwlwifi)" "lib/firmware/iwlwifi" 20
check "Grafik-Firmware (amdgpu)" "lib/firmware/amdgpu" 20
check "SOF-Audio-Firmware" "lib/firmware/intel/sof" 1
check "Mikrocode (intel)" "lib/firmware/intel-ucode" 1
check "Mikrocode (amd)" "lib/firmware/amd-ucode" 1
check "NetworkManager" "usr/sbin/NetworkManager" 1
check "wpa_supplicant" "usr/sbin/wpa_supplicant" 1

echo
echo "=== Live-Mechanik ==="
check "live-boot Skripte" "lib/live/boot" 5
check "Systemd" "lib/systemd/systemd" 1
check "Beweis-Dienst" "etc/systemd/system/openamer-os-ready.service" 1
check "Autologin getty" "getty@tty1.service.d/autologin.conf" 1

echo
echo "=== Ergebnis ==="
if grep -q "opt/openamer/venv/bin/openamer" "$LIST" && \
   [ "$(grep -c "lib/firmware/iwlwifi" "$LIST")" -ge 20 ]; then
  echo "  [ok] ISO enthaelt Agent + WLAN-Firmware — fuer echte Hardware brauchbar."
  exit 0
else
  echo "  [fail] Agent oder Firmware fehlt im ISO."
  exit 1
fi
