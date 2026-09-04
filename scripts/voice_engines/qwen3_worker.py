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
import sys
import tempfile
import time
import traceback

# Os imports pesados são feitos DENTRO das funções de load (lazy), para o
# worker não gastar tempo/memória se o modelo ainda for baixar.
import numpy as np

from _common import run_worker, data_dir


# ---------------------------------------------------------------------
# Log de DEBUG em arquivo — IMUNE ao corte do stderr do Node.
# O servidor Node trunca o stderr do worker em ~300 chars e o Windows/console
# pode "comer" linhas. Para nunca mais ficar com "erro desconhecido", gravamos
# o traceback COMPLETO (com versões do Python/torch, kwargs, etc.) num arquivo.
# ---------------------------------------------------------------------
_DEBUG_LOG = None


def _log_debug(msg):
    """Anexa uma linha/traceback a voice-data/qwen3/qwen3_worker.log."""
    global _DEBUG_LOG
    try:
        if _DEBUG_LOG is None:
            _DEBUG_LOG = os.path.join(data_dir("qwen3"), "qwen3_worker.log")
        line = "[%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
        with open(_DEBUG_LOG, "a", encoding="utf-8", errors="replace") as f:
            f.write(line)
    except Exception:
        pass


def _log_debug_exc(e, context=""):
    """Loga a exceção completa (tipo, repr, traceback) no arquivo de debug."""
    tb = traceback.format_exc().strip()
    _log_debug("%s\n  EXC type=%s repr=%r\n  traceback:\n%s"
               % (context, type(e).__name__, e, tb))


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

    # Registra o ambiente completo no arquivo de debug (diagnóstico definitivo).
    try:
        _log_debug("=== carregando %s | device=%s dtype=%s ===" % (load_target, device, dtype))
        _log_debug("  python=%s | torch=%s | numpy=%s | PY=%s"
                   % (sys.version.split()[0], torch.__version__, np.__version__, sys.executable))
    except Exception:
        pass

    # dtype aceito pelo pacote: "float32"/"bfloat16"/"float16".
    dtype_t = getattr(torch, dtype, torch.float32)
    # Sem flash-attn (comum no seu hardware), o pacote usa um "manual PyTorch
    # attention" que pode quebrar/retornar erro vazio na geração em CPU/Windows.
    # Forçamos `attn_implementation="sdpa"` (Scaled Dot Product Attention, que o
    # PyTorch moderno usa por padrão) — é o que a comunidade recomenda (ex.: o
    # fork Qwen3-TTS-JP usa --no-flash-attn para o mesmo efeito). O try/except
    # garante que, se essa versão/pacote não aceitar, caímos na chamada anterior.
    # Tenta primeiro com sdpa (evita a atenção manual que costuma quebrar na
    # CPU/Windows); depois cai em chamadas progressivamente mais simples.
    for extra in (
        {"attn_implementation": "sdpa"},
        {},  # sem attn_implementation
        None,  # chamada mínima (sem device_map/dtype)
    ):
        try:
            if extra is None:
                model = Qwen3TTSModel.from_pretrained(load_target)
            else:
                model = Qwen3TTSModel.from_pretrained(
                    load_target, device_map=device, dtype=dtype_t, **extra)
            break
        except TypeError:
            # essa versão do pacote não aceita algum kwarg — tenta a próxima.
            continue
        except Exception as e:
            print("[qwen3] falhou com kwargs %s: %r — tentando mais simples..." % (extra, e), flush=True)
            continue
    print("[qwen3] modelo carregado.", flush=True)
    model_kind = "custom" if _is_custom_variant(variant) else "base"

    # Diagnóstico: mostra na tela (e no LOG em arquivo) quais vozes/idiomas o
    # modelo INSTALADO aceita. Isso evita adivinhar (ex.: usar "Vivian" num
    # modelo Base e levar erro 500).
    try:
        spks = model.get_supported_speakers()
        langs = model.get_supported_languages()
        if spks:
            print("[qwen3] vozes disponíveis:", ", ".join(sorted(spks)[:12]) +
                  ("..." if len(spks) > 12 else ""), flush=True)
        if langs:
            print("[qwen3] idiomas suportados:", ", ".join(langs), flush=True)
        _log_debug("modelo carregado | vozes=%s | idiomas=%s"
                   % (sorted(spks) if spks else None, langs))
    except Exception as e:
        print("[qwen3] não foi possível listar vozes/idiomas: %s" % e, flush=True)
        _log_debug_exc(e, "listar vozes/idiomas")

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


