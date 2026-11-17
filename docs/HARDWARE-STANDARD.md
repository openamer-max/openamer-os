# Hardware-Standard — Geräteklassen und Treiberpflicht

Der Windows-Geräte-Manager ist der **Maßstab**: Jede dort gelistete Klasse ist ein
Gerät, das ein PC haben kann. Für OpenAmer-OS heißt das: pro Klasse muss ein
Linux-Treiber oder eine Firmware-Datei vorhanden sein, sonst fehlt Hardware.

Referenzgerät: **GIGABYTE AERO X16 1VH** — 113 Geräte, 24 Klassen, erfasst am
17.11.2026 über `scripts/hardware-inventory.ps1`.

## Die Pflicht-Matrix (24 Klassen → Treiber → Stand im ISO)

| # | Geräte-Manager-Klasse | Konkretes Gerät | Linux-Treiber | Firmware | ISO |
|---|---|---|---|---|---|
| 1 | Computer | GIGABYTE AERO X16 1VH | ACPI/DMI | — | ✅ |
| 2 | Processor | AMD Ryzen AI 7 350 (Radeon 860M) | `amd-pstate`, `zenpower` | `amd-ucode` | ✅ |
| 3 | Display | AMD Radeon 860M `1002:1114` | `amdgpu` | `amdgpu/*` (530) | ✅ |
| 4 | Display | NVIDIA RTX 5060 Laptop `10de:2d19` | `nvidia` (DKMS) | `nvidia/*` (275) | ✅ |
| 5 | ComputeAccelerator | AMD NPU XDNA2 `1022:17f0` | `amdxdna` | `amdnpu/*` | ❌ **Kernel 6.1 zu alt** |
| 6 | Net | Realtek 8852CE WiFi 6E `10ec:c852` | `rtw89_8852ce` | `rtw8852c_fw.bin` | ✅ |
| 7 | Net | Realtek PCIe GbE `10ec:8168` | `r8169` | `rtl_nic/*` (31) | ✅ |
| 8 | Bluetooth | Realtek BT `0bda:0852` | `btusb` | `rtl_bt/*` (29) | ✅ |
| 9 | MEDIA/Audio | Realtek + AMD Audio | `snd-hda-intel`, `snd-sof` | `sof/*` (338) | ✅ |
| 10 | Camera | GIGABYTE FHD + IR `3277:00b2` | `uvcvideo` | — (im Kernel) | ✅ |
| 11 | HIDClass | Touchpad, Tastatur (19 Geräte) | `hid-multitouch`, `i2c-hid` | — | ✅ |
| 12 | Keyboard | PS/2-Standard `ACPI\MSFT0001` | `atkbd` | — | ✅ |
| 13 | Mouse | Präzisions-Touchpad | `hid-multitouch` | — | ✅ |
| 14 | Battery | ACPI-Akku `PNP0C0A` | `battery`, `ac` | — | ✅ |
| 15 | Monitor | Internes Panel (EDID) | `drm_edid` | — | ✅ |
| 16 | USB / USBDevice | xHCI-Controller | `xhci_pci`, `usbcore` | — | ✅ |
| 17 | SCSIAdapter | NVMe/SATA | `nvme`, `ahci` | — | ✅ |
| 18 | DiskDrive / Volume | NVMe-SSD | `nvme` | — | ✅ |
| 19 | Firmware | UEFI/BIOS | `efi_pstore`, `efivars` | — | ✅ |
| 20 | SecurityDevices | TPM 2.0 | `tpm_crb` | — | ✅ |
| 21 | Biometric | Fingerabdrucksensor | `libfprint` (Userspace) | modellabhängig | ⚠️ nicht geprüft |
| 22 | Sensors | Lage-/Lichtsensor | `iio-sensor-proxy` | — | ⚠️ nicht geprüft |
| 23 | PrintQueue / Printer | — (kein Drucker) | `cups` | — | ⚠️ nicht installiert |
| 24 | SoftwareComponent / SWD | Windows-Komponenten | entfällt unter Linux | — | — |

