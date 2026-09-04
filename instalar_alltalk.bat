@echo off
REM ============================================================
REM  instalar_alltalk.bat - AllTalk TTS v2 (integrado ao projeto Lia)
REM
REM  Tudo e relativo a %~dp0 (a pasta onde ESTE .bat esta). Assim
REM  funciona de QUALQUER lugar (C:\Lia, J:\Lia, D:\Projetos\Lia,
REM  pendrive, etc) apos clonar este repo. Nenhum caminho fixo.
REM  Mantenha este .bat na RAIZ do projeto, junto de waifu.bat.
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "ALLTALK_DIR=%CD%\alltalk_tts"

echo ============================================
echo  Instalador do AllTalk TTS v2
echo  Pasta do projeto : %CD%
echo  AllTalk em       : %ALLTALK_DIR%
echo ============================================
echo.

REM ---------- 1. Python 3.9 - 3.11 ----------
echo [1/3] Verificando Python ...
python scripts\alltalk_config.py --check-python
if errorlevel 1 goto :fim

REM ---------- 2. Clonar AllTalk ----------
if exist "%ALLTALK_DIR%\README.md" goto :clonado
if exist "%ALLTALK_DIR%" (
    echo [AVISO] alltalk_tts existe mas parece incompleto. Recriando...
    rmdir /s /q "%ALLTALK_DIR%" 2>nul
)
echo [2/3] Clonando AllTalk TTS v2 ...
git clone https://github.com/erew123/alltalk_tts.git "%ALLTALK_DIR%"
if errorlevel 1 (
    echo [ERRO] Falha ao clonar. Verifique internet/Git.
    goto :fim
)
:clonado

REM ---------- 3. atsetup.bat (interativo) ----------
echo.
echo [3/3] Rodando atsetup.bat (interativo) ...
echo   * Escolha: AllTalk as a Standalone Application
echo   * Escolha: AMD/other requirements  (requirements_other.txt, torch CPU)
echo   * NAO instale CUDA/NVIDIA nem DeepSpeed.
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
echo Ajustando confignew.json (deepspeed off, porta 7851) ...
python scripts\alltalk_config.py --patch-confignew

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