def _salvar_wav(arr, sr, out_path):
    """Grava um array numpy como .wav de forma robusta (sem depender do soundfile).

    O `_save_audio` do _common pode quebrar com erro vazio no Python 3.14; por
    isso o próprio worker grava o .wav e devolve o CAMINHO (string), que o
    _save_audio então apenas retorna.
    """
    import numpy as np
    import os
    a = np.asarray(arr, dtype=np.float32)
    if a.ndim == 2:
        a = a.mean(axis=1)
    a = np.squeeze(a).reshape(-1).astype(np.float32)
    m = float(np.max(np.abs(a)))
    if m > 1.0:
        a = (a / (m + 1e-9)).astype(np.float32)

    # Garante que a pasta exista.
    d = os.path.dirname(os.path.abspath(out_path))
    if d:
        os.makedirs(d, exist_ok=True)

    # 1) soundfile
    try:
        import soundfile as sf
        sf.write(out_path, a, int(sr))
        return out_path
    except Exception as e1:
        pass
    # 2) scipy wavfile
    try:
        from scipy.io import wavfile as wf
        s16 = np.clip(a * 32767.0, -32768, 32767).astype(np.int16)
        wf.write(out_path, int(sr), s16)
        return out_path
    except Exception as e2:
        pass
    # 3) librosa.write_wav
    try:
        import librosa
        librosa.output.write_wav(out_path, a, int(sr))
        return out_path
    except Exception as e3:
        raise RuntimeError("não consegui salvar .wav: %r / %r / %r" % (e1, e2, e3))


def _gera_custom_voice_tolerant(model, text, language, speaker, instruct):
    """Chama generate_custom_voice com fallbacks e retorna (wavs, sr).

    O pacote `qwen-tts` pode lançar erro SEM mensagem (str(e)=="") em alguns
    builds/caminhos. Tentamos variações conhecidas e sempre reportamos o
    traceback no stderr (que o servidor Node faz aparecer no log do app).
    """
    attempts = []
    # Ordem de tentativas: a mais fiel primeiro; as seguintes são apostas para
    # contornar falhas em "Auto"/instruct/streaming.
    attempts.append(dict(text=text, language=language, speaker=speaker,
                         instruct=instruct or None,
                         non_streaming_mode=True, max_new_tokens=2048))
    attempts.append(dict(text=text, language=language, speaker=speaker,
                         instruct=instruct or None))
    # "Auto" às vezes trava; força um idioma conhecido.
    attempts.append(dict(text=text, language=(language if language != "Auto" else "Portuguese"),
                         speaker=speaker, instruct=instruct or None,
                         non_streaming_mode=True, max_new_tokens=2048))
    # speaker pode ser exigido em minúsculas.
    attempts.append(dict(text=text, language=language, speaker=speaker.lower(),
                         instruct=instruct or None,
                         non_streaming_mode=True, max_new_tokens=2048))
    # versão mínima (deixa o pacote usar os defaults).
    attempts.append(dict(text=text))

    last_exc = None
    for a in attempts:
        try:
            wavs, sr = model.generate_custom_voice(**a)
            if wavs:
                return wavs, sr
        except TypeError:
            # Kwarg não aceito nesta versão — tenta a próxima (mais simples).
            last_exc = None
            continue
        except Exception as e:
            last_exc = e
            kws = {k: v for k, v in a.items() if k != "text"}
            print("[qwen3] tentativa falhou com kwargs=%s -> %r" % (kws, e), flush=True)
            _log_debug_exc(e, "generate_custom_voice falhou (kwargs=%s)" % kws)
            continue

    _log_debug("generate_custom_voice: TODAS as tentativas falharam. last=%r"
               % (last_exc,))
    raise RuntimeError("generate_custom_voice falhou em todas as tentativas. "
                       "%s" % (repr(last_exc) if last_exc else "sem mensagem"))


