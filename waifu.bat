@echo off
REM ============================================================
REM  WAIFU - Lia App (Painel Desktop)
REM  Abre o app de desktop real.
REM ============================================================
chcp 65001 >nul
title Lia App
cd /d "%~dp0"

REM Verificar se customtkinter esta instalado (silencioso)
pythonw -c "import customtkinter" 2>nul
if errorlevel 1 (
    pip install customtkinter --quiet 2>nul
)

REM Abrir o app (pythonw = sem console)
start "" pythonw app\lia_app.py
