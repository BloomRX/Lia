@echo off
REM ============================================================
REM  PullLia.bat - Atualiza o projeto Lia com os commits recentes
REM
REM  Por que "cd /d %~dp0": essa variavel expande para a pasta ONDE
REM  ESTE .bat esta salvo. Assim o script funciona de qualquer lugar
REM  do disco (C:\Lia, D:\Projetos\Lia, pendrive, etc) sem nenhum
REM  caminho fixo no codigo. Basta manter o .bat na RAIZ do projeto,
REM  junto do waifu.bat e da pasta app\.
REM
REM  O /d e necessario porque o "cd" sozinho nao troca de UNIDADE
REM  (nao sai de C: para D:), apenas de pasta.
REM ============================================================

setlocal enabledelayedexpansion
set "BRANCH=arena/01a05b49-lia"
set "STASHED="

cd /d "%~dp0"

echo ============================================
echo  Projeto : %CD%
echo  Branch  : %BRANCH%
echo ============================================
echo.

REM Confere se estamos realmente dentro de um repositorio git antes de
REM rodar qualquer coisa. Sem isso, o usuario veria varios erros crus
REM do git em sequencia sem entender a causa raiz.
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Esta pasta nao e um repositorio git.
    echo Mantenha o PullLia.bat na RAIZ do projeto, junto do waifu.bat.
    goto :fim
)

REM ------------------------------------------------------------
REM  Alteracoes locais nao commitadas
REM
REM  Por que isso acontece neste projeto: o app gera/mexe em arquivos em
REM  runtime (voice-data\, AssetsTemp\, etc) e voce pode estar editando o
REM  codigo (app\lia_app.py) quando o servidor tambem mudou o mesmo arquivo.
REM  Nesse caso o git aborta o pull para nao sobrescrever seu trabalho.
REM
REM  Como resolvemos: guardamos as mudancas locais no "stash" (uma gaveta
REM  temporaria do git), puxamos limpo, e devolvemos as mudancas depois.
REM  Nada e perdido - e o caminho seguro, diferente do reset --hard.
REM ------------------------------------------------------------
set "SUJO="
for /f "delims=" %%i in ('git status --porcelain') do set "SUJO=1"

if defined SUJO (
    echo [AVISO] Existem alteracoes locais nao commitadas:
    echo.
    git status --short
    echo.
    echo O que fazer com elas?
    echo   [G] Guardar temporariamente e devolver apos o pull  ^(recomendado^)
    echo   [D] Descartar tudo e ficar identico ao servidor
    echo   [C] Cancelar
    echo.
    choice /c GDC /n /m "Escolha [G/D/C]: "

    if errorlevel 3 goto :fim

    if errorlevel 2 (
        echo.
        echo Descartando alteracoes locais...
        git reset --hard HEAD
        REM -d remove pastas novas, -f forca. Limpa arquivos nao rastreados
        REM que tambem poderiam atrapalhar o merge.
        git clean -fd
        goto :pulou_stash
    )

    echo.
    echo Guardando alteracoes no stash...
    REM -u inclui arquivos nao rastreados (ex.: configs/audios gerados).
    git stash push -u -m "PullLia automatico"
    if errorlevel 1 (
        echo [ERRO] Nao consegui guardar as alteracoes. Abortando por seguranca.
        goto :fim
    )
    set "STASHED=1"
)

:pulou_stash
echo.
echo [1/3] Buscando novidades no servidor...
git fetch origin --prune
if errorlevel 1 (
    echo [ERRO] Falha no fetch. Verifique a internet ou o acesso ao GitHub.
    goto :restaurar
)

echo.
echo [2/3] Indo para a branch %BRANCH%...

REM Se a branch ainda nao existe localmente, criamos ja rastreando a do
REM servidor (--track). Isso evita o erro classico de "pull" sem upstream.
git rev-parse --verify "%BRANCH%" >nul 2>&1
if errorlevel 1 (
    git switch -c "%BRANCH%" --track "origin/%BRANCH%"
) else (
    git switch "%BRANCH%"
)

if errorlevel 1 (
    echo [ERRO] Nao consegui trocar de branch.
    goto :restaurar
)

echo.
echo [3/3] Puxando commits...
git pull origin "%BRANCH%"
if errorlevel 1 (
    echo.
    echo [ERRO] O pull falhou mesmo apos limpar a area de trabalho.
    echo Isso indica conflito real de conteudo. Comando de resgate:
    echo     git reset --hard origin/%BRANCH%
    goto :restaurar
)

:restaurar
REM Devolve o que foi guardado no stash.
if defined STASHED (
    echo.
    echo Devolvendo suas alteracoes guardadas...
    git stash pop
    if errorlevel 1 (
        echo.
        echo [AVISO] Houve conflito ao devolver o stash.
        echo Suas alteracoes continuam salvas. Para ver: git stash list
        echo Para descarta-las de vez:              git stash drop
    )
)

echo.
echo ============================================
echo  Ultimos commits:
echo ============================================
git --no-pager log --oneline -5
echo.
echo Rode waifu.bat para abrir o app.

:fim
echo.
pause
endlocal
