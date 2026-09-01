"""
lia/config.py — Constantes do projeto Lia.

Centraliza os valores que antes estavam espalhados no topo de `lia_app.py`:
caminhos raiz, portas, nomes de arquivos, paletas de cor, resoluções e chaves
de i18n. Fonte de verdade única para o restante do código.
"""

from pathlib import Path

# ---------------------------------------------------------------
# Identidade do app
# ---------------------------------------------------------------
APP_NAME = "Lia"
APP_VERSION = "v58"

# ---------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------
# Este arquivo vive em app/lia/config.py; a raiz do projeto é três níveis acima.
ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
VOICE_SCRIPT = SCRIPTS / "servidor_voz_airi.js"
ASSETS_DIR = ROOT / "app" / "assets"

FLAG_FILE = ROOT / ".lia_app_configurado"

# Diretórios de dados do usuário (fora do git via .gitignore)
KOKORO_DATA = ROOT / "kokoro-data"
SOVITS_DATA = ROOT / "sovits-data"
LOGS_DIR = ROOT / "logs"

# ---------------------------------------------------------------
# Portas
# ---------------------------------------------------------------
VOICE_PORT = 9860      # servidor_voz_airi.js
AIRI_PORT = 5173       # stage-web (Vite default)
CDP_PORT = 9222        # remote-debugging do Electron (tamagotchi)
SOVITS_PORT = 9880     # API do servidor SoVITS
SOVITS_WEBUI_PORT = 9874

# ---------------------------------------------------------------
# Paletas de cor
# ---------------------------------------------------------------
# Paleta padrão da Lia verdadeira: vinho (roupa), preto carvão (casaco),
# branco (camisa), rosa-avermelhado (cabelo), magenta (olhos), violeta (detalhe).
PALETTES = {
    "Lia": {"bg": "#1a1114", "panel": "#241419", "head": "#12100f", "console": "#171113",
            "accent": "#c22a5a", "accent2": "#7a3cff", "line": "#3a1f28",
            "vinho": "#7b1e3a", "cabelo": "#c9407a", "magenta": "#e011a7", "branco": "#f4eef4"},
    # Pretos/cinzas
    "Mono": {"bg": "#0f0f12", "panel": "#1a1a20", "head": "#0a0a0c", "console": "#121216",
             "accent": "#9ca3af", "accent2": "#d1d5db", "line": "#2a2a31"},
    # Brancos/vermelhos
    "Crimson": {"bg": "#1a0d0d", "panel": "#261313", "head": "#140a0a", "console": "#1c1010",
                "accent": "#dc2626", "accent2": "#f87171", "line": "#3d1a1a"},
}

# Rótulos amigáveis (PT) exibidos no combo de paleta; as chaves internas ficam estáveis.
PALETTE_LABELS = {"Lia": "🌸 Lia", "Mono": "⬛ Preto/Cinza", "Crimson": "🔴 Branco/Vermelho"}
PALETTE_LABEL_BY_KEY = {v: k for k, v in PALETTE_LABELS.items()}

# ---------------------------------------------------------------
# Resoluções fixas (pequeno / médio / grande) — evita desalinhamento no resize.
# ---------------------------------------------------------------
SIZES = {
    "Pequeno": "880x580",
    "Medio": "1120x740",
    "Grande": "1360x880",
}
SIZE_DEFAULT = "Medio"

# ---------------------------------------------------------------
# i18n (pt-BR / en)
# ---------------------------------------------------------------
LANGS = [("pt", "🇧🇷 Português"), ("en", "🇺🇸 English")]
LANG_KEYS = dict(LANGS)


def prefs_path() -> Path:
    """Caminho do arquivo de preferências do app."""
    return ROOT / "app_prefs.json"


def voz_config_path() -> Path:
    """Caminho do config de voz (engine/voz/pitch/velocidade)."""
    return ROOT / "voz_config.json"
