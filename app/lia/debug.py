"""
lia/debug.py — Contexto de depuração do processo Lia.

Coleta o estado relevante do processo (config, versões, processos, arquivos de
log) e gera um artefato .zip em logs/debug-<data>.zip — útil para reportar
problemas sem depender da interface gráfica.
"""

import json
import os
import platform
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from . import config as _cfg
from . import log as _log


def _safe_json(obj) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    except Exception as e:  # noqa: BLE001
        return f"(erro ao serializar: {e})"


def collect_context() -> dict:
    """Monta um dicionário com o estado do processo (sem lançar exceções)."""
    ctx = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "app": {"nome": _cfg.APP_NAME, "versao": _cfg.APP_VERSION},
        "plataforma": {
            "python": sys.version,
            "os": platform.platform(),
            "machine": platform.machine(),
            "cwd": str(Path.cwd()),
        },
        "config": {
            "ROOT": str(_cfg.ROOT),
            "portas": {
                "voz": _cfg.VOICE_PORT,
                "airi": _cfg.AIRI_PORT,
                "cdp": _cfg.CDP_PORT,
                "sovits": _cfg.SOVITS_PORT,
                "sovits_webui": _cfg.SOVITS_WEBUI_PORT,
            },
            "prefs_path": str(_cfg.prefs_path()),
            "voz_config_path": str(_cfg.voz_config_path()),
        },
        "env": {
            k: v for k, v in os.environ.items()
            if k.upper().startswith(("LIA_", "AIRI_", "PYTHON"))
        },
        "versoes_node": {},
    }

    # tenta detectar node/pnpm apenas se existirem (não bloqueia a depuração)
    for cmd in (["node", "--version"], ["pnpm", "--version"], ["npm", "--version"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            ctx["versoes_node"][" ".join(cmd)] = (out.stdout or out.stderr).strip()
        except Exception:  # noqa: BLE001
            ctx["versoes_node"][" ".join(cmd)] = "(não disponível)"

    return ctx


def write_dump(pad: dict | None = None) -> Path | None:
    """
    Gera logs/debug-<data>.zip com: contexto (json), log do dia e o pad recebido.
    Retorna o caminho do zip (ou None em caso de erro).
    """
    try:
        _cfg.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        zip_path = _cfg.LOGS_DIR / f"debug-{stamp}.zip"
        context = collect_context()
        if pad:
            context["pad"] = pad

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("contexto.json", _safe_json(context))

            # inclui o log do dia, se existir
            log_file = _cfg.LOGS_DIR / datetime.now().strftime("lia-%Y-%m-%d.log")
            if log_file.exists():
                try:
                    zf.write(log_file, arcname=log_file.name)
                except Exception:  # noqa: BLE001
                    pass

        return zip_path
    except Exception as e:  # noqa: BLE001
        _log.write(f"[DEBUG] Falha ao gerar dump: {e}")
        return None
