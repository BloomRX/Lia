# ============================================================
#  iniciar_voz.ps1  (v3 - pasta automatica + kokoro offline opcional)
#  Instala e inicia o servidor de voz local (vozes Microsoft)
#  para o Project AIRI.
#
#  Uso:
#     .\iniciar_voz.ps1
#     .\iniciar_voz.ps1 -PastaVoz "D:\voz-bridge"
#     (se der erro de seguranca: powershell -ExecutionPolicy Bypass -File .\iniciar_voz.ps1)
# ============================================================
[CmdletBinding()]
param(
    [string]$PastaVoz = "",
    [int]$Port = 9860,
    [switch]$SemPausa
)

# Pasta padrao: J:\IA\voz-bridge se o drive J existir; senao, pasta do usuario
if (-not $PastaVoz) {
    if (Test-Path "J:\") {
        $PastaVoz = "J:\IA\voz-bridge"
    } else {
        $PastaVoz = Join-Path $env:USERPROFILE "voz-bridge"
    }
}

Write-Host ""
Write-Host "================================================"
Write-Host "  SERVIDOR DE VOZ (Edge + Kokoro) - instalador"
Write-Host "================================================"
Write-Host ""

# ---------- 1. Node.js ----------
try {
    $nodeVer = node --version
    Write-Host "[OK] Node.js: $nodeVer"
}
catch {
    Write-Host "[ERRO] Node.js nao encontrado. Instale em: https://nodejs.org (versao LTS)"
    if (-not $SemPausa) { Read-Host "Pressione Enter para sair" }
    exit 1
}

# ---------- 2. Pasta do servidor ----------
New-Item -ItemType Directory -Force -Path $PastaVoz | Out-Null
Write-Host "[OK] Pasta: $PastaVoz"

# ---------- 3. Copiar o servidor ----------
$scriptOrigem = Join-Path $PSScriptRoot "servidor_voz_airi.js"
if (Test-Path $scriptOrigem) {
    Copy-Item $scriptOrigem (Join-Path $PastaVoz "servidor_voz_airi.js") -Force
    Write-Host "[OK] servidor_voz_airi.js copiado"
}
else {
    Write-Host "[ERRO] servidor_voz_airi.js NAO encontrado ao lado deste script."
    Write-Host "       Os dois arquivos precisam estar na MESMA pasta:"
    Write-Host "         - iniciar_voz.ps1"
    Write-Host "         - servidor_voz_airi.js"
    Write-Host "       Confira em: $PSScriptRoot"
    if (-not $SemPausa) { Read-Host "Pressione Enter para sair" }
    exit 1
}

# ---------- 4. Instalar dependencia (so na primeira vez) ----------
if (-not (Test-Path (Join-Path $PastaVoz "node_modules\msedge-tts"))) {
    Write-Host "Instalando msedge-tts (primeira vez, ~30s)..."
    Write-Host "  (se travar aqui, a internet pode estar bloqueando o npm)"
    Push-Location $PastaVoz
    try {
        $npmOut = npm install msedge-tts --no-audit --no-fund 2>&1
    }
    finally {
        Pop-Location
    }
    if (-not (Test-Path (Join-Path $PastaVoz "node_modules\msedge-tts"))) {
        Write-Host "[ERRO] Falha ao instalar msedge-tts. Ultimas linhas do npm:"
        $npmOut | Select-Object -Last 15
        if (-not $SemPausa) { Read-Host "Pressione Enter para sair" }
        exit 1
    }
    Write-Host "[OK] msedge-tts instalado"
}
else {
    Write-Host "[OK] msedge-tts ja instalado"
}

# ---------- 5. Verificar se ja esta rodando ----------
$running = $false
try {
    $r = Invoke-WebRequest -Uri "http://localhost:$Port/health" -TimeoutSec 3 -UseBasicParsing
    if ($r.StatusCode -eq 200) { $running = $true }
}
catch { $running = $false }

