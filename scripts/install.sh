#!/usr/bin/env bash
# OpenAmer-OS — Installation (Linux/WSL), idempotent und selbstpruefend.
#
#   bash scripts/install.sh          installiert / repariert
#   bash scripts/install.sh --check  prueft nur, aendert nichts
#
# Jeder Schritt prueft zuerst, ob er schon erledigt ist. Ein zweiter Lauf
# aendert nichts und meldet dasselbe Ergebnis.
#
# Voraussetzungen, die dieses Skript NICHT herstellen kann:
#   - WSL2 + Ubuntu (Windows: INSTALL.cmd, braucht Admin und einen Neustart)
#   - NVIDIA-Treiber unter Windows (fuer GPU-Beschleunigung)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1
MODELL=openamer-max-7b
FEHLER=0
WARNUNGEN=0

ok()    { printf "  [ok]    %s\n" "$*"; }
warn()  { printf "  [warn]  %s\n" "$*"; WARNUNGEN=$((WARNUNGEN+1)); }
fail()  { printf "  [fail]  %s\n" "$*"; FEHLER=$((FEHLER+1)); }
schritt(){ printf "\n== %s ==\n" "$*"; }

echo "OpenAmer-OS Installation"
echo "Ordner: $HERE"
[ "$CHECK_ONLY" = 1 ] && echo "Modus:  nur pruefen (keine Aenderungen)"

# ---------------------------------------------------------------- 1. System
schritt "1. System"
if grep -qi microsoft /proc/version 2>/dev/null; then
  ok "WSL2: $(uname -r)"
else
  ok "Linux: $(uname -r)"
fi
[ "$(id -u)" = "0" ] && ok "Rechte: root" || warn "kein root — systemd-Dienste brauchen evtl. sudo"
printf "  Speicher: %s GB RAM, %s frei auf /\n" \
  "$(free -g | awk '/^Mem:/ {print $2}')" "$(df -h / | awk 'NR==2 {print $4}')"

# ---------------------------------------------------------------- 2. GPU
schritt "2. Hardware"
if [ -e /dev/dxg ]; then
  ok "GPU-Passthrough aktiv (/dev/dxg)"
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | sed 's/^/          /'
  else
    warn "nvidia-smi fehlt — Modell rechnet auf der CPU"
  fi
else
  warn "kein /dev/dxg — GPU nicht durchgereicht (Modell laeuft auf CPU, langsamer)"
fi

# ---------------------------------------------------------------- 3. Python
schritt "3. Python (im Ordner)"
ORDNER_PY=$(ls -d "$HERE"/agent/python/cpython-3.13*/bin/python3 2>/dev/null | head -1)
if [ -x "$ORDNER_PY" ]; then
  ok "Ordner-Python: $("$ORDNER_PY" --version 2>&1)"
else
  fail "Ordner-Python fehlt (agent/python/) — Ordner unvollstaendig"
  echo "          Nachziehen: uv python install --install-dir \"$HERE/agent/python\" 3.13"
  ORDNER_PY=""
fi

# ---------------------------------------------------------------- 4. Laufzeit
schritt "4. Agent-Laufzeit"
if [ -x "$HERE/agent/venv/bin/openamer" ]; then
  ok "venv vorhanden: $("$HERE/agent/venv/bin/openamer" --version 2>&1 | head -1)"
else
  if [ "$CHECK_ONLY" = 1 ]; then
    fail "venv fehlt (wird bei Installation angelegt)"
  elif [ -z "$ORDNER_PY" ]; then
    fail "venv fehlt und kein Ordner-Python"
  else
    echo "  lege venv an ..."
    "$ORDNER_PY" -m venv "$HERE/agent/venv" 2>&1 | tail -1
    "$HERE/agent/venv/bin/python" -m pip install -q --upgrade pip 2>&1 | tail -1
    if "$HERE/agent/venv/bin/python" -m pip install -q -e "$HERE/agent/src" 2>&1 | tail -3; then
      ok "venv angelegt: $("$HERE/agent/venv/bin/openamer" --version 2>&1 | head -1)"
    else
      fail "Installation des Agenten fehlgeschlagen"
    fi
  fi
fi

# ---------------------------------------------------------------- 5. Ollama
schritt "5. Ollama (Modell-Backend)"
if ! command -v ollama >/dev/null 2>&1; then
  if [ "$CHECK_ONLY" = 1 ]; then
    fail "ollama fehlt"
  else
    echo "  installiere Ollama ..."
    curl -fsSL https://ollama.com/install.sh -o /tmp/ollama-install.sh 2>/dev/null \
      && sh /tmp/ollama-install.sh >/dev/null 2>&1 \
      && ok "Ollama installiert: $(ollama --version 2>&1 | head -1)" \
      || fail "Ollama-Installation fehlgeschlagen"
  fi
else
  ok "Ollama: $(ollama --version 2>&1 | head -1)"
fi

