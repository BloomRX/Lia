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

    # 1) venv
    if not os.path.exists(py):
        print("[cosyvoice3] criando venv em %s ..." % venv_dir, flush=True)
        _venv.EnvBuilder(with_pip=True).create(venv_dir)

    # 2) git clone
    if not os.path.isdir(repo):
        print("[cosyvoice3] clonando repositório (grande, pode demorar)...", flush=True)
        r = subprocess.run(["git", "clone", "--recursive", COSY_REPO, repo], capture_output=True, text=True)
        if r.returncode != 0:
            print("ERRO ao clonar:\n" + (r.stderr or r.stdout)[-2000:])
            return 1
    else:
        print("[cosyvoice3] repo já existe em %s — pulando clone." % repo)

    # 3) deps
    req = os.path.join(repo, "requirements.txt")
    if os.path.exists(req):
        print("[cosyvoice3] instalando requirements.txt (pode demorar MUITO)...", flush=True)
        r = subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check",
                            "-r", req], capture_output=True, text=True)
        if r.returncode != 0:
            print("AVISO: alguns requisitos falharam:\n" + (r.stderr or r.stdout)[-1500:])

    # 4) marca
    cfg = {"engine": "cosyvoice3", "repo": repo, "venv": venv_dir, "ready": True,
           "model_id": list(MODELS)[0], "device": "cpu"}
    with open(os.path.join(data, "installed.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    print("--------------------------------------------------------------")
    print("✅ CosyVoice 3 configurado (pode precisar de ajustes manuais).")
    print("   Repo   : %s" % repo)
    print("   Venv   : %s" % venv_dir)
    print("   → Se o worker falhar, reveja os imports (beta).")
    return 0


def list_status():
    data = _data_dir()
    p = os.path.join(data, "installed.json")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            print("CosyVoice3 instalado:", json.dumps(json.load(f), ensure_ascii=False, indent=2))
    else:
        print("CosyVoice3 não instalado. Rode: python install_cosyvoice3.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Configura o CosyVoice 3 (beta/opcional).")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        list_status()
    else:
        sys.exit(install())
