#!/usr/bin/env bash
# Baut ein bootfaehiges OpenAmer-OS-Live-ISO.
#
#   wsl -d Ubuntu -- bash -s < scripts/build-iso.sh
#
# Aufbau:
#   Linux-Kernel (Debian bookworm) + live-boot + Squashfs mit dem Agenten.
#   Der freestanding Rust-Kernel (Ebene 1) traegt keinen Userspace — fuer ein
#   ISO mit Agent braucht es einen echten Linux-Kernel. Beides bleibt getrennt:
#   Ebene 1 = eigener Kernel (Forschung), Ebene 3 = dieses ISO (benutzbar).
#
# Ergebnis:  /root/openamer-iso/openamer-os-<datum>.iso
#
# Beweis: der Dienst openamer-os.service schreibt beim Boot auf die serielle
# Konsole "OPENAMER-OS-LIVE-READY" und die Agent-Version.
set -uo pipefail
export DEBIAN_FRONTEND=noninteractive

BASE=/root/openamer-iso
ROOTFS=$BASE/rootfs
STAGE=$BASE/stage
ISO=$BASE/iso
AGENT_SRC=/tmp/openamer-src
LOG=$BASE/build.log
DATEI=$(date +%Y%m%d)
SUITE=bookworm

mkdir -p "$BASE"
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

phase() { echo; echo "=========== $* ==========="; }

phase "0. Vorbereitung"
# Wiederaufsetzbar: ein fertiges rootfs (1,1 GB, ~5 min debootstrap) wird NICHT
# weggeworfen. Nur Stage und ISO-Verzeichnis werden frisch gemacht.
rm -rf "$STAGE" "$ISO"
mkdir -p "$STAGE" "$ISO/live" "$ISO/boot/grub"
mkdir -p "$ROOTFS"

phase "1. debootstrap ($SUITE)"
# Wichtig: die Include-Liste NICHT per Backslash umbrechen — der Umbruch macht
# aus "python3,..." ein eigenes Argument und debootstrap meldet dann
# "No such script: <mirror>", weil es die Suite falsch zuordnet.
INCLUDES="linux-image-amd64,live-boot,live-config,systemd-sysv,initramfs-tools,python3,python3-venv,python3-pip,ca-certificates,curl,git,ripgrep,less,procps,nano,passwd,locales"
if [ -f "$ROOTFS/etc/debian_version" ]; then
  echo "  rootfs existiert bereits ($(du -sh "$ROOTFS" | cut -f1)) — debootstrap uebersprungen"
  echo "  Neu bauen: rm -rf $ROOTFS"
else
  debootstrap --variant=minbase --arch=amd64 --include="$INCLUDES" \
    "$SUITE" "$ROOTFS" http://deb.debian.org/debian/ || { echo "FAIL debootstrap"; exit 1; }
  echo "rootfs: $(du -sh "$ROOTFS" | cut -f1)"
fi

phase "2. Agent-Quellbaum bereitstellen"
# Das Archiv liegt dauerhaft im Windows-Projekt; /tmp in WSL ist fluechtig und
# war nach dem naechsten Aufruf leer.
ARCHIVE="${OM_ARCHIVE:-/mnt/c/Users/amer7/openamer-agent-max/os/openamer-os/om-src.tgz}"
if [ ! -f "$ARCHIVE" ]; then
  echo "FEHLER: Agent-Archiv fehlt: $ARCHIVE"
  echo "Auf Windows erzeugen:  python omx.py os pack"
  exit 2
fi
echo "  Archiv: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"
rm -rf "$AGENT_SRC"
mkdir -p "$AGENT_SRC"
tar -xzf "$ARCHIVE" -C "$AGENT_SRC"
mkdir -p "$ROOTFS/opt/openamer/src"
cp -a "$AGENT_SRC"/. "$ROOTFS/opt/openamer/src"/

phase "3. DNS + chroot vorbereiten"
cp /etc/resolv.conf "$ROOTFS/etc/resolv.conf"
mount --bind /dev  "$ROOTFS/dev"  2>/dev/null || true
mount -t proc proc "$ROOTFS/proc" 2>/dev/null || true
mount -t sysfs sys "$ROOTFS/sys"  2>/dev/null || true

phase "4. Agent im chroot installieren (editable)"
if [ -x "$ROOTFS/opt/openamer/venv/bin/openamer" ]; then
  echo "  venv mit Agent existiert bereits — Install uebersprungen"
  echo "  Neu installieren: rm -rf $ROOTFS/opt/openamer/venv"
