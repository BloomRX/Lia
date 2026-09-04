@echo off
REM ============================================================
REM  iniciar_alltalk.bat - Inicia o AllTalk TTS v2 (local)
REM  Relativo a %~dp0. Funciona de qualquer lugar.
REM ============================================================
chcp 65001 >nul
title AllTalk TTS v2
cd /d "%~dp0alltalk_tts"

if exist "start_alltalk.bat" (
    call start_alltalk.bat
) else if exist "script.py" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo [ERRO] Python nao encontrado.
    ) else (
        python script.py
    )
) else (
    echo [ERRO] Nao achei start_alltalk.bat nem script.py em:
    echo   %CD%
    echo Rode instalar_alltalk.bat antes.
    echo.
    pause
)
