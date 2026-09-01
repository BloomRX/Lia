"""
lia/airi/boot.py — Preparação da página de boot da waifu no AIRI.

O AIRI (stage-web) precisa do arquivo `agentai-boot.html` dentro de
`apps/stage-web/public/`. É essa página que, ao carregar via URL, lê os
parâmetros (`url`, `model`, `voice`, `voiceBase`) e injeta a configuração do
provider/cérebro/voz **antes** de redirecionar para o app.

Como o AIRI é re-clonado/atualizado, o `agentai-boot.html` (que vive no repo da
Lia em `scripts/`) pode sumir. A função `sync_boot_page()` garante que ele
exista, copiando a versão da Lia sempre.

Também centraliza o caminho do binário do Electron (para o fluxo do
Tamagotchi na `iniciar_tamagotchi.ps1`).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .. import log as _log
from . import config as _cfg


def source_boot_page() -> Path:
    """Caminho da fonte do agentai-boot.html (no repo da Lia)."""
    return _cfg.SCRIPTS / "agentai-boot.html"


def dest_boot_page() -> Path:
    """Caminho de destino no AIRI (apps/stage-web/public/agentai-boot.html)."""
    return _cfg.boot_page_public()


def sync_boot_page(force: bool = True) -> bool:
    """Garante que o agentai-boot.html exista na pasta public do stage-web.

    Returns True se o arquivo está presente (e é o da Lia) após a chamada.
    """
    src = source_boot_page()
    dst = dest_boot_page()
    if not src.exists():
        _log.write(f"[AIRI] agentai-boot.html não encontrado na fonte: {src}")
        return False
    if not _cfg.STAGE_WEB_PUBLIC.exists():
        _log.write(f"[AIRI] Pasta public do stage-web não existe: {_cfg.STAGE_WEB_PUBLIC}")
        _log.write("[AIRI] O AIRI ainda não foi instalado/atualizado. Não há o que copiar.")
        return False
    if dst.exists() and not force:
        return True
    try:
        shutil.copy2(str(src), str(dst))
        _log.write(f"[AIRI] agentai-boot.html sincronizado → {dst}")
        return True
    except Exception as e:
        _log.write(f"[AIRI] Falha ao copiar agentai-boot.html: {e}")
        return False


def airi_installed() -> bool:
    """True se o AIRI (raiz com package.json) foi instalado."""
    return (_cfg.STAGE_WEB_PACKAGE.exists() or _cfg.TAMAGOTCHI_PACKAGE.exists())


def electron_dir() -> Path:
    """Primeiro diretório onde o pacote electron pode viver (monorepo pnpm)."""
    for c in (_cfg.AIRI_ROOT / "apps" / "stage-tamagotchi" / "node_modules" / "electron",
              _cfg.AIRI_ROOT / "node_modules" / "electron"):
        if c.exists():
            return c
    return _cfg.AIRI_ROOT / "node_modules" / "electron"


def electron_binary_ready() -> bool:
    """True se o binário do Electron (path.txt) já está presente/baixado.

    O pnpm v10 costuma PULAR o postinstall do Electron, então sem esse passo o
    electron-vite falha com 'Electron uninstall'. Ver https://github.com/electron/electron
    """
    ed = electron_dir()
    return (ed / "path.txt").exists() or (ed / "dist" / "electron.exe").exists()
