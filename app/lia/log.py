"""
lia/log.py — Logger estruturado da Lia.

Permite registrar mensagens com uma Categoria (ex.: VOZ, SOVITS, AIRI, WAIFU,
MODELO, SISTEMA) e gravar simultaneamente:
  - na saída padrão (console do processo);
  - em arquivo (logs/lia-<data>.log), sempre ativo, para depuração sem a interface.

Também oferece um helper `categorize(texto)` para inferir a categoria a partir do
prefixo tipográfico usado nas mensagens (ex.: "[VOZ] ..."), mantendo compatibilidade
com os logs legados da interface.
"""

import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from . import config as _cfg

# Mapa de prefixo textual -> categoria lógica.
_PREFIX_MAP = [
    ("[VOZ", "voice"),
    ("[VOICE", "voice"),
    ("[TTS", "voice"),
    ("[AUDIO", "voice"),
    ("[SOVITS", "sovits"),
    ("[MODEL", "model"),
    ("[MODELO", "model"),
    ("[AIRI", "airi"),
    ("[AIRA", "airi"),
    ("[WAIFU", "waifu"),
    ("[WEB", "system"),
    ("[TAMA", "system"),
    ("[NET", "system"),
    ("[SYSTEM", "system"),
    ("[SERV", "system"),
    ("[TUNNEL", "system"),
    ("[APP", "system"),
]

_lock = threading.Lock()


def categorize(text: str) -> str:
    """Infere a categoria a partir do prefixo textual (ex.: '[VOZ] ...' -> 'voice')."""
    t = (text or "").upper()
    for prefix, cat in _PREFIX_MAP:
        if prefix in t:
            return cat
    return "general"


class Logger:
    """Logger por categoria com escrita em stdout e arquivo rotacionado por dia."""

    def __init__(self, log_dir: Path | None = None, enabled: bool = True):
        self.log_dir = log_dir or _cfg.LOGS_DIR
        self.enabled = enabled
        self._fh = None
        self._ensure_file()

    # -- arquivo --------------------------------------------------
    def _ensure_file(self) -> None:
        """(Re)abre o arquivo de log do dia. Thread-safe e idempotente."""
        if not self.enabled:
            return
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            name = datetime.now().strftime("lia-%Y-%m-%d.log")
            path = self.log_dir / name
            if self._fh is not None and getattr(self._fh, "name", None) != str(path):
                self._fh.close()
                self._fh = None
            if self._fh is None:
                self._fh = open(path, "a", encoding="utf-8")
        except Exception:
            self._fh = None

    def _ts(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def write(self, text: str, category: str | None = None) -> None:
        """Grava uma linha (sem advinhar categoria se já fornecida)."""
        cat = category or categorize(text)
        line = f"[{cat.upper()}] {text}"

        with _lock:
            # stdout (quando não é interface gráfica que já captura)
            if not os.environ.get("LIA_GUI_CAPTURES_STDOUT"):
                try:
                    print(line, file=sys.stdout, flush=True)
                except Exception:
                    pass

            if self.enabled:
                self._ensure_file()
                if self._fh:
                    try:
                        self._fh.write(f"{self._ts()}  {line}\n")
                        self._fh.flush()
                    except Exception:
                        pass

    def debug(self, text: str, category: str | None = None) -> None:
        self.write(f"[DBG] {text}", category)

    def info(self, text: str, category: str | None = None) -> None:
        self.write(f"[INFO] {text}", category)

    def warn(self, text: str, category: str | None = None) -> None:
        self.write(f"[WARN] {text}", category)

    def error(self, text: str, category: str | None = None) -> None:
        self.write(f"[ERRO] {text}", category)

    def close(self) -> None:
        if self._fh:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None


# Instância única por processo (singleton leve).
_logger: Logger | None = None


def get() -> Logger:
    """Retorna o logger singleton do processo."""
    global _logger
    if _logger is None:
        _logger = Logger()
    return _logger


def write(text: str, category: str | None = None) -> None:
    """Atalho para gravar no logger singleton."""
    get().write(text, category)
