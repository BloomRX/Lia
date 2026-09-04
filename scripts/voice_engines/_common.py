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
    """Salva o resultado da geração em `out_path` de forma ROBUSTA.

    Aceita:
      * str          -> caminho de um .wav já pronto (só retorna)
      * bytes        -> dados de áudio; grava em `out_path`
      * (np.ndarray, sr) -> tupla (amostras, taxa); grava com soundfile
                         (com fallback para scipy wavfile / librosa).

    IMPORTANTE: no Python 3.14 + soundfile alguns arrays vêm em shape (1, N)
    ou dtype float64/int e causam um erro "vazio". Normalizamos sempre para
    (N,) mono float32 antes de gravar, e tentamos vários gravadores.
    """
    # 1) Já é um caminho existente: o worker gravou ele mesmo.
    if isinstance(audio, str):
        return audio

    # 2) Bytes de wav/mp3: escreve direto.
    if isinstance(audio, (bytes, bytearray)):
        with open(out_path, "wb") as f:
            f.write(bytes(audio))
        return out_path

    # 3) Tupla (samples, sr) ou (list, sr): normaliza e grava.
    if isinstance(audio, tuple) and len(audio) == 2:
        import numpy as np
        samples, sr = audio
        samples = np.asarray(samples, dtype=np.float32)
        # Só cuida de shape: garante mono (N,) e normaliza para [-1, 1].
        if samples.ndim == 2:
            samples = samples.mean(axis=1)
        samples = np.squeeze(samples)
        if samples.ndim != 1:
            samples = samples.reshape(-1)
        if samples.size == 0:
            raise ValueError("áudio vazio (0 amostras) ao salvar.")
        # Normaliza para não estourar ("saturated WAV").
        try:
            m = float(np.max(np.abs(samples)))
            if samples.dtype == np.float32 and m > 1.0:
                samples = (samples / (m + 1e-9)).astype(np.float32)
        except Exception:
            pass

        try:
            import soundfile as sf
            sf.write(out_path, samples, int(sr))
            return out_path
        except Exception as e1:
            # Fallback 1: scipy wavfile (16-bit PCM).
            try:
                import numpy as _np
                from scipy.io import wavfile as _wf
                s16 = _np.clip(samples * 32767.0, -32768, 32767).astype(_np.int16)
                _wf.write(out_path, int(sr), s16)
                return out_path
            except Exception as e2:
                # Fallback 2: librosa (usa soundfile/soundfile-backend).
                try:
                    import librosa
                    librosa.output.write_wav(out_path, samples, int(sr))
                    return out_path
                except Exception as e3:
                    raise RuntimeError(
                        "não consegui salvar o .wav. soundfile=%r scipy=%r librosa=%r"
                        % (e1, e2, e3)
                    )

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
            # traceback no `msg` (JSON), imprimimos no stderr E gravamos num
            # arquivo de debug, para o Node/log mostrar o tipo real e a linha.
            tb = traceback.format_exc().strip()
            try:
                sys.stderr.write("[%s] ERRO NA GERAÇÃO: %r\n%s\n" % (engine_name, e, tb))
                sys.stderr.flush()
            except Exception:
                pass
            # Log em arquivo (imune ao corte do stderr do Node).
            _log_file_debug(engine_name, "ERRO NA GERAÇÃO", e, tb)
            _reply({"event": "error", "id": rid,
                    "msg": "%r\n%s" % (e, tb[-2000:])})
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


def _worker_dir(engine_name):
    """Diretório de dados do worker (para gravar logs de erro em arquivo)."""
    try:
        return data_dir(engine_name)
    except Exception:
        return os.getcwd()


def _log_file_debug(engine_name, context, e, tb):
    """Anexa um erro ao <engine>_worker.log (imune ao corte do stderr)."""
    try:
        import time as _t
        logfile = os.path.join(_worker_dir(engine_name), "%s_worker.log" % engine_name)
        with open(logfile, "a", encoding="utf-8", errors="replace") as _f:
            _f.write("[%s] %s: type=%s repr=%r\n%s\n" %
                     (_t.strftime("%Y-%m-%d %H:%M:%S"), context,
                      type(e).__name__, e, tb))
    except Exception:
        pass


__all__ = ["run_worker", "data_dir", "_save_audio"]
