# ============================================================
#  atualizar_airi.ps1  (v3)
#  AgentAI (Colab) + Project AIRI (PC)
#
#  - Le a URL do tunel do Drive (com retry e CACHE local)
#  - Testa o AgentAI
#  - Garante o Airi rodando
#  - Injeta a config (chat + voz) abrindo UMA unica aba
#    (a pagina agentai-boot.html redireciona sozinha para o app)
#
#  Uso:
#     .\atualizar_airi.ps1
#     .\atualizar_airi.ps1 -Voice "pt-BR-ThalitaNeural:+30"
# ============================================================
[CmdletBinding()]
param(
    [string]$DriveFile = "G:\Meu Drive\AgentAI\memory\api_url.txt",
    [string]$AiriDir   = "",
    [int]$Port         = 5173,
    [string]$Voice     = "pt-BR-ThalitaNeural",
    [string]$CacheFile = "",
    [switch]$SkipHealthCheck
)

# Definir pasta raiz do repo
$Root = $PSScriptRoot
if (-not $Root) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }
if ((Split-Path $Root -Leaf) -eq "scripts") { $Root = Split-Path $Root -Parent }
$REPO_ROOT = $Root

if (-not $CacheFile) { $CacheFile = Join-Path $REPO_ROOT "ultima_url.txt" }

# ---------- Encontrar pasta do AIRI ----------
if (-not $AiriDir) {
    $AiriDir = Join-Path $REPO_ROOT "airi"
}

# ---------- [v3.2] Voz padrao salva pela interface (http://localhost:9860/) ----------
# Se o -Voice nao foi personalizado na chamada, usa a voz salva no painel.
$VozConfig = "J:\IA\voz-bridge\voz_config.json"
if ($Voice -eq "pt-BR-ThalitaNeural" -and (Test-Path $VozConfig)) {
    try {
        $j = Get-Content $VozConfig -Raw | ConvertFrom-Json
        if ($j.voice) {
            $Voice = [string]$j.voice
            if ($null -ne $j.pitch -and "$($j.pitch)" -ne "0" -and "$($j.pitch)" -ne "") { $Voice += ":" + $j.pitch }
            if ($j.speed -and [double]$j.speed -ne 1.0) { $Voice += "@" + [math]::Round([double]$j.speed, 2) }
            Write-Host "[OK] Voz padrao carregada da interface: $Voice"
        }
    } catch { Write-Host "(aviso: nao consegui ler $VozConfig - usando voz padrao)" }
}

Write-Host ""
Write-Host "================================================"
Write-Host "  AGENTAI + AIRI  -  INICIALIZADOR"
Write-Host "================================================"
Write-Host ""

function Test-LocalUrl([int]$port) {
    try {
        Invoke-WebRequest -Uri "http://localhost:$port" -TimeoutSec 3 -UseBasicParsing | Out-Null
        return $true
    }
    catch { return $false }
}

# ---------- 1. Encontrar api_url.txt (Google Drive) ----------
$candidates = @(
    $DriveFile,
    "G:\Meu Drive\AgentAI\memory\api_url.txt",
    "G:\My Drive\AgentAI\memory\api_url.txt",
    "H:\Meu Drive\AgentAI\memory\api_url.txt",
    "H:\My Drive\AgentAI\memory\api_url.txt"
) | Select-Object -Unique

$urlFile = $null
foreach ($c in $candidates) {
    if (Test-Path $c) { $urlFile = $c; break }
}

if (-not $urlFile) {
    Write-Host "[ERRO] api_url.txt nao encontrado no Drive."
    Write-Host "       Rode a Celula 8 no Colab primeiro e confira o caminho:"
    Write-Host "       $DriveFile"
    Write-Host ""
    Read-Host "Pressione Enter para sair"
    exit 1
}
Write-Host "[OK] Drive: $urlFile"

# ---------- 2. Ler o arquivo (retry + tamanho) ----------
$content = $null
for ($i = 0; $i -lt 8 -and [string]::IsNullOrWhiteSpace($content); $i++) {
    try { $content = Get-Content $urlFile -Raw -ErrorAction Stop } catch { $content = $null }
    if ([string]::IsNullOrWhiteSpace($content)) {
        $sz = 0
        try { $sz = (Get-Item $urlFile).Length } catch { }
        Write-Host "  (arquivo vazio - $sz bytes - tentativa $($i+1)/8...)"
        Start-Sleep -Seconds 3
    }
}

$url = $null
if ($content) {
    $match = [regex]::Match($content, "https://[a-zA-Z0-9\-\.]+\.trycloudflare\.com")
    if ($match.Success) { $url = $match.Value }
}

# ---------- 3. Se o Drive nao tem nada: cache local ----------
if (-not $url) {
    Write-Host ""
    Write-Host "[AVISO] Arquivo do Drive vazio (provavelmente o app do Google Drive"
    Write-Host "        nao sincronizou - ele pode estar em modo 'somente online')."
    Write-Host "        Vou tentar a ultima URL salva no cache local..."

    if (Test-Path $CacheFile) {
        $cacheContent = Get-Content $CacheFile -Raw
        $cacheMatch = [regex]::Match($cacheContent, "https://[a-zA-Z0-9\-\.]+\.trycloudflare\.com")
        if ($cacheMatch.Success) {
            $url = $cacheMatch.Value
            Write-Host "[OK] URL do cache: $url"
            Write-Host "     (ela so e valida se o Colab desta sessao for o mesmo)"
        }
    }

    if (-not $url) {
        Write-Host ""
        Write-Host "  Nenhuma URL no cache. Abra o Colab e veja o output da Celula 8"
        Write-Host "  (procure 'TUNEL ATIVO' / 'URL publica')."
        $manual = (Read-Host "Cole aqui a URL do tunel do Colab (ou Enter para sair)").Trim()
        if (-not $manual) { exit 1 }
        if ($manual -notmatch "^https?://") { $manual = "https://$manual" }
        $url = ($manual -replace "/v1/?$", "").TrimEnd("/")
        Write-Host "[OK] URL informada: $url"
    }
}

