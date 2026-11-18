#!/usr/bin/env bash
# VL-8B lokal installieren, ohne ollama-Registry.
#
# Warum es diesen Weg gibt: `ollama pull hf.co/...` scheitert auf diesem Rechner an
# der Namensauflösung des HF-CDN ("lookup us.aws.cdn.hf.co: no such host"), obwohl
# Windows den Namen auflöst und die Datei per HTTPS erreichbar ist (Range-Request
# HTTP 206, Kopf "GGUF"). curl kommt durch, also laden wir mit curl und bauen das
# Modell lokal mit "ollama create".
#
# Aufruf:  bash scripts/install-vl8b-local.sh
set -euo pipefail

ZIEL="${1:-$HOME/omx-8b}"
DATEI="openamer-max-vl-8b-Q4_K_M.gguf"
URL="https://huggingface.co/openamer-max/openamer-max-vl-8b/resolve/main/$DATEI"
SOLL_BYTES=5027784992

mkdir -p "$ZIEL"
cd "$ZIEL"

if [ -f "$DATEI" ] && [ "$(stat -c%s "$DATEI" 2>/dev/null || stat -f%z "$DATEI")" -eq "$SOLL_BYTES" ]; then
  echo "[ok]   $DATEI ist vollständig ($SOLL_BYTES B)"
else
  echo "[..] lade $DATEI (4,7 GB) ..."
  curl -L --fail --retry 3 -C - -o "$DATEI" "$URL"
  IST=$(stat -c%s "$DATEI" 2>/dev/null || stat -f%z "$DATEI")
  if [ "$IST" -ne "$SOLL_BYTES" ]; then
    echo "[FEHLER] Größe $IST B, erwartet $SOLL_BYTES B" >&2
    exit 2
  fi
  echo "[ok]   $DATEI geladen ($IST B)"
fi

cat > Modelfile.vl8b <<'EOF'
FROM ./openamer-max-vl-8b-Q4_K_M.gguf
PARAMETER num_ctx 16384
PARAMETER temperature 0.3
SYSTEM """Du bist OpenAmer, ein persoenlicher KI-Assistent von Amer Sacirovic aus der Schweiz. Du laeufst lokal auf dem Geraet des Nutzers, ohne Cloud und ohne Konto."""
EOF

ollama rm openamer-max-vl-8b >/dev/null 2>&1 || true
ollama create openamer-max-vl-8b -f Modelfile.vl8b
ollama list | grep -i "openamer-max-vl-8b" || { echo "[FEHLER] Modell nicht registriert" >&2; exit 3; }

cat <<'HINWEIS'

Fertig. Zwei Dinge, die man wissen muss:

  1. Kontext: dieses Modell läuft mit 16.384 Token. Der OpenAmer-Agent verlangt
     65.536 — ein 8B mit 64k bräuchte ~15 GB VRAM, hier sind 8 GB vorhanden.
     Für den Agenten bleibt deshalb openamer-max-7b zuständig.

  2. Qualität: 17/24 auf dem Prüfsatz, das 7B erreicht 22/24. Das Modell ist
     zum Ausprobieren und Weiterentwickeln da, nicht als Ersatz.

Aufruf:  ollama run openamer-max-vl-8b
HINWEIS
