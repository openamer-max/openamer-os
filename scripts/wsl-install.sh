#!/usr/bin/env bash
# OpenAmer-OS auf echter Hardware — Ebene 4: WSL als Träger mit GPU.
#
#   wsl -d Ubuntu -- bash -s < scripts/wsl-install.sh
#
# Warum dieser Weg: WSL ist ein vollstaendiges Linux auf dem Geraet und nutzt
# den WINDOWS-Treiber ueber /dev/dxg. Kein Linux-Treiber, kein Docker, keine
# Cloud — und die GPU (RTX 5060) ist mit 91 % im VRAM nutzbar.
#
# Gemessen am 17.11.2026:
#   Ubuntu 26.04.1 · Kernel 6.18.58.1-microsoft-standard-WSL2 · 16 Kerne · 15 GB
#   GPU: RTX 5060 8151 MiB, Treiber 621.14, /dev/dxg vorhanden
#   7B-Modell mit 65536 Kontext: 6,26/6,84 GB VRAM, 51 Tokens/s
#   Agent v2026.11.17 auf Python 3.13.18, Antwort in 23 s
#
# Drei Huerden, die dieses Skript nimmt:
#   1. Ubuntu 26.04 hat nur Python 3.14 — der Agent braucht < 3.14  -> uv 3.13
#   2. Der Agent verlangt >= 64.000 Kontext (MINIMUM_CONTEXT_LENGTH)
#      -> Modelfile mit PARAMETER num_ctx 65536
#   3. Windows-Ollama ist aus WSL nicht erreichbar (Firewall, HTTP 000)
#      -> das in WSL vorhandene Ollama nutzen (127.0.0.1:11434)
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"

BASE="$HOME/openamer-os"
ARCHIVE=/mnt/c/Users/amer7/openamer-agent-max/os/openamer-os/om-src.tgz
SRC_MODELLFILE=/mnt/c/Users/amer7/openamer-agent-max/model/openamer-max-one/Modelfile.openamer-max-tab
BASIS_MODELL=openamer-max-tab-rebuild   # 7B, muss im WSL-Ollama vorhanden sein
ZIEL_MODELL=om7b64k

echo "== 1. Hardware pruefen =="
if [ -e /dev/dxg ]; then echo "  [ok] GPU-Passthrough (/dev/dxg)"; else echo "  [warn] kein /dev/dxg — GPU fehlt"; fi
command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | sed 's/^/  /'
echo "  RAM: $(free -g | awk '/^Mem:/ {print $2" GB"}')  Disk: $(df -h / | awk 'NR==2 {print $4" frei"}')"

echo
echo "== 2. Ollama in WSL =="
if ! command -v ollama >/dev/null 2>&1; then
  echo "  ollama fehlt — bitte installieren: curl -fsSL https://ollama.com/install.sh | sh"
  exit 2
fi
echo "  $(ollama --version 2>&1 | head -1)"
curl -s --max-time 5 -o /dev/null -w "  API: HTTP %{http_code}\n" http://127.0.0.1:11434/api/tags || echo "  API nicht erreichbar — 'ollama serve &' starten"

echo
echo "== 3. Python 3.13 + Agent =="
if ! command -v uv >/dev/null 2>&1; then
  echo "  uv fehlt — installiere"; curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
mkdir -p "$BASE"; cd "$BASE"
if [ -x "$BASE/venv/bin/openamer" ]; then
  echo "  [ok] Agent bereits installiert: $("$BASE/venv/bin/openamer" --version 2>&1 | head -1)"
else
  [ -f "$ARCHIVE" ] || { echo "  FEHLER: $ARCHIVE fehlt (python omx.py os pack)"; exit 2; }
  rm -rf src && mkdir -p src && tar -xzf "$ARCHIVE" -C src
  uv python install 3.13 2>&1 | tail -1
  uv venv --python 3.13 venv 2>&1 | tail -1
  uv pip install --python venv/bin/python -e ./src 2>&1 | tail -2
  echo "  [ok] $("$BASE/venv/bin/openamer" --version 2>&1 | head -1)"
fi

echo
echo "== 4. 7B-Modell mit 64k-Kontext ($Basis -> $ZIEL_MODELL) =="
MODELS="$BASE/models"; mkdir -p "$MODELS"
if [ -f "$SRC_MODELLFILE" ]; then
  { echo "FROM $BASIS_MODELL"; grep -v "^FROM" "$SRC_MODELLFILE" | sed 's/^PARAMETER num_ctx .*/PARAMETER num_ctx 65536/'; } > "$MODELS/Modelfile.64k"
  ollama create "$ZIEL_MODELL" -f "$MODELS/Modelfile.64k" 2>&1 | tail -1
else
  echo "  [warn] $SRC_MODELLFILE fehlt — Modelfile manuell bauen: FROM $BASIS_MODELL + PARAMETER num_ctx 65536"
fi

echo
echo "== 5. Agent konfigurieren =="
export OPENAMER_HOME="$HOME/.openamer"
A="$BASE/venv/bin/openamer"
$A config set model.provider ollama >/dev/null 2>&1
$A config set model.base_url http://127.0.0.1:11434/v1 >/dev/null 2>&1
$A config set model.default "$ZIEL_MODELL" >/dev/null 2>&1
$A config set model.ollama_num_ctx 65536 >/dev/null 2>&1
$A config set model.context_length 65536 >/dev/null 2>&1
echo "  Modell: $ZIEL_MODELL · num_ctx 65536 · Provider ollama (127.0.0.1:11434)"

echo
echo "== 6. Test =="
timeout 300 $A chat -q "Antworte in einem Satz: Wer bist du?" 2>&1 | grep -vE "^\s*$" | tail -8

echo
echo "== Fertig =="
echo "  Starten:  cd $BASE && OPENAMER_HOME=\$HOME/.openamer ./venv/bin/openamer"
echo "  Modell:   $ZIEL_MODELL (7B, 65536 Kontext, GPU)"