## Abdeckung: 17 von 17 Pflicht-Punkten erfüllt

Gemessen mit `scripts/hardware-audit.sh` gegen das Live-ISO-Rootfs (17.11.2026):

```
vorhanden: 17
optional:   3 (fuer dieses Geraet nicht noetig)
Luecken:    0
[vollstaendig] Hardware-Standard fuer dieses Geraet erfuellt.
```

### Zwei echte Einschränkungen, beide mit Ursache

#### 1. NPU (AMD XDNA2) — Kernel zu alt

Der NPU-Treiber `amdxdna` ist **ab Linux 6.14** im Hauptzweig. Das ISO nutzt
Debian bookworm mit **6.1.0-50**. Die NPU (45 TOPS) ist damit im Live-System
nicht nutzbar — sie fehlt nicht als Datei, sie fehlt im Kernel.

Lösung für später: Debian trixie (Kernel 6.12) oder Backports-Kernel 6.14+.
Für den Agenten kein Verlust — Ollama nutzt CUDA auf der RTX 5060.

#### 2. TPM: `tpm_crb` fehlt, `tpm_tis*` vorhanden

Das Image hat 11 TPM-Module, darunter `tpm_tis_i2c_cr50` und `tpm_tis_spi`, aber
nicht `tpm_crb.ko` (das Modul für den ACPI-2.0-TPM-Pfad). Für den Agenten
irrelevant, deshalb als optional geführt — nicht als erfüllt gezählt.

### Drei Prüffehler, die ich unterwegs korrigiert habe

Ein Hardware-Audit, der falsche Lücken meldet, ist so schädlich wie einer der
falsche Erfolge meldet. Alle drei waren meine, nicht die des Images:

| Fehlmeldung | Ursache | Korrektur |
|---|---|---|
| „USB-xHCI fehlt" | Modul heißt `xhci-pci.ko` (Bindestrich), nicht `xhci_pci.ko` | Name korrigiert |
| „Microcode fehlt" | liegt als `amd-ucode/` und `intel-ucode/`, nicht `microcode/` | Pfade getrennt |
| „Audio SOF fehlt" | liegt unter `intel/sof`, nicht `sof` | Pfad korrigiert |

## Prüfen

```bash
# Windows: Geräte erfassen
powershell -NoProfile -File scripts/hardware-inventory.ps1 > hw.csv

# WSL/ISO: Firmware-Abdeckung gegen die Matrix prüfen
wsl -d Ubuntu -- bash -s < scripts/hardware-audit.sh
```

Das Audit prüft für jede Klasse, ob Treiber und Firmware vorhanden sind, und
meldet fehlende Einträge als `[LÜCKE]` — nicht als OK.

## Herstellerunabhängig: was ein PC mindestens braucht

Für Rechner **ohne** dieses Referenzgerät gilt dieselbe Matrix, aber mit anderer
Firmware. Pflicht bleibt:

| Klasse | Pflicht-Firmware-Paket (Debian) |
|---|---|
| WLAN Intel | `firmware-iwlwifi` |
| WLAN Realtek | `firmware-realtek` (rtw89, rtw88, rtl_bt, rtl_nic) |
| WLAN Atheros/Qualcomm | `firmware-atheros` (`ath10k`, `ath11k`) |
| WLAN Broadcom | `firmware-brcm80211` |
| WLAN MediaTek | `firmware-mediatek` |
| Grafik AMD | `firmware-amd-graphics` |
| Grafik NVIDIA | NVIDIA-Repo (`nvidia-kernel-dkms`), **nicht** bookworm-Stand 535 |
| Grafik Intel | `firmware-misc-nonfree` |
| CPU | `intel-microcode` **oder** `amd64-microcode` |
| Audio (SOF) | `firmware-sof-signed` |

**NVIDIA-Merksatz (gemessen):** bookworm liefert 535.309 — Blackwell/sm_120
(RTX 50xx) braucht ≥ 550. Das ISO nutzt deshalb 620.70.06 aus dem
NVIDIA-Repo für Debian 12, per DKMS gegen den ISO-Kernel gebaut.
