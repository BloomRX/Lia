@echo off
REM ============================================================
REM  Lia App - Instalador
REM  Abre o instalador com interface grafica.
REM ============================================================
chcp 65001 >nul
title Lia App - Instalador
cd /d "%~dp0"

REM Verificar python
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERRO] Python nao encontrado!
    echo  Baixe em: https://www.python.org/downloads/
    echo  Marque "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

REM Instalar customtkinter se necessario
python -c "import customtkinter" 2>nul
if errorlevel 1 (
    echo Instalando CustomTkinter...
    pip install customtkinter --quiet
)

REM Abrir o instalador
python installer.py
