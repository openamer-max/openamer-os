#!/usr/bin/env bash
# Registriert OpenAmer-Max-7B in Ollama — reproduzierbar aus diesem Ordner.
#
#   bash scripts/register-model.sh
#
# Warum ein eigenes Skript: Der Agent prueft den TATSAECHLICH geladenen
# Kontext. Hat das Modell nur 16.384 Token, bricht er mit
# "runtime context is too small for OpenAmer tool use" ab — unabhaengig davon,
# was in der config.yaml steht. Deshalb muss das Modell mit num_ctx 65536
# gebaut werden, nicht nur konfiguriert.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELFILE="$HERE/model/openamer-max-one/Modelfile.max-7b"
ZIEL=openamer-max-7b
BASIS=openamer-max-tab-rebuild

echo "== Voraussetzungen =="
if ! command -v ollama >/dev/null 2>&1; then
  echo "  FEHLER: ollama fehlt" >&2; exit 2
fi
if ! curl -s --max-time 5 -o /dev/null http://127.0.0.1:11434/api/tags; then
  echo "  FEHLER: Ollama laeuft nicht (ollama serve)" >&2; exit 2
fi
echo "  ollama: $(ollama --version 2>&1 | head -1)"

echo
echo "== Basismodell $BASIS =="
if ollama show "$BASIS" >/dev/null 2>&1; then
  echo "  vorhanden"
else
  echo "  fehlt — versuche aus den Blobs neu zu bauen"
  if ! python3 "$HERE/model/openamer-max-one/rebuild_from_manifest.py" openamer-max-tab --create --as "$BASIS"; then
    echo "  FEHLER: Basismodell weder vorhanden noch rekonstruierbar" >&2
    echo "  Alternative: ein anderes 7B-Modell eintragen (FROM in $MODELFILE)" >&2
    exit 1
  fi
fi

echo
echo "== $ZIEL registrieren =="
if [ ! -f "$MODELFILE" ]; then
  echo "  FEHLER: $MODELFILE fehlt" >&2; exit 2
fi
ollama create "$ZIEL" -f "$MODELFILE" 2>&1 | tail -2

echo
echo "== Kontrolle =="
if ollama show "$ZIEL" >/dev/null 2>&1; then
  printf "  Modell:  %s\n" "$ZIEL"
  ollama show "$ZIEL" 2>/dev/null | grep -iE "parameters|context|family" | head -4 | sed 's/^/  /'
  echo "  [ok] registriert"
  echo
  echo "  Naechster Schritt:  ./start.sh --version"
else
  echo "  [fail] Modell nicht registriert" >&2
  exit 1
fi
