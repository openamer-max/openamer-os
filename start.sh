#!/usr/bin/env bash
# OpenAmer-OS — Starter (Linux/WSL) mit Selbstheilung
#
#   ./start.sh                 interaktiver Chat (TUI)
#   ./start.sh chat -q "..."   Einzelauftrag
#   ./start.sh --version       Version pruefen
#   ./start.sh --audit         nur pruefen, nichts starten
#
# Heilt vier Fehler, die gemessen aufgetreten sind:
#   1. Config wird vom Agenten mit Cloud-Default ueberschrieben
#      (anthropic/claude-opus-4.6) -> Modell/Provider werden erzwungen
#   2. Skills fehlen in WSL (259 statt 328) -> Sync aus der Windows-Installation
#   3. Plugins fehlen komplett (openamer-rag, free-api-hub) -> Sync
#   4. Ollama-Dienst aus oder Modell nicht registriert -> starten/registrieren
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HERE/agent/venv/bin/openamer"
export OPENAMER_HOME="${OPENAMER_HOME:-$HOME/.openamer}"
# Modellwahl: ausdrueckliche Vorgabe > registriertes Modell (Reihenfolge unten) >
# Standard. Damit uebernimmt das OS ein neu trainiertes Modell automatisch, sobald
# es in Ollama registriert ist — ohne Aenderung am Shortcut.
MOD_KANDIDATEN="openamer-max-vl-8b openamer-max-7b"
modell_aus_ollama() {
  local tags k
  tags="$(curl -s --max-time 3 http://127.0.0.1:11434/api/tags 2>/dev/null)" || return 1
  [ -n "$tags" ] || return 1
  for k in $MOD_KANDIDATEN; do
    printf '%s' "$tags" | grep -q "\"$k" && { printf '%s' "$k"; return 0; }
  done
  return 1
}
MODELL="${OPENAMER_MODEL:-$(modell_aus_ollama || echo openamer-max-7b)}"
WIN_OPENAMER="/mnt/c/Users/amer7/AppData/Local/openamer"
AUDIT=0
[ "${1:-}" = "--audit" ] && AUDIT=1
PROBLEME=0

sag()  { printf "  %s\n" "$*"; }
ok()   { printf "  [ok]    %s\n" "$*"; }
heil() { printf "  [fix]   %s\n" "$*"; }
warn() { printf "  [warn]  %s\n" "$*"; PROBLEME=$((PROBLEME+1)); }

# ---------------------------------------------------------------- 1. Agent
if [ ! -x "$BIN" ]; then
  echo "FEHLER: Agent fehlt: $BIN" >&2
  echo "Einrichten: bash scripts/install.sh" >&2
  exit 2
fi

# ---------------------------------------------------------------- 2. Config
CFG="$OPENAMER_HOME/config.yaml"
mkdir -p "$OPENAMER_HOME"

config_ok() {
  [ -f "$CFG" ] || return 1
  grep -q "default: $MODELL" "$CFG" 2>/dev/null || return 1
  grep -q "provider: ollama" "$CFG" 2>/dev/null || return 1
  grep -q "127.0.0.1:11434" "$CFG" 2>/dev/null || return 1
  return 0
}

if config_ok; then
  ok "Config: $MODELL auf lokalem Ollama"
else
  if [ "$AUDIT" = 1 ]; then
    warn "Config zeigt nicht auf $MODELL (waere zu reparieren)"
  else
    heil "Config wird auf $MODELL (lokal) gesetzt"
    "$BIN" config set model.provider ollama >/dev/null 2>&1
    "$BIN" config set model.base_url http://127.0.0.1:11434/v1 >/dev/null 2>&1
    "$BIN" config set model.default "$MODELL" >/dev/null 2>&1
    "$BIN" config set model.ollama_num_ctx 65536 >/dev/null 2>&1
    "$BIN" config set model.context_length 65536 >/dev/null 2>&1
    config_ok && ok "Config repariert" || warn "Config laesst sich nicht setzen"
  fi
fi

# ---------------------------------------------------------------- 3. Skills + Plugins
SK="$OPENAMER_HOME/skills"
PL="$OPENAMER_HOME/plugins"
n_skills=$(find "$SK" -name SKILL.md 2>/dev/null | wc -l)
n_plugins=$(ls "$PL" 2>/dev/null | wc -l)

if [ -d "$WIN_OPENAMER/skills" ]; then
  n_win=$(find "$WIN_OPENAMER/skills" -name SKILL.md 2>/dev/null | wc -l)
  if [ "$n_skills" -lt "$n_win" ]; then
    if [ "$AUDIT" = 1 ]; then
      warn "Skills unvollstaendig: $n_skills von $n_win"
    else
      heil "Skills ergaenzen: $n_skills -> $n_win"
      rsync -a --ignore-existing "$WIN_OPENAMER/skills/" "$SK/" 2>/dev/null
      n_skills=$(find "$SK" -name SKILL.md 2>/dev/null | wc -l)
      ok "Skills: $n_skills"
    fi
  else
    ok "Skills: $n_skills (vollstaendig)"
  fi
