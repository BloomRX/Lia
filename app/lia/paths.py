"""
lia/paths.py — Auxiliares de caminho do projeto Lia.

Funções pequenas e testáveis para resolver caminhos de diretórios de dados
(dados de voz, modelos SoVITS, instalado do AIRI). Evita repetir Path(...)
espalhado pelo código.
"""

from pathlib import Path

from . import config as _cfg


def data_dir() -> Path:
    """Diretório de dados do usuário na raiz (kokoro-data, sovits-data)."""
    return _cfg.ROOT


def kokoro_dir() -> Path:
    """Onde o kit Kokoro (venv + modelos onnx) fica instalado."""
    return _cfg.KOKORO_DATA


def sovits_dir() -> Path:
    """Onde os modelos SoVITS ficam (sovits-data)."""
    return _cfg.SOVITS_DATA


def airi_dir() -> Path:
    """Diretório clonado do Project AIRI (gerado pelo installer.py)."""
    return _cfg.ROOT / "airi"


def logs_dir() -> Path:
    """Diretório de logs do processo."""
    return _cfg.LOGS_DIR


def assets() -> Path:
    """Diretório de assets do app (ícones, splash, etc.)."""
    return _cfg.ASSETS_DIR


def voz_config() -> Path:
    """Caminho do config de voz."""
    return _cfg.voz_config_path()


def list_voz_models() -> list[Path]:
    """Lista os modelos SoVITS presentes em sovits_data/<nome>/."""
    base = sovits_dir()
    if not base.exists():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and (p / "config.json").exists())
