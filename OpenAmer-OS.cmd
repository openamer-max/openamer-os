@echo off
REM ============================================================================
REM  OpenAmer-OS — Startbereit (Windows)
REM
REM  Doppelklick = interaktiver Chat mit dem eigenen Modell auf der GPU.
REM  Modellwahl macht start.sh: openamer-max-vl-8b (8B, Vision) wenn registriert,
REM  sonst openamer-max-7b. Der Shortcut muss dafuer nicht geaendert werden.
REM  Mit Argument: OpenAmer-OS.cmd chat -q "..."
REM
REM  Ruft IMMER start.sh im Projektordner auf — dort sitzt die Selbstheilung:
REM    Config wird auf das lokale Modell gezwungen (sonst Cloud-Default)
REM    fehlende Skills/Plugins werden ergaenzt
REM    Ollama und Modell werden geprueft und gestartet
REM ============================================================================
setlocal EnableExtensions
chcp 65001 >nul 2>&1
title OpenAmer-OS — Agent + OpenAmer-Max 8B-VL (GPU)

set "PROJEKT=/OpenAmer All in One"

REM --- 1. WSL starten, falls aus -------------------------------------------
wsl -d Ubuntu -- true >nul 2>&1
if errorlevel 1 (
  echo [1/2] WSL wird gestartet ...
  wsl -d Ubuntu -- true >nul 2>&1
)

REM --- 2. Pruefen, ob der Projektordner erreichbar ist ----------------------
wsl -d Ubuntu -- bash -c "test -x '%PROJEKT%/start.sh'" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   FEHLER: %PROJEKT%/start.sh nicht gefunden.
  echo   Erst installieren:  INSTALL.cmd
  echo.
  pause
  exit /b 2
)

REM --- 3. Agent starten (start.sh heilt Config, Skills, Plugins, Ollama) ----
wsl -d Ubuntu --cd "%PROJEKT%" -- bash ./start.sh %*

set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo   Der Agent endete mit Code %RC%.
  echo   Diagnose:  OpenAmer-OS.cmd --audit
  echo.
  pause
)
endlocal
