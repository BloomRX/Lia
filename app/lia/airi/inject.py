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
    # Sufixo de pitch (só encaixa em edge/kokoro; os novos motores já têm
    # controle de emoção/velocidade por instrução, não por pitch).
    pitch_on = pitch != 0 and engine in ("edge", "kokoro")
    rate_on = rate != 1.0 and abs(rate - 1.0) > 1e-9 and engine in ("edge", "kokoro")

    if engine == "kokoro":
        s = f"kokoro:{voice}"
    elif engine == "sovits":
        return f"sovits:{voice}"
    elif engine in ("qwen3", "qwen", "cosyvoice3"):
        # Novos motores: o gateway (servidor_voz_airi.js) detecta o engine
        # pelo prefixo `qwen3:` / `cosyvoice3:` e roteia pro worker certo.
        return f"{engine}:{voice}"
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
    """Corpo de statements que grava os providers (cérebro + voz) no localStorage.

    Remove o provider legado 'openai-audio-speech' (oficial) e configura os
    CÉREBROS OpenAI-compatíveis de nuvem (Groq + Cerebras, ambos da lista
    BRAIN_PROVIDERS) e o provider de VOZ (audio speech local).

    Cada provider de cérebro é gravado com a própria chave de API e baseUrl
    (resolvida via api_key_for), para o AIRI conseguirá autenticar de verdade
    (não é mais um proxy local).
    """
    speech_url = _cfg.speech_url()
    lines = [
        "  try {",
        "    var configured = {};",
        "    var added = {};",
        f"    try {{ configured = JSON.parse(localStorage.getItem('{_cfg.KEY_PROVIDERS_CONFIGURED}') || '{{}}'); }} catch(e) {{}}",
        f"    try {{ added = JSON.parse(localStorage.getItem('{_cfg.KEY_PROVIDERS_ADDED}') || '{{}}'); }} catch(e) {{}}",
        "    // Remove provider legado (openai oficial) — usamos os compatíveis.",
        "    delete configured['openai-audio-speech'];",
        "    delete added['openai-audio-speech'];",
    ]
    # Cérebros (nuvem): Groq + Cerebras, na ordem de prioridade do fallback.
    for prov in _cfg.BRAIN_PROVIDERS:
        pid = prov["id"]
        pdef = prov["definition"]
        pkey = _cfg.api_key_for(prov["key"])
        base = prov["base_url"].rstrip("/") + "/"
        lines.append(
            f"    configured[{json.dumps(pid)}] = {{ id: {json.dumps(pid)}, "
            f"definitionId: {json.dumps(pdef)}, "
            f"config: {{ apiKey: {json.dumps(pkey)}, baseUrl: {json.dumps(base)} }}, "
            f"status: 'configured', configuredBy: 'user' }};"
        )
        lines.append(f"    added[{json.dumps(pid)}] = true;")
    # Voz (TTS): OpenAI-compatível (audio speech) — aceita qualquer voz.
    lines.append(
        f"    configured[{json.dumps(_cfg.SPEECH_PROVIDER_ID)}] = {{ id: {json.dumps(_cfg.SPEECH_PROVIDER_ID)}, "
        f"definitionId: {json.dumps(_cfg.SPEECH_PROVIDER_DEFINITION)}, "
        f"config: {{ apiKey: {json.dumps(_cfg.LOCAL_API_KEY)}, baseUrl: {json.dumps(speech_url)} }}, "
        f"status: 'configured', configuredBy: 'user' }};"
    )
    lines.append(f"    added[{json.dumps(_cfg.SPEECH_PROVIDER_ID)}] = true;")
    lines.append(f"    localStorage.setItem('{_cfg.KEY_PROVIDERS_CONFIGURED}', JSON.stringify(configured));")
    lines.append(f"    localStorage.setItem('{_cfg.KEY_PROVIDERS_ADDED}', JSON.stringify(added));")
    lines.append("    _out.push('PROVIDERS=OK');")
    lines.append("  } catch(e) { _out.push('PROVIDERS=ERRO:' + e.message); }")
    return "\n".join(lines)


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


