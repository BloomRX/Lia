# -*- coding: utf-8 -*-
"""
install_qwen3.py — Baixa/setup do Qwen3-TTS (só o modelo que você escolher).

O usuário baixa APENAS o que vai usar (0.6B ou 1.7B — não os dois de uma vez).
Cria um venv isolado em voice-data/qwen3/venv, instala as deps e baixa os PESOS
do modelo (com % de progresso), gravando voice-data/qwen3/installed.json.

PROTOCOLO DE PROGRESSO (para a interface):
  O script imprime JSON-lines no stdout no formato:
    {"event":"step","msg":"criando venv","pct":0}
    {"event":"log","msg":"..."}                    # linha de log (texto livre)
    {"event":"progress","pct":40,"msg":"baixando modelo (memoria)"}  # %
    {"event":"done","ok":true,"model_path":"..."}
    {"event":"error","msg":"..."}

  A interface (lia_app.py) lê essas linhas ao vivo e mostra % + mensagem, para o
  usuário saber que NÃO travou.

Uso:
    python scripts/voice_engines/install_qwen3.py --variant 0.6b
    python scripts/voice_engines/install_qwen3.py --list
"""

import argparse
import json
import re
import os
import subprocess
import sys
import threading
import time
import urllib.request
import venv as _venv

# Garante que o stdout aceite emoji/acentos (✅, ç, ã...) independente do console.
# No Windows, sem isso, `print("✅...")` levanta "'charmap' codec can't encode...".
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Pacote pip do Qwen3-TTS. Deixamos o pip resolver as deps transitivas (o próprio
# qwen-tts já puxa torch/transformers); listamos só o essencial para clareza.
QWEN3_PIP_DEPS = ["qwen-tts", "huggingface_hub", "soundfile"]

# Cache pip COMPARTILHADO entre todas as engines (qwen3/cosyvoice3/kokoro).
# Sem isso, cada venv baixaria de novo os mesmos wheels (torch/transformers...).
# Com isso, o download acontece UMA vez e as demais engines reutilizam.
# Definimos como env var porque o pip lê PIP_CACHE_DIR automaticamente.
_shared_cache = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "voice-data", "pip-cache")
os.environ.setdefault("PIP_CACHE_DIR", _shared_cache)

# Variantes aceitas (id no catálogo do HuggingFace).
#  - Base         -> só CLONAGEM de voz (a partir de um áudio de referência).
#  - CustomVoice  -> vozes PRÉ-DEFINIDAS (Vivian, Ryan, Aiden...) + clone.
#    O modelo Base NÃO tem as vozes prontas — se o usuário escolher "Vivian"
#    com um modelo Base, a geração falha (HTTP 500). Por isso as variantes
#    CustomVoice também são oferecidas.
VARIANTS = {
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "0.6b-custom": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "1.7b-custom": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
}


# ---------------------------------------------------------------------
# Utilidades de saída (JSON-lines) — usadas pela interface p/ mostrar %
# ---------------------------------------------------------------------
def _emit(obj):
    """Escreve uma linha JSON no stdout (flush imediato), também como texto legível."""
    try:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        pass
    # Espelha o texto no stderr? Não — o app captura o stdout. Só emitimos o JSON.


def _step(pct, msg):
    _emit({"event": "step", "pct": pct, "msg": msg})


def _log(msg):
    _emit({"event": "log", "msg": msg})


def _progress(pct, msg):
    _emit({"event": "progress", "pct": int(pct), "msg": msg})


def _done(ok, **extra):
    _emit({"event": "done", "ok": bool(ok), **extra})


def _error(msg):
    _emit({"event": "error", "msg": msg})


# ---------------------------------------------------------------------
# Diretórios
# ---------------------------------------------------------------------
def _data_dir():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.join(base, "voice-data", "qwen3")
    os.makedirs(d, exist_ok=True)
    return d


def _venv_python(venv_dir):
    if sys.platform.startswith("win"):
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


# ---------------------------------------------------------------------
# Passo 1: criar venv
# ---------------------------------------------------------------------
def _create_venv(venv_dir):
    py = _venv_python(venv_dir)
    if os.path.exists(py):
        _log("venv já existe — pulando criação.")
        return py
    _step(5, "criando ambiente Python (venv)...")
    _venv.EnvBuilder(with_pip=True).create(venv_dir)
    if not os.path.exists(py):
        raise RuntimeError("Falha ao criar o venv em %s" % venv_dir)
    _log("venv criado em %s" % venv_dir)
    return py


