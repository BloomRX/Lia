# ============================================================
#  testar_vozes.ps1  (kit de teste A/B de motores de voz)  v2
#  Gera amostras no SEU PC para voce ESCUTAR e escolher:
#
#   [Edge]   Edge TTS (o atual, Thalita)          - leve, online
#   [Kokoro] Kokoro TTS v1.0 (pf_dora, pm_alex)   - leve, OFFLINE, CPU
#   [XTTS]   XTTS-v2 (via coqui-tts)              - pesado (~4 GB),
#            clona a voz da amostra Kokoro; MUITO mais expressivo
#            (o AllTalk e so um servidor em volta do XTTS - mesma voz)
#
#  Uso:
#     powershell -ExecutionPolicy Bypass -File .\testar_vozes.ps1
#     powershell -ExecutionPolicy Bypass -File .\testar_vozes.ps1 -XTTS
#     powershell -ExecutionPolicy Bypass -File .\testar_vozes.ps1 -SkipEdge
#
#  Resultado: pasta J:\IA\teste-vozes com os .wav/.mp3 prontos pra ouvir.
# ============================================================
[CmdletBinding()]
param(
    [string]$Pasta = "J:\IA\teste-vozes",
    [switch]$XTTS,
    [switch]$SkipEdge
)
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "================================================"
Write-Host "  KIT DE TESTE DE VOZES (Edge vs Kokoro vs XTTS)"
Write-Host "================================================"
Write-Host ""

New-Item -ItemType Directory -Force -Path $Pasta | Out-Null
Write-Host "[OK] Pasta de saida: $Pasta"

# ---------- 1. Python (prefere 3.10-3.12; 3.13+ ainda e capaz de quebrar o ecossistema ONNX) ----------
$py = $null
$pyArgs = @()
$v = ""
foreach ($c in @("-3.12", "-3.11", "-3.10")) {
    try {
        $v = & py $c --version 2>&1 | Out-String
        if ("$v" -match "3\.(10|11|12)") { $py = "py"; $pyArgs = @($c); break }
    } catch { }
}
if (-not $py) {
    try {
        $v = & python --version 2>&1 | Out-String
        if ("$v" -match "3\.(10|11|12)") { $py = "python"; $pyArgs = @() }
    } catch { }
}
if (-not $py) {
    Write-Host "[AVISO] Nao achei Python 3.10-3.12. Vou tentar com o que houver:"
    try {
        $v = & py --version 2>&1 | Out-String
        if ("$v" -match "3\.") { $py = "py"; $pyArgs = @() }
        else { throw "sem py" }
    } catch {
        try {
            $v = & python --version 2>&1 | Out-String
            if ("$v" -match "3\.") { $py = "python"; $pyArgs = @() }
        } catch { }
    }
}
if (-not $py) {
    Write-Host "[ERRO] Python nao encontrado. Instale a versao 3.12:"
    Write-Host "       winget install Python.Python.3.12"
    Read-Host "Pressione Enter para sair"
    exit 1
}
Write-Host "[OK] Python em uso: $($v.Trim())  (ideal: 3.10-3.12)"

# ---------- 2. Venv + dependencias ----------
# venv por VERSAO do python (trocar de Python nao reusa venv quebrado)
$pyver = (& $py @pyArgs -c "import sys; print('%d%d' % sys.version_info[:2])").Trim()
$venvDir = Join-Path $Pasta ("venv-" + $pyver)
if (-not (Test-Path "$venvDir\Scripts\python.exe")) {
    Write-Host "Criando venv (Python $pyver)..."
    & $py @pyArgs -m venv $venvDir
}
$pypip = "$venvDir\Scripts\python.exe"
$deps = @("kokoro-onnx", "soundfile", "espeakng-loader", "phonemizer-fork")
if (-not $SkipEdge) { $deps += "edge-tts" }
Write-Host "Instalando dependencias (pode demorar alguns minutos na 1a vez)..."
$install = & $pypip -m pip install --disable-pip-version-check @deps 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERRO] Falha ao instalar dependencias. Ultimas linhas:"
    $install | Select-Object -Last 15
    Read-Host "Pressione Enter para sair"
    exit 1
}
Write-Host "[OK] Dependencias OK"

