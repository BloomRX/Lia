# ============================================================
#  instalar_alltalk.ps1 - AllTalk TTS v2 (CPU / RX 580, sem NVIDIA)
#
#  Alternativa ao instalar_alltalk.bat (mais legivel; roda no
#  PowerShell). NAO usa o atsetup.bat oficial (que instalaria
#  torch CUDA + DeepSpeed = rota NVIDIA). Cria venv com torch
#  CPU e instala requirements SEM CUDA/DeepSpeed.
#
#  Executar NA RAIZ do projeto (onde esta o waifu.bat):
#      powershell -ExecutionPolicy Bypass -File instalar_alltalk.ps1
#  ou:
#      Set-ExecutionPolicy -Scope Process Bypass
#      .\instalar_alltalk.ps1
# ============================================================

$ErrorActionPreference = "Stop"

# ---- pasta do projeto (onde ESTE script esta) ----
$Proj = Split-Path -Parent $MyInvocation.MyCommand.Path
$Alltalk = Join-Path $Proj "alltalk_tts"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Instalador do AllTalk TTS v2  (CPU)"
Write-Host " Pasta do projeto : $Proj"
Write-Host " AllTalk em       : $Alltalk"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 1. Achar um Python 3.9-3.11 ----------
Write-Host "[1/4] Procurando Python 3.9-3.11 via  py ..." -ForegroundColor Green
$py = $null
foreach ($ver in @("3.11", "3.10", "3.9")) {
    if ($py) { break }
    $cand = (py -$ver -c "import sys;print(sys.executable)" 2>$null).Trim()
    if ($cand) {
        # valida a versao
        $ok = py -$ver -c "import sys; v=sys.version_info; sys.exit(0 if (v.major==3 and 9<=v.minor<=11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $cand }
    }
}

if (-not $py) {
    Write-Host ""
    Write-Host "[ERRO] Nao encontrei um Python 3.9-3.11 via  py -3.11 / -3.10 / -3.9  ." -ForegroundColor Red
    Write-Host "  Para conferir:  py --list"
    Write-Host "  Precisa de uma linha 'Python 3.11 (64-bit)' (nao e o 'Astral/')."
    Write-Host "  Se nao aparecer, instale o 3.11 em: https://www.python.org/downloads/windows/"
    Write-Host "  (marque 'py launcher'). O seu 3.14 continua o padrao; o 3.11 fica ao lado."
    Read-Host "Pressione Enter para sair"
    exit 1
}
Write-Host "  Usando Python: $py" -ForegroundColor Green
Write-Host "  (o seu python padrao do sistema nao foi alterado)"

# ---------- 2. Clonar AllTalk ----------
Write-Host ""
Write-Host "[2/4] Clonando AllTalk TTS v2 (se nao existir) ..." -ForegroundColor Green
if (Test-Path (Join-Path $Alltalk "README.md")) {
    Write-Host "  AllTalk ja esta clonado. Pulando clone."
} else {
    if (Test-Path $Alltalk) {
        Write-Host "  [AVISO] alltalk_tts existe mas parece incompleto. Recriando..."
        Remove-Item -Recurse -Force $Alltalk -ErrorAction SilentlyContinue
    }
    git clone https://github.com/erew123/alltalk_tts.git $Alltalk
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] Falha ao clonar. Verifique internet/Git." -ForegroundColor Red
        Read-Host "Pressione Enter para sair"
        exit 1
    }
    Write-Host "  Clone OK."
}

# ---------- 3. Instalar CPU ----------
Write-Host ""
Write-Host "[3/4] Instalando AllTalk em modo CPU (venv + torch CPU + requirements) ..." -ForegroundColor Green
Write-Host "  * Cria <projeto>\alltalk_tts\venv (isolado, nao toca no seu python)"
Write-Host "  * Instala torch CPU (SEM +cu121) e SEM DeepSpeed"
Write-Host "  * Pode demorar (baixa modelos/pacotes). Nao feche a janela."
Write-Host ""
& $py (Join-Path $Proj "scripts\alltalk_config.py") --install-cpu
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERRO] A instalacao CPU falhou. Veja as mensagens acima." -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

# ---------- 4. Confirmar config ----------
Write-Host ""
Write-Host "[4/4] Confirmando confignew.json (deepspeed off, porta 7851) ..." -ForegroundColor Green
& $py (Join-Path $Proj "scripts\alltalk_config.py") --patch-confignew

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Pronto!"
Write-Host " Iniciar  : iniciar_alltalk.bat  (ou venv\Scripts\python script.py)"
Write-Host " Interface: http://127.0.0.1:7851"
Write-Host " Airi voz : http://127.0.0.1:7851/v1"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host " Proximos passos (navegador, aba Generate):"
Write-Host "  - Swap TTS Engine = Piper   (mais rapido em CPU)"
Write-Host "  - Baixe um modelo pt-BR"
Write-Host "  - Ative RVC com seu .pth + .index  (pitch 0, index rate ~0.7)"
Write-Host " Guia completo: docs/ALLTALK-V2-CPU-RX580.md"
Write-Host ""
Read-Host "Pressione Enter para sair"
