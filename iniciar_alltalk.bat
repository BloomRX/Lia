@echo off
REM ============================================================
REM  iniciar_alltalk.bat - Inicia o AllTalk TTS v2 (CPU)
REM  Relativo a %~dp0. Funciona de qualquer lugar.
REM  Prefere o venv criado por instalar_alltalk.bat.
REM ============================================================
chcp 65001 >nul
title AllTalk TTS v2
cd /d "%~dp0alltalk_tts"

REM 1) Se existir o venv local (criado por instalar_alltalk.bat), usa ele.
if exist "venv\Scripts\python.exe" (
    echo Iniciando AllTalk via venv local ...
    venv\Scripts\python script.py
    goto :fim
)
if exist ".venv\Scripts\python.exe" (
    echo Iniciando AllTalk via .venv local ...
    .venv\Scripts\python script.py
    goto :fim
)

REM 2) Senao, tenta o start_alltalk.bat oficial (ambiente Conda do atsetup).
if exist "start_alltalk.bat" (
    echo Iniciando AllTalk via start_alltalk.bat (ambiente Conda) ...
    call start_alltalk.bat
    goto :fim
)

REM 3) Ultimo recurso: python no PATH.
where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Nenhum Python encontrado. Rode instalar_alltalk.bat antes.
) else (
    echo Iniciando AllTalk via python do PATH...
    python script.py
)

:fim
echo.
pause