# ---------- 3. Baixar modelo Kokoro (~330 MB, 1a vez) ----------
$onnx   = Join-Path $Pasta "kokoro-v1.0.onnx"
$voices = Join-Path $Pasta "voices-v1.0.bin"
$ProgressPreference = "SilentlyContinue"
if (-not (Test-Path $onnx)) {
    Write-Host "Baixando modelo Kokoro (~330 MB, so na 1a vez)..."
    Invoke-WebRequest -Uri "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx" -OutFile $onnx
}
if (-not (Test-Path $voices)) {
    Write-Host "Baixando vozes Kokoro (~27 MB)..."
    Invoke-WebRequest -Uri "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin" -OutFile $voices
}
Write-Host "[OK] Modelo Kokoro pronto"

# ---------- 4. Script Python que gera as amostras ----------
$texto = "Oi! Eu sou a sua waifu. Testando um, dois, tres... esta voz esta boa assim? Se estiver, eu falo assim pra sempre!"
$pyScript = Join-Path $Pasta "gerar_amostras.py"
$pyScriptContent = @"
import os, sys, subprocess
PASTA = r"$Pasta"
TEXTO = r"$texto"

try:
    from espeakng_loader import get_library_path, get_data_path
    os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = get_library_path()
    os.environ["ESPEAK_DATA_PATH"] = get_data_path()
except Exception as e:
    print("espeakng-loader:", e)

import numpy as np
from kokoro_onnx import Kokoro
import soundfile as sf

kokoro = Kokoro(os.path.join(PASTA, "kokoro-v1.0.onnx"), os.path.join(PASTA, "voices-v1.0.bin"))

# --- [FIX WINDOWS] numpy no Windows tem inteiro padrao int32 e algumas
# versoes do kokoro-onnx montam os tensores sem dtype explicito, o que da
# "Unexpected input data type. Actual: tensor(int32), expected: float".
# FIX A NIVEL DE SESSAO: substitui a sessao ONNX por um proxy que forca
# cada input para o dtype EXATO declarado pelo modelo - de onde vier,
# por qual caminho interno for, chega certo no onnxruntime.
try:
    _ONNX2NP = {
        "tensor(float)": np.float32, "tensor(double)": np.float64,
        "tensor(int64)": np.int64, "tensor(int32)": np.int32,
        "tensor(int16)": np.int16, "tensor(int8)": np.int8,
        "tensor(uint8)": np.uint8, "tensor(uint16)": np.uint16,
        "tensor(uint32)": np.uint32, "tensor(uint64)": np.uint64,
        "tensor(bool)": np.bool_,
    }

    class _SessProxy:
        def __init__(self, sess):
            self._sess = sess
            self._declared = {i.name: i.type for i in sess.get_inputs()}
            self._orig_run = sess.run
        def _npd(self, t):
            if t in _ONNX2NP:
                return np.dtype(_ONNX2NP[t])
            return np.dtype(str(t).replace("tensor(", "").rstrip(")"))
        def run(self, output_names, input_feed, *a, **k):
            fixed = {}
            for name, arr in input_feed.items():
                want = self._declared.get(name)
                if want is not None:
                    wt = self._npd(want)
                    if isinstance(arr, np.ndarray):
                        if arr.dtype != wt:
                            arr = arr.astype(wt)
                    else:
                        # a lib passa listas cruas; sem dtype explicito o ORT
                        # converte com o int padrao da plataforma (int32 no
                        # Windows!) - aqui convertemos NOS pro dtype certo
                        arr = np.asarray(arr, dtype=wt)
                fixed[name] = arr
            return self._orig_run(output_names, fixed, *a, **k)
        def __getattr__(self, name):
            return getattr(self._sess, name)

    kokoro.sess = _SessProxy(kokoro.sess)
    print("[FIX] proxy de sessao instalado. dtypes declarados pelo modelo:",
          {i.name: i.type for i in kokoro.sess.get_inputs()})
except Exception as e:
    print("[AVISO] nao consegui aplicar o fix de dtype (seguindo com o padrao):", repr(e))

for voz, apelido in [("pf_dora", "kokoro_pf_dora"), ("pm_alex", "kokoro_pm_alex"), ("pm_santa", "kokoro_pm_santa")]:
    try:
        print("gerando", apelido, "...")
        samples, sr = kokoro.create(TEXTO, voice=voz, speed=1.0, lang="pt-br")
        sf.write(os.path.join(PASTA, apelido + ".wav"), samples, sr)
        print("  ok ->", apelido + ".wav")
    except Exception as e:
        print("  FALHOU", apelido, ":", repr(e))

