# ============================================================
#  configurar_tamagotchi.ps1 - Configura providers E modulos do AIRI
#  100% AUTOMATICO - sem intervencao manual.
#
#  Usa openai-compatible-audio-speech que aceita qualquer voz.
#  O listVoices retorna vazio, mas a voz fica salva em
#  settings/speech/voice e usada direto na chamada da API.
#
#  Requisito: AIRI ja instalado + servidor de voz rodando.
# ============================================================
[CmdletBinding()]
param(
    [string]$AiriDir   = "",
    [int]$VoicePort    = 9860,
    [string]$Cerebro   = "",
    [int]$CdpPort      = 9222
)

$Root = $PSScriptRoot
if (-not $Root) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }
if ((Split-Path $Root -Leaf) -eq "scripts") { $Root = Split-Path $Root -Parent }
$REPO_ROOT = $Root
if (-not $Cerebro) { $Cerebro = "http://127.0.0.1:" + $VoicePort + "/cerebro/v1" }

Write-Host ""
Write-Host "================================================"
Write-Host "  CONFIGURAR AIRI (Tamagotchi) - AUTOMATICO"
Write-Host "================================================"
Write-Host ""

# ---------- 1. Pasta do Airi ----------
if (-not $AiriDir) {
    $AiriDir = Join-Path $Root "airi"
}
if (-not (Test-Path (Join-Path $AiriDir "package.json"))) {
    Write-Host "[ERRO] Pasta do Airi nao encontrada: $AiriDir"
    Write-Host "       Rode o waifu.bat opcao 1 ou 2 primeiro para baixar automaticamente."
    Read-Host "Pressione Enter para sair"
    exit 1
}
Write-Host "[OK] Airi: $AiriDir"

# ---------- 2. Voz configurada ----------
$voiceId = "pt-BR-ThalitaNeural"
$voicePitch = 0
$voiceRate = 1.0
$voiceEngine = "edge"

$vozConfigFile = Join-Path $Root "voz_config.json"
if (Test-Path $vozConfigFile) {
    try {
        $j = Get-Content $vozConfigFile -Raw | ConvertFrom-Json
        $voiceId = [string]$j.voice
        $voiceEngine = if ($j.engine) { [string]$j.engine } else { "edge" }
        if ($null -ne $j.pitch) { $voicePitch = [int]$j.pitch }
        if ($null -ne $j.speed) { $voiceRate = [double]$j.speed }
    } catch { }
}

# Montar voice string conforme o engine
# SEMPRE usar edge-tts como model — o servidor detecta o engine
# pelo prefixo da voz (kokoro: ou edge:), nao pelo model
$speechModel = "edge-tts"
if ($voiceEngine -eq "kokoro") {
    $voiceStr = "kokoro:" + $voiceId
    # Kokoro suporta pitch (aproximado via reamostragem)
    if ($voicePitch -ne 0) {
        if ($voicePitch -gt 0) { $voiceStr += ":+" + $voicePitch } else { $voiceStr += ":" + $voicePitch }
    }
    if ($voiceRate -ne 1.0) { $voiceStr += "@" + $voiceRate.ToString("F2", [System.Globalization.CultureInfo]::InvariantCulture) }
} else {
    $voiceStr = $voiceId
    if ($voicePitch -ne 0) {
        if ($voicePitch -gt 0) { $voiceStr += ":+" + $voicePitch } else { $voiceStr += ":" + $voicePitch }
    }
    if ($voiceRate -ne 1.0) { $voiceStr += "@" + $voiceRate.ToString("F2", [System.Globalization.CultureInfo]::InvariantCulture) }
}
Write-Host "[OK] Engine: $voiceEngine | Modelo: $speechModel | Voz: $voiceStr"

# ---------- 3. JavaScript de injecao ----------
$brainUrlEsc = $Cerebro.Replace("'", "\'")
$voiceBaseEsc = ("http://127.0.0.1:" + $VoicePort + "/v1/").Replace("'", "\'")
$voiceStrEsc = $voiceStr.Replace("'", "\'")
$speechModelEsc = $speechModel.Replace("'", "\'")

$injectJs = @"
(function() {
  try {
    var configured = {};
    var added = {};
    try { configured = JSON.parse(localStorage.getItem('settings/providers/configured') || '{}'); } catch(e) {}
    try { added = JSON.parse(localStorage.getItem('settings/providers/added') || '{}'); } catch(e) {}

    // LIMPAR providers antigos de speech
    delete configured['openai-audio-speech'];
    delete added['openai-audio-speech'];

    // Chat provider
    configured['openai-compatible'] = {
      id: 'openai-compatible',
      definitionId: 'openai-compatible',
      config: { apiKey: 'local', baseUrl: '$brainUrlEsc/' },
      status: 'configured',
      configuredBy: 'user'
    };
    added['openai-compatible'] = true;

    // Speech provider - openai-compatible-audio-speech (aceita qualquer voz)
    configured['openai-compatible-audio-speech'] = {
      id: 'openai-compatible-audio-speech',
      definitionId: 'openai-compatible-audio-speech',
      config: { apiKey: 'local', baseUrl: '$voiceBaseEsc' },
      status: 'configured',
      configuredBy: 'user'
    };
    added['openai-compatible-audio-speech'] = true;

    localStorage.setItem('settings/providers/configured', JSON.stringify(configured));
    localStorage.setItem('settings/providers/added', JSON.stringify(added));

    // LIMPAR e re-setar modulo de speech
    localStorage.removeItem('settings/speech/active-provider');
    localStorage.removeItem('settings/speech/active-model');
    localStorage.removeItem('settings/speech/voice');
    localStorage.removeItem('settings/speech/pitch');
    localStorage.removeItem('settings/speech/rate');

    localStorage.setItem('settings/speech/active-provider', 'openai-compatible-audio-speech');
    localStorage.setItem('settings/speech/active-model', '$speechModelEsc');
    localStorage.setItem('settings/speech/voice', '$voiceStrEsc');

    return 'OK';
  } catch(e) {
    return 'ERRO: ' + e.message;
  }
})();
"@

