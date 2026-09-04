@echo off
REM ============================================================
REM  instalar_alltalk.bat - AllTalk TTS v2 (integrado ao projeto Lia)
REM
REM  Tudo e relativo a %~dp0 (a pasta onde ESTE .bat esta). Assim
REM  funciona de QUALQUER lugar (C:\Lia, J:\Lia, D:\Projetos\Lia,
REM  pendrive, etc) apos clonar este repo. Nenhum caminho fixo.
REM  Mantenha este .bat na RAIZ do projeto, junto de waifu.bat.
REM
REM  Python: usa automaticamente o 3.9-3.11 (via `py -3.11` ou um
REM  python 3.9-3.11 ja instalado). Nao muda o `python` global.
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "ALLTALK_DIR=%CD%\alltalk_tts"
set "ALLTALK_PY="

echo ============================================
echo  Instalador do AllTalk TTS v2
echo  Pasta do projeto : %CD%
echo  AllTalk em       : %ALLTALK_DIR%
echo ============================================
echo.

REM ---------- 1. Achar um Python 3.9 - 3.11 ----------
echo [1/4] Procurando Python 3.9-3.11 ...
REM tenta `python` do PATH (so se ja for 3.9-3.11), depois o launcher py,
REM senao cai no modo interativo de instalacao.
for /f "delims=" %%i in ('python scripts\alltalk_config.py --find-python 2^>nul') do set "ALLTALK_PY=%%i"
if not defined ALLTALK_PY (
    echo.
    echo [ERRO] Nao achei um Python 3.9-3.11 instalado.
    echo   Voce tem:  python --version   (o atual sera mostrado abaixo)
    python --version 2>nul
    echo.
    echo  Solucao (NAO muda seu python global):
    echo   1. Baixe o instalador de Python 3.11:
    echo      https://www.python.org/downloads/windows/
    echo   2. Instale marcando  ^"py launcher^"  e  ^"Add Python to PATH^"  ^(opcional^).
    echo   3. Rode este instalar_alltalk.bat DE NOVO.
    echo  O instalador detecta o 3.11 sozinho via  py -3.11.
    goto :fim
)
echo   Usando Python: %ALLTALK_PY%

REM Coloca o diretorio desse python no PATH, para que o atsetup.bat
REM (que chama `python`) use a versao 3.9-3.11, e nao a 3.14 global.
for %%i in ("%ALLTALK_PY%") do set "PYDIR=%%~dpi"
set "PATH=%PYDIR%;%PATH%"

REM ---------- 2. Clonar AllTalk (se preciso) ----------
echo.
echo [2/4] Clonando AllTalk TTS v2 (se nao existir) ...
if exist "%ALLTALK_DIR%\README.md" (
    echo   AllTalk ja esta clonado. Pulando clone.
) else (
    if exist "%ALLTALK_DIR%" (
        echo [AVISO] alltalk_tts existe mas parece incompleto. Recriando...
        rmdir /s /q "%ALLTALK_DIR%" 2>nul
    )
    git clone https://github.com/erew123/alltalk_tts.git "%ALLTALK_DIR%"
    if errorlevel 1 (
        echo [ERRO] Falha ao clonar. Verifique internet/Git.
        goto :fim
    )
    echo   Clone OK.
)

REM ---------- 3. atsetup.bat (interativo, usa o python 3.9-3.11) ----------
echo.
echo [3/4] Rodando atsetup.bat (interativo) ...
echo   * Escolha: AllTalk as a Standalone Application
echo   * Escolha: AMD/other requirements  (requirements_other.txt, torch CPU)
echo   * NAO instale CUDA/NVIDIA nem DeepSpeed.
if exist "%ALLTALK_DIR%\.venv\Scripts\activate.bat" (
    echo   [AVISO] Venv ja existe. Se quiser reinstalar do zero, apague alltalk_tts.
) else if exist "%ALLTALK_DIR%\venv\Scripts\activate.bat" (
    echo   [AVISO] Venv ja existe. Se quiser reinstalar do zero, apague alltalk_tts.
)
echo.
cd /d "%ALLTALK_DIR%"
if not exist "atsetup.bat" (
    echo [ERRO] atsetup.bat nao encontrado. Verifique o clone:
    echo        https://github.com/erew123/alltalk_tts
    cd /d "%~dp0"
    goto :fim
)
call atsetup.bat
cd /d "%~dp0"

REM ---------- 4. Configurar confignew.json ----------
echo.
echo [4/4] Ajustando confignew.json (deepspeed off, porta 7851) ...
"%ALLTALK_PY%" scripts\alltalk_config.py --patch-confignew

echo.
echo ============================================
echo  Pronto!
echo  Iniciar  : iniciar_alltalk.bat
echo  Interface: http://127.0.0.1:7851
echo  Airi voz : http://127.0.0.1:7851/v1
echo ============================================
echo.
echo  Proximos passos (navegador, aba Generate):
echo   - Swap TTS Engine = Piper   (mais rapido em CPU)
echo   - Baixe um modelo pt-BR
echo   - Ative RVC com seu .pth + .index  (pitch 0, index rate ~0.7)
echo  Guia completo: docs/ALLTALK-V2-CPU-RX580.md

:fim
echo.
pause
endlocal