# Dienst starten, falls nicht erreichbar
if ! curl -s --max-time 4 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null; then
  if [ "$CHECK_ONLY" = 0 ] && command -v ollama >/dev/null 2>&1; then
    echo "  starte Ollama-Dienst ..."
    sudo -n systemctl start ollama 2>/dev/null || (ollama serve >/dev/null 2>&1 &)
    for _ in $(seq 1 30); do
      curl -s --max-time 2 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null && break
      sleep 1
    done
  fi
fi
curl -s --max-time 5 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null \
  && ok "Ollama-API erreichbar" || fail "Ollama-API nicht erreichbar"

# ---------------------------------------------------------------- 6. Modell
schritt "6. Modell $MODELL"
if curl -s --max-time 6 http://127.0.0.1:11434/api/tags 2>/dev/null | grep -q "$MODELL"; then
  ok "$MODELL registriert"
else
  if [ "$CHECK_ONLY" = 1 ]; then
    fail "$MODELL fehlt (wird bei Installation registriert)"
  else
    echo "  registriere aus dem Ordner ..."
    bash "$HERE/scripts/register-model.sh" >/dev/null 2>&1 \
      && ok "$MODELL registriert" || fail "Registrierung fehlgeschlagen"
  fi
fi

# ---------------------------------------------------------------- 7. Agent-Config
schritt "7. Agent-Konfiguration"
export OPENAMER_HOME="${OPENAMER_HOME:-$HOME/.openamer}"
CFG="$OPENAMER_HOME/config.yaml"
if [ -f "$CFG" ] && grep -q "default: $MODELL" "$CFG" 2>/dev/null; then
  ok "Konfiguration gesetzt ($CFG)"
else
  if [ "$CHECK_ONLY" = 1 ]; then
    warn "Konfiguration noch nicht gesetzt"
  elif [ -x "$HERE/agent/venv/bin/openamer" ]; then
    mkdir -p "$OPENAMER_HOME"
    A="$HERE/agent/venv/bin/openamer"
    $A config set model.provider ollama >/dev/null 2>&1
    $A config set model.base_url http://127.0.0.1:11434/v1 >/dev/null 2>&1
    $A config set model.default "$MODELL" >/dev/null 2>&1
    $A config set model.ollama_num_ctx 65536 >/dev/null 2>&1
    $A config set model.context_length 65536 >/dev/null 2>&1
    ok "Konfiguration geschrieben ($CFG)"
  else
    fail "Agent fehlt — Konfiguration nicht moeglich"
  fi
fi

# ---------------------------------------------------------------- 8. Befehl
schritt "8. Befehl openamer"
if [ -x /usr/local/bin/openamer ]; then
  ok "/usr/local/bin/openamer vorhanden"
elif [ "$CHECK_ONLY" = 1 ]; then
  warn "globaler Befehl fehlt"
else
  cat > /usr/local/bin/openamer <<WRAPPER
#!/bin/bash
export OPENAMER_HOME="\${OPENAMER_HOME:-\$HOME/.openamer}"
exec "$HERE/agent/venv/bin/openamer" "\$@"
WRAPPER
  chmod +x /usr/local/bin/openamer
  ok "installiert: $(command -v openamer)"
fi

# ---------------------------------------------------------------- 9. Test
schritt "9. Funktionstest"
if [ -x "$HERE/agent/venv/bin/openamer" ] && curl -s --max-time 5 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null; then
  if [ "$CHECK_ONLY" = 1 ]; then
    ok "Voraussetzungen erfuellt (kein Modellaufruf im Pruefmodus)"
  else
    echo "  frage das Modell (kann 30 s dauern) ..."
    LOG=$(timeout 180 "$HERE/agent/venv/bin/openamer" chat -q "Antworte mit einem Wort: bereit?" 2>&1)
    # Die Antwort steht zwischen den Rahmenzeichen der Ausgabe-Box.
    ANT=$(printf '%s\n' "$LOG" | sed -n '/OpenAmer/,/╰/p' | grep -v '╭' | grep -v '╰' | sed 's/^[[:space:]]*//' | grep -v '^$' | head -2 | tr '\n' ' ')
    if [ -n "$ANT" ]; then
      ok "Agent antwortet: ${ANT:0:70}"
    else
      warn "keine Antwort erhalten (Modell evtl. noch am Laden)"
    fi
  fi
else
  fail "Test uebersprungen — Voraussetzungen fehlen"
fi

# ---------------------------------------------------------------- Ergebnis
schritt "Ergebnis"
printf "  Fehler:    %s\n" "$FEHLER"
printf "  Warnungen: %s\n" "$WARNUNGEN"
if [ "$FEHLER" -eq 0 ]; then
  echo
  echo "  [fertig] Startbereit.  Aufruf: ./start.sh"
  exit 0
else
  echo
  echo "  [unvollstaendig] $FEHLER Punkt(e) offen (siehe [fail] oben)."
  exit 1
fi