$baseUrl = "$url/v1/"
Write-Host ""
Write-Host "[OK] URL do tunel: $url"

# ---------- 4. Salvar no cache local ----------
try {
    $cacheTxt = "URL=$url`nBASE_URL=$baseUrl`nSALVO=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n"
    Set-Content -Path $CacheFile -Value $cacheTxt -Encoding UTF8
    Write-Host "[OK] URL salva no cache: $CacheFile"
}
catch { Write-Host "(nao consegui salvar cache: $($_.Exception.Message))" }
Write-Host ""

# ---------- 5. Health check ----------
if (-not $SkipHealthCheck) {
    Write-Host "Testando conexao com o AgentAI..."
    try {
        $resp = Invoke-RestMethod -Uri "$url/health" -TimeoutSec 20
        Write-Host "[OK] AgentAI respondendo (modelo: $($resp.model))"
        # [FIX] API velha (sessao antiga do Colab) responde /health mas NAO tem
        # os campos da v2 (vram_gb/model_4bit). E ela que estoura a memoria!
        if (-not ($resp.PSObject.Properties["vram_gb"])) {
            Write-Host ""
            Write-Host "[ATENCAO] Essa URL aponta para uma API ANTIGA (pre-fixes de OOM)!"
            Write-Host "          E uma sessao anterior do Colab que continua viva -"
            Write-Host "          e a responsavel pelo 'Erro interno: CUDA out of memory'."
            Write-Host "          Abra o Colab ATUAL e copie a URL do 'TUNEL ATIVO'."
            $cont = Read-Host "Usar essa URL antiga mesmo assim? (s/n)"
            if ($cont -ne "s") { exit 1 }
        }
        else {
            Write-Host "[OK] API v2 no ar (4-bit: $($resp.model_4bit) | VRAM: $($resp.vram_gb) GB)"
        }
    }
    catch {
        Write-Host "[AVISO] Nao consegui falar com o AgentAI: $($_.Exception.Message)"
        Write-Host "        (se a URL veio do cache, o Colab pode ter mudado de sessao)"
        $cont = Read-Host "Continuar mesmo assim? (s/n)"
        if ($cont -ne "s") { exit 1 }
    }
    Write-Host ""
}

# ---------- 6. Garantir que o Airi (stage-web / Vite) esta rodando ----------
if (-not (Test-LocalUrl $Port)) {
    if (-not (Test-Path "$AiriDir\package.json")) {
        Write-Host "[ERRO] Pasta do Airi nao encontrada: $AiriDir"
        Read-Host "Pressione Enter para sair"
        exit 1
    }
    Write-Host "Iniciando o Airi (stage-web) em $AiriDir ..."
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$AiriDir`" && pnpm --filter @proj-airi/stage-web dev"

    Write-Host "Aguardando o servidor subir na porta $Port (1a vez demora ~1 min)..."
    $up = $false
    for ($i = 0; $i -lt 150; $i++) {
        Start-Sleep -Seconds 2
        if (Test-LocalUrl $Port) { $up = $true; break }
    }
    if ($up) { Write-Host "[OK] Servidor respondendo na porta $Port" }
    else     { Write-Host "[AVISO] O servidor ainda nao respondeu. Abrindo o navegador mesmo assim..." }
}
else {
    Write-Host "[OK] Airi ja esta rodando na porta $Port"
}
Write-Host ""

# ---------- 7. Injetar a URL (UMA unica aba) ----------
$bootUrl = "http://localhost:$Port/agentai-boot.html?url=$([uri]::EscapeDataString($baseUrl))&model=agentai&voice=$([uri]::EscapeDataString($Voice))&voiceBase=$([uri]::EscapeDataString('http://localhost:9860/v1'))"

# Verifica se a pagina de boot existe (se nao, avisa e abre o app direto)
$bootExists = $false
try {
    $r = Invoke-WebRequest -Uri "http://localhost:$Port/agentai-boot.html" -TimeoutSec 5 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $bootExists = $true }
}
catch { $bootExists = $false }

if ($bootExists) {
    Write-Host "Injetando configuracao no navegador (1 aba - ela redireciona sozinha)..."
    Start-Process $bootUrl
}
else {
    Write-Host "[AVISO] agentai-boot.html nao encontrado no Airi."
    Write-Host "        Copie o arquivo para: $AiriDir\apps\stage-web\public\"
    Write-Host "        Abrindo o Airi direto (voce vai precisar configurar na mao)."
    Start-Process "http://localhost:$Port"
}

Write-Host ""
Write-Host "================================================"
Write-Host "  TUDO PRONTO!"
Write-Host "================================================"
Write-Host "  Base URL : $baseUrl"
Write-Host "  Voz      : $Voice"
Write-Host ""
Write-Host "  Se for a primeira configuracao, confira no Airi:"
Write-Host "   Settings -> Providers -> Speech -> OpenAI Compatible (Speech)"
Write-Host "   Settings -> Modules -> Speech (ativar)"
Write-Host ""
Read-Host "Pressione Enter para fechar"
