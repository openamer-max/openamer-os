#!/usr/bin/env bash
# Installiert die Werkzeuge fuer den ISO-Bau.
#   wsl -d Ubuntu -- bash -s < scripts/iso-install-deps.sh
#
# Gemessener Ausgangszustand (17.11.2026): nur mksquashfs vorhanden;
# debootstrap, xorriso, grub-mkrescue, mtools, mkfs.vfat fehlten.
set -euo pipefail

echo "== apt aktualisieren =="
sudo -n apt-get update -qq

echo "== ISO-Werkzeuge installieren =="
sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  debootstrap \
  xorriso \
  squashfs-tools \
  grub-pc-bin \
  grub-efi-amd64-bin \
  grub-common \
  mtools \
  dosfstools \
  isolinux \
  syslinux-common \
  rsync \
  >/dev/null

echo
echo "== Endstand =="
for t in debootstrap xorriso mksquashfs grub-mkrescue mkfs.vfat grub-install; do
  printf "  %-14s %s\n" "$t" "$(command -v "$t" || echo FEHLT)"
done
echo "  $(debootstrap --version 2>&1 | head -1)"
