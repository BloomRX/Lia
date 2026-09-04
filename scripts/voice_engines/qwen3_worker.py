# -*- coding: utf-8 -*-
"""
qwen3_worker.py — Worker do Qwen3-TTS (substituto do GPT-SoVITS).

O Qwen3-TTS (Alibaba, Apache 2.0) suporta:
  * Voice cloning (modelo Base) a partir de ~3s de áudio de referência;
  * Vozes pré-definidas (CustomVoice) com controle de emoção por instrução;
  * Português nativo (pt-BR) entre 10 idiomas;
  * Streaming e baixa latência (ideal para a Lia conversar).

Este worker é um PROCESSO separado que o servidor Node sobe sob demanda.
Ele fala JSON-lines no stdin/stdout (ver _common.py). Roda em **CPU** por padrão
(a sua RX 580 é AMD e não tem suporte ROCm no PyTorch). Se houver NVIDIA, dá para
trocar para `cuda` no config.json da voz.

Como o servidor chama:
    python -X utf8 -u qwen3_worker.py <voice-data>/qwen3

Como gerar (via servidor):
    voz "qwen3:liz"  -> usa o config.json de voice-data/qwen3/voices/liz/
"""

import os
import json

# Os imports pesados são feitos DENTRO das funções de load (lazy), para o
# worker não gastar tempo/memória se o modelo ainda for baixar.
import numpy as np

from _common import run_worker, data_dir


# ---------------------------------------------------------------------
# Configuração / catálogo de variantes
# ---------------------------------------------------------------------
# HF id de cada variante (0.6B recomendado p/ CPU; 1.7B mais pesado).
#  - Base        -> só clonagem; NÃO tem as vozes pré-definidas.
#  - CustomVoice -> tem as vozes pronto (Vivian/Serena/...) e também clona.
Qwen3_VARIANTS = {
    "0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "0.6b-custom": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice",
    "1.7b-custom": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
}

# True para variantes que têm as vozes pré-definidas (CustomVoice).
def _is_custom_variant(variant):
    return variant is not None and str(variant).lower().endswith("-custom")
# Vozes pré-definidas (CustomVoice) — para quem não tem referência, mas quer
# uma voz pronta com emoção. A base (clone) é o foco, mas deixamos as vozes
# conhecidas disponíveis.
QWEN3_PREST_VOICES = [
    "Vivian", "Serena", "Uncle_Fu", "Dylan", "Eric",
    "Ryan", "Aiden", "Ono_Anna", "Sohee",
]

# Dispositivo padrão. Na sua máquina (sem NVIDIA/RocM) usamos CPU.
_DEFAULT_DEVICE = "cpu"
_DEFAULT_DTYPE = "float32"   # CPU: float32 é estável. Com GPU usar bfloat16.


# ---------------------------------------------------------------------
# load: carrega o modelo (uma vez por processo)
# ---------------------------------------------------------------------
def _load(model_dir):
    """Carrega o modelo Qwen3-TTS indicado pelo config.json da voz alvo.

    Como o modelo Base (clone) é o mais pedido e o mais leve de configurar,
    carregamos a variante escolhida em `installed.json` (global). Se a voz
    pedir uma variante específica, priorizamos a dela.
    """
    # Lê o installed.json (grava pelo instalador) para saber a variante e,
    # principalmente, o CAMINHO dos pesos já baixados (model_path). Isso evita
    # que o HF rebaixe o modelo no primeiro uso (economiza tempo/internet).
    variant = "0.6b"
    model_id = Qwen3_VARIANTS[variant]
    model_path = None
    installed_path = os.path.join(model_dir, "installed.json")
    if os.path.exists(installed_path):
        try:
            with open(installed_path, "r", encoding="utf-8") as f:
                installed = json.load(f)
            variant = installed.get("variant", variant)
            if variant not in Qwen3_VARIANTS:
                variant = "0.6b"
            model_id = installed.get("model_id", Qwen3_VARIANTS[variant])
            model_path = installed.get("model_path")
            # Se o model_id no config aponta pra um CustomVoice, consideramos a
            # variante custom mesmo que a chave `variant` seja antiga/base.
            if "CustomVoice" in str(model_id):
                variant = "0.6b-custom" if "0.6B" in str(model_id) else "1.7b-custom"
        except Exception:
            pass

    device = os.environ.get("QWEN3_DEVICE", _DEFAULT_DEVICE)
    dtype = os.environ.get("QWEN3_DTYPE", _DEFAULT_DTYPE)
    # Se o instalador baixou os pesos, apontamos o from_pretrained para lá;
    # senão cai no repo_id (e o HF baixa sob demanda — último recurso).
    load_target = model_path if (model_path and os.path.isdir(model_path)) else model_id
    print("[qwen3] usando modelo %s em device=%s dtype=%s" % (load_target, device, dtype), flush=True)

    import torch
    from qwen_tts import Qwen3TTSModel

    # dtype aceito pelo pacote: "float32"/"bfloat16"/"float16".
    dtype_t = getattr(torch, dtype, torch.float32)
    try:
        model = Qwen3TTSModel.from_pretrained(
            load_target,
            device_map=device,  # "cpu" ou "cuda:0"
            dtype=dtype_t,
        )
    except TypeError:
        # Versões mais antigas do pacote podem não aceitar device_map/dtype.
        model = Qwen3TTSModel.from_pretrained(load_target)
    print("[qwen3] modelo carregado.", flush=True)
    model_kind = "custom" if _is_custom_variant(variant) else "base"
    return {"model": model, "model_id": model_id, "variant": variant,
            "model_kind": model_kind}


