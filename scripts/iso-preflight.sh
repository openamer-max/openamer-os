#!/usr/bin/env bash
# Vorflugpruefung fuer den ISO-Bau (in WSL auszufuehren).
#   wsl -d Ubuntu -- bash -s < scripts/iso-preflight.sh
#
# Prueft, was der Bau wirklich braucht: Platz, Netz, apt-Pakete, Kernel-Image.
# Nichts wird installiert — das macht iso-install-deps.sh.
set -uo pipefail

echo "== Platz =="
df -h / /root /tmp 2>/dev/null | awk 'NR==1 || /\/$|\/root|\/tmp/ {printf "  %-14s %6s frei von %6s\n", $6, $4, $2}'

echo
echo "== Netz (Debian-Archiv) =="
if curl -sI --max-time 10 http://deb.debian.org/debian/ | head -1 | grep -q "200\|301\|302"; then
  echo "  deb.debian.org: erreichbar"
else
  echo "  deb.debian.org: NICHT erreichbar"
fi

echo
echo "== Werkzeuge =="
for t in debootstrap xorriso mksquashfs grub-mkrescue mtools mkfs.vfat; do
  printf "  %-14s %s\n" "$t" "$(command -v "$t" || echo FEHLT)"
done

echo
echo "== Kernel-Paket vorhanden? =="
if ls /boot/vmlinuz-* >/dev/null 2>&1; then
  ls -1 /boot/vmlinuz-* | sed 's/^/  /'
else
  echo "  kein /boot/vmlinuz-* (Kernel kommt aus linux-image-amd64)"
fi

echo
echo "== sudo =="
sudo -n true 2>/dev/null && echo "  ohne Passwort: ja" || echo "  ohne Passwort: NEIN"

echo
echo "== Bestehende ISO-Reste =="
ls -lh /root/openamer-iso 2>/dev/null | head -3 || echo "  keine"
