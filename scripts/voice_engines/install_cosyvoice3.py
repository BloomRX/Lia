# -*- coding: utf-8 -*-
"""
install_cosyvoice3.py — Setup do CosyVoice 3 (OPCIONAL, beta).

O CosyVoice 3 é ótimo em similaridade/emoção, mas o setup é mais trabalhoso:
ele NÃO é um pacote pip único — precisa do repositório GitHub clonado e de um
conjunto de modelos. Este script automatiza o que dá e deixa claro o que ainda
é manual, para você não se perder.

Uso:
    python scripts/voice_engines/install_cosyvoice3.py
    python scripts/voice_engines/install_cosyvoice3.py --list

Passos:
    1. Cria venv (voice-data/cosyvoice3/venv)
    2. git clone https://github.com/FunAudioLLM/CosyVoice
    3. pip install -r requirements.txt (do repo) + matcha-tts etc.
    4. Marca installed.json (o download dos pesos é lazy no HF).

PROTOCOLO DE PROGRESSO (para a interface):
  O script imprime JSON-lines no stdout no formato:
    {"event":"step","pct":N,"msg":"..."}
    {"event":"log","msg":"..."}
    {"event":"done","ok":true,...}
    {"event":"error","msg":"..."}
  A interface (lia_app.py) lê essas linhas ao vivo e mostra status/% — assim
  o usuário sabe que a instalação não travou.

⚠️ BETA: dependendo da versão do repo, os imports/nomes de classe podem mudar.
Por isso o worker tenta varias formas. Se falhar, o app mostra o erro.
"""

import argparse
import json
import os
import subprocess
import sys
import venv as _venv

COSY_REPO = "https://github.com/FunAudioLLM/CosyVoice.git"
MODELS = {
    "FunAudioLLM/Fun-CosyVoice3-0.5B-2512": "0.5B (recomendado)",
    "FunAudioLLM/Fun-CosyVoice3-1.5B-2512": "1.5B (pesado)",
}

# Cache pip COMPARTILHADO com qwen3/kokoro/sovits: faz o pip reutilizar os
# wheels já baixados (torch/transformers/etc.) em vez de rebaixar tudo para
# cada venv. O pip lê a env var PIP_CACHE_DIR automaticamente.
_shared_cache = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "voice-data", "pip-cache")
os.environ.setdefault("PIP_CACHE_DIR", _shared_cache)


# ---------------------------------------------------------------------
# Saída JSON-lines (a interface lê e mostra % / status)
# ---------------------------------------------------------------------
def _emit(obj):
    try:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def _step(pct, msg):
    _emit({"event": "step", "pct": pct, "msg": msg})


def _log(msg):
    _emit({"event": "log", "msg": msg})


def _done(ok, **extra):
    _emit({"event": "done", "ok": bool(ok), **extra})


def _error(msg):
    _emit({"event": "error", "msg": msg})


# ---------------------------------------------------------------------
# Diretórios
# ---------------------------------------------------------------------
def _data_dir():
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.join(base, "voice-data", "cosyvoice3")
    os.makedirs(d, exist_ok=True)
    return d


def _venv_python(venv_dir):
    if sys.platform.startswith("win"):
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def install():
    data = _data_dir()
    venv_dir = os.path.join(data, "venv")
    py = _venv_python(venv_dir)
    repo = os.path.join(data, "CosyVoice")

    try:
        # 1) venv (10%)
        _step(10, "criando ambiente Python (venv)...")
        if not os.path.exists(py):
            _venv.EnvBuilder(with_pip=True).create(venv_dir)
        _log("venv em %s" % venv_dir)

        # 2) git clone (35%) — repo é grande (submódulos).
        _step(35, "clonando repositório CosyVoice (grande, pode demorar)...")
        if not os.path.isdir(repo):
            r = subprocess.run(["git", "clone", "--recursive", COSY_REPO, repo],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError("Erro ao clonar:\n" + (r.stderr or r.stdout)[-2000:])
        else:
            _log("repo já existe em %s — pulando clone." % repo)
        _log("repositório pronto.")

        # 3) deps (70%) — pode demorar MUITO (torch etc.).
        _step(70, "instalando dependências (pode demorar; use o cache compartilhado)...")
        req = os.path.join(repo, "requirements.txt")
        if os.path.exists(req):
            # As linhas do pip não são JSON; a interface vê o step acima e o
            # texto final abaixo. Se errar, avisamos sem derrubar a instalação.
            r = subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check",
                                "--cache-dir", _shared_cache, "-r", req],
                               capture_output=True, text=True)
            if r.returncode != 0:
                _log("AVISO: alguns requisitos falharam:\n" + (r.stderr or r.stdout)[-1500:])
        _log("dependências instaladas (ou parcialmente).")

        # 4) marca (100%)
        cfg = {"engine": "cosyvoice3", "repo": repo, "venv": venv_dir, "ready": True,
               "model_id": list(MODELS)[0], "device": "cpu"}
        with open(os.path.join(data, "installed.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

        _step(100, "configurado!")
        _done(True, repo=repo, venv=venv_dir)
        # Texto final legível (a UI lê o evento done; isto ajuda se rodar manual).
        print("--------------------------------------------------------------")
        print("✅ CosyVoice 3 configurado (pode precisar de ajustes manuais).")
        print("   Repo   : %s" % repo)
        print("   Venv   : %s" % venv_dir)
        print("   → Se o worker falhar, reveja os imports (beta).")
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
            print("CosyVoice3 instalado:", json.dumps(json.load(f), ensure_ascii=False, indent=2))
    else:
        print("CosyVoice3 não instalado. Rode: python install_cosyvoice3.py")


if __name__ == "__main__":
    os.makedirs(_shared_cache, exist_ok=True)
    ap = argparse.ArgumentParser(description="Configura o CosyVoice 3 (beta/opcional).")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        list_status()
    else:
        sys.exit(install())