if "$SkipEdge".lower() != "true":
    try:
        print("gerando edge_thalita (pra comparar)...")
        subprocess.run([sys.executable, "-m", "edge_tts",
                        "--voice", "pt-BR-ThalitaNeural",
                        "--text", TEXTO,
                        "--write-media", os.path.join(PASTA, "edge_thalita.mp3")],
                       check=True, capture_output=True)
        print("  ok -> edge_thalita.mp3")
    except Exception as e:
        print("  FALHOU edge:", e)
print("PRONTO")
"@
Set-Content -Path $pyScript -Value $pyScriptContent -Encoding UTF8

Write-Host "Gerando amostras (1-2 min)..."
& $pypip $pyScript
if ($LASTEXITCODE -ne 0) { Write-Host "[AVISO] O gerador terminou com erros - veja acima quais amostras falharam." }

# ---------- 5. XTTS (opcional, pesado) ----------
if ($XTTS) {
    Write-Host ""
    Write-Host "=== XTTS-v2 (pesado: ~4 GB de download; CPU demora ~2-5 min pra 1 frase) ==="
    Write-Host "Instalando PyTorch (~2.5 GB; no Python 3.14 ainda NAO existe)..."
    $instTorch = & $pypip -m pip install --disable-pip-version-check torch torchaudio 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] PyTorch nao esta disponivel para este Python ($pyver)."
        Write-Host "       O XTTS precisa de Python 3.10-3.12. Instale:"
        Write-Host "       winget install Python.Python.3.12"
        Write-Host "       ...e rode este script de novo (ele cria um venv novo sozinho)."
    } else {
    $inst = & $pypip -m pip install --disable-pip-version-check coqui-tts 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERRO] Falha ao instalar coqui-tts. Ultimas linhas:"
        $inst | Select-Object -Last 15
    } else {
        $env:COQUI_TOS_AGREED = "1"
        $pyXtts = Join-Path $Pasta "gerar_xtts.py"
        $xttsCode = @"
import os
os.environ["COQUI_TOS_AGREED"] = "1"
from TTS.api import TTS
PASTA = r"$Pasta"
ref = os.path.join(PASTA, "kokoro_pf_dora.wav")
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
tts.tts_to_file(
    text="Oi! Eu sou a sua waifu. Testando um, dois, tres... esta voz esta boa assim? Se estiver, eu falo assim pra sempre!",
    speaker_wav=ref, language="pt",
    file_path=os.path.join(PASTA, "xtts_clonando_kokoro.wav"),
)
print("XTTS OK")
"@
        Set-Content -Path $pyXtts -Value $xttsCode -Encoding UTF8
        & $pypip $pyXtts
    }
    }
}

# ---------- 6. RVC (so instrucoes - tem interface propria) ----------
Write-Host ""
Write-Host "=== RVC (manual - tem interface propria) ==="
Write-Host " 1. Baixe o w-okada Voice Changer: github.com/w-okada/voice-changer (Releases)"
Write-Host " 2. Baixe um modelo de voz RVC (HuggingFace: busque 'rvc v2 anime female ptbr' etc)"
Write-Host " 3. No w-okada: input = microfone/Edge, modelo = o .pth baixado"
Write-Host " 4. Pipeline com o Airi: Edge gera, o w-okada converte o timbre, sai no audio"

# ---------- 7. Abrir a pasta ----------
Write-Host ""
Write-Host "================================================"
Write-Host "  PRONTO! Ouvir os arquivos e comparar:"
Write-Host "================================================"
Write-Host "  edge_thalita.mp3          : o atual (A/B)"
Write-Host "  kokoro_pf_dora.wav        : Kokoro feminina BR"
Write-Host "  kokoro_pm_alex.wav        : Kokoro masculina"
Write-Host "  kokoro_pm_santa.wav       : Kokoro feminina 2"
if ($XTTS) { Write-Host "  xtts_clonando_kokoro.wav  : XTTS clonando a pf_dora (mais expressivo)" }
Write-Host ""
Start-Process explorer.exe $Pasta
Read-Host "Pressione Enter para fechar"