else
cat > "$ROOTFS/tmp/install-agent.sh" <<'CHROOT'
#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive
# python3-venv nachziehen, falls debootstrap es nicht mitgab
python3 -m venv /opt/openamer/venv
/opt/openamer/venv/bin/pip install -q --upgrade pip
# Das Projekt verweigert Wheel-Bau -> editable ist Pflicht.
/opt/openamer/venv/bin/pip install -q -e /opt/openamer/src
/opt/openamer/venv/bin/openamer --version
CHROOT
chmod +x "$ROOTFS/tmp/install-agent.sh"
if ! chroot "$ROOTFS" /tmp/install-agent.sh; then
  echo "FAIL: Agent-Install im chroot"
  exit 1
fi
fi  # Ende der "schon installiert?"-Pruefung

phase "5. Live-System konfigurieren"
# Treiber/Firmware fuer echte Hardware. Das erste ISO war minbase ohne
# non-free-firmware — auf einem Laptop ohne LAN-Kabel gab es damit kein WLAN.
# Gemessen: ohne diese Pakete fehlen iwlwifi/amdgpu-Firmware, Mikrocode und
# NetworkManager; das System bootet, hat aber keine Netzverbindung.
cat > "$ROOTFS/etc/apt/sources.list" <<'SOURCES'
deb http://deb.debian.org/debian bookworm main contrib non-free non-free-firmware
deb http://deb.debian.org/debian bookworm-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware
SOURCES

FIRMWARE="firmware-linux firmware-misc-nonfree firmware-iwlwifi firmware-realtek firmware-atheros firmware-brcm80211 firmware-sof-signed intel-microcode amd64-microcode network-manager wpasupplicant wireless-tools rfkill mesa-utils libgl1-mesa-dri ntfs-3g exfatprogs"
echo "  hole Firmware + Netzwerkverwaltung ($(echo $FIRMWARE | wc -w) Pakete)"
if chroot "$ROOTFS" bash -c "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $FIRMWARE" >/dev/null 2>&1; then
  echo "  [ok] Firmware installiert — rootfs: $(du -sh "$ROOTFS" | cut -f1)"
else
  echo "  [warn] Firmware-Installation unvollstaendig (weiter ohne)"
fi
# NetworkManager soll das Netz uebernehmen (WLAN + LAN)
chroot "$ROOTFS" systemctl enable NetworkManager >/dev/null 2>&1 || true
chroot "$ROOTFS" systemctl enable wpa_supplicant >/dev/null 2>&1 || true

# Benutzer + Passwort (Live: openamer/openamer, ohne Netz exponierter Dienst)
chroot "$ROOTFS" useradd -m -u 1000 -s /bin/bash -G sudo openamer 2>/dev/null || true
echo 'openamer:openamer' | chroot "$ROOTFS" chpasswd
echo 'openamer ALL=(ALL) NOPASSWD:ALL' > "$ROOTFS/etc/sudoers.d/openamer"
chmod 0440 "$ROOTFS/etc/sudoers.d/openamer"

# Hostname + Autologin auf tty1
echo openamer-os > "$ROOTFS/etc/hostname"
mkdir -p "$ROOTFS/etc/systemd/system/getty@tty1.service.d"
cat > "$ROOTFS/etc/systemd/system/getty@tty1.service.d/autologin.conf" <<'AUTO'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin openamer --noclear %I $TERM
AUTO

# Agent startet beim Login auf tty1 (TUI)
cat > "$ROOTFS/home/openamer/.bash_profile" <<'PROFILE'
if [ -z "$OPENAMER_STARTED" ] && [ "$(tty)" = "/dev/tty1" ]; then
  export OPENAMER_STARTED=1
  export OPENAMER_HOME=/home/openamer/.openamer
  if [ -x /opt/openamer/venv/bin/openamer ]; then
    /opt/openamer/venv/bin/openamer
  fi
fi
PROFILE
chroot "$ROOTFS" chown -R openamer:openamer /home/openamer

# Beweis-Dienst: schreibt beim Boot auf die serielle Konsole.
# Zwei Lehren aus dem ersten ISO (17.11.2026):
#  1. Ausgabe direkt auf /dev/ttyS0 umleiten — sonst landet sie im Puffer und
#     der Log bricht mitten im Skript ab (OK/MISSING/DONE fehlten).
#  2. Den Agentenaufruf mit timeout umstellen und EXPLIZITE Marker schreiben:
#     PRESENT (Binary da) / OK (startet) / BROKEN (da, startet nicht).
cat > "$ROOTFS/usr/local/bin/openamer-os-ready" <<'READY'
#!/bin/bash
# Auf /dev/console schreiben, NICHT auf /dev/ttyS0: dort haelt getty das
# Terminal (der Log zeigt "openamer-os login:" auf ttyS0), und ein zweiter
# Schreiber blockiert mitten in der Ausgabe — genau das liess den Log nach
# "--- CLI ---" abbrechen. /dev/console ist der Kernel-Kanal, unabhaengig von getty.
exec > /dev/console 2>&1 < /dev/null || exit 0
# systemd-Dienste haben kein HOME/LANG/TERM. Ohne diese Variablen kann die
# Python-Initialisierung haengen — im chroot (mit voller Umgebung) lief sie.
export HOME=/root LANG=C.UTF-8 LC_ALL=C.UTF-8 TERM=linux
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

