"""
lia/airi/diag.py — Health-checks e diagnóstico da integração com o AIRI.

Expõe funções pequenas/retornáveis (sem GUI) para verificar se o AIRI está
instalado, rodando, se o CDP está acessível, se a página de boot existe e se
os providers/modulos estão configurados. O painel de diagnóstico do Lia App
usa estes resultados (com verde/vermelho/amarelo).
"""

from __future__ import annotations

import json
import socket
import urllib.request

from .. import config as _cfg
from . import config as _airi_cfg
from . import boot as _boot
from . import inject as _inject


def _urlopen(url: str, timeout: float = 3) -> tuple[bool, str]:
    """GET simples. Retorna (ok, detalhe/erro)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
def airi_web() -> dict:
    """Verifica o stage-web (Vite) na porta AIRI_PORT."""
    ok, detail = _urlopen(f"http://127.0.0.1:{_cfg.AIRI_PORT}")
    return {"ok": ok, "detail": detail}


def cdp_available() -> dict:
    """Verifica se o CDP do Electron está acessível (Tamagotchi)."""
    ok = _inject.is_port_open(_cfg.CDP_PORT)
    detail = f"porta {_cfg.CDP_PORT} aberta" if ok else "porta fechada (Tamagotchi não rodando?)"
    return {"ok": ok, "detail": detail}


def cdp_targets() -> dict:
    """Lista alvos de página no CDP (para diagnosticar a injeção)."""
    ws_url = _inject.cdp_page_ws_url(_cfg.CDP_PORT)
    return {"ok": ws_url is not None, "detail": ws_url or "sem alvo 'page'"}


def boot_page() -> dict:
    """Verifica se o agentai-boot.html existe no airi (pastas + servido)."""
    if not _boot.dest_boot_page().exists():
        return {"ok": False, "detail": "arquivo ausente em apps/stage-web/public/"}
    ok, detail = _urlopen(f"http://127.0.0.1:{_cfg.AIRI_PORT}/agentai-boot.html")
    served = "servido pelo Vite" if ok else f"não servido ({detail})"
    return {"ok": ok, "detail": f"presente no disco e {served}"}


def installed() -> dict:
    """Verifica se o AIRI foi clonado (package.json presente)."""
    ok = _boot.airi_installed()
    return {"ok": ok, "detail": str(_airi_cfg.AIRI_ROOT) if ok else "AIRI não instalado"}


def electron() -> dict:
    """Verifica se o binário do Electron (Tamagotchi) está pronto."""
    ready = _boot.electron_binary_ready()
    detail = "binário pronto" if ready else "binário ausente (ver iniciar_tamagotchi.ps1)"
    return {"ok": ready, "detail": detail}


def all_checks() -> list[dict]:
    """Roda todos os checks e devolve uma lista rotulada (p/ exibir no painel)."""
    return [
        {"name": "AIRI instalado", **installed()},
        {"name": "stage-web (5173)", **airi_web()},
        {"name": "CDP Electron (9222)", **cdp_available()},
        {"name": "alvo de página (CDP)", **cdp_targets()},
        {"name": "agentai-boot.html", **boot_page()},
        {"name": "binário Electron", **electron()},
    ]
