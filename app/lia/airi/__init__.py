"""
lia/airi/__init__.py — Integração com o Project AIRI.

Agrupa a lógica de: caminhos do AIRI, injeção de configuração via CDP/localStorage,
boot da waifu (web/tamagotchi) e diagnóstico.

Módulos:
    config   — caminhos/portas/chaves do AIRI e providers que a Lia usa
    inject   — geração do JS de injeção (providers+speech+consciousness+vision) e helpers CDP
    cdp      — execução do JS via CDP (PowerShell/WebSocket) com leitura de resultado
    boot     — sincroniza o agentai-boot.html no stage-web/public + Electron
    install  — garante o AIRI clonado + dependências (clone/pnpm) quando ausente
    diag     — health-checks do AIRI (web/CDP/serviços)
"""

from . import config, inject, cdp, boot, install, diag

__all__ = ["config", "inject", "cdp", "boot", "install", "diag"]
