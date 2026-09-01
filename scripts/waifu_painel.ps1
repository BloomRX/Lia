# ============================================================
#  waifu_painel.ps1 - PAINEL DA WAIFU (menu principal)  v4
#  Status ao vivo de cada peca; opcoes ligam o que falta sozinhas.
#  Na 1a vez, clona o AIRI e instala tudo automaticamente.
#  Abrir pelo  waifu.bat  (fica na mesma pasta).
# ============================================================
[CmdletBinding()]
param(
    [int]$VoicePort = 9860,
    [int]$AiriPort  = 5173
)

$Root = $PSScriptRoot
# Se o script esta em scripts/, subir um nivel
if ((Split-Path $Root -Leaf) -eq "scripts") { $Root = Split-Path $Root -Parent }
$REPO_ROOT = $Root
if (-not $Root) { $Root = Split-Path -Parent $MyInvocation.MyCommand.Path }
$AiriDir = Join-Path $Root "airi"

# ============================================================
# FUNCOES AUXILIARES
# ============================================================
function Test-Http([string]$url, [int]$secs = 2) {
    try {
        Invoke-WebRequest -Uri $url -TimeoutSec $secs -UseBasicParsing | Out-Null
        return $true
    }
    catch { return $false }
}

function Get-VozInfo {
    try {
        $r = Invoke-WebRequest -Uri ("http://127.0.0.1:" + $VoicePort + "/health") -TimeoutSec 2 -UseBasicParsing
        $j = $r.Content | ConvertFrom-Json
        return @{ up = $true; version = [string]$j.version; engines = @($j.engines) }
    }
    catch { return @{ up = $false } }
}

function Find-TunnelFile {
    $cands = @(
        (Join-Path $Root "ultima_url.txt"),
        "G:\Meu Drive\AgentAI\memory\api_url.txt",
        "G:\My Drive\AgentAI\memory\api_url.txt",
        "H:\Meu Drive\AgentAI\memory\api_url.txt",
        "H:\My Drive\AgentAI\memory\api_url.txt"
    )
    foreach ($c in $cands) {
        if (Test-Path $c) {
            $line = ""
            try { $line = (Get-Content $c -TotalCount 1 -ErrorAction SilentlyContinue) } catch { }
            if ($line) { $line = ("$line").Trim() }
            if ($line -like "http*") { return @{ file = $c; url = $line } }
        }
    }
    return $null
}

function Wait-VozUp([int]$secs) {
    for ($i = 0; $i -lt $secs; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Http ("http://127.0.0.1:" + $VoicePort + "/health") 2) { return $true }
    }
    return $false
}

function Avisa-Tunnel {
    if (-not (Find-TunnelFile)) {
        Write-Host ""
        Write-Host "[AVISO] Sem URL do tunel do Colab salva (ele deve estar desligado)."
        Write-Host "        Siga normal: a voz ja funciona, e quando o Colab ligar"
        Write-Host "        o cerebro reconecta sozinho (URL fixa)."
        return $false
    }
    return $true
}

# ============================================================
# VERIFICAR ATUALIZACOES (roda no inicio)
# ============================================================
function Check-Updates {
    $temAtualizacao = $false

    # --- Kit (AIRI_Collab) ---
    if (Test-Path (Join-Path $Root ".git")) {
        try {
            $null = & git -C $Root fetch origin 2>&1
            $local  = & git -C $Root rev-parse HEAD 2>&1
            $remote = & git -C $Root rev-parse origin/main 2>&1
            if ($local -ne $remote) {
                Write-Host ""
                Write-Host "[UPDATE] Ha atualizacoes no kit (AIRI_Collab)!"
                $log = & git -C $Root log --oneline "$local..$remote" 2>&1
                Write-Host $log
                $r = (Read-Host "Baixar atualizacoes? (S/n)").Trim()
                if ($r -ne "n" -and $r -ne "N") {
                    Write-Host "  Baixando..."
                    & git -C $Root pull --rebase 2>&1
                    Write-Host "  [OK] Kit atualizado!"
                    $temAtualizacao = $true
                }
            }
        } catch { }
    }

    # --- AIRI ---
    if (Test-Path (Join-Path $AiriDir ".git")) {
        try {
            $null = & git -C $AiriDir fetch origin 2>&1
            $local  = & git -C $AiriDir rev-parse HEAD 2>&1
            $remote = & git -C $AiriDir rev-parse origin/main 2>&1
            if ($local -ne $remote) {
                Write-Host ""
                Write-Host "[UPDATE] Ha atualizacoes no AIRI!"
                $log = & git -C $AiriDir log --oneline "$local..$remote" 2>&1
                Write-Host $log
                $r = (Read-Host "Baixar atualizacoes? (S/n)").Trim()
                if ($r -ne "n" -and $r -ne "N") {
                    Write-Host "  Baixando..."
                    & git -C $AiriDir pull --rebase 2>&1
                    Write-Host "  [OK] AIRI atualizado!"
                    Write-Host "  Rodando pnpm install (caso tenha novas dependencias)..."
                    Push-Location $AiriDir
                    try { & pnpm install 2>&1 } catch { }
                    Pop-Location
                    $temAtualizacao = $true
                }
            }
        } catch { }
    }

    if ($temAtualizacao) {
        Write-Host ""
        Write-Host "[OK] Tudo atualizado! Continuando..."
        Start-Sleep -Seconds 2
    }
}

