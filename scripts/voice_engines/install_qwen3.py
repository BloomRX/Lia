# -*- coding: utf-8 -*-
"""
install_qwen3.py — Baixa/setup do Qwen3-TTS (só o modelo que você escolher).

O objetivo é o usuário baixar APENA O QUE VAI USAR (0.6B ou 1.7B) — não os dois
de uma vez. Cria um venv isolado em voice-data/qwen3/venv e grava
voice-data/qwen3/installed.json com a variante escolhida.

Uso:
    python scripts/voice_engines/install_qwen3.py --variant 0.6b
    python scripts/voice_engines/install_qwen3.py --variant 1.7b
    python scripts/voice_engines/install_qwen3.py --list

Passos que ele faz:
    1. Cria venv (voice-data/qwen3/venv)
    2. pip install qwen-tts (e deps: torch, soundfile, transformers)
    3. Marca installed.json com a variante escolhida
    4. (O DOWNLOAD do modelo em si é lazy — o HF baixa no primeiro load do
       worker, porque os pesos são grandes e a variante é escolhida no uso.)
"""

import argparse
import json
import os
import subprocess
import sys
import venv as _venv

# Pacote pip do Qwen3-TTS.
QWEN3_PIP_DEPS = ["qwen-tts", "soundfile", "transformers", "torch"]

# Variantes aceitas (id no catálogo).
VARIANTS = {
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
}


def _data_dir():
    # voice-data/qwen3/ na raiz do repo (mesma lógica do _common.data_dir).
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.join(base, "voice-data", "qwen3")
    os.makedirs(d, exist_ok=True)
    return d


def _venv_python(venv_dir):
    if sys.platform.startswith("win"):
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def install(variant):
    if variant not in VARIANTS:
        print("ERRO: variante %r inválida. Use: %s" % (variant, list(VARIANTS)))
        return 2

    data = _data_dir()
    venv_dir = os.path.join(data, "venv")
    py = _venv_python(venv_dir)
    cfg = {"engine": "qwen3", "variant": variant, "model_id": VARIANTS[variant],
           "ready": False, "install_path": data, "venv": venv_dir, "device": "cpu"}

    # 1) venv
    if not os.path.exists(py):
        print("[qwen3] criando venv em %s ..." % venv_dir, flush=True)
        _venv.EnvBuilder(with_pip=True).create(venv_dir)
        if not os.path.exists(py):
            print("ERRO: falha ao criar o venv: %s" % py)
            return 1

    # 2) deps
    print("[qwen3] instalando dependências (%s) — pode demorar..." % ", ".join(QWEN3_PIP_DEPS), flush=True)
    r = subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check",
                        "--upgrade", "pip"], capture_output=True, text=True)
    r = subprocess.run([py, "-m", "pip", "install", "--disable-pip-version-check"] + QWEN3_PIP_DEPS,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("ERRO no pip install:\n" + (r.stderr or r.stdout)[-2000:])
        return 1

    # 3) marca installed.json. Os pesos baixam no primeiro uso (lazy via HF).
    with open(os.path.join(data, "installed.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    cfg["ready"] = True

    print("--------------------------------------------------------------")
    print("✅ Qwen3-TTS (%s) pronto!" % variant)
    print("   Variante : %s" % VARIANTS[variant])
    print("   Venv     : %s" % venv_dir)
    print("   Pasta    : %s" % data)
    print("   → O modelo agora é baixado no 1º uso (worker) e fica no cache do HF.")
    print("   → Escolha a voz no app: engine 'Qwen' → voz custom (clone) ou"),
    print("     voz pré-definida (Vivian/Ryan/...).")
    return 0


def list_status():
    data = _data_dir()
    p = os.path.join(data, "installed.json")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            print("Qwen3 instalado:", json.dumps(json.load(f), ensure_ascii=False, indent=2))
    else:
        print("Qwen3 não instalado. Rode: python install_qwen3.py --variant 0.6b")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Instala o Qwen3-TTS (baixa só o modelo escolhido).")
    ap.add_argument("--variant", choices=list(VARIANTS), help="0.6b (recomendado) ou 1.7b")
    ap.add_argument("--list", action="store_true", help="mostra o status atual")
    a = ap.parse_args()
    if a.list:
        list_status()
    elif a.variant:
        sys.exit(install(a.variant))
    else:
        ap.print_help()
        sys.exit(0)