def _gera_clone_tolerant(model, text, language, ref_audio, ref_text):
    """Chama generate_voice_clone com fallbacks e retorna (wavs, sr)."""
    attempts = [
        dict(text=text, language=language, ref_audio=ref_audio, ref_text=ref_text or None),
        dict(text=text, language=language, ref_audio=ref_audio),
        dict(text=text),
    ]
    last_exc = None
    for a in attempts:
        try:
            wavs, sr = model.generate_voice_clone(**a)
            if wavs:
                return wavs, sr
        except TypeError:
            last_exc = None
            continue
        except Exception as e:
            last_exc = e
            print("[qwen3] clone tentativa falhou com kwargs=%s -> %r" %
                  ({k: v for k, v in a.items() if k != "text"}, e), flush=True)
            traceback.print_exc()
            continue
    # Último recurso: criar prompt de clone e gerar.
    try:
        prompt = model.create_voice_clone_prompt(ref_audio=ref_audio, ref_text=ref_text or "")
        wavs, sr = model.generate_voice_clone(text=text, language=language, voice_clone_prompt=prompt)
        if wavs:
            return wavs, sr
    except Exception as e:
        last_exc = e
        traceback.print_exc()
    raise RuntimeError("generate_voice_clone falhou. " % (repr(last_exc) if last_exc else "sem mensagem"))


def _generate(req, state):
    try:
        r = _generate_inner(req, state)
        _log_debug("OK voz=%r -> wav=%r" % (req.get("voice"), r))
        return r
    except Exception as e:
        # SEMPRE imprime o traceback no stderr (o Node o exibe no log do app)
        # E grava no arquivo de debug, para o erro nunca chegar "vazio".
        print("[qwen3] ERRO NA GERAÇÃO: %r" % e, flush=True)
        traceback.print_exc()
        _log_debug_exc(e, "ERRO NA GERAÇÃO voz=%r" % (req.get("voice"),))
        raise


def _generate_inner(req, state):
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
        wavs, sr = _gera_custom_voice_tolerant(model, text, language, voice_key, instruct)
        if not wavs:
            raise RuntimeError("generate_custom_voice devolveu áudio vazio (sem wavs).")
        arr = wavs[0]
        if getattr(arr, "shape", None) is not None and arr.shape[0] == 0:
            raise RuntimeError("generate_custom_voice devolveu áudio vazio (comprimento 0).")
        arr, sr = _aplicar_speed(arr, sr, speed)
        # O worker GRAVA o .wav e devolve o CAMINHO (string) — imune à falha do
        # _save_audio/soundfile no Python 3.14. Se não houver `out`, usa um temp.
        out = req.get("out") or os.path.join(tempfile.gettempdir(),
                                             "qwen3_%s.wav" % (req.get("id") or os.getpid()))
        return _salvar_wav(arr, sr, out)

    # Caso contrário, tenta CLONE a partir de um config.json de voz.
    voice_dir = _voice_dir(state, voice_key)
    cfg = _load_voice_cfg(voice_dir)
    ref_audio = ref_audio or cfg.get("ref_audio") or _find_ref(voice_dir)
    ref_text = ref_text or cfg.get("ref_text") or ""

    if not ref_audio:
        raise ValueError(
            "voz %r sem áudio de referência. Forneça ref_audio (5–15s) ou "
            "clique em 'Importar voz' na interface." % voice_key
        )

    wavs, sr = _gera_clone_tolerant(model, text, language, ref_audio, ref_text)
    if not wavs:
        raise RuntimeError("generate_voice_clone devolveu áudio vazio (sem wavs).")
    arr, sr = _aplicar_speed(wavs[0], sr, speed)
    # Grava o .wav e devolve o caminho (string) — imune ao bug do soundfile.
    out = req.get("out") or os.path.join(tempfile.gettempdir(),
                                         "qwen3_%s.wav" % (req.get("id") or os.getpid()))
    return _salvar_wav(arr, sr, out)


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
