@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0PRIMEIRA_CONFIGURACAO_SRIS.ps1"
