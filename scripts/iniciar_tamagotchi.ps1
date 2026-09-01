# ============================================================
#  iniciar_tamagotchi.ps1  (v2)
#  Airi DESKTOP (Tamagotchi transparente na tela) rodando do FONTE
#  que ja esta no PC (mesmo repo do stage-web).
#
#  O que faz:
#    - acha a pasta do Airi (airi\ ao lado deste script)
#    - na 1a vez instala dependencias que faltam (Electron etc.)
#    - abre o stage-tamagotchi em janela propria
#
#  Uso:
#     .\iniciar_tamagotchi.ps1
#     .\iniciar_tamagotchi.ps1 -AiriDir "D:\alguma\airi"
# ============================================================
[CmdletBinding()]
param(
    [string]$AiriDir = "",
    [int]$CdpPort = 9222
)

$Root = $PSScriptRoot
# Se o script esta em scripts/, subir um nivel
if ((Split-Path $Root -Leaf) -eq "scripts") { $Root = Split-Path $Root -Parent }
$REPO_ROOT = $Root
if (-not $Root) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }

Write-Host ""
Write-Host "================================================"
Write-Host "  AIRI DESKTOP (tamagotchi) - janela na tela"
Write-Host "================================================"
Write-Host ""

# ---------- 1. Pasta do Airi ----------
if (-not $AiriDir) {
    $AiriDir = Join-Path $Root "airi"
}

if (-not ($AiriDir -and (Test-Path (Join-Path $AiriDir "package.json")))) {
    Write-Host "[ERRO] Pasta do Airi nao encontrada: $AiriDir"
    Write-Host "       Rode o waifu.bat opcao 1 ou 2 para baixar automaticamente."
    Write-Host "       Rode: .\iniciar_tamagotchi.ps1 -AiriDir 'caminho\da\pasta\airi'"
    Read-Host "Pressione Enter para sair"
    exit 1
}
Write-Host "[OK] Pasta do Airi: $AiriDir"

# ---------- 2. pnpm ----------
try {
    $pnpmVer = pnpm --version
    Write-Host "[OK] pnpm: $pnpmVer"
}
catch {
    Write-Host "[ERRO] pnpm nao encontrado. Instale com:"
    Write-Host "       npm install -g pnpm"
    Read-Host "Pressione Enter para sair"
    exit 1
}

# ---------- 3. Descobrir o comando certo ----------
$cmd = "pnpm --filter @proj-airi/stage-tamagotchi dev"
try {
    $pkg = Get-Content (Join-Path $AiriDir "package.json") -Raw
    if ($pkg -match '"dev:tamagotchi"') { $cmd = "pnpm dev:tamagotchi" }
} catch { }
Write-Host "[OK] Comando: $cmd"

# ---------- 4. Electron: pacote E binario (pnpm novo pula o download!) ----------
# Acha a pasta real do pacote electron (monorepo pnpm: apps/stage-tamagotchi/node_modules)
$eleDir = $null
foreach ($c in @((Join-Path $AiriDir "apps\stage-tamagotchi\node_modules\electron"), (Join-Path $AiriDir "node_modules\electron"))) {
    if (Test-Path (Join-Path $c "package.json")) { $eleDir = $c; break }
}
if (-not $eleDir) {
    $hit = Get-ChildItem (Join-Path $AiriDir "node_modules\.pnpm") -Filter "electron@*" -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { $eleDir = Join-Path $hit.FullName "node_modules\electron" }
}

if (-not ($eleDir -and (Test-Path (Join-Path $eleDir "package.json")))) {
    Write-Host ""
    Write-Host "[INFO] Electron nao esta no node_modules. Instalando dependencias (pnpm install)..."
    Write-Host "       (pode demorar bastante - SO NA 1a VEZ)"
    Write-Host ""
    Push-Location $AiriDir
    try { pnpm install 2>&1 | Select-Object -Last 10 }
    finally { Pop-Location }
    $hit = Get-ChildItem (Join-Path $AiriDir "node_modules\.pnpm") -Filter "electron@*" -Directory -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($hit) { $eleDir = Join-Path $hit.FullName "node_modules\electron" }
}

if (-not ($eleDir -and (Test-Path (Join-Path $eleDir "package.json")))) {
    Write-Host "[ERRO] Pacote do Electron nao encontrado depois do pnpm install."
    Read-Host "Pressione Enter para sair"
    exit 1
}

# O binario (~100 MB) vem do postinstall do electron, que o pnpm v10 costuma PULAR.
# Sem ele: "Error: Electron uninstall" no electron-vite.
if (-not (Test-Path (Join-Path $eleDir "path.txt"))) {
    Write-Host ""
    Write-Host "[INFO] O pacote do Electron esta la, mas falta o PROGRAMA (binario ~100 MB)."
    Write-Host "       (o pnpm novo pula esse download - baixando agora, SO NESTA VEZ...)"
    Write-Host ""
    Push-Location $AiriDir
    try { node "$eleDir\install.js" }
    finally { Pop-Location }
    if (-not (Test-Path (Join-Path $eleDir "path.txt"))) {
        Write-Host ""
        Write-Host "[ERRO] Nao consegui baixar o binario do Electron (rede? firewall?)."
        Write-Host "       Teste manual:"
        Write-Host "         cd $AiriDir"
        Write-Host "         node \"$eleDir\install.js\""
        Write-Host "       Se a rede bloquear o GitHub, tente:"
        Write-Host "         $env:ELECTRON_MIRROR = \"https://npmmirror.com/mirrors/electron/\""
        Write-Host "         (e rode o install.js de novo)"
        Read-Host "Pressione Enter para sair"
        exit 1
    }
    Write-Host "[OK] Electron baixado!"
}
else {
    Write-Host "[OK] Electron pronto"
}

# ---------- 5. Abrir o tamagotchi em janela propria ----------
Write-Host ""
Write-Host "Abrindo o Airi desktop (uma janela nova vai aparecer, com o logs)..."
# Passar --remote-debugging-port para permitir auto-configuracao via CDP
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$AiriDir`" && $cmd -- --remote-debugging-port=$CdpPort"

Write-Host ""
Write-Host "================================================"
Write-Host "  CONFIGURAR DENTRO DO APP (SO UMA VEZ):"
Write-Host "================================================"
Write-Host ""
Write-Host "  Settings -> Providers:"
Write-Host "    Cerebro (LLM): OpenAI Compatible"
Write-Host "      Base URL: http://localhost:9860/cerebro/v1   <- URL FIXA!"
Write-Host "      API Key : local    Model: agentai"
Write-Host "    Voz (Speech): OpenAI Compatible (Speech)"
Write-Host "      Base URL: http://localhost:9860/v1           <- URL FIXA!"
Write-Host "      Model   : edge-tts"
Write-Host "      Voice   : a que voce escolheu na interface"
Write-Host ""
Write-Host "  (o servidor de voz repassa pro tunel do Colab sozinho;"
Write-Host "   o tunel pode mudar que aqui nao muda NADA)"
Write-Host ""
Write-Host "  Dica: o servidor de voz precisa estar rodando (opcao 2 do menu)."
Write-Host ""
Read-Host "Pressione Enter para fechar esta janela (a do Airi fica aberta)"