# ============================================================
# SETUP AUTOMATICO (1a vez)
# ============================================================
function Garantir-Airi {
    # Ja tem o AIRI?
    if (Test-Path (Join-Path $AiriDir "package.json")) {
        Write-Host "[OK] AIRI encontrado: $AiriDir"
        return $true
    }

    Write-Host ""
    Write-Host "================================================"
    Write-Host "  INSTALANDO O AIRI (1a vez, demora um pouco)"
    Write-Host "================================================"
    Write-Host ""
    Write-Host "  Clonando o Project AIRI..."
    Write-Host ""

    try {
        & git clone https://github.com/moeru-ai/airi.git $AiriDir 2>&1
    }
    catch {
        Write-Host "[ERRO] Git clone falhou: $($_.Exception.Message)"
        Write-Host "       Tente manualmente:"
        Write-Host "       git clone https://github.com/moeru-ai/airi.git `"$AiriDir`""
        Read-Host "Enter para continuar"
        return $false
    }

    if (-not (Test-Path (Join-Path $AiriDir "package.json"))) {
        Write-Host "[ERRO] Clone nao criou package.json. Algo deu errado."
        Read-Host "Enter para continuar"
        return $false
    }

    Write-Host ""
    Write-Host "[OK] AIRI clonado!"
    Write-Host ""
    Write-Host "  Instalando dependencias (pnpm install)..."
    Write-Host ""

    Push-Location $AiriDir
    try {
        & pnpm install 2>&1
    }
    catch {
        Write-Host "[ERRO] pnpm install falhou: $($_.Exception.Message)"
        Write-Host "       Tente manualmente: cd airi && pnpm install"
        Pop-Location
        Read-Host "Enter para continuar"
        return $false
    }
    finally {
        Pop-Location
    }

    Write-Host ""
    Write-Host "[OK] Dependencias instaladas!"
    Write-Host ""
    return $true
}

function Garantir-NodeModules {
    # node_modules do servidor de voz (msedge-tts)
    $nm = Join-Path $Root "node_modules"
    if (Test-Path (Join-Path $nm "msedge-tts")) {
        return
    }
    Write-Host "[INFO] Instalando msedge-tts..."
    Push-Location $Root
    try { & npm install msedge-tts 2>&1 } catch { }
    Pop-Location
}

# ============================================================
# FUNCOES DE AÇÃO
# ============================================================
function Start-Voz {
    Write-Host ""
    Write-Host "--- Ligando o servidor de voz ---"
    Garantir-NodeModules
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "iniciar_voz.ps1") -SemPausa
    if (Wait-VozUp 25) {
        Write-Host ""
        Write-Host "[OK] Servidor de voz rodando!"
        return $true
    }
    Write-Host ""
    Write-Host "[ERRO] O servidor de voz nao subiu (veja os erros acima)."
    return $false
}

function Start-Aba {
    Write-Host ""
    Write-Host "--- Airi na ABA do navegador (Vite + URL do cerebro) ---"
    Start-Process powershell -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + (Join-Path $Root "atualizar_airi.ps1") + '"')
    Write-Host "[OK] Aberto numa janela propria (acompanha por la)."
}

function Start-Janela {
    Write-Host ""
    Write-Host "--- Airi na JANELINHA da tela (desktop) ---"
    Start-Process powershell -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + (Join-Path $Root "iniciar_tamagotchi.ps1") + '"')
    Write-Host "[OK] Aberto numa janela propria (acompanha por la)."
}

function Pergunta-Onde {
    Write-Host ""
    Write-Host "Onde a waifu vai aparecer?"
    Write-Host "   [A] Aba do navegador (como sempre foi)"
    Write-Host "   [J] Tamagotchi na tela (Airi desktop)"
    Write-Host "   [D] As duas"
    $modo = (Read-Host "Escolha (padrao J)").Trim()
    if ($modo -eq "" -or $modo -eq "J" -or $modo -eq "j") { return "J" }
    if ($modo -eq "D" -or $modo -eq "d") { return "D" }
    return "A"
}

function Get-DeskInfo {
    if (-not (Test-Path (Join-Path $AiriDir "package.json"))) {
        return @{ dir = $null }
    }
    $pkg = $false; $bin = $false
    foreach ($c in @(
        (Join-Path $AiriDir "apps\stage-tamagotchi\node_modules\electron"),
        (Join-Path $AiriDir "node_modules\electron")
    )) {
        if (Test-Path (Join-Path $c "package.json")) {
            $pkg = $true
            $bin = Test-Path (Join-Path $c "path.txt")
            break
        }
    }
    if (-not $pkg) {
        $hit = Get-ChildItem (Join-Path $AiriDir "node_modules\.pnpm") -Filter "electron@*" -Directory -ErrorAction SilentlyContinue
        $pkg = [bool]$hit
    }
    return @{ dir = $AiriDir; pkg = $pkg; bin = $bin }
}

function Criar-Atalho {
    try {
        $desk = [Environment]::GetFolderPath("Desktop")
        $lnkPath = Join-Path $desk "WAIFU.lnk"
        $ws = New-Object -ComObject WScript.Shell
        $sc = $ws.CreateShortcut($lnkPath)
        $sc.TargetPath = Join-Path $Root "waifu.bat"
        $sc.WorkingDirectory = $Root
        $sc.Description = "Painel da Waifu"
        $sc.Save()
        Write-Host "[OK] Atalho WAIFU criado na area de trabalho!"
        return $true
    }
    catch {
        Write-Host ("(nao consegui criar o atalho: " + $_.Exception.Message + ")")
        return $false
    }
}

function Ligar-Tudo {
    $modo = Pergunta-Onde
    $voz = Get-VozInfo
    if (-not $voz.up) {
        Write-Host ""
        Write-Host "A voz nao esta rodando - ligando antes de tudo..."
        $ok = Start-Voz
        if (-not $ok) { Read-Host "Enter para voltar ao menu"; return }
    }
    Avisa-Tunnel | Out-Null
    if ($modo -eq "A" -or $modo -eq "D") { Start-Aba }
    if ($modo -eq "J" -or $modo -eq "D") {
        if (-not (Garantir-Airi)) { Read-Host "Enter para voltar ao menu"; return }
        Start-Janela
    }
    Read-Host "Enter para voltar ao menu"
}

function Ligar-SemVoz {
    $modo = Pergunta-Onde
    Write-Host ""
    Write-Host "[INFO] A voz fica DESLIGADA: a waifu conversa por texto e nao fala."
    Avisa-Tunnel | Out-Null
    if ($modo -eq "A" -or $modo -eq "D") { Start-Aba }
    if ($modo -eq "J" -or $modo -eq "D") {
        if (-not (Garantir-Airi)) { Read-Host "Enter para voltar ao menu"; return }
        Start-Janela
    }
    Read-Host "Enter para voltar ao menu"
}

# ============================================================
# MENU
# ============================================================
function Show-Menu {
    Clear-Host
    Write-Host "================================================"
    Write-Host "  WAIFU - PAINEL"
    Write-Host "================================================"
    Write-Host ""
    Write-Host "  O que esta acontecendo agora:"

    $voz = Get-VozInfo
    if ($voz.up) { Write-Host ("   [OK ] Voz    : rodando v" + $voz.version + " (porta $VoicePort)") }
    else         { Write-Host "   [OFF] Voz    : nao esta rodando" }

    if (Test-Http ("http://127.0.0.1:" + $AiriPort) 2) { Write-Host "   [OK ] Aba    : Airi no navegador (porta $AiriPort)" }
    else                                               { Write-Host "   [OFF] Aba    : Airi no navegador nao esta rodando" }

    if (Find-TunnelFile) { Write-Host "   [OK ] Colab  : URL do tunel salva" }
    else                 { Write-Host "   [?? ] Colab  : URL do tunel desconhecida (suba as celulas la)" }

    $desk = Get-DeskInfo
    if (-not $desk.dir)  { Write-Host "   [-- ] Janela : AIRI nao instalado (opcao 1 ou 2 baixa automatico)" }
    elseif ($desk.bin)   { Write-Host "   [OK ] Janela : Airi desktop pronto" }
    elseif ($desk.pkg)   { Write-Host "   [1X ] Janela : falta o binario do Electron - a opcao 1 baixa na hora" }
    else                 { Write-Host "   [1X ] Janela : Airi desktop - 1a vez instala Electron (demora)" }

    Write-Host ""
    Write-Host "  O que voce quer fazer?"
    Write-Host "   [1] Ligar tudo (voz + escolhe: aba, Tamagotchi ou as duas)"
    Write-Host "   [2] Ligar SEM voz (so a waifu: aba, Tamagotchi ou as duas)"
    Write-Host "   [3] Voz: ligar ou reiniciar o servidor"
    Write-Host "   [4] So injetar a URL no Airi da aba"
    Write-Host "   [5] Status detalhado (testa o tunel do Colab)"
    Write-Host "   [6] Configurar o app desktop (cerebro + voz, 1 vez so)"
    Write-Host "   [0] Sair"
    Write-Host ""
    return (Read-Host "Digite o numero e Enter")
}

# ============================================================
# INICIO
# ============================================================

# primeira vez: oferecer atalho na area de trabalho
$flagAtalho = Join-Path $Root "atalho_waifu.criado"
if (-not (Test-Path $flagAtalho)) {
    Write-Host ""
    $r = Read-Host "Criar um atalho WAIFU na area de trabalho? (S/n)"
    if ($r -ne "n" -and $r -ne "N") {
        Criar-Atalho | Out-Null
    }
    "" | Out-File $flagAtalho -Encoding ASCII
}

# verificar atualizacoes ao abrir
Check-Updates

while ($true) {
    $op = Show-Menu
    switch ($op) {
        "1" { Ligar-Tudo }
        "2" { Ligar-SemVoz }
        "3" {
            $voz = Get-VozInfo
            if ($voz.up) {
                $r = Read-Host "A voz ja esta rodando. REINICIAR? (s/N)"
                if ($r -ne "s" -and $r -ne "S") { continue }
                $ouvido = $null
                try {
                    $ouvido = (Get-NetTCPConnection -LocalPort $VoicePort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
                } catch { }
                if ($ouvido) {
                    Write-Host "Parando o servidor antigo (pid $ouvido)..."
                    Stop-Process -Id $ouvido -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Seconds 2
                }
            }
            Start-Voz | Out-Null
            Read-Host "Enter para voltar ao menu"
        }
        "4" {
            Write-Host ""
            Write-Host "Abrindo o INJETAR URL numa janela nova..."
            Start-Process powershell -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + (Join-Path $Root "atualizar_airi.ps1") + '"')
            Read-Host "Enter para voltar ao menu"
        }
        "5" {
            Write-Host ""
            Write-Host "=== STATUS DETALHADO ==="
            $voz = Get-VozInfo
            if ($voz.up) {
                Write-Host ("   Voz     : v" + $voz.version + " | engines: " + ($voz.engines -join ", "))
            } else {
                Write-Host "   Voz     : OFF"
            }
            $tun = Find-TunnelFile
            if ($tun) {
                Write-Host ("   Tunel   : " + $tun.url)
                Write-Host ("   Arquivo : " + $tun.file)
                Write-Host "   Testando o tunel (ate 5s)..."
                if (Test-Http ($tun.url + "/health") 5) { Write-Host "   Tunel   : RESPONDEU (Colab no ar!)" }
                else { Write-Host "   Tunel   : nao respondeu agora (Colab desligado?)" }
            } else {
                Write-Host "   Tunel   : sem URL salva"
            }
            Read-Host "Enter para voltar ao menu"
        }
        "6" {
            Write-Host ""
            Start-Process powershell -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ('"' + (Join-Path $Root "configurar_tamagotchi.ps1") + '"')
            Write-Host "[OK] Aberto numa janela propria (acompanha por la)."
            Read-Host "Enter para voltar ao menu"
        }
        "0" { exit 0 }
        default { }
    }
}
