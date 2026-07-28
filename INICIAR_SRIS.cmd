@echo off
cd /d "%~dp0"
if not exist ".env" (
  echo Falta a configuracao inicial.
  echo Execute primeiro PRIMEIRA_CONFIGURACAO_SRIS.cmd
  pause
  exit /b 1
)
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SRIS_LAUNCHER.ps1"