# ---------------------------------------------------------------------
# Passo 2: instalar dependências (com leitura de progresso do pip)
# ---------------------------------------------------------------------
def _install_deps(py):
    _step(10, "instalando dependências (pode demorar)...")
    _log("pip install: %s" % ", ".join(QWEN3_PIP_DEPS))
    # Faz upgrade do pip antes (evita avisos/erros de versão antiga).
    # --cache-dir aponta para o cache compartilhado de todas as engines.
    r = subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check",
                        "--upgrade", "pip", "wheel", "--cache-dir", _shared_cache],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [py, "-m", "pip", "install", "--disable-pip-version-check", "--prefer-binary",
         "--cache-dir", _shared_cache] + QWEN3_PIP_DEPS,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", bufsize=1,
    )
    # Lê a saída do pip e reporta as últimas linhas úteis (não inunda o log).
    last_lines = []
    for line in proc.stdout:
        line = line.rstrip()
        if not line.strip():
            continue
        last_lines.append(line)
        if len(last_lines) > 6:
            last_lines.pop(0)
        # Mensagens-chave do pip viram log visível.
        for kw in ("Downloading", "Collecting", "Installing", "Successfully",
                   "Requirement already satisfied", "ERROR"):
            if kw in line:
                _log(line.strip()[:160])
                break
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("pip install falhou:\n" + "\n".join(last_lines))
    _log("dependências instaladas.")
    _step(20, "dependências prontas.")


