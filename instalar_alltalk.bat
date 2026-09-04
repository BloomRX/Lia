@echo off
REM ============================================================
REM  instalar_alltalk.bat - AllTalk TTS v2 (CPU / RX 580, sem NVIDIA)
REM
REM  Tudo e relativo a %~dp0 (a pasta onde ESTE .bat esta). Assim
REM  funciona de QUALQUER lugar (C:\Lia, J:\Lia, D:\Projetos\Lia,
REM  pendrive, etc) apos clonar este repo. Nenhum caminho fixo.
REM  Mantenha este .bat na RAIZ do projeto, junto de waifu.bat.
REM
REM  Este instalador NAO usa o atsetup.bat oficial (que instala
REM  torch CUDA + DeepSpeed, rota NVIDIA). Ele cria um venv com
REM  torch CPU e instala o requirements_standalone SEM CUDA/DeepSpeed.
REM  Usa o launcher `py` direto para achar o Python 3.9-3.11, sem
REM  mexer no `python` global do sistema.
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "ALLTALK_DIR=%CD%\alltalk_tts"
set "ALLTALK_PY="

echo.
echo ============================================
echo  Instalador do AllTalk TTS v2  (CPU)
echo  Pasta do projeto : %CD%
echo  AllTalk em       : %ALLTALK_DIR%
echo ============================================
echo.

REM ---------- 1. Achar um Python 3.9-3.11 via launcher py ----------
echo [1/4] Procurando Python 3.9-3.11 via  py ...
REM Simples: testa cada versao, uma por vez, sem loop com parse.
py -3.11 -c "import sys; v=sys.version_info; sys.exit(0 if (v.major==3 and 9<=v.minor<=11) else 1)" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%i in ('py -3.11 -c "import sys;print(sys.executable)"') do set "ALLTALK_PY=%%i"
)
if not defined ALLTALK_PY (
    py -3.10 -c "import sys; v=sys.version_info; sys.exit(0 if (v.major==3 and 9<=v.minor<=11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%i in ('py -3.10 -c "import sys;print(sys.executable)"') do set "ALLTALK_PY=%%i"
    )
)
if not defined ALLTALK_PY (
    py -3.9 -c "import sys; v=sys.version_info; sys.exit(0 if (v.major==3 and 9<=v.minor<=11) else 1)" >nul 2>&1
    if not errorlevel 1 (
        for /f "delims=" %%i in ('py -3.9 -c "import sys;print(sys.executable)"') do set "ALLTALK_PY=%%i"
    )
)

if not defined ALLTALK_PY (
    echo.
    echo [ERRO] Nao encontrei um Python 3.9-3.11 via  py -3.11 / -3.10 / -3.9  .
    echo.
    echo   Para conferir o que esta instalado, rode num terminal:
    echo       py --list
    echo   Voce precisa de uma linha  "Python 3.11 (64-bit)"  - nao e o "Astral/".
    echo.
    echo   Se NAO aparecer 3.11, instale-o:
    echo       https://www.python.org/downloads/windows/
    echo   E, na instalacao, MARQUE a opcao  "py launcher"  ^(ja vem marcada^).
    echo.
    echo   Dica: o seu 3.14 continua o padrao; o 3.11 fica ao lado sem quebrar nada.
    goto :fim
)
echo   Usando Python: %ALLTALK_PY%
echo   (o seu python padrao do sistema nao foi alterado)

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

REM ---------- 3. Instalar CPU (venv + torch CPU + requirements) ----------
echo.
echo [3/4] Instalando AllTalk em modo CPU (venv + torch CPU + requirements) ...
echo   * Isso cria <projeto>\alltalk_tts\venv (isolado, nao toca no seu python)
echo   * Instala torch CPU (SEM +cu121) e SEM DeepSpeed
echo   * Pode demorar (baixa modelos/pacotes). Nao feche a janela.
echo.
"%ALLTALK_PY%" scripts\alltalk_config.py --install-cpu
if errorlevel 1 (
    echo.
    echo [ERRO] A instalacao CPU falhou. Veja as mensagens acima.
    goto :fim
)

REM ---------- 4. Confirmar config ----------
echo.
echo [4/4] Confirmando confignew.json (deepspeed off, porta 7851) ...
"%ALLTALK_PY%" scripts\alltalk_config.py --patch-confignew

echo.
echo ============================================
echo  Pronto!
echo  Iniciar  : iniciar_alltalk.bat  (ou venv\Scripts\python script.py)
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
echo  (pressione qualquer tecla para fechar...)
pause >nul
endlocal
