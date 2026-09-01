"""
lia/airi/inject.py — Injeção de configuração no AIRI via CDP/localStorage.

Gera o JavaScript que escreve as chaves de localStorage do AIRI (providers +
speech + consciousness + vision) e o executa pelo CDP do Electron
(porta de remote-debugging), depois recarrega a página e (opcionalmente) lê
de volta para confirmar que o AIRI reconheceu.

As chaves foram verificadas no main (beta) — ver docs/ESTUDO-AIRI.md §11.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.request
from typing import Optional

from .. import log as _log
from . import config as _cfg


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _timestamp() -> str:
    """Timestamp curto p/ nomear arquivos temporários de injeção."""
    return time.strftime("%Y%m%d-%H%M%S")


def wrap_js(body: str) -> str:
    """Embrulha um corpo de statements num IIFE executável (return do status)."""
    return f"""
(function() {{
  var _out = [];
  try {{
{body}
    _out.push('OK');
  }} catch(e) {{ _out.push('ERRO: ' + e.message); }}
  return _out.join(' | ');
}})();
"""


# --------------------------------------------------------------------------
# Composição da voz (formato usado na chave settings/speech/voice)
# --------------------------------------------------------------------------
def build_voice_str(engine: str, voice: str, pitch: int = 0, rate: float = 1.0) -> str:
    """Monta a string de voz que o AIRI guarda em settings/speech/voice.

    Formato por engine:
      - edge:      ``<voice>[:+/-pitch][@rate]``  (ex.: pt-BR-ThalitaNeural@1.00)
      - kokoro:    ``kokoro:<voice>[:+/-pitch][@rate]``  (ex.: kokoro:pf_dora@1.05)
      - sovits:    ``sovits:<voice>``  (ex.: sovits:minha_voz)

    Obs.: o servidor_voz_airi.js detecta o engine pelo prefixo (kokoro:/sovits:)
    ou pelo id da voz; pitch/rate são sufixos opcionais.
    """
    engine = (engine or "edge").lower()
    voice = voice or ""
    # Sufixo de pitch (só encaixa em edge/kokoro, não em sovits).
    pitch_on = pitch != 0 and engine in ("edge", "kokoro")
    rate_on = rate != 1.0 and abs(rate - 1.0) > 1e-9 and engine in ("edge", "kokoro")

    if engine == "kokoro":
        s = f"kokoro:{voice}"
    elif engine == "sovits":
        return f"sovits:{voice}"
    else:
        s = voice

    if pitch_on:
        s += f":+{pitch}" if pitch > 0 else f":{pitch}"
    if rate_on:
        s += f"@{rate:.2f}".rstrip("0").rstrip(".")
    return s


# --------------------------------------------------------------------------
# Builders (cada um retorna um corpo de statements puro)
# --------------------------------------------------------------------------
def build_providers_js() -> str:
    """Corpo de statements que grava os providers (chat + voz) no localStorage.

    Remove o provider legado 'openai-audio-speech' (oficial) e configura os
    dois providers OpenAI-compatíveis que a Lia usa.
    """
    brain_url = _cfg.brain_url()
    speech_url = _cfg.speech_url()
    return f"""
  try {{
    var configured = {{}};
    var added = {{}};
    try {{ configured = JSON.parse(localStorage.getItem('{_cfg.KEY_PROVIDERS_CONFIGURED}') || '{{}}'); }} catch(e) {{}}
    try {{ added = JSON.parse(localStorage.getItem('{_cfg.KEY_PROVIDERS_ADDED}') || '{{}}'); }} catch(e) {{}}

    // Remove provider legado (openai oficial) — usamos os compatíveis locais.
    delete configured['openai-audio-speech'];
    delete added['openai-audio-speech'];

    // Cérebro (chat): OpenAI-compatível apontando para o túnel via bridge.
    configured['{_cfg.BRAIN_PROVIDER_ID}'] = {{
      id: '{_cfg.BRAIN_PROVIDER_ID}',
      definitionId: '{_cfg.BRAIN_PROVIDER_DEFINITION}',
      config: {{ apiKey: '{_cfg.LOCAL_API_KEY}', baseUrl: '{brain_url}' }},
      status: 'configured', configuredBy: 'user'
    }};
    added['{_cfg.BRAIN_PROVIDER_ID}'] = true;

    // Voz (TTS): OpenAI-compatível (audio speech) — aceita qualquer voz.
    configured['{_cfg.SPEECH_PROVIDER_ID}'] = {{
      id: '{_cfg.SPEECH_PROVIDER_ID}',
      definitionId: '{_cfg.SPEECH_PROVIDER_DEFINITION}',
      config: {{ apiKey: '{_cfg.LOCAL_API_KEY}', baseUrl: '{speech_url}' }},
      status: 'configured', configuredBy: 'user'
    }};
    added['{_cfg.SPEECH_PROVIDER_ID}'] = true;

    localStorage.setItem('{_cfg.KEY_PROVIDERS_CONFIGURED}', JSON.stringify(configured));
    localStorage.setItem('{_cfg.KEY_PROVIDERS_ADDED}', JSON.stringify(added));
    _out.push('PROVIDERS=OK');
  }} catch(e) {{ _out.push('PROVIDERS=ERRO:' + e.message); }}