def build_consciousness_js(model: str = _cfg.BRAIN_MODEL, provider_id: Optional[str] = None) -> str:
    """Corpo de statements que grava o módulo de consciência (cérebro) no localStorage.

    Crucial na beta: o default de active-provider/active-model é '' — sem isso o
    cérebro fica 'adicionado' mas não 'ativo'. O provider ativo é o escolhido pelo
    health-check (Groq primário, Cerebras fallback).
    """
    provider_id = provider_id or _cfg.BRAIN_PROVIDER_ID
    return f"""
  try {{
    localStorage.setItem('{_cfg.KEY_CONSCIOUSNESS_PROVIDER}', {json.dumps(provider_id)});
    localStorage.setItem('{_cfg.KEY_CONSCIOUSNESS_MODEL}', {json.dumps(model)});
    localStorage.removeItem('{_cfg.KEY_CONSCIOUSNESS_CUSTOM_MODEL}');
    _out.push('CONS=OK');
  }} catch(e) {{ _out.push('CONS=ERRO:' + e.message); }}
"""


def build_vision_js(model: str = _cfg.BRAIN_MODEL, provider_id: Optional[str] = None) -> str:
    """Corpo de statements que grava o módulo de visão (VLM) no localStorage.

    A visão usa o mesmo provider de cérebro da Lia (VLM). Se nenhum modelo de
    visão for configurado, deixamos vazio (desativado).
    """
    provider_id = provider_id or _cfg.BRAIN_PROVIDER_ID
    return f"""
  try {{
    localStorage.setItem('{_cfg.KEY_VISION_PROVIDER}', {json.dumps(provider_id)});
    localStorage.setItem('{_cfg.KEY_VISION_MODEL}', {json.dumps(model)});
    localStorage.removeItem('{_cfg.KEY_VISION_CUSTOM_MODEL}');
    _out.push('VIS=OK');
  }} catch(e) {{ _out.push('VIS=ERRO:' + e.message); }}
"""


# --------------------------------------------------------------------------
# Montagem final
# --------------------------------------------------------------------------
def build_all_js(
    active_model: str,
    voice: str,
    pitch: int = 0,
    rate: float = 1.0,
    brain_provider_id: Optional[str] = None,
    brain_model: Optional[str] = None,
) -> str:
    """Junta todos os blocos num único IIFE executável via CDP.

    Args:
        active_model: modelo TTS.
        voice: string de voz.
        pitch/rate: ajustes de voz.
        brain_provider_id: provider de CÉREBRO a ativar (Groq/Cerebras). Default
            = primário (BRAIN_PROVIDER_ID).
        brain_model: modelo do cérebro. Default = BRAIN_MODEL (do provider primário).
    """
    provider_id = brain_provider_id or _cfg.BRAIN_PROVIDER_ID
    _model = brain_model or _cfg.BRAIN_MODEL
    body = "\n".join([
        build_providers_js(),
        build_speech_js(active_model, voice, pitch, rate),
        build_consciousness_js(_model, provider_id),
        build_vision_js(_model, provider_id),
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
    var active_cons = get('settings/consciousness/active-provider');
    var brain = configured[active_cons];
    var speech = configured['openai-compatible-audio-speech'];
    out['brain_provider'] = active_cons;
    out['brain_base']   = brain && brain.config ? brain.config.baseUrl : null;
    out['brain_model']  = get('settings/consciousness/active-model');
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


def build_inject_and_verify_js(
    active_model: str,
    voice: str,
    pitch: int = 0,
    rate: float = 1.0,
    brain_provider_id: Optional[str] = None,
    brain_model: Optional[str] = None,
) -> str:
    """Junta Injeção (todos os blocos) + Verificação num único IIFE."""
    provider_id = brain_provider_id or _cfg.BRAIN_PROVIDER_ID
    _model = brain_model or _cfg.BRAIN_MODEL
    body = "\n".join([
        build_providers_js(),
        build_speech_js(active_model, voice, pitch, rate),
        build_consciousness_js(_model, provider_id),
        build_vision_js(_model, provider_id),
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


def _pick_page(targets) -> Optional[dict]:
    """Escolhe um target 'page' com WebSocket; prefere a página real da app."""
    if not isinstance(targets, list):
        return None
    pages = [t for t in targets if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
    if not pages:
        return None
    real = [t for t in pages if t.get("url") and not t.get("url", "").startswith("about:blank")]
    if real:
        pages = real
    dev = [t for t in pages if "localhost:" in t.get("url", "")]
    if dev:
        return dev[0]
    return pages[0]


def cdp_page_ws_url(port: int = _cfg.CDP_PORT) -> Optional[str]:
    """Retorna a URL do WebSocket da página da app (prefere a do Vite).

    Usa o endpoint /json do Chrome DevTools Protocol. Retorna None se não houver.
    """
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as resp:
            targets = json.loads(resp.read().decode("utf-8", "replace"))
        page = _pick_page(targets)
        if page:
            return page.get("webSocketDebuggerUrl")
    except Exception as e:
        _log.write(f"[AIRI] CDP /json falhou: {e}")
    return None