echo "OPENAMER-OS-LIVE-READY"
echo "host: $(uname -a)"

BIN=/opt/openamer/venv/bin/openamer
PY=/opt/openamer/venv/bin/python
if [ -x "$BIN" ] && [ -x "$PY" ]; then
  echo "OPENAMER-OS-AGENT-PRESENT"
  ls -l "$BIN"
else
  echo "OPENAMER-OS-AGENT-MISSING"
  echo "OPENAMER-OS-LIVE-DONE"
  exit 1
fi

echo "--- Python-Import (beweist venv + Code) ---"
if timeout -k 5 45 "$PY" -c "import sys; sys.path.insert(0,'/opt/openamer/src'); import openamer_constants; print('OPENAMER-OS-IMPORT-OK', openamer_constants.__name__)"; then
  echo "OPENAMER-OS-PYTHON-OK"
else
  echo "OPENAMER-OS-PYTHON-BROKEN rc=$?"
fi

echo "--- CLI (beweist Startbarkeit) ---"
if timeout -k 10 120 "$BIN" --version; then
  echo "OPENAMER-OS-AGENT-OK"
else
  echo "OPENAMER-OS-AGENT-BROKEN rc=$?"
fi
echo "OPENAMER-OS-LIVE-DONE"
READY
chmod +x "$ROOTFS/usr/local/bin/openamer-os-ready"

cat > "$ROOTFS/etc/systemd/system/openamer-os-ready.service" <<'UNIT'
[Unit]
Description=OpenAmer OS readiness proof on serial console
After=multi-user.target network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/openamer-os-ready
StandardOutput=tty
TTYPath=/dev/ttyS0
TimeoutStartSec=300
Environment=HOME=/root TERM=linux LANG=C.UTF-8 PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
UNIT
chroot "$ROOTFS" systemctl enable openamer-os-ready.service 2>&1 | tail -2 || true

phase "6. Kernel + initrd kopieren"
KERNEL=$(ls "$ROOTFS"/boot/vmlinuz-* 2>/dev/null | head -1)
INITRD=$(ls "$ROOTFS"/boot/initrd.img-* 2>/dev/null | head -1)
if [ -z "$KERNEL" ] || [ -z "$INITRD" ]; then
  echo "FAIL: Kernel/initrd fehlt im rootfs"
  ls -la "$ROOTFS/boot" 2>/dev/null | head
  exit 1
fi
echo "  kernel: $(basename "$KERNEL") ($(du -h "$KERNEL" | cut -f1))"
echo "  initrd: $(basename "$INITRD") ($(du -h "$INITRD" | cut -f1))"
cp "$KERNEL" "$ISO/live/vmlinuz"
cp "$INITRD" "$ISO/live/initrd.img"

phase "7. Squashfs bauen"
# chroot-Mounts loesen, sonst landen /proc /sys /dev im Image
umount "$ROOTFS/dev"  2>/dev/null || true
umount "$ROOTFS/proc" 2>/dev/null || true
umount "$ROOTFS/sys"  2>/dev/null || true
rm -f "$ROOTFS/tmp/install-agent.sh"
mksquashfs "$ROOTFS" "$ISO/live/filesystem.squashfs" \
  -comp xz -e boot -noappend -quiet || { echo "FAIL mksquashfs"; exit 1; }
echo "  filesystem.squashfs: $(du -h "$ISO/live/filesystem.squashfs" | cut -f1)"

phase "8. GRUB-Konfiguration"
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

phase "9. ISO bauen (BIOS + UEFI)"
OUT=$BASE/openamer-os-$DATEI.iso
rm -f "$OUT"
grub-mkrescue -o "$OUT" "$ISO" \
  -- -volid OPENAMER_OS 2>&1 | tail -6
if [ ! -f "$OUT" ]; then
  echo "FAIL: kein ISO erzeugt"
  exit 1
fi

phase "10. Ergebnis"
ls -lh "$OUT"
echo "  Typ: $(file -b "$OUT" 2>/dev/null | cut -c1-60)"
echo "  Volid: $(isoinfo -d -i "$OUT" 2>/dev/null | grep -i "volume id" || echo n/a)"
echo
echo "  Naechster Schritt — booten:"
echo "    wsl -d Ubuntu -- bash -s < scripts/iso-boot-test.sh"