# ---------------------------------------------------------------------
# Passo 3: baixar os PESOS do modelo (com % de progresso real)
# ---------------------------------------------------------------------
def _model_total_size(model_id):
    """Consulta a API do HF para saber o tamanho total (bytes) do modelo."""
    url = "https://huggingface.co/api/models/%s?blobs=true" % model_id
    try:
        with urllib.request.urlopen(url + ("" if "?" in url else ""), timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        total = 0
        for s in data.get("siblings", []):
            size = s.get("size") or 0
            total += size
        return total if total > 0 else 0
    except Exception as e:
        _log("Aviso: não consegui consultar o tamanho do modelo (%s) — reporto progresso por arquivo." % e)
        return 0


def _dir_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _download_model(py, model_id, local_dir):
    """Baixa o modelo para local_dir, reportando % EM TEMPO REAL.

    Estratégia:
      - Baixa usando snapshot_download (huggingface_hub) DENTRO do venv.
      - Uma thread de fundo mede o tamanho da pasta `local_dir` a cada ~1s e,
        comparando com o tamanho total (API do HF), emite eventos `progress`
        com o % atual — é isso que a interface mostra na barra.
      - A thread principal apenas lê/registra linhas do subprocess (logs de
        tqdm são filtrados para não inundar).
    """
    os.makedirs(local_dir, exist_ok=True)
    total_size = _model_total_size(model_id)
    _step(25, "baixando o modelo (%s, pode demorar...)" % model_id.split("/")[-1])
    _log("Baixando modelo: %s" % model_id)
    if total_size:
        _log("Tamanho estimado: %.0f MB" % (total_size / (1024 * 1024)))

    # Script que roda DENTRO do venv e baixa via HF (caminho de libs garantido).
    # Observação: `resume_download` foi removido nas versões novas do
    # huggingface_hub (o resume é automático). Tentamos com ele e, se falhar
    # TypeError, chamamos sem ele.
    dl_script = (
        "import sys\n"
        "try:\n"
        "    from huggingface_hub import snapshot_download\n"
        "except Exception as e:\n"
        "    print('ERR_IMPORT=' + repr(e)); sys.exit(3)\n"
        "try:\n"
        "    p = snapshot_download(repo_id=%r, local_dir=%r, resume_download=True)\n"
        "except TypeError:\n"
        "    p = snapshot_download(repo_id=%r, local_dir=%r)\n"
        "print('DONE_PATH=' + str(p))\n"
    ) % (model_id, local_dir, model_id, local_dir)

    # encoding="utf-8": a saída do download (tqdm, avisos) pode ter bytes fora
    # do cp1252; sem isso dá "'charmap' codec can't decode byte ..." no Windows.
    proc = subprocess.Popen(
        [py, "-X", "utf8", "-c", dl_script],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", bufsize=1,
    )

    # Regex para extrair % de barras de progresso do tqdm/huggingface_hub.
    # Ex.: "Downloading data...:  42%|██████ | 1.2/3.0G [00:01<00:02, 2.0GB/s]"
    _pct_re = re.compile(r"(\d+)%\|")

    def _monitor():
        """Mede o tamanho baixado e emite % a cada segundo (fonte A: tamanho)."""
        last_pct = -1
        while proc.poll() is None:
            try:
                downloaded = _dir_size(local_dir)
            except OSError:
                downloaded = 0
            if total_size and downloaded:
                pct = min(99, int(downloaded * 100 // total_size))
                if pct != last_pct:
                    last_pct = pct
                    _progress(pct, "baixando modelo... %d%% (%d/%d MB)" % (
                        pct, downloaded // 1048576, total_size // 1048576))
            time.sleep(1)
        # Final: emite 100% quando o processo terminar.
        _progress(100, "modelo baixado (%.0f MB)" % (_dir_size(local_dir) / 1048576))

    mon = threading.Thread(target=_monitor, daemon=True)
    mon.start()

    # Lê linhas do subprocess e extrai progresso (%) das barras tqdm.
    reported_pct = set()
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("ERR_IMPORT="):
            raise RuntimeError("huggingface_hub não disponível: " + line[len("ERR_IMPORT="):])
        if line.startswith("DONE_PATH="):
            continue
        # Fonte B: parseia o % do tqdm (usada quando a API de tamanho falhou).
        if not total_size:
            m = _pct_re.search(line)
            if m:
                pct = int(m.group(1))
                if pct not in reported_pct and pct < 100:
                    reported_pct.add(pct)
                    _progress(pct, "baixando modelo... %d%%" % pct)
        # Loga apenas linhas "úteis" (com texto), não barras de tqdm.
        # (os parênteses deixam clara a precedência: barra = tem "[ " OU tem "|" com "it/s")
        if ("[ " in line) or ("|" in line and "it/s" in line):
            continue  # barra de progresso do tqdm — já coberta acima.
        _log(line[:200])

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("Falha ao baixar o modelo (código %s)." % proc.returncode)
    if not os.path.isdir(local_dir) or not any(os.scandir(local_dir)):
        raise RuntimeError("O download terminou mas a pasta do modelo está vazia.")
    _log("Modelo baixado em: %s" % local_dir)
    return local_dir

def install(variant):
    if variant not in VARIANTS:
        _error("variante %r inválida. Use: %s" % (variant, list(VARIANTS)))
        return 2

    data = _data_dir()
    venv_dir = os.path.join(data, "venv")
    model_id = VARIANTS[variant]
    model_path = os.path.join(data, "models", variant)

    cfg_path = os.path.join(data, "installed.json")

    try:
        # 1) venv
        py = _create_venv(venv_dir)

        # 2) deps
        _install_deps(py)

        # 3) pesos do modelo (com % de progresso)
        _download_model(py, model_id, model_path)

        # 4) marca installed.json
        cfg = {
            "engine": "qwen3",
            "variant": variant,
            "model_id": model_id,
            "model_path": model_path,   # usado pelo worker (from_pretrained)
            "ready": True,
            "install_path": data,
            "venv": venv_dir,
            "device": "cpu",
        }
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        _step(100, "pronto!")
        _done(True, model_path=model_path, variant=variant, model_id=model_id)
        print("--------------------------------------------------------------")
        print("✅ Qwen3-TTS (%s) pronto!" % variant)
        print("   Modelo   : %s" % model_id)
        print("   Pesos    : %s" % model_path)
        print("   Venv     : %s" % venv_dir)
        print("   → Escolha a voz no app: engine 'Qwen' → voz custom (clone) ou")
        print("     voz pré-definida (Vivian/Ryan/...) — esta última exige a")
        print("     variante CustomVoice (0.6b-custom / 1.7b-custom).")
        return 0

    except Exception as e:
        _error(str(e))
        print("ERRO: %s" % e)
        return 1


def list_status():
    data = _data_dir()
    p = os.path.join(data, "installed.json")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            print("Qwen3 instalado:", json.dumps(json.load(f), ensure_ascii=False, indent=2))
    else:
        print("Qwen3 não instalado. Rode: python install_qwen3.py --variant 0.6b")


if __name__ == "__main__":
    os.makedirs(_shared_cache, exist_ok=True)
    ap = argparse.ArgumentParser(description="Instala o Qwen3-TTS (baixa só o modelo escolhido).")
    ap.add_argument("--variant", choices=list(VARIANTS),
                    help="0.6b/1.7b (clone) ou 0.6b-custom/1.7b-custom (vozes pré-definidas)")
    ap.add_argument("--list", action="store_true", help="mostra o status atual")
    a = ap.parse_args()
    if a.list:
        list_status()
    elif a.variant:
        sys.exit(install(a.variant))
    else:
        ap.print_help()
        sys.exit(0)
