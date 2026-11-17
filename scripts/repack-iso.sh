#!/usr/bin/env bash
# Packt ein vorhandenes Rootfs neu zum ISO — ohne debootstrap.
#
#   wsl -d Ubuntu -- bash -s < scripts/repack-iso.sh
#
# Warum: debootstrap + Agent-Install + Firmware kosten ~6 Minuten. Wer nur eine
# Aenderung im Rootfs testet (z. B. den NVIDIA-Treiber), will diese Zeit nicht
# jedes Mal zahlen. Dieses Skript macht nur Squashfs + GRUB + ISO.
#
# Gemessen 17.11.2026: Rootfs mit Firmware + NVIDIA 620.70.06 = 3,6 GB,
# Squashfs ~1,9 GB, ISO ~2,0 GB.
set -uo pipefail

BASE=/root/openamer-iso
ROOTFS=$BASE/rootfs
ISO=$BASE/iso
DATUM=$(date +%Y%m%d)

phase() { printf "\n=========== %s ===========\n" "$*"; }

[ -d "$ROOTFS/etc" ] || { echo "FAIL: kein Rootfs unter $ROOTFS"; exit 1; }

phase "1. chroot-Mounts loesen"
for d in dev proc sys; do
  mountpoint -q "$ROOTFS/$d" 2>/dev/null && umount "$ROOTFS/$d" 2>/dev/null && echo "  $d geloest" || true
done
rm -f "$ROOTFS/tmp/install-agent.sh"

phase "2. Kernel + initrd bereitstellen"
mkdir -p "$ISO/live"
K=$(ls "$ROOTFS"/boot/vmlinuz-* 2>/dev/null | head -1)
I=$(ls "$ROOTFS"/boot/initrd.img-* 2>/dev/null | head -1)
if [ -z "$K" ] || [ -z "$I" ]; then echo "FAIL: Kernel oder initrd fehlt"; exit 1; fi
cp -f "$K" "$ISO/live/vmlinuz"
cp -f "$I" "$ISO/live/initrd.img"
echo "  $(basename "$K") / $(basename "$I")"

phase "3. Squashfs bauen"
mksquashfs "$ROOTFS" "$ISO/live/filesystem.squashfs" \
  -comp xz -e boot -noappend -quiet || { echo "FAIL mksquashfs"; exit 1; }
echo "  filesystem.squashfs: $(du -h "$ISO/live/filesystem.squashfs" | cut -f1)"

phase "4. GRUB-Konfiguration"
mkdir -p "$ISO/boot/grub"
cat > "$ISO/boot/grub/grub.cfg" <<'GRUB'
set default=0
set timeout=5
insmod all_video
menuentry "OpenAmer-OS (live, Agent)" {
    linux /live/vmlinuz boot=live components quiet console=tty0 console=ttyS0,115200
    initrd /live/initrd.img
}
menuentry "OpenAmer-OS (live, ausfuehrlich)" {
    linux /live/vmlinuz boot=live components console=tty0 console=ttyS0,115200
    initrd /live/initrd.img
}
GRUB

phase "5. ISO bauen (BIOS + UEFI)"
OUT=$BASE/openamer-os-$DATUM.iso
rm -f "$OUT"
grub-mkrescue -o "$OUT" "$ISO" -- -volid OPENAMER_OS 2>&1 | tail -4
[ -f "$OUT" ] || { echo "FAIL: kein ISO erzeugt"; exit 1; }

phase "6. Ergebnis"
ls -lh "$OUT" | awk '{print "  "$9, $5}'
echo "  Typ: $(file -b "$OUT" 2>/dev/null | cut -c1-50)"
echo
echo "  Booten pruefen:"
echo "    wsl -d Ubuntu -- bash -s < scripts/iso-boot-test.sh 360"
