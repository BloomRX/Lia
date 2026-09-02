"""
lia/airi/install.py — Download/instalação do Project AIRI.

O AIRI (stage-web / stage-tamagotchi) precisa estar clonado em `ROOT/airi`
com as dependências (pnpm) instaladas. Se o usuário não o baixou (ex.: veio de
um clone sem o subdiretório `airi/`), o "Iniciar Waifu" dispara o clone + pnpm
automaticamente — igual ao fluxo do `app/installer.py`.

Mantém-se livre de GUI: recebe um `callback` (opcional) de log, para o Lia App
mostrar o progresso no console.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from .. import log as _log
from . import config as _cfg

AIRI_URL = "https://github.com/moeru-ai/airi.git"

# Sinais de que o AIRI está instalado (package.json na raiz do clone).
def airi_dir():
    """Diretório onde o Airi deve estar (ROOT/airi)."""
    return _cfg.AIRI_ROOT


def airi_installed() -> bool:
    """True se o AIRI foi clonado (package.json presente)."""
    return (airi_dir() / "package.json").exists()


def is_git_available() -> bool:
    """Verifica se o `git` está no PATH (necessário para clonar)."""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def pnpm_cmd() -> Optional[str]:
    """Encontra o executável do pnpm (que no Windows é um shim .cmd).

    Chamar ``["pnpm", "install"]`` via ``subprocess`` no Windows falha com
    ``[WinError 2]`` porque o pnpm é um ``pnpm.cmd``/``pnpm.ps1`` — o
    ``CreateProcess`` não resolve a extensão sozinho. Devolvemos o caminho
    completo do shim para poder rodá-lo direto.
    """
    # 1) Tenta resolver pelo PATH (shutil.which acha o .cmd/.exe do pnpm).
    for cand in ("pnpm", "pnpm.cmd", "pnpm.exe", "pnpm.ps1"):
        p = shutil.which(cand)
        if p and p.lower().endswith((".cmd", ".exe", ".ps1")):
            return p
    # 2) Procura em locais típicos do pnpm instalado globalmente (npm/corepack).
    appdata = os.environ.get("APPDATA", "")
    local = os.environ.get("LOCALAPPDATA", "")
    bases = [
        Path(appdata) / "npm",                 # shim do npm install -g pnpm
        Path(local) / "pnpm",                  # instalador standalone
        Path(local) / "Programs" / "pnpm",
    ]
    for base in bases:
        for cand in ("pnpm.cmd", "pnpm.exe", "pnpm"):
            p = base / cand
            if p.exists():
                return str(p)
    return None


def _run(cmd, cwd=None, timeout: int = 3600):
    """Roda um comando e devolve o CompletedProcess.

    No Windows usa CREATE_NO_WINDOW para não abrir um console à toa.
    """
    kwargs = {"capture_output": True, "text": True, "timeout": timeout, "cwd": cwd}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000
    return subprocess.run(cmd, **kwargs)


def ensure_airi(callback: Optional[Callable[[str], None]] = None) -> bool:
    """Garante que o AIRI esteja clonado + dependências instaladas.

    Args:
        callback: função `fn(msg)` para logar progresso (pode ser um
            `self.after(0, ...)` do Lia App). Se None, loga só no logger.

    Returns:
        True se o AIRI está pronto para rodar; False em erro (git ausente,
        clone falhou, etc.).
    """
    def _emit(msg: str):
        if callback:
            try:
                callback(msg)
            except Exception:
                pass
        _log.write(msg)

    if airi_installed():
        _emit(f"[AIRI] Já instalado em {airi_dir()}")
        return True

    if not is_git_available():
        _emit("[ERRO] Git não encontrado. Instale o Git: https://git-scm.com/download/win")
        return False

    _emit("[AIRI] AIRI não encontrado. Baixando (1ª vez - pode demorar alguns minutos)...")
    try:
        airi_dir().parent.mkdir(parents=True, exist_ok=True)
        r = _run(["git", "clone", AIRI_URL, str(airi_dir())])
        if r.returncode != 0:
            _emit("[ERRO] Falha ao clonar o AIRI:\n" + (r.stderr or r.stdout).strip()[-600:])
            return False
        _emit("[AIRI] ✅ AIRI clonado em " + str(airi_dir()))
    except subprocess.TimeoutExpired:
        _emit("[ERRO] Timeout ao clonar o AIRI.")
        return False
    except Exception as e:
        _emit("[ERRO] Exceção ao clonar o AIRI: " + str(e))
        return False

    # Instala as dependências (pnpm). Pode demorar e pode exigir node/pnpm
    # corretos (ver .tool-versions do repo).
    pm = pnpm_cmd()
    if not pm:
        _emit("[ERRO] pnpm não encontrado. Instale com: npm install -g pnpm")
        return False
    _emit("[AIRI] Instalando dependências (pnpm install - pode demorar)...")
    try:
        r = _run([pm, "install"], cwd=str(airi_dir()))
        if r.returncode != 0:
            _emit("[AVISO] pnpm install retornou código " + str(r.returncode))
            _emit("[AVISO] Se der erro de versão, rode manualmente em " + str(airi_dir()))
        else:
            _emit("[AIRI] ✅ Dependências instaladas!")
    except subprocess.TimeoutExpired:
        _emit("[AVISO] Timeout no pnpm install (pode ter ficado incompleto).")
    except Exception as e:
        _emit("[AVISO] Exceção no pnpm install: " + str(e))

    return airi_installed()
