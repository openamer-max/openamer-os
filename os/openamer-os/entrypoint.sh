#!/usr/bin/env bash
# OpenAmer-OS Entrypoint — startet den Agenten als Dienst.
# Grundsatz: erst messen, dann melden. Kein stiller Fehlschlag.
set -euo pipefail

echo "[openamer-os] Start $(date -u +%FT%TZ)"
echo "[openamer-os] Home: ${OPENAMER_HOME}"

mkdir -p "${OPENAMER_HOME}/logs" "${OPENAMER_HOME}/sessions"

if [ -x /opt/openamer/venv/bin/openamer ]; then
    AGENT=/opt/openamer/venv/bin/openamer
elif command -v openamer >/dev/null 2>&1; then
    AGENT=$(command -v openamer)
else
    echo "[openamer-os] FEHLER: kein openamer-Binary gefunden." >&2
    echo "[openamer-os] Das Image wurde ohne Quellbaum gebaut (Ebene 1)." >&2
    tail -f /dev/null
fi

echo "[openamer-os] Agent: ${AGENT}"
"${AGENT}" doctor || echo "[openamer-os] doctor meldet Befunde (siehe oben)"

# Dienst-Modus: Dashboard/Gateway, damit der Container sinnvoll laeuft.
exec "${AGENT}" gateway