else
  ok "Skills: $n_skills"
fi

if [ -d "$WIN_OPENAMER/plugins" ]; then
  for p in "$WIN_OPENAMER"/plugins/*/; do
    name=$(basename "$p")
    if [ ! -d "$PL/$name" ]; then
      if [ "$AUDIT" = 1 ]; then
        warn "Plugin fehlt: $name"
      else
        mkdir -p "$PL"
        rsync -a "$p" "$PL/$name/" 2>/dev/null && heil "Plugin ergaenzt: $name"
      fi
    fi
  done
  n_plugins=$(ls "$PL" 2>/dev/null | wc -l)
fi
ok "Plugins: $n_plugins"

# ---------------------------------------------------------------- 4. Ollama
if ! curl -s --max-time 5 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null; then
  if [ "$AUDIT" = 1 ]; then
    warn "Ollama nicht erreichbar"
  else
    heil "Ollama wird gestartet"
    systemctl start ollama 2>/dev/null || (ollama serve >/dev/null 2>&1 &)
    for _ in $(seq 1 30); do
      curl -s --max-time 2 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null && break
      sleep 1
    done
  fi
fi
if curl -s --max-time 5 -o /dev/null http://127.0.0.1:11434/api/tags 2>/dev/null; then
  ok "Ollama: erreichbar"
else
  warn "Ollama: nicht erreichbar (Modell antwortet nicht)"
fi

# ---------------------------------------------------------------- 5. Modell
# Automatische Uebernahme: ist ein besserer Kandidat registriert, wird er genommen
# und die Config nachgezogen (Reihenfolge siehe MOD_KANDIDATEN). So landet ein neu
# trainiertes Modell ohne Handgriff im Shortcut-Start.
BESSER="$(modell_aus_ollama || true)"
if [ -n "$BESSER" ] && [ "$BESSER" != "$MODELL" ] && [ -z "${OPENAMER_MODEL:-}" ]; then
  if [ "$AUDIT" = 1 ]; then
    warn "besseres Modell registriert: $BESSER (statt $MODELL) — Config wuerde umgestellt"
  else
    heil "besseres Modell uebernommen: $MODELL -> $BESSER"
    "$BIN" config set model.default "$BESSER" >/dev/null 2>&1
    MODELL="$BESSER"
  fi
fi
if curl -s --max-time 6 http://127.0.0.1:11434/api/tags 2>/dev/null | grep -q "\"$MODELL"; then
  ok "Modell: $MODELL registriert"
else
  if [ "$AUDIT" = 1 ]; then
    warn "Modell $MODELL fehlt"
  else
    heil "Modell $MODELL wird registriert"
    bash "$HERE/scripts/register-model.sh" >/dev/null 2>&1 \
      && ok "Modell registriert" || warn "Registrierung fehlgeschlagen"
  fi
fi

# ---------------------------------------------------------------- 6. Reasoning
# Gemessener Fehler: Ollama antwortet HTTP 400 '"<modell>" does not support
# thinking', wenn reasoning_effort mit einem Level (low/medium/high) an ein
# Modell ohne thinking-Capability geht. Der custom-Provider (lokales Ollama)
# sendet dann reasoning_effort="none" + think=false — das akzeptiert Ollama.
CAPS="$(curl -s --max-time 6 http://127.0.0.1:11434/api/show -d "{\"model\":\"$MODELL\"}" 2>/dev/null)"
if printf '%s' "$CAPS" | grep -q '"thinking"'; then
  THINK=ja
  REASON_SOLL=medium
else
  THINK=nein
  REASON_SOLL=false
fi
REASON_IST="$(grep -E '^  reasoning_effort:' "$CFG" 2>/dev/null | head -1 | awk '{print $2}')"
if [ "$REASON_IST" = "$REASON_SOLL" ]; then
  ok "Reasoning: $REASON_IST (thinking: $THINK)"
elif [ "$AUDIT" = 1 ]; then
  warn "reasoning_effort=$REASON_IST passt nicht zu $MODELL (thinking: $THINK, soll: $REASON_SOLL) -> HTTP 400"
else
  heil "reasoning_effort: $REASON_IST -> $REASON_SOLL (thinking: $THINK)"
  "$BIN" config set agent.reasoning_effort "$REASON_SOLL" >/dev/null 2>&1
  REASON_IST="$(grep -E '^  reasoning_effort:' "$CFG" 2>/dev/null | head -1 | awk '{print $2}')"
  if [ "$REASON_IST" = "$REASON_SOLL" ]; then
    ok "Reasoning: $REASON_IST"
  else
    warn "reasoning_effort laesst sich nicht setzen"
  fi
fi

# ---------------------------------------------------------------- Ergebnis
echo
if [ "$AUDIT" = 1 ]; then
  printf "  Audit: %s Problem(e)\n" "$PROBLEME"
  exit $([ "$PROBLEME" -eq 0 ] && echo 0 || echo 1)
fi

echo "=====================================[ start ]"
exec "$BIN" "$@"