if ($running) {
    Write-Host "[OK] Servidor de voz JA ESTA rodando na porta $Port"
    # avisa se a versao rodando e diferente da dos arquivos (depois de atualizar)
    $jsVersion = ""
    try {
        Select-String -Path (Join-Path $PastaVoz "servidor_voz_airi.js") -Pattern "const VERSION = '([^']+)'" |
            ForEach-Object { $jsVersion = $_.Matches[0].Groups[1].Value }
    } catch { }
    try {
        $h = Invoke-WebRequest -Uri "http://localhost:$Port/health" -TimeoutSec 3 -UseBasicParsing | ConvertFrom-Json
        if ($jsVersion -and $h.version -and ($h.version -ne $jsVersion)) {
            Write-Host ""
            Write-Host "[ATENCAO] O servidor RODANDO e a versao $($h.version), mas os arquivos sao a $jsVersion."
            Write-Host "          Feche a janela do servidor antigo e rode este script de novo"
            Write-Host "          (senao a pagina nao mostra as novidades, ex.: botao do Kokoro)."
        }
    } catch { }
}
else {
    # Cria um atalho .cmd (mais confiavel que chamar cmd direto)
    $cmdContent = "@echo off`r`ncd /d `"$PastaVoz`"`r`nnode servidor_voz_airi.js`r`npause`r`n"
    Set-Content -Path (Join-Path $PastaVoz "iniciar_voz.cmd") -Value $cmdContent -Encoding ASCII
    Write-Host "Iniciando servidor de voz (janela separada)..."
    Start-Process -FilePath (Join-Path $PastaVoz "iniciar_voz.cmd")

    $up = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri "http://localhost:$Port/health" -TimeoutSec 2 -UseBasicParsing
            if ($r.StatusCode -eq 200) { $up = $true; break }
        }
        catch { }
    }
    if ($up) {
        Write-Host "[OK] Servidor de voz respondendo!"
    }
    else {
        Write-Host ""
        Write-Host "[AVISO] Ainda nao detectei o servidor. A janela abriu?"
        Write-Host "        Se ela fechou sozinha ou mostrou erro, rode MANUALMENTE:"
        Write-Host ""
        Write-Host "        cd $PastaVoz"
        Write-Host "        node servidor_voz_airi.js"
        Write-Host ""
        Write-Host "        E me mande o que aparecer na tela."
        Write-Host ""
        Write-Host "        Tambem pode abrir no navegador: http://localhost:$Port/health"
        Write-Host "        (deve mostrar {\"status\":\"ok\",...})"
    }
}

Write-Host ""
Write-Host "================================================"
Write-Host "  AGORA CONFIGURE NO AIRI (uma vez so):"
Write-Host "================================================"
Write-Host ""
Write-Host "  0. NOVO! Interface de configuracao de voz:"
Write-Host "     abra  http://localhost:$Port/  no navegador"
Write-Host "     (escolhe voz, pitch fofinho, testa e copia a config)"
Write-Host ""
Write-Host "  1. Settings -> Providers -> Speech"
Write-Host "     -> OpenAI Compatible (Speech)"
Write-Host "        Base URL: http://localhost:$Port/v1"
Write-Host "        API Key : local   (qualquer valor)"
Write-Host "        Model   : edge-tts"
Write-Host "        Voice   : pt-BR-ThalitaNeural  (voz jovem/fofa)"
Write-Host "        (teste pelo playground: digite texto e clique em testar)"
Write-Host ""
Write-Host "  2. Settings -> Modules -> Speech"
Write-Host "     -> ative o modulo e selecione o provider"
Write-Host "        OpenAI Compatible (Speech)"
Write-Host ""
Write-Host "  Vozes para experimentar (campo Voice):"
Write-Host "    pt-BR-ThalitaNeural    jovem, fofa (recomendada)"
Write-Host "    pt-BR-ThalitaNeural:+30 tom ainda mais agudo (super fofa)"
Write-Host "    pt-BR-BrendaNeural     feminina"
Write-Host "    pt-BR-FranciscaNeural  feminina classica"
Write-Host "    pt-BR-AntonioNeural    masculino"
Write-Host "    ja-JP-NanamiNeural     japonesa (sotaque anime!)"
Write-Host "    ja-JP-AoiNeural        japonesa jovem"
Write-Host ""
Write-Host "  VOZ OFFLINE (Kokoro, opcional):"
Write-Host "    na interface (http://localhost:$Port/) tem o botao INSTALAR KOKORO"
Write-Host "    Ele instala tudo sozinho (venv + modelos ~360 MB, uma vez so)"
Write-Host "    Requisito: Python instalado (winget install Python.Python.3.12)"
Write-Host "    Depois use vozes como: kokoro:pf_dora"
Write-Host ""
if (-not $SemPausa) { Read-Host "Pressione Enter para fechar" }
