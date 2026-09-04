@echo off
REM ============================================================
REM  instalar_alltalk.bat - AllTalk TTS v2 (integrado ao projeto Lia)
REM
REM  Tudo e relativo a %~dp0 (a pasta onde ESTE .bat esta). Assim
REM  funciona de QUALQUER lugar (C:\Lia, J:\Lia, D:\Projetos\Lia,
REM  pendrive, etc) apos clonar este repo. Nenhum caminho fixo.
REM  Mantenha este .bat na RAIZ do projeto, junto de waifu.bat.
REM
REM  Python: chama o launcher `py` DIRETAMENTE para achar um 3.9-3.11.
REM  Nao muda o `python` global do sistema. Se nao achar, mostra como
REM  instalar/usar o 3.11.
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "ALLTALK_DIR=%CD%\alltalk_tts"
set "ALLTALK_PY="
set "ALLTALK_PYOK="

echo ============================================
echo  Instalador do AllTalk TTS v2
echo  Pasta do projeto : %CD%
echo  AllTalk em       : %ALLTALK_DIR%
echo ============================================
echo.

REM ---------- 1. Achar um Python 3.9-3.11 via launcher py ----------
echo [1/4] Procurando Python 3.9-3.11 via  py  ...
REM Tenta os varios candidatos na ordem. O `py -3.x -c` devolve o caminho
REM exato do executavel daquela versao. Usamos o 1o que responder.
for %%V in (3.11 3.10 3.9) do (
    if not defined ALLTALK_PY (
        for /f "delims=" %%i in ('py -%%V -c "import sys;print(sys.executable)" 2^>nul') do set "ALLTALK_PY=%%i"
    )
)

if not defined ALLTALK_PY (
    echo.
    echo [ERRO] Nao encontrei um Python 3.9-3.11 via  py -3.11 / -3.10 / -3.9  .
    echo.
    echo   Para conferir o que esta instalado, rode:
    echo       py --list
    echo   Voce precisa de uma linha  "Python 3.11 (64-bit)"  (nao e o "Astral/").
    echo.
    echo   Se NAO aparecer 3.11, instale-o:
    echo       https://www.python.org/downloads/windows/
    echo   E, na instalacao, MARQUE a opcao  "py launcher"  ^(ja vem marcada^).
    echo.
    echo   Dica: o seu 3.14 continua o padrao; o 3.11 fica ao lado sem quebrar nada.
    goto :fim
)

REM Valida que o caminho achado realmente e um python 3.9-3.11.
"%ALLTALK_PY%" -c "import sys; v=sys.version_info; sys.exit(0 if (v.major==3 and 9<=v.minor<=11) else 1)" >nul 2>&1
if errorlevel 1 set "ALLTALK_PY="
if not defined ALLTALK_PY (
    echo [ERRO] O Python 3.11 achado nao e 3.9-3.11. Rode: py --list
    goto :fim
)
echo   Usando Python: %ALLTALK_PY%
echo   (o seu python padrao do sistema nao foi alterado)
set "ALLTALK_PYOK=1"

REM Coloca o diretorio desse python na frente do PATH, para o atsetup.bat
REM (que chama `python` por dentro) usar o 3.9-3.11, e nao o 3.14 global.
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
