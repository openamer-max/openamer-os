@echo off
REM ============================================================================
REM  OpenAmer-OS — Installation (Windows-Seite)
REM
REM  Doppelklick. Das Skript prueft die Voraussetzungen und richtet den Agenten
REM  in WSL ein. Rechnet mit 3-10 Minuten beim ersten Mal.
REM
REM  Es kann NICHT herstellen (Windows-Grenzen):
REM    - WSL2 selbst -> braucht Administrator und einen Neustart
REM    - NVIDIA-Treiber -> kommt vom Hersteller
REM  Beides wird geprueft und mit Anleitung gemeldet.
REM ============================================================================
setlocal EnableDelayedExpansion
title OpenAmer-OS — Installation

set "HIER=%~dp0"
set "HIER=%HIER:~0,-1%"
set "WSL_ORDNER=/OpenAmer All in One"
set "FEHLER=0"

echo ============================================================
echo   OpenAmer-OS — Installation
echo ============================================================
echo   Quelle: %HIER%
echo.

REM ---------------------------------------------------------------- 1. Windows
echo [1/6] Windows pruefen ...
for /f "tokens=4-5 delims=. " %%i in ('ver') do set "WINVER=%%i.%%j"
echo       Windows %WINVER%

REM ---------------------------------------------------------------- 2. WSL
echo [2/6] WSL pruefen ...
wsl -d Ubuntu -- true >nul 2>&1
if errorlevel 1 (
  echo.
  echo   WSL mit Ubuntu ist NICHT einsatzbereit.
  echo.
  echo   Einmalig als Administrator ausfuehren:
  echo       wsl --install -d Ubuntu
  echo   Danach Windows neu starten und dieses Skript erneut starten.
  echo.
  echo   Ohne WSL gibt es kein OpenAmer-OS auf diesem PC.
  set "FEHLER=1"
  goto :ende
)
echo       WSL + Ubuntu: bereit

REM ---------------------------------------------------------------- 3. WSL-Version
wsl -d Ubuntu -- bash -c "test -e /dev/dxg" >nul 2>&1
if errorlevel 1 (
  echo [3/6] GPU:      kein /dev/dxg — Modell rechnet auf der CPU ^(langsamer^)
) else (
  echo [3/6] GPU:      Passthrough aktiv
)

REM ---------------------------------------------------------------- 4. Ordner in WSL
echo [4/6] Projektordner in WSL ...
wsl -d Ubuntu -- bash -c "test -d '%WSL_ORDNER%'" >nul 2>&1
if errorlevel 1 (
  echo       nicht vorhanden — kopiere aus %HIER%
  wsl -d Ubuntu -- bash -c "mkdir -p '%WSL_ORDNER%'" >nul 2>&1
  REM Windows-Pfad in WSL-Form bringen und kopieren
  for /f "usebackq delims=" %%p in (`wsl -d Ubuntu -- wslpath -u "%HIER%"`) do set "WSL_QUELLE=%%p"
  wsl -d Ubuntu -- bash -c "cp -a '!WSL_QUELLE!'/. '%WSL_ORDNER%'/" >nul 2>&1
  if errorlevel 1 (
    echo       FEHLER beim Kopieren
    set "FEHLER=1"
    goto :ende
  )
  echo       kopiert nach %WSL_ORDNER%
) else (
  echo       vorhanden: %WSL_ORDNER%
)

REM ---------------------------------------------------------------- 5. Installation in WSL
echo [5/6] Installation in WSL ^(kann einige Minuten dauern^) ...
echo.
wsl -d Ubuntu --cd "%WSL_ORDNER%" -- bash scripts/install.sh
if errorlevel 1 (
  echo.
  echo   Die Installation meldet offene Punkte ^(siehe [fail] oben^).
  set "FEHLER=1"
)

REM ---------------------------------------------------------------- 6. Verknuepfung
echo.
echo [6/6] Desktop-Verknuepfung ...
powershell -NoProfile -Command ^
  "$w=New-Object -ComObject WScript.Shell; $p=Join-Path ([Environment]::GetFolderPath('Desktop')) 'OpenAmer-OS.lnk'; $s=$w.CreateShortcut($p); $s.TargetPath='%HIER%\OpenAmer-OS.cmd'; $s.WorkingDirectory='%HIER%'; $s.Description='OpenAmer-OS - Agent + OpenAmer-Max 7B (GPU)'; if (Test-Path '%HIER%\dist\openamer.ico') { $s.IconLocation='%HIER%\dist\openamer.ico' }; $s.Save(); if (Test-Path $p) { '      erstellt: ' + $p } else { '      FEHLER' }"

:ende
echo.
echo ============================================================
if "%FEHLER%"=="0" (
  echo   [fertig] Installation abgeschlossen.
  echo.
  echo   Starten:  Doppelklick auf "OpenAmer-OS" auf dem Desktop
  echo             oder: OpenAmer-OS.cmd
) else (
  echo   [unvollstaendig] Bitte die Meldungen oben beachten.
)
echo ============================================================
echo.
pause
endlocal
