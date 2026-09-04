"""
lia/airi/config.py — Constantes de integração com o Project AIRI.

Centraliza tudo que o AIRI espera (chaves de localStorage, IDs de providers,
URLs base da Lia) para que a injeção seja construída de uma fonte de verdade
única. As chaves foram verificadas no main (beta) — ver docs/ESTUDO-AIRI.md §11.
"""

import json
import os
from pathlib import Path

from .. import config as _cfg

# ---------------------------------------------------------------
# Caminho do AIRI
# ---------------------------------------------------------------
# Diretório raiz do Project AIRI clonado (gerado pelo installer.py).
AIRI_ROOT = _cfg.ROOT / "airi"
# Pasta scripts do repo da Lia (onde mora o agentai-boot.html).
SCRIPTS = _cfg.SCRIPTS
STAGE_WEB_PUBLIC = AIRI_ROOT / "apps" / "stage-web" / "public"
STAGE_WEB_PACKAGE = AIRI_ROOT / "apps" / "stage-web" / "package.json"
TAMAGOTCHI_PACKAGE = AIRI_ROOT / "apps" / "stage-tamagotchi" / "package.json"

# ---------------------------------------------------------------
# Portas
# ---------------------------------------------------------------
# stage-web (Vite, default 5173) e CDP do Electron (remote-debugging).
WEB_PORT = _cfg.AIRI_PORT
CDP_PORT = _cfg.CDP_PORT
# Voice bridge da Lia (servidor_voz_airi.js) — porta 9860.
VOICE_PORT = _cfg.VOICE_PORT

# ---------------------------------------------------------------
# Providers que a Lia usa no AIRI
# ---------------------------------------------------------------
# CÉREBRO na nuvem (OpenAI-compatível): Groq PRIMÁRIO + Cerebras FALLBACK.
# O AIRI usa um único active-provider por vez; o health-check (lia.airi.diag)
# escolhe o 1º que responder na ordem desta lista. Cada entrada tem:
#   key        -> apelido usado nas env/keys ("groq") e no health-check.
#   id         -> id do provider gravado no localStorage do AIRI.
#   definition -> definitionId (o AIRI trata como OpenAI-compatible).
#   base_url   -> URL base OpenAI-compatible (o AIRI anexa /chat/completions).
#   model      -> modelo padrão usado como active-model.
#   env_key    -> variável de ambiente que guarda a chave de API.
BRAIN_PROVIDERS = [
    {
        "key": "groq",
        "id": "groq",
        "definition": "openai-compatible",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
    },
    {
        "key": "cerebras",
        "id": "cerebras",
        "definition": "openai-compatible",
        "base_url": "https://api.cerebras.ai/v1",
        "model": "llama-3.1-8b",
        "env_key": "CEREBRAS_API_KEY",
    },
]

# Compatibilidade: o provider PRIMÁRIO (Groq) vira o padrão do restante do código.
BRAIN_PROVIDER_ID = BRAIN_PROVIDERS[0]["id"]
BRAIN_PROVIDER_DEFINITION = BRAIN_PROVIDERS[0]["definition"]
BRAIN_MODEL = BRAIN_PROVIDERS[0]["model"]
BRAIN_BASE_URL = BRAIN_PROVIDERS[0]["base_url"]

# TTS/voz: OpenAI-compatível (audio speech) — aceita qualquer voz (edge/kokoro/sovits).
SPEECH_PROVIDER_ID = "openai-compatible-audio-speech"
SPEECH_PROVIDER_DEFINITION = "openai-compatible-audio-speech"
SPEECH_BASE_URL = f"http://127.0.0.1:{VOICE_PORT}/v1"
SPEECH_MODEL_EDGE = "edge-tts"
SPEECH_MODEL_SOVITS = "sovits"
# Novos motores (substituem o SoVITS). O gateway roteia pelo prefixo da voz,
# então o active-model é só um rótulo aqui — mas mantemos os IDs organizados.
SPEECH_MODEL_QWEN3 = "qwen3"
SPEECH_MODEL_COSYVOICE3 = "cosyvoice3"

# API key fake (qualquer valor; o servidor de voz local ignora).
LOCAL_API_KEY = "local"

# Arquivo de chaves de API (fora do git, ver .gitignore). Formato:
#   { "groq": "gsk_...", "cerebras": "..." }
# Precedência: variável de ambiente (GROQ_API_KEY / CEREBRAS_API_KEY) > este arquivo.
KEYS_FILE = _cfg.ROOT / "airi_keys.json"


def _api_keys_file() -> dict:
    """Lê airi_keys.json da raiz do projeto. Devolve dict (ou {} se ausente)."""
    try:
        if KEYS_FILE.exists():
            data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def api_key_for(key: str) -> str:
    """Resolve a chave de API de um provedor de cérebro.

    Ordem: variável de ambiente (<ENV_KEY>) → airi_keys.json[<key>] → "".
    """
    prov = next((p for p in BRAIN_PROVIDERS if p["key"] == key), None)
    if prov is None:
        return ""
    env_key = prov.get("env_key")
    if env_key:
        v = os.environ.get(env_key, "").strip()
        if v:
            return v
    return str(_api_keys_file().get(key, "")).strip()

# ---------------------------------------------------------------
# Chaves de localStorage do AIRI
# ---------------------------------------------------------------
# Providers configurados / adicionados.
KEY_PROVIDERS_CONFIGURED = "settings/providers/configured"
KEY_PROVIDERS_ADDED = "settings/providers/added"
# Speech (voz).
KEY_SPEECH_ACTIVE_PROVIDER = "settings/speech/active-provider"
KEY_SPEECH_ACTIVE_MODEL = "settings/speech/active-model"
KEY_SPEECH_VOICE = "settings/speech/voice"
KEY_SPEECH_PITCH = "settings/speech/pitch"
KEY_SPEECH_RATE = "settings/speech/rate"
KEY_SPEECH_SSML = "settings/speech/ssml-enabled"
# Consciousness (cérebro).
KEY_CONSCIOUSNESS_PROVIDER = "settings/consciousness/active-provider"
KEY_CONSCIOUSNESS_MODEL = "settings/consciousness/active-model"
KEY_CONSCIOUSNESS_CUSTOM_MODEL = "settings/consciousness/active-custom-model"
KEY_CONSCIOUSNESS_REASONING = "settings/consciousness/reasoning"
# Vision (ver a tela) — VLM.
KEY_VISION_PROVIDER = "settings/vision/active-provider"
KEY_VISION_MODEL = "settings/vision/active-model"
KEY_VISION_CUSTOM_MODEL = "settings/vision/active-custom-model"


def brain_url() -> str:
    """URL base do cérebro (com barra no fim, conforme o AIRI espera)."""
    return BRAIN_BASE_URL.rstrip("/") + "/"


def speech_url() -> str:
    """URL base do TTS (com barra no fim)."""
    return SPEECH_BASE_URL.rstrip("/") + "/"


def boot_page_public() -> Path:
    """Caminho onde o agentai-boot.html deve existir (na pasta public do stage-web)."""
    return STAGE_WEB_PUBLIC / "agentai-boot.html"