"""


def build_speech_js(active_model: str, voice: str, pitch: int = 0, rate: float = 1.0) -> str:
    """Corpo de statements que grava o módulo de voz (speech) no localStorage.

    Args:
        active_model: modelo TTS (ex.: 'edge-tts', 'sovits').
        voice: string de voz (ex.: 'pt-BR-ThalitaNeural', 'kokoro:pf_dora@1.05').
        pitch: pitch (inteiro; usado no sufixo da voz pela Lia).
        rate: velocidade (float; usado no sufixo da voz pela Lia).
    """
    return f"""
  try {{
    localStorage.setItem('{_cfg.KEY_SPEECH_ACTIVE_PROVIDER}', '{_cfg.SPEECH_PROVIDER_ID}');
    localStorage.setItem('{_cfg.KEY_SPEECH_ACTIVE_MODEL}', {json.dumps(active_model)});
    localStorage.setItem('{_cfg.KEY_SPEECH_VOICE}', {json.dumps(voice)});
    localStorage.setItem('{_cfg.KEY_SPEECH_PITCH}', {json.dumps(str(pitch))});
    localStorage.setItem('{_cfg.KEY_SPEECH_RATE}', {json.dumps(str(rate))});
    _out.push('SPEECH=OK');
  }} catch(e) {{ _out.push('SPEECH=ERRO:' + e.message); }}
"""


def build_consciousness_js(model: str = _cfg.BRAIN_MODEL) -> str:
    """Corpo de statements que grava o módulo de consciência (cérebro) no localStorage.

    Crucial na beta: o default de active-provider/active-model é '' — sem isso o
    cérebro fica 'adicionado' mas não 'ativo'.
    """
    return f"""
  try {{
    localStorage.setItem('{_cfg.KEY_CONSCIOUSNESS_PROVIDER}', '{_cfg.BRAIN_PROVIDER_ID}');
    localStorage.setItem('{_cfg.KEY_CONSCIOUSNESS_MODEL}', {json.dumps(model)});
    localStorage.removeItem('{_cfg.KEY_CONSCIOUSNESS_CUSTOM_MODEL}');
    _out.push('CONS=OK');
  }} catch(e) {{ _out.push('CONS=ERRO:' + e.message); }}
"""


def build_vision_js(model: str = _cfg.BRAIN_MODEL) -> str:
    """Corpo de statements que grava o módulo de visão (VLM) no localStorage.

    A visão usa o mesmo provider openai-compatible da Lia (VLM). Se nenhum
    modelo de visão for configurado, deixamos vazio (desativado).
    """
    return f"""
  try {{
    localStorage.setItem('{_cfg.KEY_VISION_PROVIDER}', '{_cfg.BRAIN_PROVIDER_ID}');
    localStorage.setItem('{_cfg.KEY_VISION_MODEL}', {json.dumps(model)});
    localStorage.removeItem('{_cfg.KEY_VISION_CUSTOM_MODEL}');
    _out.push('VIS=OK');
  }} catch(e) {{ _out.push('VIS=ERRO:' + e.message); }}
"""


# --------------------------------------------------------------------------
# Montagem final
# --------------------------------------------------------------------------
def build_all_js(active_model: str, voice: str, pitch: int = 0, rate: float = 1.0) -> str:
    """Junta todos os blocos num único IIFE executável via CDP."""
    body = "\n".join([
        build_providers_js(),
        build_speech_js(active_model, voice, pitch, rate),
        build_consciousness_js(),
        build_vision_js(),
    ])
    return wrap_js(body)


def build_verify_js() -> str:
    """Corpo de statements que lê de volta o localStorage e devolve um JSON.

    Usado após a Injeção+reload para confirmar que o AIRI reconheceu os
    providers e os módulos (speech / consciousness / vision). Retorna um JSON
    que o `cdp.py` converte em dict.
    """
    return """
  try {
    var out = {};
    function get(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }
    var configured = {};
    try { configured = JSON.parse(get('settings/providers/configured') || '{}'); } catch(e) {}
    var brain = configured['openai-compatible'];
    var speech = configured['openai-compatible-audio-speech'];
    out['brain_base']   = brain && brain.config ? brain.config.baseUrl : null;
    out['speech_base']  = speech && speech.config ? speech.config.baseUrl : null;
    out['speech_provider'] = get('settings/speech/active-provider');
    out['speech_model'] = get('settings/speech/active-model');
    out['speech_voice'] = get('settings/speech/voice');
    out['cons_provider'] = get('settings/consciousness/active-provider');
    out['cons_model']   = get('settings/consciousness/active-model');
    out['vis_provider'] = get('settings/vision/active-provider');
    out['vis_model']    = get('settings/vision/active-model');
    _out.push('VERIFY=' + JSON.stringify(out));
  } catch(e) { _out.push('VERIFY=ERRO:' + e.message); }
"""


def build_inject_and_verify_js(active_model: str, voice: str, pitch: int = 0, rate: float = 1.0) -> str:
    """Junta Injeção (todos os blocos) + Verificação num único IIFE."""
    body = "\n".join([
        build_providers_js(),
        build_speech_js(active_model, voice, pitch, rate),
        build_consciousness_js(),
        build_vision_js(),
        build_verify_js(),
    ])
    return wrap_js(body)


# --------------------------------------------------------------------------
# CDP (Chrome DevTools Protocol)
# --------------------------------------------------------------------------
def is_port_open(port: int = _cfg.CDP_PORT, host: str = "127.0.0.1", timeout: float = 2.0) -> bool:
    """Verifica se o CDP do Electron está respondendo na porta."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port)) == 0
    except Exception:
        return False
    finally:
        sock.close()


def cdp_page_ws_url(port: int = _cfg.CDP_PORT) -> Optional[str]:
    """Retorna a URL do WebSocket da primeira página 'page' no CDP.

    Usa o endpoint /json do Chrome DevTools Protocol. Retorna None se não houver.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as resp:
            targets = json.loads(resp.read().decode("utf-8", "replace"))
        for t in targets:
            if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                return t["webSocketDebuggerUrl"]
    except Exception as e:
        _log.write(f"[AIRI] CDP /json falhou: {e}")
    return None
