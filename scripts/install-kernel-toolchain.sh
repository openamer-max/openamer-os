#!/usr/bin/env bash
# Richtet die Bau-Toolchain fuer den OpenAmer-OS-Kernel in WSL ein.
#
# Aufruf aus Windows:
#   wsl -d Ubuntu -- bash -s < scripts/install-kernel-toolchain.sh
#
# Gemessener Ausgangszustand (17.11.2026): rustup installiert cargo nach
# ~/.cargo/bin (fehlt im nicht-interaktiven PATH), cc/gcc/make/qemu fehlen,
# nur das Target x86_64-unknown-linux-gnu war vorhanden — der Kernel braucht
# x86_64-unknown-none und x86_64-unknown-uefi.
set -euo pipefail
export PATH="$HOME/.cargo/bin:$PATH"

echo "== apt: build-essential + qemu =="
sudo -n apt-get update -qq
sudo -n DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
  build-essential qemu-system-x86 qemu-utils pkg-config >/dev/null

echo "== rust: nightly + rust-src + targets =="
if ! command -v cargo >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup.sh
  sh /tmp/rustup.sh -y --default-toolchain none --profile minimal
fi
rustup toolchain install nightly --profile minimal -c rust-src >/dev/null 2>&1 || true
rustup target add --toolchain nightly x86_64-unknown-none x86_64-unknown-uefi

echo
echo "== Endstand =="
for t in cc gcc make ld qemu-system-x86_64; do
  printf "  %-20s %s\n" "$t" "$(command -v "$t" || echo FEHLT)"
done
echo "  cargo:   $(cargo --version)"
echo "  targets:"
rustup target list --installed --toolchain nightly | sed 's/^/    /'