# ---------- 4. Funcoes CDP ----------
function Test-Port($port) {
    $sock = New-Object System.Net.Sockets.TcpClient
    try { $sock.Connect("127.0.0.1", $port); $sock.Close(); return $true }
    catch { return $false }
}

function Get-CdpTargets($cdpPort) {
    try { return Invoke-RestMethod -Uri "http://127.0.0.1:${cdpPort}/json" -TimeoutSec 3 }
    catch { return $null }
}

function Send-CdpCommand($wsUrl, $method, $params) {
    $ws = New-Object System.Net.WebSockets.ClientWebSocket
    $ct = New-Object System.Threading.CancellationToken($false)
    $ws.ConnectAsync([Uri]$wsUrl, $ct).Wait()
    $id = Get-Random -Minimum 1 -Maximum 99999
    $msg = @{ id = $id; method = $method; params = $params } | ConvertTo-Json -Depth 10
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)
    $ws.SendAsync([System.ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    $buf = New-Object byte[] 65536
    $result = ""
    do {
        $r = $ws.ReceiveAsync([System.ArraySegment[byte]]::new($buf), $ct).Result
        $result += [System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
    } while (-not $r.EndOfMessage)
    $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
    return $result | ConvertFrom-Json
}

# ---------- 5. Iniciar AIRI se necessario ----------
$airiStarted = $false

if (-not (Test-Port $CdpPort)) {
    Write-Host "[INFO] AIRI nao esta rodando com CDP. Iniciando..."
    $tamaDir = Join-Path $AiriDir "apps\stage-tamagotchi"
    if (-not (Test-Path (Join-Path $tamaDir "package.json"))) {
        Write-Host "[ERRO] Tamagotchi nao encontrado em: $tamaDir"
        Read-Host "Pressione Enter para sair"; exit 1
    }
    $env:ELECTRON_ENABLE_LOGGING = "0"
    $proc = Start-Process -FilePath "npx" -ArgumentList "electron", ".", "--remote-debugging-port=$CdpPort" `
        -WorkingDirectory $tamaDir -PassThru -WindowStyle Normal
    $airiStarted = $true
    Write-Host "[OK] AIRI iniciado (PID $($proc.Id)). Aguardando carregar..."
    $waited = 0
    while ($waited -lt 60) {
        Start-Sleep -Seconds 3; $waited += 3
        if (Get-CdpTargets $CdpPort) { Write-Host "[OK] CDP disponivel apos ${waited}s"; break }
        Write-Host "  Aguardando... (${waited}s)"
    }
    if (-not (Get-CdpTargets $CdpPort)) {
        Write-Host "[ERRO] CDP nao ficou disponivel apos 60s."
        Read-Host "Pressione Enter para sair"; exit 1
    }
    Start-Sleep -Seconds 5
}

# ---------- 6. Injetar via CDP ----------
Write-Host "[INFO] Injetando providers + modulo speech via CDP..."

$targets = Get-CdpTargets $CdpPort
if (-not $targets) {
    Write-Host "[ERRO] Nao foi possivel conectar ao CDP na porta $CdpPort"
    Read-Host "Pressione Enter para sair"; exit 1
}

$pageTarget = $null
foreach ($t in $targets) {
    if ($t.type -eq "page" -and $t.webSocketDebuggerUrl) { $pageTarget = $t; break }
}
if (-not $pageTarget) {
    Write-Host "[ERRO] Nenhuma pagina encontrada via CDP"
    Read-Host "Pressione Enter para sair"; exit 1
}

Write-Host "[OK] Pagina: $($pageTarget.title)"

$wsUrl = $pageTarget.webSocketDebuggerUrl
try {
    $result = Send-CdpCommand $wsUrl "Runtime.evaluate" @{
        expression = $injectJs; returnByValue = $true
    }
    $value = $result.result.result.value
    if ($value -like "OK*") { Write-Host "[OK] $value" }
    else { Write-Host "[AVISO] $value" }

    Write-Host "[INFO] Recarregando pagina..."
    Send-CdpCommand $wsUrl "Page.reload" @{ ignoreCache = $false } | Out-Null
    Write-Host "[OK] Pagina recarregada!"
} catch {
    Write-Host "[ERRO] Falha ao injetar via CDP: $_"
}

Write-Host ""
Write-Host "================================================"
Write-Host "  PRONTO! Tudo configurado"
Write-Host "================================================"
Write-Host ""
Write-Host "  Chat:    OpenAI Compatible -> $Cerebro"
Write-Host "  Speech:  OpenAI Compatible Audio -> http://127.0.0.1:$VoicePort/v1/"
Write-Host "  Modelo:  $speechModel"
Write-Host "  Voz:     $voiceStr"
Write-Host ""

if (-not $airiStarted) { Read-Host "Pressione Enter para fechar" }
