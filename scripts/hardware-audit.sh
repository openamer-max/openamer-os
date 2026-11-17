#!/usr/bin/env bash
# Hardware-Audit: prueft die Pflicht-Matrix gegen ein Rootfs oder das Live-System.
#
#   wsl -d Ubuntu -- bash -s < scripts/hardware-audit.sh          # ISO-Chroot
#   bash scripts/hardware-audit.sh /pfad/zum/rootfs                # beliebiges Rootfs
#
# Ausgabe: pro Geraeteklasse OK oder LUECKE. Eine Luecke wird NIE als OK gezaehlt.
# Siehe docs/HARDWARE-STANDARD.md fuer die Begruendung jeder Zeile.
set -uo pipefail

R="${1:-/root/openamer-iso/rootfs}"
F="$R/lib/firmware"
FEHLT=0
OK=0
OPT=0

[ -d "$F" ] || { echo "FEHLER: kein Firmware-Ordner unter $F" >&2; exit 2; }

zeile() {  # zeile <label> <pfad-oder-paket> <art> [pflicht]
  local label="$1" target="$2" art="${3:-fw}" pflicht="${4:-pflicht}" n=0
  case "$art" in
    # Wildcard, weil Kernel-Module je nach Build .ko oder .ko.xz heissen
    fw)   n=$(find "$F/$target" -type f 2>/dev/null | wc -l) ;;
    file) n=$([ -e "$R$target" ] && echo 1 || echo 0) ;;
    mod)  n=$(find "$R/lib/modules" \( -name "$target" -o -name "$target.xz" \) 2>/dev/null | wc -l) ;;
    pkg)  n=$(chroot "$R" dpkg -l "$target" 2>/dev/null | grep -c '^ii') ;;
  esac
  if [ "${n:-0}" -gt 0 ]; then
    printf "  [ok]        %-42s %s\n" "$label" "($n)"
    OK=$((OK+1))
  elif [ "$pflicht" = "optional" ]; then
    printf "  [optional]  %-42s nicht vorhanden\n" "$label"
    OPT=$((OPT+1))
  else
    printf "  [LUECKE]    %-42s\n" "$label"
    FEHLT=$((FEHLT+1))
  fi
}

echo "Hardware-Audit gegen: $R"
echo
echo "=== Grafik ==="
zeile "AMD Radeon (amdgpu-Firmware)"            amdgpu      fw
zeile "NVIDIA Treibermodul (nvidia.ko)"         "nvidia.ko" mod
zeile "NVIDIA Firmware (GSP)"                   nvidia      fw

echo
echo "=== Netzwerk ==="
zeile "WLAN Realtek 8852CE (Firmware)"          rtw89       fw
zeile "WLAN Realtek Treiber (rtw89)"            "rtw89_core.ko" mod
zeile "Bluetooth Realtek (rtl_bt)"              rtl_bt      fw
zeile "LAN Realtek (rtl_nic)"                   rtl_nic     fw
zeile "WLAN Intel (firmware-iwlwifi)"           iwlwifi     fw optional
zeile "WLAN Atheros/Qualcomm"                   ath11k      fw optional
zeile "WLAN MediaTek"                           mediatek    fw optional

echo
echo "=== Audio / Kamera ==="
# SOF liegt bei Debian unter intel/sof, teils auch unter intel/sof-ipc4
zeile "Audio SOF-Firmware"                      "intel/sof"  fw optional
zeile "Kamera (uvcvideo)"                       "uvcvideo.ko" mod

echo
echo "=== CPU / Sicherheit ==="
zeile "Microcode AMD (amd-ucode)"               amd-ucode   fw
zeile "Microcode Intel (intel-ucode)"           intel-ucode fw optional
# Gemessen: tpm_crb.ko fehlt im bookworm-Image, tpm_tis ist vorhanden.
# TPM wird fuer den Agenten nicht gebraucht — als optional gefuehrt, ehrlich benannt.
zeile "TPM 2.0 (tpm_crb)"                       "tpm_crb.ko" mod optional
zeile "TPM Alternative (tpm_tis*)"              "tpm_tis*.ko" mod

echo
echo "=== NPU (optional) ==="
zeile "AMD NPU (amdxdna, Kernel >= 6.14)"       "amdxdna.ko" mod optional

echo
echo "=== Speicher / Bus ==="
zeile "NVMe"                                    "nvme.ko"   mod
zeile "AHCI/SATA"                               "ahci.ko"   mod
# Bindestrich, nicht Unterstrich — gemessener Fehler im ersten Entwurf
zeile "USB-xHCI"                                "xhci-pci.ko" mod

echo
echo "=== Ergebnis ==="
printf "  vorhanden: %s\n" "$OK"
printf "  optional:  %s (fuer dieses Geraet nicht noetig)\n" "$OPT"
printf "  Luecken:   %s\n" "$FEHLT"
if [ "$FEHLT" -eq 0 ]; then
  echo "  [vollstaendig] Hardware-Standard fuer dieses Geraet erfuellt."
  exit 0
else
  echo "  [unvollstaendig] $FEHLT Pflicht-Luecke(n) — siehe docs/HARDWARE-STANDARD.md"
  exit 1
fi