# ---------------------------------------------------------------------
# generate: recebe a requisição e devolve o caminho do .wav
# ---------------------------------------------------------------------
def _aplicar_speed(y, sr, speed):
    """Altera a velocidade preservando o tom (time_stretch do librosa).

    Qwen3-TTS não tem parâmetro nativo de "speed" — então fazemos um pós-processo
    no áudio: rate > 1 deixa mais rápido, 0 < rate < 1 deixa mais lento.
    """
    try:
        speed = float(speed)
    except Exception:
        speed = 1.0
    if speed is None or abs(speed - 1.0) < 1e-3:
        return y, sr
    try:
        import numpy as np
        arr = np.asarray(y, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        import librosa
        arr2 = librosa.effects.time_stretch(arr, rate=max(0.4, min(2.5, float(speed))))
        return arr2, sr
    except Exception as e:
        print("[qwen3] speed pós-processo falhou (%s) — usando áudio original." % e, flush=True)
        return y, sr


def _generate(req, state):
    model = state["model"]
    text = req.get("text", "").strip()
    if not text:
        raise ValueError("texto vazio")

    voice = req.get("voice", "").strip()
    language = req.get("language") or "Auto"
    instruct = req.get("instruct", "")
    ref_audio = req.get("ref_audio")
    ref_text = req.get("ref_text")
    speed = req.get("speed", 1.0)

    # Entende o formato do nome da voz:
    #   "qwen3:liz"          -> voz clonada em voices/liz/
    #   "liz"                -> idem (o servidor já removeu o prefixo)
    #   "Vivian"             -> voz pré-definida (CustomVoice)
    voice_key = voice.replace("qwen3:", "").strip()

    # Se for uma voz pré-definida conhecida, usa generate_custom_voice.
    if voice_key in QWEN3_PREST_VOICES:
        # Essa API só existe no modelo CustomVoice. O modelo Base (clone) NÃO as
        # tem — daí o erro 500. Avisamos com uma mensagem clara em vez de deixar
        # o servidor devolver um erro desconhecido.
        if state.get("model_kind") != "custom":
            raise ValueError(
                "a voz '%s' (pré-definida) precisa do modelo CustomVoice "
                "(variante '0.6b-custom' ou '1.7b-custom'). O modelo instalado é "
                "o Base, que só faz clone. Baixe a variante CustomVoice no app "
                "('⬇ Baixar engine') para usar as vozes prontas (Vivian/Ryan/...)."
                % voice_key
            )
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=language,
            speaker=voice_key,
            instruct=instruct or None,
        )
        return _aplicar_speed(wavs[0], sr, speed)

    # Caso contrário, tenta CLONE a partir de um config.json de voz.
    voice_dir = _voice_dir(state, voice_key)
    cfg = _load_voice_cfg(voice_dir)
    ref_audio = ref_audio or cfg.get("ref_audio") or _find_ref(voice_dir)
    ref_text = ref_text or cfg.get("ref_text") or ""

    if not ref_audio:
        raise ValueError(
            "voz %r sem áudio de referência. Forneça ref_audio (5–15s) ou "
            "clique em 'Clonar' na interface." % voice_key
        )

    # O modelo Base clona a partir de um prompt de voz.
    # `generate_voice_clone` aceita ref_audio/ref_text ou voice_clone_prompt.
    try:
        wavs, sr = model.generate_voice_clone(
            text=text,
            language=language,
            ref_audio=ref_audio,
            ref_text=ref_text or None,
        )
    except TypeError:
        # API alternativa: criar prompt e depois gerar.
        prompt = model.create_voice_clone_prompt(ref_audio=ref_audio, ref_text=ref_text or "")
        wavs, sr = model.generate_voice_clone(text=text, language=language, voice_clone_prompt=prompt)

    return _aplicar_speed(wavs[0], sr, speed)


# ---------------------------------------------------------------------
# Helpers locais (config de voz + referência)
# ---------------------------------------------------------------------
def _voice_dir(state, voice_key):
    """Diretório de dados da voz: voice-data/qwen3/voices/<voice_key>/"""
    model_dir = state.get("model_dir")
    if not model_dir:
        model_dir = data_dir("qwen3")
    vd = os.path.join(model_dir, "voices", voice_key)
    os.makedirs(vd, exist_ok=True)
    return vd


def _load_voice_cfg(voice_dir):
    cfg = {}
    p = os.path.join(voice_dir, "config.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    return cfg


def _find_ref(voice_dir):
    """Procura um ref.wav / ref.mp3 / amostra de áudio na pasta da voz."""
    for ext in (".wav", ".mp3", ".flac", ".ogg"):
        p = os.path.join(voice_dir, "ref" + ext)
        if os.path.exists(p):
            return p
    for name in os.listdir(voice_dir) if os.path.isdir(voice_dir) else []:
        if name.lower().endswith((".wav", ".mp3", ".flac", ".ogg")):
            return os.path.join(voice_dir, name)
    return None


# ---------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------
if __name__ == "__main__":
    # O `model_dir` é passado como 1º argumento (ou --selftest).
    def _load_wrap(model_dir):
        state = _load(model_dir)
        state["model_dir"] = model_dir
        return state

    def _gen_wrap(req, state):
        return _generate(req, state)

    run_worker("qwen3", _load_wrap, _gen_wrap)
