# -*- coding: utf-8 -*-
"""
cosyvoice3_worker.py — Worker do CosyVoice 3 (opcional, beta).

O CosyVoice 3 (Alibaba, Apache 2.0) é famoso pela **similaridade de voz** e
**controle de emoção**. Suporta português (~9 idiomas + dialetos). É um pouco
mais pesado que o Qwen3 para CPU e o setup é mais chato (usa Matcha-TTS,
FunASR, FunCodec...). Por isso é marcado como **beta/opcional** — deixamos ele
opcional na interface, mas o Qwen3 é o recomendado.

⚠️ AVISO: a instalação do CosyVoice requer dependências extras e pode precisar
de passos manuais (por isso `install_cosyvoice3.py` é só um guia/parcial).
"""

import os
import json
import shutil
import subprocess
import sys

from _common import run_worker, data_dir


# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
# Modelo HF (0.5B é o recomendado; dá para trocar para 1.5B se sobrar RAM).
COSY_MODEL_ID = "FunAudioLLM/Fun-CosyVoice3-0.5B-2512"


# ---------------------------------------------------------------------
# load
# ---------------------------------------------------------------------
def _load(model_dir):
    """Carrega o CosyVoice 3. Requer o repo clonado em voice-data/cosyvoice3/."""
    # O CosyVoice não é um pacote pip "puro"; precisa do repositório clonado
    # (`CosyVoice/`) e dos modelos baixados. Procuramos o repo dentro do data dir.
    repo = os.environ.get("COSY_REPO", None) or _find_cosy_repo(model_dir)
    if not repo:
        raise ValueError(
            "CosyVoice 3 não encontrado. Clone o repositório em voice-data/cosyvoice3/CosyVoice "
            "(ver install_cosyvoice3.py)."
        )

    sys.path.insert(0, repo)
    import torch
    # Importações típicas do CosyVoice 3 (podem variar por versão — daí ser beta).
    try:
        from cosyvoice.cli.cosyvoice import CosyVoice2  # atual usa CosyVoice2/3
    except Exception:
        from cosyvoice.cli.cosyvoice import CosyVoice

    # Caminhos de modelos (o instalador deixa um manifest em installed.json)
    installed = {}
    p = os.path.join(model_dir, "installed.json")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            installed = json.load(f)

    model_dir_path = installed.get("model_dir")
    if not model_dir_path:
        # Fallback: assume o padrão do repo.
        model_dir_path = os.path.join(repo, "pretrained_models", "CosyVoice-0.5B")

    device = os.environ.get("COSY_DEVICE", "cpu")
    print("[cosyvoice3] carregando modelo %s (device=%s)..." % (COSY_MODEL_ID, device), flush=True)
    model = CosyVoice2(COSY_MODEL_ID, load_jit=False, load_trt=False, fp16=False)
    print("[cosyvoice3] modelo carregado.", flush=True)
    return {"model": model, "model_id": COSY_MODEL_ID, "repo": repo}


# ---------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------
def _generate(req, state):
    model = state["model"]
    text = req.get("text", "").strip()
    if not text:
        raise ValueError("texto vazio")

    voice = req.get("voice", "").replace("cosyvoice3:", "").strip()
    instruct = req.get("instruct", "")
    ref_audio = req.get("ref_audio")
    ref_text = req.get("ref_text")

    # Prefere áudio de referência explícito, senão o da voz salva.
    if not ref_audio:
        vdir = os.path.join(data_dir("cosyvoice3"), "voices", voice)
        ref_audio = _find_ref(vdir)
    # CosyVoice exige texto de referência para clonagem de voz.
    if not ref_text:
        ref_text = req.get("ref_text", "") or ""

    # CosyVoice 3: ``synthesis`` aceita um prompt de voz (speaker).
    # `instruct_llm` é o modo que aceita instrução de emoção/estilo.
    try:
        for i, out in enumerate(model.inference_sft(text, instruct=instruct or None, stream=False)):
            import soundfile as sf
            import numpy as np
            wav = out["tts_speech"]
            sf.write(req.get("out") or os.path.join(os.path.dirname(req.get("out") or "."), "_c.wav"),
                     wav.detach().cpu().numpy() if hasattr(wav, "detach") else wav, 22050)
            return req.get("out")
    except Exception as e:
        raise ValueError("CosyVoice 3 não conseguiu gerar (%s). É beta — reveja config." % e)


def _find_ref(voice_dir):
    if not voice_dir or not os.path.isdir(voice_dir):
        return None
    for name in os.listdir(voice_dir):
        if name.lower().endswith((".wav", ".mp3", ".flac")):
            return os.path.join(voice_dir, name)
    return None


def _find_cosy_repo(model_dir):
    """Procura o repo clonado do CosyVoice dentro de voice-data/cosyvoice3/."""
    for cand in ("CosyVoice", "cosyvoice"):
        p = os.path.join(model_dir, cand)
        if os.path.isdir(p):
            return p
    return None


if __name__ == "__main__":
    def _load_wrap(md):
        st = _load(md); st["model_dir"] = md; return st
    run_worker("cosyvoice3", _load_wrap, _generate)
