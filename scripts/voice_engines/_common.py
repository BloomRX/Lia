# -*- coding: utf-8 -*-
"""
_common.py — Framework dos workers de voz (voice_engines).

Cada worker (qwen3_worker.py, cosyvoice3_worker.py) reimplementa apenas duas
funções:
    * load(model_dir)                   -> carrega o modelo (pode demorar)
    * generate(req, model) -> caminho   -> gera o .wav e devolve o caminho

Este módulo cuida de todo o "encanamento" de I/O com o servidor Node:
    * lê JSON-lines no STDIN  (uma requisição por linha)
    * escreve JSON-lines no STDOUT (ready / warn / ok / error)
    * salva o áudio num arquivo temporário (se o worker já devolver wav)
    * é robusto: nunca deixa um erro matar o processo inteiro sem responder.

Protocolo (igual ao worker do Kokoro, para o servidor tratar igual):
    stdin : {id, text, voice, speed, ..., out}
    stdout: {event:"ready"} | {event:"warn",msg} | {event:"ok",id,file}
          | {event:"error",id,msg}

Uso no worker:
    from _common import run_worker
    run_worker("qwen3", load_fn, generate_fn, ["--voice-data", dir])

    # load_fn(model_dir) -> modelo carregado (ou None)
    # generate_fn(req, model) -> caminho do .wav (ou bytes de áudio)
"""

import sys
import os
import json
import tempfile
import traceback

# ---------------------------------------------------------------------
# Utilidades de áudio
# ---------------------------------------------------------------------
def _save_audio(audio, out_path, sr=None, audio_fmt=None):
    """Salva o resultado da geração em `out_path`.

    Aceita:
      * str          -> caminho de um .wav já pronto (só retorna)
      * bytes        -> dados de áudio; grava em `out_path`
      * (np.ndarray, sr) -> tupla (amostras, taxa); grava com soundfile
    """
    # 1) Já é um caminho existente: o worker gravou ele mesmo.
    if isinstance(audio, str):
        return audio

    # 2) Bytes de wav/mp3: escreve direto.
    if isinstance(audio, (bytes, bytearray)):
        with open(out_path, "wb") as f:
            f.write(bytes(audio))
        return out_path

    # 3) Tupla (samples, sr): usa soundfile.
    if isinstance(audio, tuple) and len(audio) == 2:
        import numpy as np
        samples, sr = audio
        import soundfile as sf
        samples = np.asarray(samples)
        sf.write(out_path, samples, int(sr))
        return out_path

    raise ValueError("formato de áudio não reconhecido: %r" % type(audio))


def _reply(obj):
    """Escreve uma linha JSON no stdout (flush imediato) e não quebra se falhar."""
    try:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


# ---------------------------------------------------------------------
# Loop principal do worker
# ---------------------------------------------------------------------
def run_worker(engine_name, load_fn, generate_fn, argv=None):
    """Lê requisições JSON do stdin e despacha para `generate_fn`.

    Parâmetros:
      engine_name : nome do motor, usado em mensagens de log (ex.: "qwen3").
      load_fn     : callable(model_dir) -> modelo. Uma `ready` é emitida ao fim.
      generate_fn : callable(req, model) -> áudio (str/bytes/tuple).
      argv        : usa sys.argv se None; o primeiro argumento é o diretório de
                    dados do motor (model_dir). Se `--selftest` passar, roda um
                    teste embutido e sai.
    """
    argv = argv if argv is not None else sys.argv

    # ---- Modo auto-teste -------------------------------------------------
    if "--selftest" in argv:
        _selftest(engine_name, load_fn, generate_fn, argv)
        return

    # ---- Diretório de dados do motor ------------------------------------
    extra = [a for a in argv[1:] if not a.startswith("-")]
    model_dir = extra[0] if extra else os.getcwd()
    model_dir = os.path.abspath(model_dir)

    # ---- Carrega o modelo ------------------------------------------------
    model = None
    try:
        model = load_fn(model_dir)
        _reply({"event": "ready"})
    except Exception as e:
        _reply({"event": "error", "id": None, "msg": "[%s] falha ao carregar: %s" % (engine_name, e)})
        _reply({"event": "fatal", "msg": traceback.format_exc()})
        _exit(1)
        return

    # ---- Loop de requisições --------------------------------------------
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = {}
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            _reply({"event": "start", "id": rid})  # informa ao Node que começou
            audio = generate_fn(req, model)
            out = req.get("out")
            if not out:
                out = os.path.join(tempfile.gettempdir(), "%s_%s.wav" % (engine_name, rid or os.getpid()))
            path = _save_audio(audio, out)
            _reply({"event": "ok", "id": rid, "file": path})
        except Exception as e:
            # O erro vinha VAZIO ("erro desconhecido") porque alguns erros
            # (ex.: RuntimeError() sem texto) têm str(e) == "". Incluímos o
            # traceback para o Node/log mostrar o tipo real e a linha que falhou.
            tb = traceback.format_exc().strip()
            _reply({"event": "error", "id": rid,
                    "msg": "%r\n%s" % (e, tb[-1600:])})
            # Mantém o worker vivo após um erro pontual (não derruba o servidor).
            continue


def _selftest(engine_name, load_fn, generate_fn, argv):
    """Roda uma geração de teste sem depender do servidor Node."""
    extra = [a for a in argv[1:] if not a.startswith("-")]
    model_dir = extra[0] if extra else os.getcwd()
    print("[%s] SELFTEST: carregando modelo de %s ..." % (engine_name, model_dir), flush=True)
    try:
        model = load_fn(model_dir)
    except Exception as e:
        print("ERRO no load: %s" % e, flush=True)
        sys.exit(2)
    print("[%s] SELFTEST: modelo carregado. Gerando 'Olá, Lia!' ..." % engine_name, flush=True)
    req = {
        "id": "selftest",
        "text": "Olá, Lia! Como você está hoje?",
        "voice": "",
        "language": "Auto",
        "instruct": "fale com carinho e suavidade",
        "out": os.path.join(tempfile.gettempdir(), "%s_selftest.wav" % engine_name),
    }
    try:
        path = generate_fn(req, model)
        print("[%s] SELFTEST OK -> %s" % (engine_name, path), flush=True)
    except Exception as e:
        print("ERRO na geração: %s" % e, flush=True)
        traceback.print_exc()
        sys.exit(2)


def _exit(code):
    """Exit helper só para manter o linter feliz (não usa sys.exit direto)."""
    sys.exit(code)


# ---------------------------------------------------------------------
# Helper para achar o diretório de dados do motor a partir de um caminho conhecido
# ---------------------------------------------------------------------
def data_dir(engine_name, base=None):
    """Devolve <repo>/voice-data/<engine> (criando se necessário).

    Usado também pelo instalador para guardar venv/modelos/voices.
    """
    base = base or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    d = os.path.join(base, "voice-data", engine_name)
    os.makedirs(d, exist_ok=True)
    return d


__all__ = ["run_worker", "data_dir", "_save_audio"]
