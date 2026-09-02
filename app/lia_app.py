# ============================================================
#  Lia App - Painel da Waifu (Desktop)  v57
#  Tudo integrado: dependências, servidor de voz, configuração.
# ============================================================
import customtkinter as ctk
from tkinter import messagebox, filedialog
import subprocess
import threading
import json
import os
import sys
import re
import urllib.request
import urllib.error
import io
import shutil
import socket
import ctypes
import time
from pathlib import Path

# ── Infraestrutura modular (config, logs, depuração) ──
# A lógica de negócio/especificação foi movida para o pacote app/lia/ para
# não poluir o entry point e permitir depuração do processo.
from lia import config as _cfg
from lia import log as _logmod
from lia import debug as _dbg
from lia import paths as _paths
from lia import airi as _airi

# Mantém compatibilidade: essas constantes continuam disponíveis no escopo do
# módulo (usadas em todo o arquivo), mas agora vêm da fonte de verdade _cfg.
APP_NAME = _cfg.APP_NAME
APP_VERSION = _cfg.APP_VERSION
ROOT = _cfg.ROOT
SCRIPTS = _cfg.SCRIPTS
VOICE_SCRIPT = _cfg.VOICE_SCRIPT
VOICE_PORT = _cfg.VOICE_PORT
AIRI_PORT = _cfg.AIRI_PORT
CDP_PORT = _cfg.CDP_PORT
SOVITS_PORT = _cfg.SOVITS_PORT
SOVITS_WEBUI_PORT = _cfg.SOVITS_WEBUI_PORT
FLAG_FILE = _cfg.FLAG_FILE
ASSETS_DIR = _cfg.ASSETS_DIR
PALETTES = _cfg.PALETTES
PALETTE_LABELS = _cfg.PALETTE_LABELS
PALETTE_LABEL_BY_KEY = _cfg.PALETTE_LABEL_BY_KEY
SIZES = _cfg.SIZES
SIZE_DEFAULT = _cfg.SIZE_DEFAULT
LANGS = _cfg.LANGS
LANG_KEYS = _cfg.LANG_KEYS

# Logger de arquivo/console (usado fora da GUI e dentro do método _log da classe).
_file_logger = _logmod.get()

# ── Single instance check (Windows mutex) ──
_lock_server = None

def _check_single_instance():
    """Use Windows mutex to prevent multiple instances."""
    global _lock_server
    try:
        mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "LiaAppMutex")
        error = ctypes.windll.kernel32.GetLastError()
        ERROR_ALREADY_EXISTS = 183
        if error == ERROR_ALREADY_EXISTS:
            ctypes.windll.kernel32.CloseHandle(mutex)
            return False
        _lock_server = mutex  # Keep handle alive
        return True
    except Exception:
        # Fallback: try socket-based lock
        import socket
        try:
            _lock_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _lock_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            _lock_server.bind(('127.0.0.1', 19876))
            _lock_server.listen(1)
            _lock_server.settimeout(0)
            return True
        except OSError:
            return False

def _bring_window_to_front():
    """Bring existing Lia App window to front."""
    try:
        user32 = ctypes.windll.user32
        # Try to find by class name or partial title
        EnumWindows = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        found_hwnd = [None]
        
        def _enum_callback(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if "Lia App" in buf.value:
                    found_hwnd[0] = hwnd
                    return False  # Stop enumeration
            return True
        
        EnumWindows(EnumWindowsProc(_enum_callback), 0)
        if found_hwnd[0]:
            user32.ShowWindow(found_hwnd[0], 9)  # SW_RESTORE
            user32.SetForegroundWindow(found_hwnd[0])
    except Exception:
        pass

# Audio playback
try:
    import pygame
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
    HAS_PYGAME = True
except:
    HAS_PYGAME = False

# ============================================================
# Config
# ============================================================
# (Valores de ROOT/portas/FLAG_FILE agora vêm de lia.config no topo do arquivo.)


def _stem_model_name(stem):
    """Extrai o base name de um arquivo de peso (ex: 'lia_e8_s1920' ou 'lia-e20' -> 'lia')."""
    m = re.match(r"(.+?)[_-]e\d+", stem)
    return m.group(1) if m else stem


# ============================================================
# i18n (pt-BR / en) — termos "multilíngues" (Waifu, Online, Network,
# SoVITS, Engine, Tamagotchi, Kokoro) ficam iguais nos dois idiomas.
# ============================================================
# (LANGS / LANG_KEYS agora vêm de lia.config no topo do arquivo.)

L10N = {
    "pt": {
        "mode_idle": "IDENTE", "mode_training": "⛔ TREINANDO", "mode_waifu": "▲ WAIFU ATIVA",
        "status_voz": "Voz", "status_web": "Web", "status_sovits": "SoVITS", "status_tama": "Tamagotchi",
        "cta_start": "🚀 INICIAR WAIFU", "cta_training": "⛔ Treinando…",
        "menu_injetar": "🔗 Injetar URL", "menu_diag": "🔍 Diagnosticar", "menu_config": "⚙ Configurar",
        "menu_sovits": "🎤 Painel SoVITS", "menu_voice": "🎙️ Ajustar Voz",
        "rail_home": "Início", "rail_sovits": "SoVITS", "rail_voice": "Voz", "rail_options": "Opções",
        "stage_title": "Lia está aqui", "stage_wait": "SUA WAIFU AGUARDA",
        "console_label": "LOG CONSOLE", "tab_general": "General", "tab_voice": "Voice", "tab_system": "System",
        "loading_wait": "Preparando seu modelo...",
        "stage_hint": "Clique na Waifu para escolher o modelo",
        "stage_hint2": "Escolha a voz e pressione INICIAR WAIFU para conversar",
        "console": "📋 Console", "console_clear": "🗑️", "console_hide": "🙈",
        "voice_title": "🎙️ Ajustar Voz", "voice_engine": "Engine:", "voice_voice": "Voz:",
        "voice_pitch": "Pitch:", "voice_speed": "Velocidade:", "voice_install_kokoro": "🦉 Instalar Kokoro",
        "voice_test": "🔊 Testar voz", "voice_save": "💾 Salvar", "voice_start": "▶ Iniciar voz", "voice_stop": "⏹ Parar voz",
        "sovits_title": "🎤 Painel SoVITS", "sovits_hint": "Treinamento avançado de voz (clonagem).",
        "sovits_install": "📦 Instalar Servidor", "sovits_start": "▶ Rodar Servidor", "sovits_stop": "⏹ Parar Servidor",
        "sovits_import": "📤 Importar Modelo", "sovits_train": "🔥 Treinar Local", "sovits_delete": "🗑️ Deletar Modelo",
        "sovits_training": "🔥 Treinando", "sovits_none": "Nenhum modelo treinando",
        "sovits_fechar": "✕ Fechar",
        "model_title": "Escolher modelo da Waifu",
        "model_placeholder": "Nenhum modelo de personagem instalado",
        "lang_label": "🌐 Idioma:", "palette": "🎨 Paleta:", "size_label": "📐 Tamanho:",
        "pronto": "Pronto", "loading": "Carregando", "off": "Off",
        "rodando": "Rodando", "instalado": "Instalado", "nao_instalado": "Não instalado",
        "aba": "Web", "online": "Online",
    },
    "en": {
        "mode_idle": "IDLE", "mode_training": "⛔ TRAINING", "mode_waifu": "▲ WAIFU ACTIVE",
        "status_voz": "Voice", "status_web": "Web", "status_sovits": "SoVITS", "status_tama": "Tamagotchi",
        "cta_start": "🚀 START WAIFU", "cta_training": "⛔ Training…",
        "menu_injetar": "🔗 Inject URL", "menu_diag": "🔍 Diagnose", "menu_config": "⚙ Configure",
        "menu_sovits": "🎤 SoVITS Panel", "menu_voice": "🎙️ Adjust Voice",
        "rail_home": "Home", "rail_sovits": "SoVITS", "rail_voice": "Voice", "rail_options": "Options",
        "stage_title": "Lia is here", "stage_wait": "YOUR WAIFU AWAITS",
        "console_label": "LOG CONSOLE", "tab_general": "General", "tab_voice": "Voice", "tab_system": "System",
        "loading_wait": "Preparing your model...",
        "stage_hint": "Click the Waifu to choose a model",
        "stage_hint2": "Pick a voice and press START WAIFU to talk",
        "console": "📋 Console", "console_clear": "🗑️", "console_hide": "🙈",
        "voice_title": "🎙️ Adjust Voice", "voice_engine": "Engine:", "voice_voice": "Voice:",
        "voice_pitch": "Pitch:", "voice_speed": "Speed:", "voice_install_kokoro": "🦉 Install Kokoro",
        "voice_test": "🔊 Test voice", "voice_save": "💾 Save", "voice_start": "▶ Start voice", "voice_stop": "⏹ Stop voice",
        "sovits_title": "🎤 SoVITS Panel", "sovits_hint": "Advanced voice (clone) training.",
        "sovits_install": "📦 Install Server", "sovits_start": "▶ Start Server", "sovits_stop": "⏹ Stop Server",
        "sovits_import": "📤 Import Model", "sovits_train": "🔥 Train Local", "sovits_delete": "🗑️ Delete Model",
        "sovits_training": "🔥 Training", "sovits_none": "No model training",
        "sovits_fechar": "✕ Close",
        "model_title": "Choose Waifu model",
        "model_placeholder": "No character model installed",
        "lang_label": "🌐 Language:", "palette": "🎨 Palette:", "size_label": "📐 Size:",
        "pronto": "Ready", "loading": "Loading", "off": "Off",
        "rodando": "Running", "instalado": "Installed", "nao_instalado": "Not installed",
        "aba": "Web", "online": "Online",
    },
}

# Paletas/tamanhos/id do app vêm de lia.config (topo do arquivo).

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ============================================================
# Dependências
# ============================================================
def garantir_node_modules(callback=None):
    nm = ROOT / "node_modules"
    if (nm / "msedge-tts").exists():
        if callback: callback("[OK] node_modules já instalado")
        return True
    if callback: callback("[INFO] Instalando dependências Node.js (msedge-tts)...")
    npm_cmd = None
    for candidate in ["npm", "npm.cmd"]:
        try:
            proc = subprocess.run([candidate, "--version"], capture_output=True, text=True, creationflags=0x08000000)
            if proc.returncode == 0: npm_cmd = candidate; break
        except: pass
    if not npm_cmd:
        appdata = os.environ.get("APPDATA", "")
        local = os.environ.get("LOCALAPPDATA", "")
        for c in [Path(appdata)/"npm"/"npm.cmd", Path(local)/"Programs"/"node"/"npm.cmd",
                   Path("C:/Program Files/nodejs/npm.cmd"), Path("C:/Program Files (x86)/nodejs/npm.cmd")]:
            if c.exists(): npm_cmd = str(c); break
    if not npm_cmd:
        if callback: callback("[ERRO] npm não encontrado! Instale o Node.js: https://nodejs.org")
        return False
    try:
        proc = subprocess.run([npm_cmd, "install", "msedge-tts"], cwd=str(ROOT), capture_output=True, text=True, creationflags=0x08000000)
        if proc.returncode == 0:
            if callback: callback("[OK] Dependências instaladas!")
            return True
        else:
            if callback: callback(f"[ERRO] {proc.stderr or proc.stdout}")
            return False
    except Exception as e:
        if callback: callback(f"[ERRO] {e}")
        return False

def criar_atalhos():
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    bat_path = ROOT / "waifu.bat"
    for destino in [desktop, start_menu]:
        if not destino.exists(): continue
        lnk = destino / "Lia App.lnk"
        try:
            cmd = f'''
            $ws = New-Object -ComObject WScript.Shell
            $sc = $ws.CreateShortcut("{lnk}")
            $sc.TargetPath = "{bat_path}"
            $sc.WorkingDirectory = "{ROOT}"
            $sc.Description = "Lia App - Painel da Waifu"
            $sc.Save()
            '''
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, creationflags=0x08000000)
        except: pass

def verificar_primeira_vez():
    if FLAG_FILE.exists(): return
    criar = messagebox.askyesno("🌸 Lia App - Primeira vez", "Deseja criar atalhos na Área de Trabalho e Menu Iniciar?")
    if criar:
        criar_atalhos()
        messagebox.showinfo("Pronto!", "Atalhos criados!")
    FLAG_FILE.write_text("ok")

# ============================================================
# Status checks
# ============================================================
def check_voice():
    try:
        r = urllib.request.urlopen(f"http://127.0.0.1:{VOICE_PORT}/health", timeout=2)
        d = json.loads(r.read())
        return {"up": True, "version": d.get("version", "?"), "engines": d.get("engines", [])}
    except: return {"up": False}

def check_aba():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{AIRI_PORT}", timeout=2)
        return {"up": True}
    except: return {"up": False}

def check_tamagotchi():
    airi_dir = ROOT / "airi"
    if (airi_dir / "package.json").exists(): return {"up": True}
    return {"up": False, "status": "not_installed"}

# ============================================================
# App
# ============================================================
class LiaApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.size_key = "Medio"
        self._surfaces = []      # frames de superfície a recolorear
        # ── i18n + tema (carregado antes da UI p/ aplicar tamanho/paleta) ──
        self.lang = "pt"
        self._i18n_widgets = {}  # key -> widget (Label/Button) a retraduzir
        self.palette = "Lia"
        self._load_prefs()
        self.geometry(SIZES.get(self.size_key, SIZES[SIZE_DEFAULT]))
        self.minsize(880, 580)
        self.resizable(False, False)  # tamanho fixo (resolução controlada)
        # ── Janela sem barras (borderless) + cantos arredondados ──
        #   overrideredirect(True) removeria a janela da barra de tarefas e quebraria
        #   a minimização; por isso usamos ctypes para tirar só a borda/caption.
        self._hwnd = None  # handle nativo p/ arrasto suave (SetWindowPos)
        self.after(120, self._make_borderless)
        # ── Identidade do app (nome/ícone no Windows) ──
        self._set_app_identity()
        self.voice_process = None
        self.other_process = None
        self.sovits_process = None
        self._child_pids = []  # PIDs de processos filhos pra cleanup
        self._last_audio_path = None  # Remember last audio selection directory
        self._training_procs = {}  # model_name -> Popen de treino ativo (pra não deletar em uso)
        self._waifu_busy = False    # True enquanto o fluxo de Iniciar Waifu roda (evita dupla subida)
        # ── Estado operacional (evita conflitos) ──
        #   idle      -> nada rodando, tudo liberado
        #   training  -> um treino ativo: recursos vão pro treino (bloqueia iniciar waifu/voz/servidores)
        #   waifu     -> Airi aberto (aba ou tamagotchi): não pode treinar, mas pode configurar túnel/opções
        self.mode = "idle"
        self._btn = {}  # key -> CTkButton (pra habilitar/desabilitar via gating)
        self._aba_up = False   # cache do status da aba (atualizado em background)
        self._tama_up = False  # cache do status do tamagotchi
        self._log_buf = []     # buffer de linhas do console (p/ filtro por abas)
        self._log_filter = "general"
        # ── Drawer OVERLAY (esq. → dir.): chip / mic / gear ──
        self.drawer_open = False
        self._drawer_mode = None
        self.voice_drawer_open = False
        self._voice_anim_job = None
        self._voice_pinned = False
        # ── Modelo de personagem (splash art / avatar) ──
        self._personagens = ["Lia", "Airi", "Neon"]
        self._personagem_atual = "Lia"
        self._build_ui()
        self._build_sovits_panel()
        self.after(500, verificar_primeira_vez)
        self.after(100, self._init_deps)
        self.after(600, self._atualizar_gating)
        self._refresh_status()
        self._refresh_training_status()
        
        # Cleanup ao fechar
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _make_borderless(self):
        """Remove a borda/barra de título nativa do Windows e arredonda os cantos (Win11)."""
        try:
            if sys.platform != "win32":
                return
            import ctypes as _c
            hwnd = _c.windll.user32.GetParent(self.winfo_id())
            self._hwnd = hwnd  # guarda p/ arrasto nativo (evita flicker/teleporte)
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            style = _c.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            style &= ~(WS_CAPTION | WS_THICKFRAME)
            _c.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style)
            # Cantos arredondados (Windows 11) via DWM
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            _c.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                                                   _c.byref(_c.c_int(DWMWCP_ROUND)), 4)
            _c.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0020)
        except Exception:
            pass

    def _set_app_identity(self):
        """Configura nome/ícone do processo no Windows (barra de tarefas / gerenciador)."""
        try:
            if sys.platform == "win32":
                import ctypes as _c
                _c.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
        except Exception:
            pass
        self._apply_window_icon()

    def _apply_window_icon(self):
        """Usa app/assets/icon.ico como ícone da janela. Se só houver icon.png,
        converte para .ico com Pillow (runtime) e aplica; senão tenta .ico diretamente."""
        try:
            ico = ASSETS_DIR / "icon.ico"
            png = ASSETS_DIR / "icon.png"
            if not ico.exists() and png.exists():
                try:
                    from PIL import Image
                    im = Image.open(png)
                    im.save(str(ico), format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
                except Exception:
                    ico = None
            if ico and ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

    def _init_deps(self):
        def _install():
            garantir_node_modules(lambda t: self.after(0, lambda: self._log(t)))
        threading.Thread(target=_install, daemon=True).start()

    # ------------------------------------------------------------------
    # i18n / tema
    # ------------------------------------------------------------------
    def _t(self, key):
        return L10N.get(self.lang, L10N["pt"]).get(key, key)

    def _reg(self, key, widget):
        self._i18n_widgets[key] = widget

    def _apply_lang(self):
        for key, w in self._i18n_widgets.items():
            try:
                w.configure(text=self._t(key))
            except Exception:
                pass
        # Abas do console refletem o idioma (mantendo o filtro atual)
        if hasattr(self, "_log_tabs"):
            self._log_tabs.configure(values=[self._t("tab_general"), self._t("tab_voice"), self._t("tab_system")])
            self._log_tabs.set(self._t("tab_" + getattr(self, "_log_filter", "general")))
        if self.mode:
            self._set_mode(self.mode)

    def _set_lang(self, code):
        if code in LANG_KEYS:
            self.lang = code
            self._save_prefs()
            self._apply_lang()

    def _load_prefs(self):
        try:
            f = ROOT / "app_prefs.json"
            if f.exists():
                d = json.loads(f.read_text(encoding="utf-8"))
                if d.get("lang") in LANG_KEYS:
                    self.lang = d["lang"]
                if d.get("palette") in PALETTES:
                    self.palette = d["palette"]
                if d.get("size") in SIZES:
                    self.size_key = d["size"]
        except Exception:
            pass

    def _save_prefs(self):
        try:
            (ROOT / "app_prefs.json").write_text(
                json.dumps({"lang": self.lang, "palette": self.palette, "size": self.size_key}),
                encoding="utf-8")
        except Exception:
            pass

    def _p(self, key):
        """Acessa uma cor da paleta com fallback (paletas como Mono/Crimson não têm chaves extras)."""
        p = PALETTES.get(self.palette, PALETTES["Lia"])
        return p.get(key, p.get("accent", "#c22a5a"))

    def _apply_palette(self, name):
        if name not in PALETTES:
            return
        self.palette = name
        p = PALETTES[name]
        for (w, role) in self._surfaces:
            try:
                w.configure(fg_color=p.get(role, p["bg"]))
            except Exception:
                pass
        if "waifu" in self._btn:
            self._btn["waifu"].configure(fg_color=p["accent"], hover_color=p["accent2"],
                                         border_color=self._p("magenta"))
        if hasattr(self, "_stage_wait_lbl"):
            self._stage_wait_lbl.configure(text_color=p["accent2"])
        if hasattr(self, "_spinner_lbl"):
            self._spinner_lbl.configure(text_color=p["accent2"])
        if hasattr(self, "_loading"):
            self._loading.configure(fg_color=p["bg"])

    def _set_palette(self, name):
        self.palette = name
        self._apply_palette(name)
        self._save_prefs()

    # ------------------------------------------------------------------
    # Painel de voz lateral (drawer vertical colapsável)
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # LEFT DRAWER (overlay esquerda → direita a partir dos ícones)
    # ------------------------------------------------------------------
    def _anim_drawer(self, target):
        """Anima o `x` do drawer (place). target=0 => aberto; target=-W => fora da tela."""
        if self._voice_anim_job:
            try:
                self.after_cancel(self._voice_anim_job)
            except Exception:
                self._voice_anim_job = None
        body = self.left_drawer
        try:
            cur = int(body.place_info().get("x", -self._DRAWER_W))
        except Exception:
            cur = -self._DRAWER_W
        dist = target - cur
        if dist == 0:
            body.place(relx=0.0, rely=0.0, x=target, y=64, anchor="nw")
            return
        steps = max(1, int(abs(dist) / 7))  # ~7px por passo => rápido
        step = dist / steps
        def _step(remaining):
            cur2 = int(body.place_info().get("x", -self._DRAWER_W))
            nx = cur2 + step
            if (step < 0 and nx < target) or (step > 0 and nx > target):
                nx = target
            body.place(relx=0.0, rely=0.0, x=int(nx), y=64, anchor="nw")
            if abs(nx - target) < 1 or remaining <= 1:
                body.place(relx=0.0, rely=0.0, x=int(target), y=64, anchor="nw")
                self._voice_anim_job = None
                return
            self._voice_anim_job = self.after(6, lambda: _step(remaining - 1))
        _step(steps)

    def _open_drawer(self, mode):
        """Abre o drawer (voice | options | model) deslizando da esquerda p/ a direita."""
        self.drawer_open = True
        self._drawer_mode = mode
        self._voice_pinned = False
        # Mostra o conteúdo correspondente
        self._show_drawer_content(mode)
        try:
            h = min(620, max(400, self.winfo_height() - 80))
            self.left_drawer.configure(height=h)
        except Exception:
            pass
        self.left_drawer.lift()
        self._anim_drawer(0)

    def _close_drawer(self):
        self.drawer_open = False
        self._anim_drawer(-self._DRAWER_W)

    def _show_drawer_content(self, mode):
        for name in ("voice", "options", "model"):
            getattr(self, f"_content_{name}").pack_forget()
        getattr(self, f"_content_{mode}").pack(fill="both", expand=True, padx=14, pady=(0, 12))
        title = {"voice": self._t("voice_title"), "options": self._t("rail_options"), "model": self._t("model_title")}
        try:
            self._drawer_title_lbl.configure(text=title.get(mode, ""))
        except Exception:
            pass

    def _abrir_voz(self):
        """Abre o drawer de VOZ pelo ícone do microfone."""
        self._open_drawer("voice")

    def _toggle_voice_drawer(self):
        if self.drawer_open and getattr(self, "_drawer_mode", "") == "voice":
            self._close_drawer()
        else:
            self._open_drawer("voice")

    def _toggle_options_menu(self):
        """Abre o drawer de OPÇÕES (idioma/tema/tamanho+ações) pela engrenagem."""
        if self.drawer_open and getattr(self, "_drawer_mode", "") == "options":
            self._close_drawer()
        else:
            self._open_drawer("options")

    def _open_model_selector(self):
        """Abre o drawer de PERSONAGEM (customizar a Lia) pelo chip / clique no palco."""
        if self.drawer_open and getattr(self, "_drawer_mode", "") == "model":
            self._close_drawer()
        else:
            self._open_drawer("model")

    def _build_ui(self):
        # ============================================================
        # HEADER / TITLE BAR (custom, draggable) — logo + status
        # ============================================================
        self._surfaces.clear()
        self._title_bar = ctk.CTkFrame(self, corner_radius=0, height=64, fg_color=PALETTES[self.palette]["head"])
        self._title_bar.pack(fill="x", padx=0, pady=0)
        self._title_bar.pack_propagate(False)
        self._surfaces.append((self._title_bar, "head"))
        self._title_bar.bind("<Button-1>", self._drag_start)
        self._title_bar.bind("<B1-Motion>", self._drag_move)

        logo_frame = ctk.CTkFrame(self._title_bar, fg_color="transparent")
        logo_frame.pack(side="left", padx=(16, 10), pady=0)
        logo_frame.bind("<Button-1>", self._drag_start)
        logo_frame.bind("<B1-Motion>", self._drag_move)
        self._logo_lbl = ctk.CTkLabel(logo_frame, text="🌸 " + APP_NAME, font=("", 21, "bold"), text_color="#f5f5f5")
        self._logo_lbl.pack(side="left")
        self._version_lbl = ctk.CTkLabel(logo_frame, text=" " + APP_VERSION, font=("", 11), text_color="#9ca3af")
        self._version_lbl.pack(side="left", padx=(2, 0))

        # Janela (minimizar / fechar) — barra custom
        win_controls = ctk.CTkFrame(self._title_bar, fg_color="transparent")
        win_controls.pack(side="right", padx=(4, 8))
        self._btn_min = ctk.CTkButton(win_controls, text="—", command=self._minimize_win, width=36, height=34,
                                       font=("", 16, "bold"), fg_color="transparent", hover_color="#27272e",
                                       text_color="#9ca3af")
        self._btn_min.pack(side="left", padx=1)
        self._btn_close = ctk.CTkButton(win_controls, text="✕", command=self._on_close, width=36, height=34,
                                        font=("", 16, "bold"), fg_color="transparent", hover_color="#7f1d1d",
                                        text_color="#9ca3af")
        self._btn_close.pack(side="left", padx=1)

        # LED status cards (header — única fonte de status)
        self.mode_badge = ctk.CTkLabel(self._title_bar, text=self._t("mode_idle"), font=("", 12, "bold"),
                                       text_color="#e5e7eb", corner_radius=10, fg_color=PALETTES[self.palette]["panel"])
        self.mode_badge.pack(side="right", padx=(8, 14))
        status_cards = ctk.CTkFrame(self._title_bar, fg_color="transparent")
        status_cards.pack(side="right", padx=8)
        self.st_voice = self._make_status_card(status_cards, "icon-stat-voice", self._t("status_voz"), "off", key="status_voz")
        self.st_aba = self._make_status_card(status_cards, "icon-stat-web", self._t("status_web"), "off", key="status_web")
        self.st_sovits = self._make_status_card(status_cards, "icon-stat-sovits", self._t("status_sovits"), "off", key="status_sovits")
        self.st_tama = self._make_status_card(status_cards, "icon-stat-tama", self._t("status_tama"), "off", key="status_tama")

        # ============================================================
        # MAIN — legenda esq. (ícones) | centro (palco) | base (CTA + console)
        # ============================================================
        main = ctk.CTkFrame(self, fg_color=PALETTES[self.palette]["bg"])
        main.pack(fill="both", expand=True, padx=(0, 8), pady=(4, 4))
        self._surfaces.append((main, "bg"))

        # Linha superior: trilha de ícones (esq.) + palco (centro)
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.pack(side="top", fill="both", expand=True)
        self._surfaces.append((top, "bg"))

        # ---------- LEFT: trilha de ícones (encostada na borda esq.) ----------
        left = ctk.CTkFrame(top, width=104, corner_radius=0, fg_color=PALETTES[self.palette]["panel"])
        left.pack(side="left", fill="y", padx=(0, 6))
        left.pack_propagate(False)
        self._surfaces.append((left, "panel"))

        # Botões de ícone (imagens) — Home, Chip (personagem), Mic (voz), Gear (opções)
        self._icon_btns = []
        def _icon_btn(image, cmd, key):
            b = ctk.CTkButton(left, image=image, text="", command=cmd, width=54, height=54, corner_radius=12,
                              fg_color="transparent", hover_color=PALETTES[self.palette]["line"])
            b.pack(pady=6)
            if key:
                self._btn[key] = b
            self._icon_btns.append(b)
            return b

        home_img = self._load_icon("icon-home")
        chip_img = self._load_icon("icon-chip")
        mic_img = self._load_icon("icon-mic")
        gear_img = self._load_icon("icon-gear")

        self._icon_home = _icon_btn(home_img, self._resetar_palco, "rail_home")
        self._icon_chip = _icon_btn(chip_img, self._open_model_selector, "rail_chip")
        self._icon_mic = _icon_btn(mic_img, self._abrir_voz, "voice_rail")
        self._icon_gear = _icon_btn(gear_img, self._toggle_options_menu, "options")

        # Espaço inferior da trilha reservado para a identidade futura da empresa
        # (permanece vazio por ora — nada de logo/nome).
        ctk.CTkFrame(left, fg_color="transparent").pack(fill="both", expand=True)

        # ---------- CENTER: palco ----------
        center = ctk.CTkFrame(top, corner_radius=12, fg_color=PALETTES[self.palette]["bg"])
        center.pack(side="left", fill="both", expand=True, padx=0)
        self._surfaces.append((center, "bg"))

        # Palco com imagem de fundo (falsa impressão 3D) + arte da waifu
        stage_holder = ctk.CTkFrame(center, corner_radius=14, fg_color=PALETTES[self.palette]["panel"])
        stage_holder.pack(fill="both", expand=True, padx=(0, 4), pady=(0, 6))
        stage_holder.pack_propagate(False)
        self._surfaces.append((stage_holder, "panel"))

        bg = self._load_background()
        self.stage = ctk.CTkFrame(stage_holder, corner_radius=14, fg_color=PALETTES[self.palette]["bg"], cursor="hand2")
        self.stage.pack(fill="both", expand=True)
        self.stage.pack_propagate(False)
        self._surfaces.append((self.stage, "bg"))
        self.stage.bind("<Button-1>", lambda e: self._open_model_selector())

        # Imagem de fundo (background.png) cobrindo o palco (place)
        if bg is not None:
            self._stage_bg = ctk.CTkLabel(self.stage, image=bg, text="")
            self._stage_bg.place(relx=0.5, rely=0.5, anchor="center", relwidth=1.0, relheight=1.0)
            self._stage_bg.bind("<Button-1>", lambda e: self._open_model_selector())

        # Título "SUA WAIFU AGUARDA" no topo
        self._stage_wait_lbl = ctk.CTkLabel(self.stage, text=self._t("stage_wait"), font=("", 15, "bold"),
                                            text_color=PALETTES[self.palette]["accent2"])
        self._stage_wait_lbl.place(relx=0.5, rely=0.05, anchor="center")
        self._stage_wait_lbl.bind("<Button-1>", lambda e: self._open_model_selector())

        # Arte da waifu (splash) sobreposta ao fundo
        splash = self._load_splash()
        if splash is not None:
            self._stage_label = ctk.CTkLabel(self.stage, image=splash, text="")
        else:
            self._stage_label = ctk.CTkLabel(self.stage, text="🌸", font=("", 80))
        self._stage_label.place(relx=0.5, rely=0.5, anchor="center")
        self._stage_label.bind("<Button-1>", lambda e: self._open_model_selector())
        self._stage_label.lift()

        # Nome + dica (parte de baixo do palco)
        self.stage_title = ctk.CTkLabel(self.stage, text=f"{self._personagem_atual}", font=("", 18, "bold"), text_color="#f5f5f5")
        self.stage_title.place(relx=0.5, rely=0.88, anchor="center")
        self.stage_title.bind("<Button-1>", lambda e: self._open_model_selector())
        self.stage_hint = ctk.CTkLabel(self.stage, text=self._t("stage_hint"), font=("", 10), text_color="gray")
        self.stage_hint.place(relx=0.5, rely=0.94, anchor="center")
        self.stage_hint.bind("<Button-1>", lambda e: self._open_model_selector())

        # Overlay de LOADING (spinner) durante treino — sobreposto ao palco
        self._loading = ctk.CTkFrame(self.stage, fg_color=PALETTES[self.palette]["bg"], corner_radius=14)
        self._loading.pack_propagate(False)
        self._loading_lbl = ctk.CTkLabel(self._loading, text="TREINANDO", font=("", 14, "bold"),
                                         text_color="#fbbf24")
        self._loading_lbl.pack(pady=(0, 4))
        self._spinner_lbl = ctk.CTkLabel(self._loading, text="◐", font=("", 40, "bold"), text_color=PALETTES[self.palette]["accent2"])
        self._spinner_lbl.pack()
        self._loading_lbl2 = ctk.CTkLabel(self._loading, text="", font=("", 10), text_color="gray")
        self._loading_lbl2.pack(pady=(4, 0))
        self._loading.place_forget()

        # ---------- BOTTOM: INICIAR WAIFU + Console (nivelados, até a borda esq.) ----------
        bottom = ctk.CTkFrame(main, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=0, pady=(6, 0))

        # CTA (esquerda — encosta na borda esquerda da tela)
        cta_wrap = ctk.CTkFrame(bottom, width=300, fg_color=PALETTES[self.palette]["panel"], corner_radius=10)
        cta_wrap.pack(side="left", fill="both", padx=(0, 6))
        cta_wrap.pack_propagate(False)
        self._btn["waifu"] = ctk.CTkButton(
            cta_wrap, text=self._t("cta_start"), command=self._act_iniciar_waifu,
            font=("", 15, "bold"), corner_radius=8,
            fg_color=PALETTES[self.palette]["accent"], hover_color=PALETTES[self.palette]["accent2"],
            border_width=1, border_color=self._p("magenta"), text_color="#ffffff")
        self._btn["waifu"].pack(fill="both", expand=True, padx=3, pady=3)

        # Console (direita) — altura nivelada com o CTA
        self.console_frame = ctk.CTkFrame(bottom, fg_color=PALETTES[self.palette]["console"], corner_radius=10)
        self._surfaces.append((self.console_frame, "console"))
        self.console_frame.pack(side="left", fill="both", expand=True)
        self.console_frame.pack_propagate(False)
        self.console_frame.configure(height=170)
        console_header = ctk.CTkFrame(self.console_frame, fg_color="transparent", height=36)
        console_header.pack(fill="x", padx=10, pady=(8, 0))
        self._console_title_lbl = ctk.CTkLabel(console_header, text=self._t("console_label"), font=("", 12, "bold"),
                                               text_color=PALETTES[self.palette]["accent2"])
        self._console_title_lbl.pack(side="left")
        self._log_tabs = ctk.CTkSegmentedButton(console_header, values=[self._t("tab_general"), self._t("tab_voice"), self._t("tab_system")],
                                                command=self._on_log_tab, height=26, corner_radius=7,
                                                font=("", 10), fg_color="#26262e",
                                                selected_color=PALETTES[self.palette]["accent"],
                                                selected_hover_color=PALETTES[self.palette]["accent2"],
                                                unselected_color="#2a2a31", unselected_hover_color="#33333c")
        self._log_tabs.pack(side="left", padx=10)
        self._log_tabs.set(self._t("tab_general"))
        self._btn_hide_log = ctk.CTkButton(console_header, text=self._t("console_hide"), command=self._hide_console,
                                           width=34, height=26, font=("", 13), fg_color="transparent",
                                           hover_color="#26262e", text_color="#9ca3af")
        self._btn_hide_log.pack(side="right")
        self._btn_clear_log = ctk.CTkButton(console_header, text=self._t("console_clear"), command=self._clear_log,
                                            width=34, height=26, font=("", 13), fg_color="transparent",
                                            hover_color="#26262e", text_color="#f87171")
        self._btn_clear_log.pack(side="right")
        self.log_status_label = ctk.CTkLabel(console_header, text="⏸ " + self._t("pronto"), font=("", 11), text_color="#9ca3af")
        self.log_status_label.pack(side="right", padx=8)
        self.log_progress_label = ctk.CTkLabel(console_header, text="", font=("", 11), text_color="#9ca3af")
        self.log_progress_label.pack(side="right", padx=(0, 6))

        self.log_text = ctk.CTkTextbox(self.console_frame, font=("Consolas", 11), wrap="word", height=5)
        try:
            self.log_text.tag_configure("voice", foreground="#e011a7")
            self.log_text.tag_configure("system", foreground="#4ade80")
        except Exception:
            pass
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        self._console_state = "open"

        # ---------- Drawer-overlay esquerdo (chip / mic / gear) ----------
        self._build_left_drawer()

        # Estado inicial + paleta
        self._apply_palette(self.palette)

        # Registo i18n
        self._reg("cta_start", self._btn["waifu"])
        self._reg("stage_wait", self._stage_wait_lbl)
        self._reg("stage_hint", self.stage_hint)
        self._reg("console_label", self._console_title_lbl)
        self._reg("console_clear", self._btn_clear_log)
        self._reg("console_hide", self._btn_hide_log)


    def _build_left_drawer(self):
        """Drawer-overlay único na ESQUERDA (desliza da esquerda p/ a direita).
        Abre pelo Chip (modelo), Mic (voz) ou Gear (opções)."""
        self._DRAWER_W = 340
        self.left_drawer = ctk.CTkFrame(self, width=self._DRAWER_W, corner_radius=0,
                                        fg_color=PALETTES[self.palette]["panel"])
        self.left_drawer.pack_propagate(False)
        self._surfaces.append((self.left_drawer, "panel"))
        self.left_drawer.place(relx=0.0, rely=0.0, x=-self._DRAWER_W, y=64, anchor="nw")
        self.left_drawer.bind("<Leave>", lambda e: self.after(280, self._voice_maybe_collapse))

        # Cabeçalho do drawer (título + fechar)
        hdr = self._drawer_header = ctk.CTkFrame(self.left_drawer, fg_color="transparent", height=46)
        hdr.pack(fill="x", padx=16, pady=(14, 2))
        hdr.pack_propagate(False)
        self._drawer_title_lbl = ctk.CTkLabel(hdr, text="", font=("", 14, "bold"),
                                              text_color=PALETTES[self.palette]["accent2"], anchor="w")
        self._drawer_title_lbl.pack(side="left", fill="x", expand=True)

        # Conteúdos (um por modo)
        self._content_voice = ctk.CTkFrame(self.left_drawer, fg_color="transparent")
        self._content_options = ctk.CTkFrame(self.left_drawer, fg_color="transparent")
        self._content_model = ctk.CTkFrame(self.left_drawer, fg_color="transparent")

        self._build_voice_content(self._content_voice)
        self._build_options_content(self._content_options)
        self._build_model_content(self._content_model)

        self.drawer_open = False
        self.voice_drawer_body = self._content_voice  # alias p/ compatibilidade

    def _build_voice_content(self, content):
        """Conteúdo do drawer de VOZ (engine, voz, pitch, velocidade, iniciar/parar/testar)."""
        # Engine
        engine_frame = ctk.CTkFrame(content, fg_color="transparent")
        engine_frame.pack(fill="x", padx=2, pady=(4, 4))
        self._engine_lbl = ctk.CTkLabel(engine_frame, text=self._t("voice_engine"), font=("", 12, "bold"))
        self._engine_lbl.pack(anchor="w")
        self.engine_var = ctk.StringVar(value="edge")
        self.engine_combo = ctk.CTkComboBox(engine_frame, values=["edge", "kokoro", "sovits"],
                                            variable=self.engine_var, width=300, height=30,
                                            command=lambda _: self._update_voice_list())
        self.engine_combo.pack(pady=4)
        self.engine_combo.set("edge")

        # Kokoro install (só kokoro)
        self.kokoro_frame = ctk.CTkFrame(content, fg_color="transparent")
        self.kokoro_frame.pack(fill="x", padx=2, pady=4)
        self._kokoro_btn = ctk.CTkButton(self.kokoro_frame, text=self._t("voice_install_kokoro"), command=self._instalar_kokoro,
                                         width=150, fg_color="#6b21a8", hover_color="#7c3aed", height=30)
        self._kokoro_btn.pack(side="left")
        self.kokoro_status = ctk.CTkLabel(self.kokoro_frame, text="", font=("", 10), text_color="gray")
        self.kokoro_status.pack(side="left", padx=6)

        # Voz
        self._voice_lbl = ctk.CTkLabel(content, text=self._t("voice_voice"), font=("", 12, "bold"))
        self._voice_lbl.pack(anchor="w", padx=2, pady=(10, 2))
        self.voice_combo = ctk.CTkComboBox(content, values=["pt-BR-ThalitaNeural"], width=300, height=30)
        self.voice_combo.pack(padx=2, pady=2)
        self.voice_combo.set("pt-BR-ThalitaNeural")

        # Pitch
        self.pitch_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._pitch_lbl = ctk.CTkLabel(self.pitch_frame, text=self._t("voice_pitch"), font=("", 12, "bold"))
        self._pitch_lbl.pack(anchor="w", padx=2, pady=(8, 2))
        pitch_slider_row = ctk.CTkFrame(self.pitch_frame, fg_color="transparent")
        pitch_slider_row.pack(fill="x", padx=2)
        self.pitch_slider = ctk.CTkSlider(pitch_slider_row, from_=-50, to=50, number_of_steps=100, width=240)
        self.pitch_slider.pack(side="left")
        self.pitch_slider.set(0)
        self.pitch_label = ctk.CTkLabel(pitch_slider_row, text="0", font=("", 12), width=32)
        self.pitch_label.pack(side="left", padx=4)
        self.pitch_slider.configure(command=lambda v: self.pitch_label.configure(text=str(int(v))))

        # Velocidade
        self.speed_frame = ctk.CTkFrame(content, fg_color="transparent")
        self._speed_lbl = ctk.CTkLabel(self.speed_frame, text=self._t("voice_speed"), font=("", 12, "bold"))
        self._speed_lbl.pack(anchor="w", padx=2, pady=(8, 2))
        speed_slider_row = ctk.CTkFrame(self.speed_frame, fg_color="transparent")
        speed_slider_row.pack(fill="x", padx=2)
        self.speed_slider = ctk.CTkSlider(speed_slider_row, from_=0.5, to=2.0, number_of_steps=30, width=240)
        self.speed_slider.pack(side="left")
        self.speed_slider.set(1.0)
        self.speed_label = ctk.CTkLabel(speed_slider_row, text="1.0", font=("", 12), width=32)
        self.speed_label.pack(side="left", padx=4)
        self.speed_slider.configure(command=lambda v: self.speed_label.configure(text=f"{v:.1f}"))

        # Iniciar / Parar voz (testes / recuperação)
        srv_row = ctk.CTkFrame(content, fg_color="transparent")
        srv_row.pack(fill="x", padx=2, pady=(14, 4))
        self._btn["voz_on"] = ctk.CTkButton(srv_row, text=self._t("voice_start"), command=self._act_ligar_voz, width=145, height=32)
        self._btn["voz_on"].pack(side="left", padx=2)
        self._btn["voz_off"] = ctk.CTkButton(srv_row, text=self._t("voice_stop"), command=self._act_parar_voz, width=145, height=32,
                                             fg_color="#7f1d1d", hover_color="#991b1b")
        self._btn["voz_off"].pack(side="left", padx=2)

        # Testar / Salvar
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(fill="x", padx=2, pady=(8, 8))
        self._btn["test_voz"] = ctk.CTkButton(btn_frame, text=self._t("voice_test"), command=self._testar_voz, width=170, height=34)
        self._btn["test_voz"].pack(side="left", padx=3)
        self._btn["salvar"] = ctk.CTkButton(btn_frame, text=self._t("voice_save"), command=self._salvar_voz, width=110, height=34)
        self._btn["salvar"].pack(side="left", padx=3)

        self.voz_status = ctk.CTkLabel(content, text="...", font=("", 10), text_color="gray", wraplength=300)
        self.voz_status.pack(anchor="w", padx=2, pady=(0, 6))

        # Resumo de voz (engine/voz) — usado também por _atualizar_resumo_voz
        self.voz_summary = ctk.CTkLabel(content, text="", font=("", 10), text_color="gray",
                                        anchor="w", wraplength=300, justify="left")
        self.voz_summary.pack(anchor="w", padx=2, pady=(0, 4))
        self.sovits_status = ctk.CTkLabel(content, text="SoVITS: ...", font=("", 10), text_color="gray",
                                          anchor="w", wraplength=300, justify="left")
        self.sovits_status.pack(anchor="w", padx=2, pady=(0, 10))

        self._update_voice_list()

        self._reg("voice_engine", self._engine_lbl)
        self._reg("voice_voice", self._voice_lbl)
        self._reg("voice_pitch", self._pitch_lbl)
        self._reg("voice_speed", self._speed_lbl)
        self._reg("voice_install_kokoro", self._kokoro_btn)
        self._reg("voice_start", self._btn["voz_on"])
        self._reg("voice_stop", self._btn["voz_off"])
        self._reg("voice_test", self._btn["test_voz"])
        self._reg("voice_save", self._btn["salvar"])

    def _build_options_content(self, content):
        """Conteúdo do drawer de OPÇÕES (idioma / tema / tamanho + ações)."""
        self._lang_lbl = ctk.CTkLabel(content, text=self._t("lang_label"), font=("", 11, "bold"))
        self._lang_lbl.pack(anchor="w", pady=(6, 2))
        self.lang_combo = ctk.CTkComboBox(content, values=list(LANG_KEYS.values()), width=300, height=30,
                                          state="normal", command=self._on_lang_change)
        self.lang_combo.pack(fill="x", pady=(0, 8))
        self.lang_combo.set(LANG_KEYS[self.lang])

        self._palette_lbl = ctk.CTkLabel(content, text=self._t("palette"), font=("", 11, "bold"))
        self._palette_lbl.pack(anchor="w", pady=(6, 2))
        self.palette_combo = ctk.CTkComboBox(content, values=list(PALETTE_LABELS.values()), width=300, height=30,
                                             state="normal", command=self._on_palette_change)
        self.palette_combo.pack(fill="x", pady=(0, 8))
        self.palette_combo.set(PALETTE_LABELS.get(self.palette, self.palette))

        self._size_lbl = ctk.CTkLabel(content, text=self._t("size_label"), font=("", 11, "bold"))
        self._size_lbl.pack(anchor="w", pady=(6, 2))
        self.size_combo = ctk.CTkComboBox(content, values=list(SIZES.keys()), width=300, height=30,
                                          state="normal", command=self._on_size_change)
        self.size_combo.pack(fill="x", pady=(0, 8))
        self.size_combo.set(self.size_key)

        ctk.CTkFrame(content, height=1, fg_color=PALETTES[self.palette]["line"]).pack(fill="x", pady=8)
        # Ações de manutenção
        self._make_button(content, self._t("menu_injetar"), self._act_injetar_url, key="url", ikey="menu_injetar")
        self._make_button(content, self._t("menu_diag"), self._act_diagnosticar, key="diag", ikey="menu_diag")
        self._make_button(content, self._t("menu_config"), self._act_configurar, key="config", ikey="menu_config")
        self._make_button(content, self._t("menu_sovits"), self._show_sovits_panel, key="menu_sovits", ikey="menu_sovits")

        # Registro i18n das LABELS de configuração (os combos não têm `text`)
        self._reg("lang_label", self._lang_lbl)
        self._reg("palette", self._palette_lbl)
        self._reg("size_label", self._size_lbl)

    def _build_model_content(self, content):
        """Conteúdo do drawer de PERSONAGEM (customizar a Lia / escolher modelo)."""
        self._model_title_lbl = ctk.CTkLabel(content, text=self._t("model_title"), font=("", 12, "bold"),
                                             text_color=PALETTES[self.palette]["accent2"])
        self._model_title_lbl.pack(anchor="w", pady=(4, 8))
        self._reg("model_title", self._model_title_lbl)
        for nome in self._personagens:
            def _pick(n=nome):
                self._personagem_atual = n
                self.stage_title.configure(text=n)
                self._close_drawer()
                self._log(f"[MODEL] Personagem: {n}")
            ctk.CTkButton(content, text="🌸 " + nome, command=_pick, width=300, height=38,
                          fg_color=PALETTES[self.palette]["panel"], hover_color=PALETTES[self.palette]["line"]).pack(pady=4)
        ctk.CTkLabel(content, text=self._t("model_placeholder"), font=("", 11), text_color="gray").pack(pady=(12, 8))

    # --- Assets / helpers de imagem ---
    def _load_icon(self, name):
        """Carrega um ícone (assets/icon-<name>.png) como CTkImage (transparente)."""
        try:
            from PIL import Image
            f = ASSETS_DIR / f"{name}.png"
            if not f.exists():
                return None
            im = Image.open(f).convert("RGBA")
            photo = ctk.CTkImage(light_image=im, dark_image=im, size=(34, 34))
            return photo
        except Exception:
            return None

    def _load_background(self):
        """Carrega o fundo do palco (assets/background.png) esticado ao frame."""
        try:
            from PIL import Image
            f = ASSETS_DIR / "background.png"
            if not f.exists():
                return None
            im = Image.open(f).convert("RGB")
            # Mantém proporção larga; o place estica por relwidth/relheight
            photo = ctk.CTkImage(light_image=im, dark_image=im, size=(1200, 675))
            return photo
        except Exception:
            return None

    # --- Janela custom (drag / minimizar) ---
    def _drag_start(self, e):
        # Posição inicial da janela + coordenadas ABSOLUTAS do ponteiro.
        # Usamos x_root/y_root (não x/y relativos) para o arrasto não "derrapar"
        # nem teleportar o cursor para o canto da janela durante o movimento.
        self._win_x0 = self.winfo_x()
        self._win_y0 = self.winfo_y()
        self._drag_x_root = getattr(e, "x_root", e.x)
        self._drag_y_root = getattr(e, "y_root", e.y)

    def _drag_move(self, e):
        try:
            if self._hwnd and sys.platform == "win32":
                import ctypes as _c
                # MOVE NATIVO via SetWindowPos: NÃO refaz o layout dos widgets
                # place()/pack() (que é o que causava flicker/teleporte de elementos).
                dx = getattr(e, "x_root", self._win_x0) - self._drag_x_root
                dy = getattr(e, "y_root", self._win_y0) - self._drag_y_root
                x = int(self._win_x0 + dx)
                y = int(self._win_y0 + dy)
                # SWP_NOSIZE|SWP_NOZORDER|SWP_NOACTIVATE
                _c.windll.user32.SetWindowPos(self._hwnd, 0, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)
            else:
                dx = getattr(e, "x_root", self._win_x0) - self._drag_x_root
                dy = getattr(e, "y_root", self._win_y0) - self._drag_y_root
                self.geometry(f"+{int(self._win_x0 + dx)}+{int(self._win_y0 + dy)}")
        except Exception:
            pass

    def _minimize_win(self):
        try:
            self.iconify()
        except Exception:
            pass


    def _pointer_dentro(self, widget):
        try:
            x, y = self.winfo_pointerxy()
            rx = widget.winfo_rootx()
            ry = widget.winfo_rooty()
            rw = widget.winfo_width()
            rh = widget.winfo_height()
            return rx <= x <= rx + rw and ry <= y <= ry + rh
        except Exception:
            return False

    def _voice_outside_now(self):
        # Considera 'dentro' se o ponteiro estiver sobre o drawer inteiro.
        return not self._pointer_dentro(self.left_drawer)

    def _voice_maybe_collapse(self):
        # Fecha sozinho pouco depois de o mouse sair do drawer (exceto se fixado).
        if not self._voice_pinned and self.drawer_open and self._voice_outside_now():
            self._close_drawer()

    def _load_splash(self):
        """Carrega a splash art da waifu (PNG) em app/assets/. Se não existir, retorna None."""
        try:
            from PIL import Image
        except Exception:
            return None
        candidates = [
            ASSETS_DIR / "splash.png",
            ASSETS_DIR / "splash.jpg",
        ]
        for f in candidates:
            if f.exists():
                try:
                    img = Image.open(f)
                    img = img.convert("RGBA")
                    img.thumbnail((520, 520))
                    photo = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    return photo
                except Exception:
                    continue
        return None

    def _resetar_palco(self):
        """Ação 'Início': volta o palco para a Lia e atualiza a splash."""
        try:
            self._personagem_atual = "Lia"
            self.stage_title.configure(text="Lia")
            self._log("[APP] Palco resetado para Lia")
        except Exception:
            pass

    def _escolher_imagem_modelo(self, nome):
        """Ao treinar um modelo novo: permite associar um emote ou uma imagem
        (ex.: a arte real da Lia) ao modelo. A imagem vai para app/assets/ e
        para sovits-data/<nome>/avatar.png; o emote fica em avatar.json."""
        from PIL import Image
        from tkinter import filedialog as _fd
        result = {"emote": None, "img": None}

        win = ctk.CTkToplevel(self)
        win.title("🖼️ Imagem do modelo")
        win.geometry("420x330")
        win.attributes("-topmost", True)
        win.grab_set()
        ctk.CTkLabel(win, text=f"Imagem para o modelo '{nome}'", font=("", 15, "bold")).pack(pady=(16, 4))
        ctk.CTkLabel(win, text="Emote rápido, ou envie sua imagem personalizada (arte da Lia):",
                     font=("", 10), text_color="gray").pack(pady=(0, 8))

        grid = ctk.CTkFrame(win, fg_color="transparent")
        grid.pack(padx=12, pady=4)
        emotes = ["🌸", "😊", "✨", "❤️", "🎤", "🌟", "💜", "🖤", "🔥", "👑"]
        for i, e in enumerate(emotes):
            b = ctk.CTkButton(grid, text=e, width=44, height=40, font=("", 16),
                              fg_color=PALETTES[self.palette]["panel"], hover_color="#26262e",
                              command=lambda em=e: self._aplicar_imagem_modelo(win, result, nome, emote=em))
            b.grid(row=i // 5, column=i % 5, padx=3, pady=3)

        def _file():
            f = _fd.askopenfilename(
                title="Imagem da Lia (real)",
                filetypes=[("Imagem", "*.png *.jpg *.jpeg *.webp *.bmp *.ico"), ("Todos", "*.*")])
            if f:
                self._aplicar_imagem_modelo(win, result, nome, img=f)

        ctk.CTkButton(win, text="📂 Enviar imagem personalizada...", command=_file,
                      width=260, height=34, fg_color=PALETTES[self.palette]["accent"],
                      hover_color=PALETTES[self.palette]["accent2"]).pack(pady=(16, 4))
        ctk.CTkLabel(win, text="A arte da Lia deve ir em: app/assets/splash.png",
                     font=("", 9), text_color="gray").pack(pady=(4, 6))
        win.wait_window()
        return result

    def _aplicar_imagem_modelo(self, win, result, nome, emote=None, img=None):
        if emote:
            result["emote"] = emote
        if img:
            result["img"] = img
        try:
            from PIL import Image
            model_dir = ROOT / "sovits-data" / nome
            model_dir.mkdir(parents=True, exist_ok=True)
            if img:
                # Copia a imagem do usuário para sovits-data/<nome>/avatar.png
                im = Image.open(img)
                im = im.convert("RGBA")
                im.thumbnail((512, 512))
                dst = model_dir / "avatar.png"
                im.save(dst)
                result["img"] = str(dst)
                self._log(f"[MODEL] Imagem salva em {dst}")
            if emote:
                (model_dir / "avatar.json").write_text(json.dumps({"emote": emote}), encoding="utf-8")
                self._log(f"[MODEL] Emote '{emote}' associado ao modelo {nome}")
        except Exception as e:
            self._log(f"[MODEL] Erro ao salvar imagem: {e}")
        win.destroy()

    # ------------------------------------------------------------------
    # Console (log): recolher / limpar / ocultar
    # ------------------------------------------------------------------
    def _clear_log(self):
        try:
            self.log_text.delete("1.0", "end")
            self._log_buf.clear()
        except Exception:
            pass

    def _toggle_console(self):
        # Console sempre presente no rodapé; recolhe apenas a altura do texto.
        if self._console_state == "open":
            self._console_state = "collapsed"
            self.log_text.pack_forget()
            self.console_frame.configure(height=40)
        else:
            self._console_state = "open"
            self.console_frame.configure(height=170)
            self.log_text.pack(fill="both", expand=True, padx=10, pady=(6, 10))

    def _hide_console(self):
        self._console_state = "hidden"
        self.log_text.pack_forget()
        self.console_frame.configure(height=40)

    def _restore_console(self, show_log=True):
        self._console_state = "open" if show_log else "collapsed"
        if show_log:
            self.console_frame.configure(height=170)
            self.log_text.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        else:
            self.console_frame.configure(height=40)
            self.log_text.pack_forget()

    # ------------------------------------------------------------------
    # Menu de opções
    # ------------------------------------------------------------------
    def _on_lang_change(self, _=None):
        label = self.lang_combo.get()
        for code, lab in LANGS:
            if lab == label:
                self._set_lang(code)
                self.lang_combo.set(LANG_KEYS[self.lang])
                break

    def _on_palette_change(self, _=None):
        label = self.palette_combo.get()
        key = PALETTE_LABEL_BY_KEY.get(label, label)
        if key in PALETTES:
            self._set_palette(key)

    def _on_size_change(self, _=None):
        key = self.size_combo.get()
        if key in SIZES and key != self.size_key:
            self.size_key = key
            try:
                # Tamanho fixo: apenas troca a geometria; widgets place/pack se reposicionam
                self.geometry(SIZES[key])
            except Exception:
                pass
            self._save_prefs()

    # ------------------------------------------------------------------
    # Painel SoVITS (janela secundária, fora da tela principal)
    # ------------------------------------------------------------------
    def _build_sovits_panel(self):
        self.sovits_win = ctk.CTkToplevel(self)
        self.sovits_win.title(self._t("sovits_title"))
        self.sovits_win.geometry("420x640")
        self.sovits_win.minsize(400, 600)
        self.sovits_win.withdraw()
        self.sovits_win.protocol("WM_DELETE_WINDOW", self._hide_sovits_panel)
        p = PALETTES[self.palette]
        self.sovits_win.configure(fg_color=p["bg"])

        self._sovits_title_lbl = ctk.CTkLabel(self.sovits_win, text=self._t("sovits_title"), font=("", 16, "bold"),
                     text_color=p["accent2"])
        self._sovits_title_lbl.pack(anchor="w", padx=16, pady=(16, 2))
        self._reg("sovits_title", self._sovits_title_lbl)
        self._sovits_hint_lbl = ctk.CTkLabel(self.sovits_win, text=self._t("sovits_hint"), font=("", 10), text_color="gray",
                     anchor="w", wraplength=380, justify="left")
        self._sovits_hint_lbl.pack(anchor="w", padx=16, pady=(0, 8))
        self._reg("sovits_hint", self._sovits_hint_lbl)

        self._make_button(self.sovits_win, self._t("sovits_install"), self._instalar_sovits_servidor, "#b45309", key="sovits_inst", ikey="sovits_install")
        self._make_button(self.sovits_win, self._t("sovits_start"), self._run_sovits_local, "#15803d", key="sovits_on", ikey="sovits_start")
        self._make_button(self.sovits_win, self._t("sovits_stop"), self._parar_sovits, key="sovits_off", ikey="sovits_stop")
        ctk.CTkFrame(self.sovits_win, height=1, fg_color=p["line"]).pack(fill="x", padx=16, pady=6)
        self._make_button(self.sovits_win, self._t("sovits_import"), self._importar_modelo_sovits, "#6d28d9", key="import", ikey="sovits_import")
        self._make_button(self.sovits_win, self._t("sovits_train"), self._treinar_sovits_local, "#dc2626", key="train", ikey="sovits_train")
        self._make_button(self.sovits_win, self._t("sovits_delete"), self._deletar_modelo_sovits, "#7f1d1d", key="delete", ikey="sovits_delete")

        ctk.CTkFrame(self.sovits_win, height=1, fg_color=p["line"]).pack(fill="x", padx=16, pady=6)
        # Status do servidor (não sobrescreve o resumo do painel principal)
        self.sovits_win_status = ctk.CTkLabel(self.sovits_win, text="SoVITS: ...", font=("", 10), text_color="gray",
                                              anchor="w", wraplength=380, justify="left")
        self.sovits_win_status.pack(anchor="w", padx=16, pady=(0, 4))
        # Treinamento (status ao vivo)
        self._sovits_training_lbl = ctk.CTkLabel(self.sovits_win, text=self._t("sovits_training"), font=("", 11, "bold"),
                     text_color="#f97316")
        self._sovits_training_lbl.pack(anchor="w", padx=16, pady=(6, 2))
        self._reg("sovits_training", self._sovits_training_lbl)
        self.training_frame = ctk.CTkFrame(self.sovits_win, fg_color="transparent")
        self.training_frame.pack(fill="x", padx=16, pady=(0, 4))
        self.training_labels = {}  # model_name -> label widget
        self._no_training_label = ctk.CTkLabel(self.training_frame, text=self._t("sovits_none"), font=("", 9), text_color="gray")
        self._no_training_label.pack(anchor="w", padx=2)
        self._reg("sovits_none", self._no_training_label)
        self.training_progress = ctk.CTkProgressBar(self.training_frame, width=380, height=12, progress_color="#f97316")
        self.training_progress.set(0)
        self.training_progress_label = ctk.CTkLabel(self.training_frame, text="", font=("", 9), text_color="#fbbf24",
                                                    anchor="w", wraplength=380)
        self.training_progress_label.pack(anchor="w", padx=2, pady=(2, 0))

        # Rodapé
        ctk.CTkFrame(self.sovits_win, fg_color="transparent").pack(fill="both", expand=True)
        self._sovits_close_btn = ctk.CTkButton(self.sovits_win, text=self._t("sovits_fechar"), command=self._hide_sovits_panel,
                      width=120, height=32, fg_color="#1f2937", hover_color="#374151")
        self._sovits_close_btn.pack(pady=(0, 14))
        self._reg("sovits_fechar", self._sovits_close_btn)

    def _show_sovits_panel(self):
        if hasattr(self, "sovits_win"):
            self.sovits_win.deiconify()
            self.sovits_win.lift()
            self.sovits_win.focus_force()

    def _hide_sovits_panel(self):
        if hasattr(self, "sovits_win"):
            self.sovits_win.withdraw()

    def _make_status_card(self, parent, icon, label, value, key=None):
        card = ctk.CTkFrame(parent, corner_radius=8, height=46, width=126, fg_color=PALETTES[self.palette]["panel"])
        card.pack(side="left", padx=4, pady=8)
        card.pack_propagate(False)
        self._surfaces.append((card, "panel"))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=8, pady=5)
        # Ícone como imagem (sem emoji — evita quadradinhos no Windows)
        ic = self._load_icon(icon) if isinstance(icon, str) and icon.startswith("icon-") else None
        if ic is not None:
            ctk.CTkLabel(inner, image=ic, text="", width=26).pack(side="left")
        else:
            ctk.CTkLabel(inner, text=icon, font=("", 15), width=26).pack(side="left")
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(4, 0))
        lbl = ctk.CTkLabel(info, text=label, font=("", 10, "bold"), text_color="#cbd5e1", anchor="w")
        lbl.pack(fill="x")
        card._status_lbl = lbl
        # LED (círculo colorido) + valor
        val_row = ctk.CTkFrame(info, fg_color="transparent")
        val_row.pack(fill="x", pady=(2, 0))
        led = ctk.CTkFrame(val_row, width=9, height=9, corner_radius=5, fg_color="#6b7280")
        led.pack(side="left", padx=(0, 4))
        val_label = ctk.CTkLabel(val_row, text=value, font=("", 10, "bold"), anchor="w")
        val_label.pack(side="left", fill="x", expand=True)
        card._val_label = val_label
        card._led = led
        if key:
            self._reg(key, lbl)
        return card

    def _make_button(self, parent, text, command, color=None, key=None, ikey=None):
        kwargs = {"text": text, "font": ("", 11), "height": 30, "corner_radius": 6, "anchor": "w", "command": command}
        if color:
            kwargs["fg_color"] = color
            kwargs["hover_color"] = "#22c55e"
        btn = ctk.CTkButton(parent, **kwargs)
        btn.pack(fill="x", padx=10, pady=2)
        if key:
            self._btn[key] = btn
        if ikey:
            self._reg(ikey, btn)
        return btn

    _LED_COLORS = {"on": "#22c55e", "loading": "#f59e0b", "off": "#6b7280", "err": "#ef4444"}

    def _set_status(self, card, state, text):
        """Atualiza um card de status com LED colorido.
        state: 'on' | 'loading' | 'off' | 'err' (ou True/False por compatibilidade)."""
        if state is True:
            state = "on"
        elif state is False:
            state = "off"
        color = self._LED_COLORS.get(state, "#6b7280")
        if hasattr(card, "_led"):
            card._led.configure(fg_color=color)
        card._val_label.configure(text=text, text_color=color)

    # ============================================================
    # Estado operacional e bloqueio de ações (evita conflitos)
    # ============================================================
    def _modo_atual(self):
        """Retorna 'training', 'waifu' ou 'idle' com base no estado real.
        Usa cache (_aba_up/_tama_up) atualizado em background p/ não travar a UI."""
        training = any(p and p.poll() is None for p in self._training_procs.values())
        if training:
            return "training"
        if self._aba_up or self._tama_up:
            return "waifu"
        return "idle"

    def _set_mode(self, mode):
        self.mode = mode
        cols = {"idle": "#e5e7eb", "training": "#f59e0b", "waifu": "#22c55e"}
        txt = self._t("mode_" + mode)
        col = cols.get(mode, "#e5e7eb")
        if hasattr(self, "mode_badge"):
            self.mode_badge.configure(text=txt, text_color=col)
        # Loading overlay: durante treino, troca a splash por um spinner
        if mode == "training":
            self._show_loading(True)
        else:
            self._show_loading(False)
        self._aplicar_gating()

    def _show_loading(self, show):
        """Mostra/oculta o overlay de loading (spinner) sobre o palco."""
        if not hasattr(self, "_loading"):
            return
        try:
            if show:
                w = self.stage.winfo_width()
                h = self.stage.winfo_height()
                self._loading.place(relx=0.5, rely=0.5, anchor="center", width=min(420, max(200, w - 80)),
                                    height=min(240, max(150, h - 80)))
                self._loading.lift()
                self._loading_lbl2.configure(text=self._t("loading_wait"))
                self._start_spinner()
            else:
                self._loading.place_forget()
                self._stop_spinner()
        except Exception:
            pass

    _SPIN = ["◐", "◓", "◑", "◒"]
    def _start_spinner(self):
        self._spin_i = 0
        self._spin_job = None
        if getattr(self, "_spin_job", None) is None:
            def _tick():
                try:
                    self._spinner_lbl.configure(text=self._SPIN[self._spin_i % len(self._SPIN)])
                    self._spin_i += 1
                    self._spin_job = self.after(120, _tick)
                except Exception:
                    self._spin_job = None
            self._spin_job = self.after(120, _tick)

    def _stop_spinner(self):
        job = getattr(self, "_spin_job", None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._spin_job = None

    def _aplicar_gating(self):
        """Habilita/desabilita botões conforme o modo, para não disputar recursos.
        Em treino bloqueia TUDO exceto as opções cosméticas (idioma/tema/tamanho)."""
        if not hasattr(self, "_btn"):
            return
        mode = self.mode
        b = self._btn

        def _enable(key):
            if key in b and b[key] is not None:
                try: b[key].configure(state="normal")
                except: pass
        def _disable(key):
            if key in b and b[key] is not None:
                try: b[key].configure(state="disabled")
                except: pass

        # Em treino: TUDO desabilitado, menos as opções (combos de idioma/tema/tamanho ficam livres)
        if mode == "training":
            for k in ["waifu", "options", "rail_home", "rail_chip", "voice_rail",
                      "voz_on", "url", "diag", "config", "menu_voice", "menu_sovits",
                      "sovits_inst", "sovits_on", "import", "train", "delete",
                      "test_voz", "salvar"]:
                _disable(k)
            for k in ["voz_off", "sovits_off"]:
                _enable(k)
            if "waifu" in b:
                b["waifu"].configure(text=self._t("cta_training"))
            return

        # Com a waifu aberta: não pode treinar. Pode configurar túnel/voz/servidores.
        if mode == "waifu":
            for k in ["train", "delete"]:
                _disable(k)
            for k in ["waifu", "options", "rail_home", "rail_chip", "voice_rail",
                      "voz_on", "voz_off", "url", "diag", "config", "menu_voice", "menu_sovits",
                      "sovits_inst", "sovits_on", "sovits_off", "import",
                      "test_voz", "salvar"]:
                _enable(k)
            if "waifu" in b:
                b["waifu"].configure(text=self._t("cta_start"))
            return

        # idle
        for k in ["waifu", "options", "rail_home", "rail_chip", "voice_rail",
                  "voz_on", "voz_off", "url", "diag", "config", "menu_voice", "menu_sovits",
                  "sovits_inst", "sovits_on", "sovits_off", "import", "train", "delete",
                  "test_voz", "salvar"]:
            _enable(k)
        if "waifu" in b:
            b["waifu"].configure(text=self._t("cta_start"))

    def _atualizar_gating(self):
        """Reavalia o modo e reaplica o gating (chamado em refresh e após eventos)."""
        self._set_mode(self._modo_atual())

    def _is_port_open(self, port):
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try: return sock.connect_ex(('127.0.0.1', port)) == 0
        except: return False
        finally: sock.close()

    def _kill_port_process(self, port):
        try:
            proc = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, creationflags=0x08000000)
            for line in proc.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) > 0:
                        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, creationflags=0x08000000)
                        return True
        except: pass
        return False

    def _get_sovits_env(self):
        """Retorna env dict com PYTHONIOENCODING=utf-8, ffmpeg no PATH e .pth configurado."""
        sovits_dir = ROOT / "sovits-data"
        venv_dir = sovits_dir / "venv"
        repo_dir = sovits_dir / "GPT-SoVITS"
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"  # Força UTF-8 para leitura de arquivos .py
        # Adicionar imageio-ffmpeg binaries ao PATH (ffmpeg.exe bundled)
        ffmpeg_bin = venv_dir / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries"
        if ffmpeg_bin.exists():
            env["PATH"] = str(ffmpeg_bin) + ";" + env.get("PATH", "")
        # Adicionar venv Scripts ao PATH
        env["PATH"] = str(venv_dir / "Scripts") + ";" + env.get("PATH", "")
        # Criar .pth no site-packages (mesma abordagem do webui.py)
        site_packages = venv_dir / "Lib" / "site-packages"
        if site_packages.exists():
            pth_file = site_packages / "users.pth"
            pth_content = "\n".join([
                str(repo_dir),
                str(repo_dir / "GPT_SoVITS" / "BigVGAN"),
                str(repo_dir / "tools"),
                str(repo_dir / "tools" / "asr"),
                str(repo_dir / "GPT_SoVITS"),
                str(repo_dir / "tools" / "uvr5"),
            ])
            try:
                pth_file.write_text(pth_content, encoding="utf-8")
            except:
                pass
        return env

    def _refresh_status(self):
        def _check():
            voice = check_voice()
            aba = check_aba()
            tama = check_tamagotchi()
            if voice["up"]:
                self.after(0, lambda: self._set_status(self.st_voice, "on", f"v{voice.get('version', '?')}"))
                self.after(0, lambda: self.voz_status.configure(text=f"Servidor de voz: rodando v{voice.get('version', '?')}", text_color="#4ade80"))
            else:
                self.after(0, lambda: self._set_status(self.st_voice, "off", "Off"))
                self.after(0, lambda: self.voz_status.configure(text="Servidor de voz: parado", text_color="#f87171"))
            self.after(0, lambda: self._set_status(self.st_aba, "on" if aba["up"] else "off", "Online" if aba["up"] else "Off"))
            sovits_ok = self._is_port_open(SOVITS_PORT)
            if sovits_ok:
                self.after(0, lambda: self._set_status(self.st_sovits, "on", "Rodando"))
                self.after(0, lambda: self.sovits_status.configure(text="SoVITS: rodando ✅", text_color="#4ade80"))
            else:
                sovits_dir = ROOT / "sovits-data"
                if (sovits_dir / "GPT-SoVITS" / "api_v2.py").exists():
                    self.after(0, lambda: self._set_status(self.st_sovits, "loading", "Instalado"))
                    self.after(0, lambda: self.sovits_status.configure(text="SoVITS: instalado (parado)", text_color="#fbbf24"))
                else:
                    self.after(0, lambda: self._set_status(self.st_sovits, "err", "Não instalado"))
                    self.after(0, lambda: self.sovits_status.configure(text="SoVITS: não instalado", text_color="#f87171"))
            if tama["up"]:
                self.after(0, lambda: self._set_status(self.st_tama, "on", "Pronto"))
            else:
                self.after(0, lambda: self._set_status(self.st_tama, "off", "Não instalado"))
            # Cache do estado da aba/tamagotchi (evita HTTP no thread principal)
            self._aba_up = aba["up"]
            self._tama_up = tama["up"]
            # Atualizar modo operacional (gating) no fim da checagem
            self.after(0, self._atualizar_gating)
        threading.Thread(target=_check, daemon=True).start()
        self.after(15000, self._refresh_status)

    def _log(self, text):
        # Grava também no arquivo/console (depuração sem interface), via pacote lia/log.
        _file_logger.write(text, self._log_category(text))
        self._log_buf.append(text)
        cat = self._log_category(text)
        if self._log_filter == "general" or self._log_filter == cat:
            self.log_text.insert("end", text + "\n", cat)
            self.log_text.see("end")

    def _log_category(self, text):
        t = text.upper()
        if any(k in t for k in ("[VOZ", "[SOVITS", "[MODEL", "[VOICE", "[TTS", "[AUDIO")):
            return "voice"
        if any(k in t for k in ("[WEB", "[TAMA", "[NET", "[SYSTEM", "[SERV", "[TUNNEL", "[AIRA")):
            return "system"
        return "general"

    def _on_log_tab(self, value):
        m = {self._t("tab_general"): "general", self._t("tab_voice"): "voice", self._t("tab_system"): "system"}
        self._log_filter = m.get(value, "general")
        self._apply_log_filter()

    def _apply_log_filter(self):
        try:
            self.log_text.delete("1.0", "end")
            for line in self._log_buf:
                cat = self._log_category(line)
                if self._log_filter == "general" or self._log_filter == cat:
                    self.log_text.insert("end", line + "\n", cat)
            self.log_text.see("end")
        except Exception:
            pass

    def _on_close(self):
        """Cleanup ao fechar o app."""
        self._log("[APP] Fechando e limpando processos...")
        for proc in [self.voice_process, self.sovits_process, self.other_process]:
            if proc and proc.poll() is None:
                try: proc.terminate()
                except: pass
        for pid in self._child_pids:
            try: subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=0x08000000)
            except: pass
        try:
            result = subprocess.run(["wmic", "process", "where", "commandline like '%train_auto.py%' and name='python.exe'", "get", "processid"], capture_output=True, text=True, creationflags=0x08000000)
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.isdigit() and int(line) > 0:
                    subprocess.run(["taskkill", "/PID", line, "/F"], capture_output=True, creationflags=0x08000000)
        except: pass
        # Fecha janelas secundárias (SoVITS panel, options menu, model selector)
        for wname in ["sovits_win", "options_menu"]:
            w = getattr(self, wname, None)
            if w is not None and w.winfo_exists():
                try:
                    w.destroy()
                except Exception:
                    pass
        global _lock_server
        if _lock_server:
            try:
                # Could be a Windows mutex handle (int) or a socket
                if isinstance(_lock_server, int):
                    ctypes.windll.kernel32.CloseHandle(_lock_server)
                else:
                    _lock_server.close()
            except: pass
        self.destroy()

    def _refresh_training_status(self):
        """Verifica modelos em treinamento e atualiza UI."""
        def _check():
            sovits_dir = ROOT / "sovits-data"
            if not sovits_dir.exists():
                self.after(0, lambda: self._update_training_ui([]))
                return
            training = []
            # Check both sovits-data/ and sovits-data/GPT-SoVITS/logs/ for progress files
            search_dirs = []
            # Direct model dirs (for future use)
            for d in sorted(sovits_dir.iterdir()):
                if d.is_dir() and d.name not in ("venv", "GPT-SoVITS", "__pycache__"):
                    search_dirs.append(d)
            # GPT-SoVITS/logs/ dirs (where train_auto.py writes progress)
            logs_dir = sovits_dir / "GPT-SoVITS" / "logs"
            if logs_dir.exists():
                for d in sorted(logs_dir.iterdir()):
                    if d.is_dir():
                        search_dirs.append(d)
            
            for d in search_dirs:
                progress_file = d / ".training_progress.json"
                if progress_file.exists():
                    try:
                        data = json.loads(progress_file.read_text(encoding="utf-8"))
                        step = data.get("step", 0)
                        ts = data.get("timestamp", 0)
                        names = {0: "📦 Deps", 1: "🔪 Slice", 2: "🎤 ASR", 3: "🌐 Idioma", 4: "📊 Dataset", 5: "🧠 SoVITS", 6: "🤖 GPT"}
                        step_name = names.get(step, f"Etapa {step}")
                        elapsed = int(time.time() - ts) if ts else 0
                        elapsed_str = f"{elapsed//3600}h{(elapsed%3600)//60}m" if elapsed > 60 else f"{elapsed//60}m{elapsed%60}s"
                        # Progresso ao vivo (fase/epoch/%) escrito pelo train_auto.py
                        live = None
                        live_file = d / "training_live.json"
                        if live_file.exists():
                            try:
                                ldata = json.loads(live_file.read_text(encoding="utf-8"))
                                if isinstance(ldata, dict) and ldata.get("pct") is not None:
                                    live = ldata
                            except:
                                live = None
                        training.append({"name": d.name, "step": step_name, "elapsed": elapsed_str, "step_num": step, "live": live})
                    except:
                        training.append({"name": d.name, "step": "?", "elapsed": "?", "step_num": -1, "live": None})
            self.after(0, lambda: self._update_training_ui(training))
        threading.Thread(target=_check, daemon=True).start()
        self.after(15000, self._refresh_training_status)

    def _update_training_ui(self, training):
        """Update the training status section in the left panel."""
        # Clear old labels
        for lbl in self.training_labels.values():
            lbl.destroy()
        self.training_labels.clear()
        
        if not training:
            self._no_training_label.pack(anchor="w", padx=2)
            self.sovits_status.configure(text=self._t("sovits_none"), text_color="gray")
            self.training_progress.pack_forget()
            self.training_progress_label.pack_forget()
        else:
            self._no_training_label.pack_forget()
            for info in training:
                name = info["name"]
                step = info["step"]
                elapsed = info["elapsed"]
                step_num = info.get("step_num", -1)
                # Color based on progress
                color = "#4ade80" if step_num >= 5 else "#fbbf24" if step_num >= 0 else "#f87171"
                text = f"  {name}: {step} ({elapsed})"
                btn = ctk.CTkButton(
                    self.training_frame, text=text, font=("", 9),
                    fg_color="transparent", text_color=color, hover_color="#333",
                    anchor="w", height=22, width=180,
                    command=lambda n=name: self._resume_training(n)
                )
                btn.pack(anchor="w", padx=2, pady=1)
                self.training_labels[name] = btn
            # Update sovits_status too
            names = ", ".join(info["name"] for info in training)
            self.sovits_status.configure(text=f"Treinando: {names}", text_color="#fbbf24")
            # Barra de progresso ao vivo (fase/epoch/%) — usa o primeiro modelo com live
            self.training_progress.pack(anchor="w", padx=2, pady=(6, 0))
            self.training_progress_label.pack(anchor="w", padx=2)
            live = next((info["live"] for info in training if info.get("live")), None)
            if live:
                pct = min(max(float(live.get("pct", 0)) / 100.0, 0.0), 1.0)
                self.training_progress.set(pct)
                phase = (live.get("phase") or "Treino").replace("SoVITS", "🧠 SoVITS").replace("GPT", "🤖 GPT")
                epoch = live.get("epoch", "")
                cur = live.get("current", 0)
                tot = live.get("total", 0)
                rate = live.get("rate", "?")
                loss = live.get("loss", "?")
                acc = live.get("acc", "?")
                parts = []
                if epoch not in ("", None): parts.append(f"Epoch {epoch}")
                parts.append(f"{cur}/{tot}")
                if rate not in ("?", None): parts.append(rate)
                if loss not in ("?", None): parts.append(f"loss={loss}")
                if acc not in ("?", None): parts.append(f"acc={acc}")
                self.training_progress_label.configure(text=f"{phase} {int(pct*100)}% · " + " · ".join(parts))
            else:
                self.training_progress.set(0)
                self.training_progress_label.configure(text="")

    def _resume_training(self, model_name):
        """Resume training for a partially trained model."""
        sovits_dir = ROOT / "sovits-data"
        model_dir = sovits_dir / model_name
        if not model_dir.exists():
            self._log(f"[SOVITS] ❌ Modelo '{model_name}' não encontrado")
            return
        # Check for audio files
        audio_files = [f for f in model_dir.iterdir() if f.suffix.lower() in ('.wav', '.mp3', '.flac', '.ogg', '.m4a')]
        if not audio_files:
            self._log(f"[SOVITS] ❌ Nenhum áudio encontrado em {model_dir}")
            return
        self._log(f"[SOVITS] 🔄 Retomando treino de '{model_name}'...")
        self._start_training(model_name, model_dir)

    def _start_training(self, nome, model_dir):
        """Start or resume training for a model."""
        if self._modo_atual() == "waifu":
            self._log("[SOVITS] ⛔ Pare/feche a waifu (Airi) antes de treinar uma voz.")
            return
        sovits_dir = ROOT / "sovits-data"
        repo_dir = sovits_dir / "GPT-SoVITS"
        venv_python = sovits_dir / "venv" / "Scripts" / "python.exe"
        train_script = SCRIPTS / "train_auto.py"

        if not (repo_dir / "webui.py").exists():
            self._log("[SOVITS] ❌ Servidor não instalado. Clique '📦 Instalar Servidor' primeiro.")
            return
        if not venv_python.exists():
            self._log("[SOVITS] ❌ Ambiente Python não encontrado.")
            return

        self._log(f"[SOVITS] 🔥 Treinando '{nome}'...")
        self._log("[SOVITS] Pipeline: Slice → ASR → Idiomas (pt) → Dataset → Treino")
        self._set_busy(f"Treinando '{nome}'...")

        output_dir = repo_dir / "logs" / nome
        output_dir.mkdir(parents=True, exist_ok=True)

        def _train():
            try:
                sovits_env = self._get_sovits_env()
                sovits_env["PYTHONUNBUFFERED"] = "1"
                # O treino usa o frontend de texto do GPT-SoVITS (1-get-text.py),
                # que precisa do suporte a 'pt' (G2P) para fonemizar em português.
                # Aplica o patch PT antes de treinar, se necessário.
                pt_patch_script = SCRIPTS / "patch_sovits_pt.py"
                if pt_patch_script.exists():
                    try:
                        pr_pt = subprocess.run(
                            [str(venv_python), str(pt_patch_script), str(repo_dir)],
                            capture_output=True, text=True, timeout=120,
                            creationflags=0x08000000, env=sovits_env
                        )
                        for line in (pr_pt.stdout or "").splitlines():
                            if line.strip():
                                self.after(0, lambda l=line: self._log(f"[SOVITS] {l}"))
                    except Exception as e:
                        self.after(0, lambda: self._log(f"[SOVITS] ⚠️ Erro ao aplicar patch PT antes do treino: {e}"))
                cmd = [
                    str(venv_python), str(train_script),
                    "--model", nome,
                    "--audio-dir", str(model_dir),
                    "--repo", str(repo_dir),
                    "--output", str(output_dir),
                    "--python", str(venv_python),
                    "--lang", "pt",
                ]
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    bufsize=1, cwd=str(ROOT),
                    creationflags=0x08000000, env=sovits_env
                )
                self._training_procs[nome] = proc
                self.after(0, self._atualizar_gating)  # bloqueia ações enquanto treina
                for line in iter(proc.stdout.readline, b""):
                    line = line.decode("utf-8", errors="replace").rstrip()
                    if line:
                        self.after(0, lambda l=line: self._log(f"[SOVITS] {l}"))
                proc.wait()
                self._training_procs.pop(nome, None)
                self.after(0, self._atualizar_gating)  # libera ao terminar
                if proc.returncode == 0:
                    self.after(0, lambda: self._log(""))
                    self.after(0, lambda: self._log("=" * 50))
                    self.after(0, lambda: self._log(f"[SOVITS] ✅ Modelo '{nome}' treinado!"))
                    self.after(0, lambda: self._log("[SOVITS] Use '▶ Rodar Servidor' para usar."))
                    self.after(0, lambda: self._log("=" * 50))
                    self.after(0, lambda: self._set_done(f"Treino '{nome}' concluído"))
                else:
                    self.after(0, lambda: self._log(f"[SOVITS] ❌ Treino falhou (código {proc.returncode})"))
                    self.after(0, lambda: self._set_done("Treino falhou", error=True))
            except Exception as e:
                self.after(0, lambda: self._log(f"[ERRO] {e}"))
                self.after(0, lambda: self._set_done("Erro no treino", error=True))

        threading.Thread(target=_train, daemon=True).start()

    # ── Status / Progress indicator ──
    _spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _spinner_idx = 0
    _is_busy = False
    _busy_start = 0

    def _set_busy(self, label="Processando..."):
        """Mostra spinner + label quando algo está rodando."""
        import time
        self._is_busy = True
        self._busy_start = time.time()
        self.log_status_label.configure(text=f"⏳ {label}", text_color="#fbbf24")
        self._animate_spinner()

    def _set_done(self, label="Pronto", error=False):
        """Mostra status finalizado."""
        import time
        self._is_busy = False
        elapsed = int(time.time() - self._busy_start) if self._busy_start else 0
        color = "#f87171" if error else "#4ade80"
        icon = "❌" if error else "✅"
        elapsed_str = f" ({elapsed//60}m{elapsed%60}s)" if elapsed > 5 else ""
        self.log_status_label.configure(text=f"{icon} {label}{elapsed_str}", text_color=color)
        self.log_progress_label.configure(text="")

    def _set_progress(self, current, total, label=""):
        """Mostra progresso numérico (ex: 3/10)."""
        if total > 0:
            pct = int(current / total * 100)
            self.log_progress_label.configure(text=f"{current}/{total} ({pct}%)")
        if label:
            self.log_status_label.configure(text=f"⏳ {label}", text_color="#fbbf24")

    def _animate_spinner(self):
        """Anima o spinner enquanto algo está rodando."""
        if not self._is_busy:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner_frames)
        frame = self._spinner_frames[self._spinner_idx]
        current_text = self.log_status_label.cget("text")
        # Substituir o emoji inicial pelo frame do spinner
        if current_text.startswith("⏳"):
            base = current_text[2:].strip()
            self.log_status_label.configure(text=f"{frame} {base}")
        # Calcular tempo decorrido
        import time
        elapsed = int(time.time() - self._busy_start)
        if elapsed > 5:
            self.log_progress_label.configure(text=f"{elapsed//60}m{elapsed%60}s")
        self.after(100, self._animate_spinner)

    # ============================================================
    # Voice server
    # ============================================================
    def _act_ligar_voz(self):
        if self.voice_process and self.voice_process.poll() is None:
            self._log("[VOZ] Já está rodando."); return
        self.voice_process = None
        if not VOICE_SCRIPT.exists():
            self._log(f"[ERRO] Script não encontrado: {VOICE_SCRIPT}"); return
        if self._is_port_open(VOICE_PORT):
            try:
                r = urllib.request.urlopen(f"http://127.0.0.1:{VOICE_PORT}/health", timeout=2)
                d = json.loads(r.read())
                self._log(f"[VOZ] Servidor já rodando na porta {VOICE_PORT} (v{d.get('version', '?')})")
                self._refresh_status(); return
            except:
                self._log(f"[VOZ] Porta {VOICE_PORT} ocupada. Limpando...")
                self._kill_port_process(VOICE_PORT)
                import time; time.sleep(1)
        if not garantir_node_modules(lambda t: self.after(0, lambda: self._log(t))):
            self._log("[ERRO] Falha ao instalar dependências."); return
        self._log("[VOZ] Iniciando servidor de voz...")
        def _start():
            try:
                proc = subprocess.Popen(["node", str(VOICE_SCRIPT)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=str(ROOT), creationflags=0x08000000)
                self.voice_process = proc
                for line in proc.stdout:
                    line = line.rstrip()
                    if line: self.after(0, lambda l=line: self._log(f"[VOZ] {l}"))
                proc.wait()
                self.after(0, lambda: self._log("[VOZ] Servidor parou."))
                self.voice_process = None
                self.after(1000, self._refresh_status)
            except Exception as e:
                self.after(0, lambda: self._log(f"[ERRO] {e}"))
                self.voice_process = None
        threading.Thread(target=_start, daemon=True).start()

    def _act_parar_voz(self):
        stopped = False
        if self.voice_process and self.voice_process.poll() is None:
            try: self.voice_process.terminate(); self._log("[VOZ] Parando servidor..."); stopped = True
            except Exception as e: self._log(f"[ERRO] {e}")
        self.voice_process = None
        if self._kill_port_process(VOICE_PORT):
            self._log(f"[VOZ] Processo na porta {VOICE_PORT} finalizado."); stopped = True
        if not stopped: self._log("[VOZ] Nenhum servidor de voz rodando.")
        self._refresh_status()
        self.after(500, self._atualizar_gating)

    def _atualizar_resumo_voz(self):
        try:
            eng = self.engine_var.get()
            voz = self.voice_combo.get()
            self.voz_summary.configure(text=f"Engine: {eng}\nVoz: {voz}")
        except Exception:
            pass

    def _update_voice_list(self):
        engine = self.engine_var.get()
        # Mostra apenas os controles suportados pela engine
        self.pitch_frame.pack_forget()
        self.kokoro_frame.pack_forget()
        self.speed_frame.pack_forget()
        if engine == "kokoro":
            self.voice_combo.configure(values=["af_heart","af_bella","af_nicole","af_sarah","af_sky","am_adam","am_michael","pf_dora","pm_santa","pm_alex","jf_alpha","jf_gongitsune","jm_kumo","zf_xiaobei","zm_yunxi"])
            self.voice_combo.set("pf_dora")
            self.kokoro_frame.pack(fill="x", padx=12, pady=4)
            self.speed_frame.pack(fill="x", padx=12, pady=4)
        elif engine == "sovits":
            sovits_models = self._listar_modelos_sovits()
            if sovits_models:
                self.voice_combo.configure(values=sovits_models)
                self.voice_combo.set(sovits_models[0])
            else:
                self.voice_combo.configure(values=["(nenhum modelo)"])
                self.voice_combo.set("(nenhum modelo)")
            self.speed_frame.pack(fill="x", padx=12, pady=4)
        else:
            self.voice_combo.configure(values=["pt-BR-ThalitaNeural","pt-BR-FranciscaNeural","pt-BR-GiovannaNeural","pt-BR-BrendaNeural","pt-BR-AntonioNeural","pt-BR-DonatoNeural","pt-BR-ValerioNeural","pt-BR-ManuelaNeural","pt-BR-NicolauNeural","ja-JP-NanamiNeural","ja-JP-AoiNeural","ja-JP-KeitaNeural","ja-JP-DaichiNeural","en-US-AriaNeural","en-US-JennyNeural","en-US-SaraNeural","en-US-GuyNeural","en-US-TonyNeural","es-MX-DaliaNeural","es-ES-ElviraNeural","fr-FR-DeniseNeural","ko-KR-SunHiNeural","zh-CN-XiaoxiaoNeural","zh-CN-YunxiNeural"])
            self.voice_combo.set("pt-BR-ThalitaNeural")
            self.pitch_frame.pack(fill="x", padx=12, pady=4)
            self.speed_frame.pack(fill="x", padx=12, pady=4)
        self._atualizar_resumo_voz()

    # ============================================================
    # Kokoro
    # ============================================================
    def _instalar_kokoro(self):
        self._log("[KOKORO] Iniciando instalação...")
        self.kokoro_status.configure(text="Instalando...", text_color="#fbbf24")
        def _install():
            try:
                kokoro_dir = ROOT / "kokoro-data"
                kokoro_dir.mkdir(exist_ok=True)
                venv_dir = kokoro_dir / "venv"
                venv_python = venv_dir / "Scripts" / "python.exe"
                if not venv_python.exists():
                    self.after(0, lambda: self._log("[KOKORO] Criando ambiente Python..."))
                    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], capture_output=True, creationflags=0x08000000)
                if not venv_python.exists():
                    self.after(0, lambda: self._log("[ERRO] Falha ao criar venv"))
                    self.after(0, lambda: self.kokoro_status.configure(text="Erro", text_color="#f87171")); return
                self.after(0, lambda: self._log("[KOKORO] Instalando kokoro-onnx..."))
                subprocess.run([str(venv_python), "-m", "pip", "install", "--disable-pip-version-check", "kokoro-onnx", "soundfile", "numpy"], capture_output=True, creationflags=0x08000000)
                self.after(0, lambda: self._log("[KOKORO] Baixando modelos (~360 MB)..."))
                model_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
                for fname in ["kokoro-v1.0.onnx", "voices-v1.0.bin"]:
                    fpath = kokoro_dir / fname
                    if not fpath.exists():
                        self.after(0, lambda f=fname: self._log(f"[KOKORO] Baixando {f}..."))
                        try: urllib.request.urlretrieve(f"{model_url}/{fname}", str(fpath))
                        except Exception as e:
                            self.after(0, lambda: self._log(f"[ERRO] {e}"))
                            self.after(0, lambda: self.kokoro_status.configure(text="Erro no download", text_color="#f87171")); return
                self.after(0, lambda: self._log("[KOKORO] ✅ Instalação concluída!"))
                self.after(0, lambda: self.kokoro_status.configure(text="Instalado!", text_color="#4ade80"))
            except Exception as e:
                self.after(0, lambda: self._log(f"[ERRO] {e}"))
                self.after(0, lambda: self.kokoro_status.configure(text="Erro", text_color="#f87171"))
        threading.Thread(target=_install, daemon=True).start()

    # ============================================================
    # GPT-SoVITS
    # ============================================================
    def _listar_modelos_sovits(self):
        sovits_dir = ROOT / "sovits-data"
        models = []
        if sovits_dir.exists():
            for d in sorted(sovits_dir.iterdir()):
                if d.is_dir() and d.name not in ("venv", "GPT-SoVITS", "__pycache__"):
                    has_pth = any(d.glob("*.pth"))
                    has_ckpt = any(d.glob("*.ckpt"))
                    has_wav = any(d.glob("*.wav")) or any(d.glob("*.mp3"))
                    if has_pth or has_ckpt or has_wav:
                        models.append(d.name)
        return models if models else []

    def _instalar_sovits_servidor(self):
        self._log("[SOVITS] Instalando servidor (só o necessário para rodar modelos)...")
        self._log("[SOVITS] 💡 Depois importe áudio (📤) e treine localmente (🔥)")
        self.sovits_status.configure(text="Instalando...", text_color="#fbbf24")
        self._set_busy("Instalando servidor SoVITS...")

        def _install():
            try:
                sovits_dir = ROOT / "sovits-data"
                sovits_dir.mkdir(exist_ok=True)
                repo_dir = sovits_dir / "GPT-SoVITS"

                # 1. Clonar repo
                if not (repo_dir / "api_v2.py").exists():
                    self.after(0, lambda: self._log("[SOVITS] Etapa 1/4: Clonando repositório..."))
                    result = subprocess.run(
                        ["git", "clone", "--depth", "1", "https://github.com/RVC-Boss/GPT-SoVITS.git", str(repo_dir)],
                        capture_output=True, text=True, creationflags=0x08000000
                    )
                    if result.returncode != 0:
                        self.after(0, lambda: self._log(f"[ERRO] Git clone falhou: {result.stderr[:200]}"))
                        self.after(0, lambda: self.sovits_status.configure(text="Erro", text_color="#f87171"))
                        self.after(0, lambda: self._set_done("Erro no clone", error=True)); return

                if not (repo_dir / "api_v2.py").exists():
                    self.after(0, lambda: self._log("[ERRO] api_v2.py não encontrado após clone."))
                    self.after(0, lambda: self.sovits_status.configure(text="Erro", text_color="#f87171"))
                    self.after(0, lambda: self._set_done("Erro no clone", error=True)); return
                self.after(0, lambda: self._log("[SOVITS] ✅ Repositório clonado."))

                # 2. Criar venv
                venv_dir = sovits_dir / "venv"
                venv_python = venv_dir / "Scripts" / "python.exe"
                if not venv_python.exists():
                    self.after(0, lambda: self._log("[SOVITS] Etapa 2/4: Criando ambiente Python..."))
                    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], capture_output=True, creationflags=0x08000000)
                if not venv_python.exists():
                    self.after(0, lambda: self._log("[ERRO] Falha ao criar venv"))
                    self.after(0, lambda: self.sovits_status.configure(text="Erro", text_color="#f87171"))
                    self.after(0, lambda: self._set_done("Erro no venv", error=True)); return
                self.after(0, lambda: self._log("[SOVITS] ✅ Ambiente Python criado."))

                # 3. Verificar e corrigir versões incompatíveis
                self.after(0, lambda: self._log("[SOVITS] Etapa 3/4: Verificando versões..."))
                self.after(0, lambda: self._log("[SOVITS]   Limpando pacotes incompatíveis..."))
                
                # Versões fixas que sabemos que funcionam juntas
                pinned_versions = {
                    "transformers": "4.51.3",
                    "peft": "0.15.2",
                    "pytorch-lightning": "2.5.2",
                    "torchmetrics": "1.5.0",
                }
                
                # Verificar cada pacote pinado
                for pkg, target_ver in pinned_versions.items():
                    check = subprocess.run(
                        [str(venv_python), "-c", f"import {pkg.replace('-', '_')}; print({pkg.replace('-', '_')}.__version__)"],
                        capture_output=True, text=True, creationflags=0x08000000
                    )
                    if check.returncode == 0:
                        current = check.stdout.strip().split("\n")[-1]
                        # Verificar se a versão é compatível (mesma major.minor)
                        cur_parts = current.split(".")[:2]
                        tgt_parts = target_ver.split(".")[:2]
                        if cur_parts != tgt_parts:
                            self.after(0, lambda p=pkg, c=current, t=target_ver: self._log(f"[SOVITS]   ⚠️ {p}={c} → forçando {t}"))
                            subprocess.run(
                                [str(venv_python), "-m", "pip", "install", "--disable-pip-version-check",
                                 "--force-reinstall", "--no-deps", f"{pkg}=={target_ver}"],
                                capture_output=True, creationflags=0x08000000
                            )
                        else:
                            self.after(0, lambda p=pkg, c=current: self._log(f"[SOVITS]   ✅ {p}={c}"))
                    else:
                        self.after(0, lambda p=pkg: self._log(f"[SOVITS]   ℹ️ {p} não instalado ainda"))

                # 4. Instalar deps do servidor
                self.after(0, lambda: self._log("[SOVITS] Etapa 4/4: Instalando dependências do servidor..."))
                subprocess.run([str(venv_python), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip", "wheel"], capture_output=True, creationflags=0x08000000)

                # PyTorch CPU
                self.after(0, lambda: self._log("[SOVITS] Instalando PyTorch (CPU)..."))
                subprocess.run([str(venv_python), "-m", "pip", "install", "--disable-pip-version-check", "torch", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cpu"], capture_output=True, creationflags=0x08000000)

                self.after(0, lambda: self._log("[SOVITS] Instalando dependências do servidor..."))
                
                # Só o que o api_v2.py precisa para RODAR modelos
                server_deps = [
                    # Core
                    "numpy<2.0", "scipy", "soundfile", "psutil", "tqdm", "pyyaml",
                    # Audio
                    "librosa==0.10.2", "numba", "av>=11", "ffmpeg-python", "imageio-ffmpeg",
                    # torchaudio em versoes novas exige torchcodec para carregar audio
                    "torchcodec",
                    # ML (inference) — versões fixas pra evitar conflito
                    "transformers==4.51.3", "peft==0.15.2", "huggingface_hub", "safetensors",
                    "sentencepiece", "chardet", "onnxruntime", "ctranslate2>=4.0,<5",
                    # Text
                    "cn2an", "pypinyin", "jieba", "jieba_fast", "g2p_en", "modelscope",
                    # Model
                    "rotary_embedding_torch", "x_transformers",
                    "fast_langdetect>=0.3.1", "wordsegment", "split-lang",
                    # Server
                    "fastapi", "uvicorn", "gradio", "pytorch-lightning==2.5.2", "matplotlib",
                ]
                
                # Instalar em batches de 5
                failed = []
                for i in range(0, len(server_deps), 5):
                    batch = server_deps[i:i+5]
                    self.after(0, lambda b=batch: self._log(f"[SOVITS]   Instalando: {', '.join(b[:3])}..."))
                    result = subprocess.run(
                        [str(venv_python), "-m", "pip", "install", "--disable-pip-version-check", "--prefer-binary"] + batch,
                        capture_output=True, text=True, creationflags=0x08000000
                    )
                    if result.returncode != 0:
                        for pkg in batch:
                            r = subprocess.run(
                                [str(venv_python), "-m", "pip", "install", "--disable-pip-version-check", "--prefer-binary", pkg],
                                capture_output=True, text=True, creationflags=0x08000000
                            )
                            if r.returncode != 0:
                                failed.append(pkg)
                
                if failed:
                    self.after(0, lambda: self._log(f"[AVISO] Falharam: {', '.join(failed)}"))
                
                # Verificar deps críticas do servidor
                self.after(0, lambda: self._log("[SOVITS] Verificando dependências do servidor..."))
                critical = ["torch", "numpy", "librosa", "transformers", "peft", "gradio", "fastapi", "imageio_ffmpeg", "pytorch_lightning", "matplotlib", "jieba_fast"]
                for pkg in critical:
                    r = subprocess.run([str(venv_python), "-c", f"import {pkg}"], capture_output=True, creationflags=0x08000000)
                    if r.returncode != 0:
                        self.after(0, lambda p=pkg: self._log(f"[SOVITS]   ❌ {p} - reinstalando..."))
                        subprocess.run(
                            [str(venv_python), "-m", "pip", "install", "--disable-pip-version-check", "--force-reinstall", pkg],
                            capture_output=True, creationflags=0x08000000
                        )
                        r2 = subprocess.run([str(venv_python), "-c", f"import {pkg}"], capture_output=True, creationflags=0x08000000)
                        status = "✅" if r2.returncode == 0 else "❌ FALHOU"
                        self.after(0, lambda p=pkg, s=status: self._log(f"[SOVITS]   {s} {p}"))
                    else:
                        self.after(0, lambda p=pkg: self._log(f"[SOVITS]   ✅ {p}"))

                # Verificar ffmpeg binário
                self.after(0, lambda: self._log("[SOVITS] Verificando ffmpeg..."))
                ffmpeg_check = subprocess.run(
                    [str(venv_python), "-c", "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"],
                    capture_output=True, text=True, creationflags=0x08000000
                )
                if ffmpeg_check.returncode == 0:
                    self.after(0, lambda: self._log("[SOVITS]   ✅ ffmpeg (via imageio-ffmpeg)"))
                else:
                    ff_path = subprocess.run(["ffmpeg", "-version"], capture_output=True, creationflags=0x08000000)
                    if ff_path.returncode == 0:
                        self.after(0, lambda: self._log("[SOVITS]   ✅ ffmpeg (sistema)"))
                    else:
                        self.after(0, lambda: self._log("[SOVITS]   ⚠️ ffmpeg não encontrado!"))

                # Baixar modelos pré-treinados
                self.after(0, lambda: self._log("[SOVITS] Baixando modelos pré-treinados..."))
                pretrained_dir = repo_dir / "GPT_SoVITS" / "pretrained_models"
                
                download_script = f"""
import os
from huggingface_hub import snapshot_download
pretrained = '{str(pretrained_dir).replace(chr(92), "/")}'

print("Baixando GPT-SoVITS models...")
snapshot_download('lj1995/GPT-SoVITS', local_dir=pretrained, ignore_patterns=['*.md','*.txt','.gitattributes'])

roberta_dir = os.path.join(pretrained, 'chinese-roberta-wwm-ext-large')
if not os.path.exists(os.path.join(roberta_dir, 'config.json')):
    print("Baixando chinese-roberta-wwm-ext-large...")
    snapshot_download('hfl/chinese-roberta-wwm-ext-large', local_dir=roberta_dir)

hubert_dir = os.path.join(pretrained, 'chinese-hubert-base')
if not os.path.exists(os.path.join(hubert_dir, 'config.json')):
    print("Baixando chinese-hubert-base...")
    snapshot_download('TencentGameMate/chinese-hubert-base', local_dir=hubert_dir)

print("OK: Todos os modelos baixados!")
"""
                subprocess.run([str(venv_python), "-m", "pip", "install", "--disable-pip-version-check", "huggingface_hub"], capture_output=True, creationflags=0x08000000)
                r = subprocess.run(
                    [str(venv_python), "-c", download_script],
                    capture_output=True, text=True, cwd=str(repo_dir), creationflags=0x08000000
                )
                if r.returncode == 0:
                    self.after(0, lambda: self._log("[SOVITS] ✅ Modelos pré-treinados baixados!"))
                else:
                    self.after(0, lambda: self._log(f"[SOVITS] ⚠️ Erro ao baixar modelos (pode ter parcial)"))

                self.after(0, lambda: self._log("[SOVITS] ✅ Servidor instalado!"))
                self.after(0, lambda: self._log("[SOVITS] Próximos passos:"))
                self.after(0, lambda: self._log("[SOVITS]   1. 📤 Importe áudio (.wav/.mp3)"))
                self.after(0, lambda: self._log("[SOVITS]   2. 🔥 Treine localmente (instala deps de treino automaticamente)"))
                self.after(0, lambda: self._log("[SOVITS]   3. ▶ Rode o servidor"))
                self.after(0, lambda: self.sovits_status.configure(text="Instalado!", text_color="#4ade80"))
                self.after(0, lambda: self._set_done("Servidor instalado"))
            except Exception as e:
                self.after(0, lambda: self._log(f"[ERRO] {e}"))
                self.after(0, lambda: self.sovits_status.configure(text="Erro", text_color="#f87171"))
                self.after(0, lambda: self._set_done("Erro na instalação", error=True))
        threading.Thread(target=_install, daemon=True).start()

    def _gerar_config_sovits(self):
        """Gera um tts_infer.yaml apontando pro modelo treinado mais recente (v2Pro).
        O api_v2.py (GPT-SoVITS) carrega os pesos do bloco 'custom' do config yaml na
        inicializacao. Se nao passarmos -c, ele usa o padrao (gsv-v2final, v2) — ou seja,
        NAO usa o modelo que acabamos de treinar. Retorna (caminho_do_yaml, nome) ou (None, None)."""
        sovits_dir = ROOT / "sovits-data"
        repo_dir = sovits_dir / "GPT-SoVITS"
        sow = repo_dir / "SoVITS_weights_v2Pro"
        gpw = repo_dir / "GPT_weights_v2Pro"
        if not sow.is_dir() or not gpw.is_dir():
            return None, None, None, None
        sovits_files = sorted(sow.glob("*.pth"), key=lambda p: p.stat().st_mtime, reverse=True)
        gpt_files = sorted(gpw.glob("*.ckpt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not sovits_files or not gpt_files:
            return None, None, None, None
        sovits = sovits_files[0]
        gpt = gpt_files[0]
        def _rel(p):
            return str(p.relative_to(repo_dir)).replace("\\", "/")
        import re as _re
        def _name(p):
            m = _re.match(r"(.+?)[_-]e\d+", p.stem)
            return m.group(1) if m else p.stem
        model_name = _name(sovits)
        custom = {
            "device": "cpu",
            "is_half": False,
            "version": "v2Pro",
            "t2s_weights_path": _rel(gpt),
            "vits_weights_path": _rel(sovits),
            "bert_base_path": "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large",
            "cnhuhbert_base_path": "GPT_SoVITS/pretrained_models/chinese-hubert-base",
        }
        yaml_lines = ["custom:"]
        for k, v in custom.items():
            yaml_lines.append(f"  {k}: {v}")
        temp = repo_dir / "TEMP"
        temp.mkdir(parents=True, exist_ok=True)
        cfg_path = temp / f"tts_infer_{model_name}.yaml"
        cfg_path.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
        return str(cfg_path), model_name, str(sovits), str(gpt)

    def _run_sovits_local(self):
        sovits_dir = ROOT / "sovits-data"
        repo_dir = sovits_dir / "GPT-SoVITS"
        venv_python = sovits_dir / "venv" / "Scripts" / "python.exe"

        if not (repo_dir / "api_v2.py").exists():
            self._log("[SOVITS] ❌ Servidor não instalado. Clique '📦 Instalar Servidor' primeiro.")
            return
        if not venv_python.exists():
            self._log("[SOVITS] ❌ Ambiente Python não encontrado.")
            return

        models = self._listar_modelos_sovits()
        if not models:
            self._log("[SOVITS] ⚠️ Nenhum modelo encontrado em sovits-data/")
            self._log("[SOVITS] Importe áudio (📤) e treine (🔥) ou importe modelo treinado.")

        if self.sovits_process and self.sovits_process.poll() is None:
            self._log("[SOVITS] Já está rodando."); return

        if self._is_port_open(SOVITS_PORT):
            self._log(f"[SOVITS] Porta {SOVITS_PORT} já em uso."); return

        # Gera config do modelo treinado (v2Pro) — assim o servidor usa o modelo treinado,
        # e não o padrão gsv-v2final/v2.
        cfg_path, trained_name, sovits_path, gpt_path = self._gerar_config_sovits()

        self._log(f"[SOVITS] Iniciando servidor na porta {SOVITS_PORT}...")
        if cfg_path:
            self._log(f"[SOVITS] 🎯 Usando modelo treinado '{trained_name}' (v2Pro)")
        else:
            self._log("[SOVITS] ⚠️ Nenhum modelo treinado encontrado — usando pesos padrão.")
        self._log("[SOVITS] ⏳ Aguarde... carregando modelos...")
        self._set_busy("Carregando servidor SoVITS...")

        # O GPT-SoVITS salva os pesos do GPT em meia precisao (float16) no
        # GPT_weights_v2Pro. Em CPU isso gera "Input type (FloatTensor) and
        # weight type (HalfTensor)". Converte p/ float32 antes de subir.
        convert_script = SCRIPTS / "fix_sovits_fp32.py"
        # Patch definitivo no TTS.py: forca .float() no modelo VITS e T2S quando
        # is_half=False (independente do dtype salvo no checkpoint). E a correcao
        # mais confiavel, pois o .pth do VITS nao pode ser lido por torch.load
        # (o servidor usa o load_sovits_new proprio do GPT-SoVITS).
        patch_script = SCRIPTS / "patch_sovits_float.py"
        tts_file = repo_dir / "GPT_SoVITS" / "TTS_infer_pack" / "TTS.py"
        api_file = repo_dir / "api_v2.py"

        def _start():
            try:
                # 1) Patch no TTS.py (forca todos os modelos p/ float32) e no api_v2.py (traceback)
                if patch_script.exists():
                    try:
                        self.after(0, lambda: self._log("[SOVITS] 🔧 Aplicando patch .float() no GPT-SoVITS (fix CPU)..."))
                        args = [str(venv_python), str(patch_script)]
                        if tts_file.exists():
                            args.append(str(tts_file))
                        if api_file.exists():
                            args.append(str(api_file))
                        pr = subprocess.run(
                            args,
                            capture_output=True, text=True, timeout=120, creationflags=0x08000000,
                            env=self._get_sovits_env()
                        )
                        for line in (pr.stdout or "").splitlines():
                            if line.strip():
                                self.after(0, lambda l=line: self._log(f"[SOVITS] {l}"))
                        if "PATCH_INCOMPLETO" in (pr.stdout or ""):
                            self.after(0, lambda: self._log("[SOVITS] ⚠️ Patch incompleto — veja acima. Modelo pode continuar em fp16."))
                    except Exception as e:
                        self.after(0, lambda: self._log(f"[SOVITS] ⚠️ Erro ao aplicar patch: {e}"))

                # 1b) Patch de suporte a PT-BR: instala GPT_SoVITS/text/portuguese.py
                #     (G2P pt) e habilita text_lang='pt' no cleaner/TTS/TextPreprocessor.
                pt_patch_script = SCRIPTS / "patch_sovits_pt.py"
                if pt_patch_script.exists():
                    try:
                        self.after(0, lambda: self._log("[SOVITS] 🔧 Aplicando patch PT-BR (G2P / text_lang=pt)..."))
                        pr_pt = subprocess.run(
                            [str(venv_python), str(pt_patch_script), str(repo_dir)],
                            capture_output=True, text=True, timeout=120, creationflags=0x08000000,
                            env=self._get_sovits_env()
                        )
                        for line in (pr_pt.stdout or "").splitlines():
                            if line.strip():
                                self.after(0, lambda l=line: self._log(f"[SOVITS] {l}"))
                        if "PATCH_OK" in (pr_pt.stdout or ""):
                            self.after(0, lambda: self._log("[SOVITS] ✅ Suporte a português ativado (text_lang=pt)."))
                        else:
                            self.after(0, lambda: self._log("[SOVITS] ⚠️ Patch PT incompleto — revisar mensagens acima."))
                    except Exception as e:
                        self.after(0, lambda: self._log(f"[SOVITS] ⚠️ Erro ao aplicar patch PT: {e}"))

                # 2) Garante o pacote torchcodec (torchaudio em versões novas exige p/ carregar áudio)
                if venv_python.exists():
                    try:
                        check = subprocess.run([str(venv_python), "-c", "import torchcodec"], capture_output=True, text=True, creationflags=0x08000000, timeout=60)
                        if check.returncode != 0:
                            self.after(0, lambda: self._log("[SOVITS] 📦 Instalando torchcodec (necessário p/ carregar áudio)..."))
                            subprocess.run(
                                [str(venv_python), "-m", "pip", "install", "--disable-pip-version-check",
                                 "--index-url", "https://download.pytorch.org/whl/cpu", "torchcodec"],
                                capture_output=True, text=True, creationflags=0x08000000, timeout=600
                            )
                            check2 = subprocess.run([str(venv_python), "-c", "import torchcodec"], capture_output=True, text=True, creationflags=0x08000000, timeout=60)
                            if check2.returncode == 0:
                                self.after(0, lambda: self._log("[SOVITS] ✅ torchcodec instalado."))
                            else:
                                self.after(0, lambda: self._log(f"[SOVITS] ⚠️ Falha ao instalar torchcodec: {(check2.stderr or '')[:200]}"))
                        else:
                            self.after(0, lambda: self._log("[SOVITS] ✅ torchcodec presente."))
                    except Exception as e:
                        self.after(0, lambda: self._log(f"[SOVITS] ⚠️ Erro ao checar torchcodec: {e}"))

                # 3) Conversao de pesos (caso o ckpt ainda esteja em fp16)
                if cfg_path and gpt_path and convert_script.exists():
                    try:
                        self.after(0, lambda: self._log(f"[SOVITS] 🔧 Ajustando pesos p/ float32 (fix CPU): {os.path.basename(gpt_path)} e {os.path.basename(sovits_path)}..."))
                        # O ckpt do GPT e o que costuma ter pesos fp16; passamos ELE primeiro
                        # (o script processa cada arquivo de forma independente — falha de um nao aborta o outro).
                        conv = subprocess.run(
                            [str(venv_python), str(convert_script), gpt_path, sovits_path],
                            capture_output=True, text=True, timeout=900, creationflags=0x08000000,
                            env=self._get_sovits_env()
                        )
                        for line in (conv.stdout or "").splitlines():
                            if line.strip():
                                self.after(0, lambda l=line: self._log(f"[SOVITS] {l}"))
                        if conv.returncode != 0:
                            self.after(0, lambda: self._log(f"[SOVITS] ⚠️ Falha ao converter: {(conv.stderr or '')[:400]}"))
                    except Exception as e:
                        self.after(0, lambda: self._log(f"[SOVITS] ⚠️ Erro ao converter fp32: {e}"))

                cmd = [str(venv_python), str(repo_dir / "api_v2.py"), "-a", "127.0.0.1", "-p", str(SOVITS_PORT)]
                if cfg_path:
                    cmd += ["-c", cfg_path]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1,
                    cwd=str(repo_dir), creationflags=0x08000000, env=self._get_sovits_env()
                )
                self.sovits_process = proc
                for line in proc.stdout:
                    line = line.decode("utf-8", errors="replace").rstrip()
                    if line: self.after(0, lambda l=line: self._log(f"[SOVITS] {l}"))
                proc.wait()
                self.after(0, lambda: self._log(f"[SOVITS] Servidor finalizou (código {proc.returncode})"))
                self.sovits_process = None
                self.after(0, lambda: self._set_done("Servidor parou", error=(proc.returncode != 0)))
            except Exception as e:
                self.after(0, lambda: self._log(f"[ERRO] {e}"))
                self.sovits_process = None
                self.after(0, lambda: self._set_done("Erro no servidor", error=True))
        threading.Thread(target=_start, daemon=True).start()

    def _parar_sovits(self):
        stopped = False
        if self.sovits_process and self.sovits_process.poll() is None:
            try: self.sovits_process.terminate(); self._log("[SOVITS] Parando servidor..."); stopped = True
            except Exception as e: self._log(f"[ERRO] {e}")
        self.sovits_process = None
        if self._kill_port_process(SOVITS_PORT):
            self._log(f"[SOVITS] Processo na porta {SOVITS_PORT} finalizado."); stopped = True
        if not stopped: self._log("[SOVITS] Nenhum servidor rodando.")
        self.after(500, self._atualizar_gating)

    def _importar_modelo_sovits(self):
        self._log("[SOVITS] Importar modelo...")
        self._log("[SOVITS] 💡 Pode importar áudio (.wav/.mp3) OU modelo treinado (.pth/.ckpt)")

        nome = ctk.CTkInputDialog(text="Nome do modelo (ex: minha_voz):", title="📤 Importar Modelo").get_input()
        if not nome: return
        nome = nome.strip().replace(" ", "_")
        if not nome:
            self._log("[ERRO] Nome inválido."); return

        sovits_dir = ROOT / "sovits-data"
        model_dir = sovits_dir / nome
        model_dir.mkdir(parents=True, exist_ok=True)

        files = filedialog.askopenfilenames(
            title=f"Selecione os arquivos do modelo '{nome}'",
            initialdir=self._last_audio_path,
            filetypes=[("Áudio/Modelo", "*.pth *.ckpt *.wav *.mp3 *.flac *.ogg"), ("Todos", "*.*")]
        )
        if not files:
            self._log("[SOVITS] Importação cancelada."); return
        self._last_audio_path = str(Path(files[0]).parent)

        for f in files:
            src = Path(f)
            dst = model_dir / src.name
            shutil.copy2(str(src), str(dst))
            self._log(f"[SOVITS] Copiado: {src.name}")

        self._log(f"[SOVITS] ✅ Modelo '{nome}' importado!")
        self._log(f"[SOVITS] Arquivos: {', '.join(p.name for p in model_dir.iterdir())}")

        if self.engine_var.get() == "sovits":
            self._update_voice_list()

    def _modelo_em_treino(self, nome):
        proc = self._training_procs.get(nome)
        return bool(proc and proc.poll() is None)

    def _paths_do_modelo(self, nome):
        """Retorna tudo que pertence a um modelo: áudio-fonte, logs de treino,
        pesos finais (SoVITS/GPT v2Pro) e a config temporária do servidor."""
        sovits_dir = ROOT / "sovits-data"
        repo_dir = sovits_dir / "GPT-SoVITS"
        paths = []
        src = sovits_dir / nome
        if src.is_dir():
            paths.append(src)
        logs = repo_dir / "logs" / nome
        if logs.is_dir():
            paths.append(logs)
        for root in (repo_dir / "SoVITS_weights_v2Pro", repo_dir / "GPT_weights_v2Pro"):
            if root.is_dir():
                for f in sorted(root.iterdir()):
                    if f.suffix.lower() in (".pth", ".ckpt", ".pt") and _stem_model_name(f.stem) == nome:
                        paths.append(f)
        cfg = repo_dir / "TEMP" / f"tts_infer_{nome}.yaml"
        if cfg.exists():
            paths.append(cfg)
        return paths

    def _paths_size(self, paths):
        total = 0
        for p in paths:
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        try:
                            total += f.stat().st_size
                        except OSError:
                            pass
        return total

    def _deletar_modelo_sovits(self):
        sovits_dir = ROOT / "sovits-data"
        repo_dir = sovits_dir / "GPT-SoVITS"
        if not sovits_dir.exists():
            self._log("[SOVITS] ⚠️ Nada para deletar (sovits-data/ não existe).")
            return
        candidates = set()
        for d in sorted(sovits_dir.iterdir()):
            if d.is_dir() and d.name not in ("venv", "GPT-SoVITS", "__pycache__"):
                candidates.add(d.name)
        logs_dir = repo_dir / "logs"
        if logs_dir.exists():
            for d in sorted(logs_dir.iterdir()):
                if d.is_dir():
                    candidates.add(d.name)
        models = sorted(candidates)
        if not models:
            self._log("[SOVITS] ⚠️ Nenhum modelo para deletar.")
            return
        opts = "\n".join(f"  {i+1} = {m}" for i, m in enumerate(models))
        escolha = ctk.CTkInputDialog(
            text=f"Escolha o modelo a DELETAR:\n\n{opts}",
            title="🗑️ Deletar Modelo"
        ).get_input()
        if not escolha or not escolha.strip():
            return
        escolha = escolha.strip()
        try:
            idx = int(escolha) - 1
            if 0 <= idx < len(models):
                nome = models[idx]
            else:
                self._log("[SOVITS] Opção inválida.")
                return
        except ValueError:
            nome = escolha
            if nome not in models:
                self._log(f"[SOVITS] ⚠️ Modelo '{nome}' não encontrado.")
                return
        self._confirmar_delecao_modelo(nome)

    def _confirmar_delecao_modelo(self, nome):
        if self._modelo_em_treino(nome):
            self._log(f"[SOVITS] ⚠️ Não posso deletar '{nome}' agora — está treinando. Pare o treino primeiro.")
            return
        paths = self._paths_do_modelo(nome)
        if not paths:
            self._log(f"[SOVITS] ✅ '{nome}' já não tem arquivos (nada a deletar).")
            self._update_voice_list()
            return
        total = self._paths_size(paths)
        servidor_usa = bool(self.sovits_process and self.sovits_process.poll() is None)
        voz_atual = self.engine_var.get() == "sovits" and self.voice_combo.get() == nome
        desc = "\n".join("  • " + str(p) for p in paths[:30])
        if len(paths) > 30:
            desc += f"\n  … e mais {len(paths) - 30} arquivo(s)."
        aviso = ""
        if servidor_usa or voz_atual:
            aviso = ("\n\n⚠️ O servidor SoVITS está rodando / este é o modelo de voz atual.\n"
                     "   Depois de deletar, pare e reinicie o servidor e escolha outra voz, se necessário.")
        ok = messagebox.askyesno(
            "🗑️ Deletar Modelo",
            f"Deletar o modelo '{nome}'?\n\nIsso apaga:\n{desc}\n\n"
            f"Total: {total/1024/1024:.1f} MB\n\nTem certeza?{aviso}"
        )
        if not ok:
            self._log("[SOVITS] Deleção cancelada.")
            return
        apagados = 0
        falhas = []
        for p in paths:
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                    apagados += 1
                elif p.exists():
                    p.unlink()
                    apagados += 1
            except OSError as e:
                falhas.append(f"{p.name}: {e}")
        self._log(f"[SOVITS] 🗑️ Modelo '{nome}' deletado ({apagados} itens).")
        if falhas:
            self._log("[SOVITS] ⚠️ Alguns arquivos não puderam ser apagados:")
            for f in falhas:
                self._log("[SOVITS]   - " + f)
        if self.engine_var.get() == "sovits":
            self._update_voice_list()
        self._refresh_status()
        self._refresh_training_status()

    def _treinar_sovits_local(self):
        """Treinamento 100% automático via script train_auto.py."""
        # Bloqueio: não treina voz enquanto a waifu estiver aberta
        if self._modo_atual() == "waifu":
            self._log("[SOVITS] ⛔ Pare/feche a waifu (Airi) antes de treinar uma voz. Os recursos estão com a waifu.")
            return
        sovits_dir = ROOT / "sovits-data"
        repo_dir = sovits_dir / "GPT-SoVITS"
        venv_python = sovits_dir / "venv" / "Scripts" / "python.exe"
        train_script = SCRIPTS / "train_auto.py"

        if not (repo_dir / "webui.py").exists():
            self._log("[SOVITS] ❌ Servidor não instalado. Clique '📦 Instalar Servidor' primeiro.")
            return
        if not venv_python.exists():
            self._log("[SOVITS] ❌ Ambiente Python não encontrado.")
            return

        # Check for partially trained models
        partial_models = []
        logs_dir = repo_dir / "logs"
        if logs_dir.exists():
            for d in sorted(logs_dir.iterdir()):
                if d.is_dir():
                    progress_file = d / ".training_progress.json"
                    if progress_file.exists():
                        try:
                            data = json.loads(progress_file.read_text(encoding="utf-8"))
                            step = data.get("step", 0)
                            names = {0: "Deps", 1: "Slice", 2: "ASR", 3: "Idioma", 4: "Dataset", 5: "SoVITS", 6: "GPT"}
                            partial_models.append({"name": d.name, "step": step, "step_name": names.get(step, "?")})
                        except:
                            partial_models.append({"name": d.name, "step": -1, "step_name": "?"})

        if partial_models:
            options = "Modelos parcialmente treinados:\n"
            for i, m in enumerate(partial_models):
                options += f"\n  {i+1} = {m['name']} (etapa {m['step']}: {m['step_name']})"
            options += f"\n  {len(partial_models)+1} = Treinar novo modelo"
            escolha = ctk.CTkInputDialog(text=options, title="🔥 Treinar Voz").get_input()
            if not escolha: return
            escolha = escolha.strip()
            try:
                idx = int(escolha) - 1
                if 0 <= idx < len(partial_models):
                    model_name = partial_models[idx]["name"]
                    model_dir = sovits_dir / model_name
                    self._log(f"[SOVITS] 🔄 Retomando treino de '{model_name}'...")
                    self._start_training(model_name, model_dir)
                    return
                elif idx == len(partial_models):
                    pass  # Fall through to new model
                else:
                    self._log("[SOVITS] Opção inválida."); return
            except ValueError:
                # User typed a name — treat as new model name
                nome = escolha.strip().replace(" ", "_")
                if not nome:
                    self._log("[ERRO] Nome inválido."); return
                # Check if model dir already exists
                model_dir = sovits_dir / nome
                if model_dir.exists():
                    audio_files = [f for f in model_dir.iterdir() if f.suffix.lower() in ('.wav', '.mp3', '.flac', '.ogg', '.m4a')]
                    if audio_files:
                        self._log(f"[SOVITS] 🔄 Retomando treino de '{nome}'...")
                        self._start_training(nome, model_dir)
                        return
                # New model — need audio files
                files = filedialog.askopenfilenames(
                    title=f"Selecione os áudios para treinar '{nome}'",
                    initialdir=self._last_audio_path,
                    filetypes=[("Áudio", "*.wav *.mp3 *.flac *.ogg *.m4a"), ("Todos", "*.*")]
                )
                if not files:
                    self._log("[SOVITS] Cancelado."); return
                self._last_audio_path = str(Path(files[0]).parent)
                model_dir.mkdir(parents=True, exist_ok=True)
                for f in files:
                    src = Path(f)
                    dst = model_dir / src.name
                    if not dst.exists():
                        shutil.copy2(str(src), str(dst))
                        self._log(f"[SOVITS] Copiado: {src.name}")
                self._escolher_imagem_modelo(nome)
                self._start_training(nome, model_dir)
                return

        # No partial models — new model flow
        nome = ctk.CTkInputDialog(
            text="Nome da voz (ex: minha_voz):",
            title="🔥 Treinar Voz"
        ).get_input()
        if not nome: return
        nome = nome.strip().replace(" ", "_")
        if not nome:
            self._log("[ERRO] Nome inválido."); return

        files = filedialog.askopenfilenames(
            title=f"Selecione os áudios para treinar '{nome}'",
            initialdir=self._last_audio_path,
            filetypes=[("Áudio", "*.wav *.mp3 *.flac *.ogg *.m4a"), ("Todos", "*.*")]
        )
        if not files:
            self._log("[SOVITS] Cancelado."); return
        self._last_audio_path = str(Path(files[0]).parent)

        model_dir = sovits_dir / nome
        model_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            src = Path(f)
            dst = model_dir / src.name
            if not dst.exists():
                shutil.copy2(str(src), str(dst))
                self._log(f"[SOVITS] Copiado: {src.name}")

        self._escolher_imagem_modelo(nome)
        self._start_training(nome, model_dir)

    # ============================================================
    # Testar / Salvar voz
    # ============================================================
    def _testar_voz(self):
        engine = self.engine_var.get()
        voice = self.voice_combo.get()
        pitch = int(self.pitch_slider.get())
        speed = round(self.speed_slider.get(), 2)

        # Montar voice_str baseado no engine
        if engine == "kokoro":
            voice_str = f"kokoro:{voice}"
            if pitch != 0: voice_str += f":{'+' if pitch > 0 else ''}{pitch}"
            if speed != 1.0: voice_str += f"@{speed}"
        elif engine == "sovits":
            voice_str = f"sovits:{voice}"
        else:
            voice_str = voice
            if pitch != 0: voice_str += f":{'+' if pitch > 0 else ''}{pitch}"
            if speed != 1.0: voice_str += f"@{speed}"

        self._log(f"[VOZ] Testando: {voice_str} (engine: {engine})")
        def _test():
            # SoVITS precisa de DOIS servidores: o bridge da waifu (9860) E o GPT-SoVITS (9880).
            # O bridge é quem o Airi fala; o SoVITS é o motor de clonagem. Para o teste, garantimos ambos.
            if engine == "sovits":
                if not self._is_port_open(VOICE_PORT):
                    self.after(0, lambda: self._log("[VOZ] Servidor de voz (9860) parado. Iniciando..."))
                    self.after(0, lambda: self._act_ligar_voz())
                    time.sleep(3)
                if not self._is_port_open(SOVITS_PORT):
                    self.after(0, lambda: self._log("[SOVITS] Servidor SoVITS (9880) parado. Iniciando e aguardando modelos..."))
                    self.after(0, lambda: self._run_sovits_local())
                    waited = 0
                    while not self._is_port_open(SOVITS_PORT) and waited < 240:
                        time.sleep(2)
                        waited += 2
                    if not self._is_port_open(SOVITS_PORT):
                        self.after(0, lambda: self._log("[SOVITS] ❌ Servidor SoVITS não subiu em 240s. Veja o log acima."))
                        return
                    time.sleep(3)  # dá um respiro pro servidor terminar de carregar

            timeout = 180 if engine == "sovits" else 30
            try:
                data = json.dumps({"model": "edge-tts", "input": "Oi! Eu sou a Lia, sua assistente pessoal. Tudo bem?", "voice": voice_str}).encode()
                req = urllib.request.Request(f"http://127.0.0.1:{VOICE_PORT}/v1/audio/speech", data=data, headers={"Content-Type": "application/json"})
                r = urllib.request.urlopen(req, timeout=timeout)
                audio_data = r.read()
                if HAS_PYGAME:
                    try:
                        pygame.mixer.music.load(io.BytesIO(audio_data))
                        pygame.mixer.music.play()
                        self.after(0, lambda: self._log("[VOZ] ▶ Tocando áudio..."))
                        while pygame.mixer.music.get_busy():
                            time.sleep(0.1)
                        self.after(0, lambda: self._log("[VOZ] ✅ Áudio finalizado"))
                    except Exception as e:
                        msg = str(e)
                        self.after(0, lambda: self._log(f"[VOZ] Erro pygame: {msg}"))
                        audio_file = ROOT / "teste_voz.mp3"
                        audio_file.write_bytes(audio_data)
                        self.after(0, lambda: os.startfile(str(audio_file)))
                else:
                    audio_file = ROOT / "teste_voz.mp3"
                    audio_file.write_bytes(audio_data)
                    self.after(0, lambda: self._log("[VOZ] Áudio gerado! Abrindo player..."))
                    self.after(0, lambda: os.startfile(str(audio_file)))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace").strip()
                ecode = e.code
                self.after(0, lambda: self._log(f"[ERRO] O servidor de voz respondeu HTTP {ecode}: {body[:400]}"))
            except Exception as e:
                msg = str(e)
                self.after(0, lambda: self._log(f"[ERRO] {msg}"))
        threading.Thread(target=_test, daemon=True).start()

    def _salvar_voz(self):
        voice = self.voice_combo.get()
        pitch = int(self.pitch_slider.get())
        speed = round(self.speed_slider.get(), 2)
        engine = self.engine_var.get()
        config = {"voice": voice, "pitch": pitch, "speed": speed, "engine": engine}
        config_file = ROOT / "voz_config.json"
        config_file.write_text(json.dumps(config, indent=2))
        self._log(f"[VOZ] Configuração salva: {voice} (pitch={pitch}, speed={speed}, engine={engine})")
        self._atualizar_resumo_voz()

    # ============================================================
    # Other actions
    # ============================================================
    def _iniciar_engines_da_waifu(self):
        """Sobe o servidor de voz relativo à engine selecionada (bridge 9860 sempre;
        se a engine for sovits, também o GPT-SoVITS 9880). Roda em thread p/ não travar a UI."""
        engine = self.engine_var.get()
        def _run():
            import time as _t
            # 1) Bridge (9860): é o que o Airi fala (edge/kokoro/proxy) — sempre necessário
            if not self._is_port_open(VOICE_PORT):
                self.after(0, lambda: self._log("[VOZ] Iniciando servidor de voz (bridge)..."))
                self.after(0, lambda: self._act_ligar_voz())
                waited = 0
                while not self._is_port_open(VOICE_PORT) and waited < 30:
                    _t.sleep(1); waited += 1
                self.after(0, lambda: self._log("[VOZ] ✅ Bridge pronto."))
            # 2) Se a engine for sovits, garantir o GPT-SoVITS (9880)
            if engine == "sovits" and not self._is_port_open(SOVITS_PORT):
                self.after(0, lambda: self._log("[SOVITS] Iniciando GPT-SoVITS (modelo clonado)..."))
                self.after(0, lambda: self._run_sovits_local())
                waited = 0
                while not self._is_port_open(SOVITS_PORT) and waited < 240:
                    _t.sleep(2); waited += 2
                _t.sleep(3)
                self.after(0, lambda: self._log("[SOVITS] ✅ GPT-SoVITS pronto para a waifu."))
            self.after(0, self._atualizar_gating)
        threading.Thread(target=_run, daemon=True).start()

    def _act_iniciar_waifu(self):
        """Inicia a waifu (somente o Tamagotchi/desktop).

        Sem o diálogo de escolha (web/abas foi removido — só usamos a versão
        desktop, que é o que a Lia usa). Fluxo:
          1. Sobe o servidor de voz da engine selecionada.
          2. Garante o AIRI instalado (baixa + pnpm se faltar).
          3. Abre o stage-tamagotchi.
          4. Auto-configura providers no AIRI via CDP.
        """
        # Bloqueio: não inicia a waifu enquanto houver treino em andamento
        if self._modo_atual() == "training":
            self._log("[AÇÃO] ⛔ Não posso iniciar a waifu durante o treino. Aguarde terminar.")
            return
        if self._waifu_busy:
            self._log("[AÇÃO] A waifu já está sendo iniciada/baixada... Aguarde.")
            return
        if self.other_process:
            self._log("[AÇÃO] Já existe um processo rodando. Aguarde finalizar.")
            return
        self._waifu_busy = True
        self._log("[AÇÃO] Iniciar Waifu (Tamagotchi)")
        threading.Thread(target=self._fluxo_iniciar_waifu, daemon=True).start()

    def _fluxo_iniciar_waifu(self):
        """Orquestra a subida da waifu (voz → AIRI → tamagotchi → auto-config)."""
        import time as _t
        engine = self.engine_var.get()

        # 1) Servidor de voz da engine selecionada (bridge; + GPT-SoVITS se sovits)
        self.after(0, lambda: self._log("[AÇÃO] Garantindo servidor de voz..."))
        self._iniciar_engines_da_waifu()
        waited = 0
        while not self._is_port_open(VOICE_PORT) and waited < 30:
            _t.sleep(1); waited += 1
        def _fim():
            self._waifu_busy = False

        if not self._is_port_open(VOICE_PORT):
            self.after(0, lambda: self._log("[ERRO] Servidor de voz não subiu em 30s. Aborte."))
            self.after(0, _fim)
            return
        self.after(0, lambda: self._log("[AÇÃO] ✅ Servidor de voz pronto."))

        if engine == "sovits" and not self._is_port_open(SOVITS_PORT):
            self.after(0, lambda: self._log("[SOVITS] Aguardando GPT-SoVITS (modelo clonado)..."))
            waited = 0
            while not self._is_port_open(SOVITS_PORT) and waited < 240:
                _t.sleep(2); waited += 2
            _t.sleep(3)

        # 2) Garante o AIRI instalado (baixa se faltar)
        def _clone_log(msg):
            self.after(0, lambda m=msg: self._log(m))
        if not _airi.install.ensure_airi(callback=_clone_log):
            self.after(0, lambda: self._log("[AÇÃO] ⛔ AIRI não instalado e o download falhou. Veja o log acima."))
            self.after(0, _fim)
            return
        # Sincroniza a página de boot (caso o web seja usado; inofensivo se não).
        self.after(0, lambda: self._log("[AÇÃO] Sincronizando agentai-boot.html no AIRI..."))
        _airi.boot.sync_boot_page()

        # 3) Abre o stage-tamagotchi (airi apps)
        self.after(0, lambda: self._run_script("iniciar_tamagotchi.ps1"))

        # 4) Aguarda carregar e auto-configura providers no AIRI (via CDP)
        _t.sleep(30)
        self.after(0, lambda: self._log("[CONFIG] Auto-configurando providers..."))
        self._auto_configurar_providers()
        self.after(0, self._atualizar_gating)

        # 5) Libera o fluxo (a waifu continuará aberta; modo vira 'waifu' pelo refresh)
        self.after(0, _fim)

    def _act_injetar_url(self):
        self._log("[AÇÃO] Injetar URL do túnel")
        url = None
        candidates = [ROOT / "ultima_url.txt", Path("G:/Meu Drive/AgentAI/memory/api_url.txt"), Path("G:/My Drive/AgentAI/memory/api_url.txt"), Path("H:/Meu Drive/AgentAI/memory/api_url.txt"), Path("H:/My Drive/AgentAI/memory/api_url.txt")]
        for f in candidates:
            try:
                content = f.read_text(encoding="utf-8").strip()
                match = re.search(r"https://[a-zA-Z0-9\-\.]+\.trycloudflare\.com", content)
                if match: url = match.group(0); self._log(f"[URL] Encontrada em: {f}"); break
            except: pass
        if not url:
            dialog = ctk.CTkInputDialog(text="Cole a URL do túnel:\n(ex: https://xxx.trycloudflare.com)", title="🔗 URL do Túnel")
            url = dialog.get_input()
            if not url: return
            url = url.strip()
            if not url.startswith("http"): url = "https://" + url
        import datetime
        cache_file = ROOT / "ultima_url.txt"
        cache_file.write_text(f"URL={url}\nSALVO={datetime.datetime.now().isoformat()}\n", encoding="utf-8")
        self._log(f"[URL] Salva: {url}")
        if not self._is_port_open(VOICE_PORT):
            self._log("[AVISO] Servidor de voz não está rodando. Iniciando...")
            self._act_ligar_voz()
            import time; time.sleep(3)
        self._auto_configurar_providers()

    def _act_configurar(self):
        self._log("[AÇÃO] Configurar Tamagotchi (auto)")
        self._auto_configurar_providers()

    def _act_diagnosticar(self):
        """Menu de diagnóstico com várias opções."""
        escolha = ctk.CTkInputDialog(
            text="O que diagnosticar?\n\n1 = Tudo\n2 = Servidores (voz + SoVITS + AIRI)\n3 = Voz (Edge/Kokoro/SoVITS)\n4 = SoVITS (deps + modelos)\n5 = Sistema (Python/Node/ffmpeg)\n6 = AIRI (Tamagotchi)",
            title="🔍 Diagnóstico"
        ).get_input()
        if not escolha: return
        escolha = escolha.strip()
        
        if escolha == "1":
            self._diag_tudo()
        elif escolha == "2":
            self._diag_servidores()
        elif escolha == "3":
            self._diag_voz()
        elif escolha == "4":
            self._diag_sovits()
        elif escolha == "5":
            self._diag_sistema()
        elif escolha == "6":
            self._diag_airi()
        else:
            self._log("[DIAG] Opção inválida. Use 1-6.")

    def _diag_tudo(self):
        """Executa todos os diagnósticos."""
        self._log("=" * 50)
        self._log("🔍 DIAGNÓSTICO COMPLETO")
        self._log("=" * 50)
        self._diag_sistema()
        self._diag_servidores()
        self._diag_voz()
        self._diag_sovits()
        self._diag_airi()
        self._log("=" * 50)
        self._log("🔍 DIAGNÓSTICO FINALIZADO")
        self._log("=" * 50)

    def _diag_sistema(self):
        """Verifica Python, Node.js, ffmpeg, Git."""
        self._log("")
        self._log("── SISTEMA ──")
        
        # Python
        self._log(f"[SISTEMA] Python: {sys.executable}")
        self._log(f"[SISTEMA] Versão: {sys.version.split()[0]}")
        
        # Node.js
        try:
            r = subprocess.run(["node", "--version"], capture_output=True, text=True, creationflags=0x08000000)
            if r.returncode == 0:
                self._log(f"[SISTEMA] Node.js: {r.stdout.strip()} ✅")
            else:
                self._log("[SISTEMA] Node.js: NÃO ENCONTRADO ❌")
        except:
            self._log("[SISTEMA] Node.js: NÃO ENCONTRADO ❌")
        
        # npm
        npm_cmd = None
        for candidate in ["npm", "npm.cmd"]:
            try:
                r = subprocess.run([candidate, "--version"], capture_output=True, text=True, creationflags=0x08000000)
                if r.returncode == 0: npm_cmd = candidate; break
            except: pass
        if npm_cmd:
            self._log(f"[SISTEMA] npm: {r.stdout.strip()} ✅")
        else:
            self._log("[SISTEMA] npm: NÃO ENCONTRADO ❌")
        
        # Git
        try:
            r = subprocess.run(["git", "--version"], capture_output=True, text=True, creationflags=0x08000000)
            if r.returncode == 0:
                self._log(f"[SISTEMA] Git: {r.stdout.strip()} ✅")
            else:
                self._log("[SISTEMA] Git: NÃO ENCONTRADO ❌")
        except:
            self._log("[SISTEMA] Git: NÃO ENCONTRADO ❌")
        
        # ffmpeg
        try:
            r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, creationflags=0x08000000)
            if r.returncode == 0:
                version = r.stdout.split('\n')[0] if r.stdout else "?"
                self._log(f"[SISTEMA] ffmpeg: {version[:60]} ✅")
            else:
                self._log("[SISTEMA] ffmpeg: NÃO ENCONTRADO ❌")
        except:
            self._log("[SISTEMA] ffmpeg: NÃO ENCONTRADO ❌")
        
        # node_modules
        nm = ROOT / "node_modules"
        if (nm / "msedge-tts").exists():
            self._log("[SISTEMA] node_modules/msedge-tts: ✅")
        else:
            self._log("[SISTEMA] node_modules/msedge-tts: ❌ (execute 'npm install msedge-tts')")

    def _diag_servidores(self):
        """Verifica status de todos os servidores."""
        self._log("")
        self._log("── SERVIDORES ──")
        
        # Voz
        voice = check_voice()
        if voice["up"]:
            self._log(f"[SERV] Voz (porta {VOICE_PORT}): ✅ Rodando (v{voice.get('version', '?')})")
        else:
            if self._is_port_open(VOICE_PORT):
                self._log(f"[SERV] Voz (porta {VOICE_PORT}): ⚠️ Porta ocupada mas não responde")
            else:
                self._log(f"[SERV] Voz (porta {VOICE_PORT}): ❌ Parado")
        
        # SoVITS
        if self._is_port_open(SOVITS_PORT):
            self._log(f"[SERV] SoVITS (porta {SOVITS_PORT}): ✅ Rodando")
        else:
            sovits_dir = ROOT / "sovits-data"
            if (sovits_dir / "GPT-SoVITS" / "api_v2.py").exists():
                self._log(f"[SERV] SoVITS (porta {SOVITS_PORT}): ⚠️ Instalado mas parado")
            else:
                self._log(f"[SERV] SoVITS (porta {SOVITS_PORT}): ❌ Não instalado")
        
        # AIRI
        aba = check_aba()
        if aba["up"]:
            self._log(f"[SERV] AIRI (porta {AIRI_PORT}): ✅ Rodando")
        else:
            self._log(f"[SERV] AIRI (porta {AIRI_PORT}): ❌ Parado")
        
        # Tamagotchi
        tama = check_tamagotchi()
        if tama["up"]:
            self._log(f"[SERV] Tamagotchi: ✅ Instalado")
        else:
            self._log(f"[SERV] Tamagotchi: ❌ Não instalado")

    def _diag_voz(self):
        """Diagnóstico detalhado do sistema de voz."""
        self._log("")
        self._log("── VOZ ──")
        
        # Script
        if VOICE_SCRIPT.exists():
            self._log(f"[VOZ] Script: {VOICE_SCRIPT} ✅")
        else:
            self._log(f"[VOZ] Script: {VOICE_SCRIPT} ❌ NÃO ENCONTRADO")
            return
        
        # Servidor rodando?
        voice = check_voice()
        if not voice["up"]:
            self._log("[VOZ] Servidor não está rodando! Clique '▶ Iniciar voz'")
            return
        
        self._log(f"[VOZ] Servidor: rodando (v{voice.get('version', '?')})")
        engines = voice.get("engines", [])
        self._log(f"[VOZ] Engines disponíveis: {', '.join(engines) if engines else 'nenhuma'}")
        
        # Testar Edge
        self._log("[VOZ] Testando Edge...")
        try:
            data = json.dumps({"model": "edge-tts", "input": "teste", "voice": "pt-BR-ThalitaNeural"}).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{VOICE_PORT}/v1/audio/speech", data=data, headers={"Content-Type": "application/json"})
            r = urllib.request.urlopen(req, timeout=10)
            audio = r.read()
            self._log(f"[VOZ] Edge: ✅ ({len(audio)} bytes)")
        except Exception as e:
            self._log(f"[VOZ] Edge: ❌ {e}")
        
        # Testar Kokoro
        kokoro_dir = ROOT / "kokoro-data"
        if (kokoro_dir / "kokoro-v1.0.onnx").exists():
            self._log("[VOZ] Kokoro: modelos encontrados ✅")
            try:
                data = json.dumps({"model": "edge-tts", "input": "teste", "voice": "kokoro:pf_dora"}).encode()
                req = urllib.request.Request(f"http://127.0.0.1:{VOICE_PORT}/v1/audio/speech", data=data, headers={"Content-Type": "application/json"})
                r = urllib.request.urlopen(req, timeout=15)
                audio = r.read()
                self._log(f"[VOZ] Kokoro: ✅ ({len(audio)} bytes)")
            except Exception as e:
                self._log(f"[VOZ] Kokoro: ❌ {e}")
        else:
            self._log("[VOZ] Kokoro: modelos não encontrados (instale via botão)")
        
        # Testar SoVITS
        if self._is_port_open(SOVITS_PORT):
            self._log("[VOZ] SoVITS: servidor rodando ✅")
            try:
                data = json.dumps({"model": "edge-tts", "input": "teste", "voice": "sovits:test"}).encode()
                req = urllib.request.Request(f"http://127.0.0.1:{VOICE_PORT}/v1/audio/speech", data=data, headers={"Content-Type": "application/json"})
                r = urllib.request.urlopen(req, timeout=15)
                self._log("[VOZ] SoVITS: ✅ respondeu")
            except Exception as e:
                self._log(f"[VOZ] SoVITS: ❌ {e}")
        else:
            self._log("[VOZ] SoVITS: servidor não rodando (inicie via botão)")

    def _diag_sovits(self):
        """Diagnóstico detalhado do GPT-SoVITS."""
        self._log("")
        self._log("── GPT-SoVITS ──")
        
        sovits_dir = ROOT / "sovits-data"
        repo_dir = sovits_dir / "GPT-SoVITS"
        venv_dir = sovits_dir / "venv"
        venv_python = venv_dir / "Scripts" / "python.exe"
        
        # Repo
        if (repo_dir / "api_v2.py").exists():
            self._log(f"[SOVITS] Repo: {repo_dir} ✅")
        else:
            self._log(f"[SOVITS] Repo: ❌ Não clonado (execute '📦 Instalar Servidor')")
            return
        
        # Venv
        if venv_python.exists():
            self._log(f"[SOVITS] Venv: {venv_python} ✅")
        else:
            self._log(f"[SOVITS] Venv: ❌ Não criado")
            return
        
        # Verificar TODAS as deps críticas
        self._log("[SOVITS] Verificando dependências no venv...")
        deps_to_check = [
            "torch", "numpy", "scipy", "librosa", "soundfile", "psutil",
            "transformers", "gradio", "matplotlib", "numba", "onnxruntime",
            "fastapi", "uvicorn", "pydantic", "safetensors", "huggingface_hub",
            "pytorch_lightning", "tensorboard", "nltk", "funasr", "opencc",
            "g2p_en", "jieba", "pypinyin", "cn2an", "modelscope",
            "ctranslate2", "av", "faster_whisper", "imageio_ffmpeg",
        ]
        ok_count = 0
        fail_list = []
        for pkg in deps_to_check:
            r = subprocess.run(
                [str(venv_python), "-c", f"import {pkg}"],
                capture_output=True, creationflags=0x08000000
            )
            if r.returncode == 0:
                ok_count += 1
            else:
                fail_list.append(pkg)
        
        self._log(f"[SOVITS] Dependências: {ok_count}/{len(deps_to_check)} OK")
        if fail_list:
            self._log(f"[SOVITS] ❌ Faltando: {', '.join(fail_list)}")
            self._log("[SOVITS] → Clique '📦 Instalar Servidor' para reinstalar")
        else:
            self._log("[SOVITS] ✅ Todas as dependências OK!")
        
        # Modelos pré-treinados
        pretrained = repo_dir / "GPT_SoVITS" / "pretrained_models"
        if pretrained.exists():
            files = list(pretrained.rglob("*.pth")) + list(pretrained.rglob("*.bin"))
            self._log(f"[SOVITS] Modelos pré-treinados: {len(files)} arquivos ✅")
        else:
            self._log("[SOVITS] Modelos pré-treinados: ❌ Não encontrados")
        
        # Modelos do usuário
        models = self._listar_modelos_sovits()
        if models:
            for m in models:
                model_dir = sovits_dir / m
                pth = list(model_dir.glob("*.pth"))
                ckpt = list(model_dir.glob("*.ckpt"))
                wav = list(model_dir.glob("*.wav")) + list(model_dir.glob("*.mp3"))
                parts = []
                if pth: parts.append(f"{len(pth)} .pth")
                if ckpt: parts.append(f"{len(ckpt)} .ckpt")
                if wav: parts.append(f"{len(wav)} áudio(s)")
                self._log(f"[SOVITS] Modelo '{m}': {', '.join(parts)}")
        else:
            self._log("[SOVITS] Modelos do usuário: nenhum (importe via 📤)")
        
        # Porta
        if self._is_port_open(SOVITS_PORT):
            self._log(f"[SOVITS] Porta {SOVITS_PORT}: em uso (servidor rodando?)")
        else:
            self._log(f"[SOVITS] Porta {SOVITS_PORT}: livre")

    def _diag_airi(self):
        """Diagnóstico do AIRI/Tamagotchi."""
        self._log("")
        self._log("── AIRI / TAMAGOTCHI ──")
        
        airi_dir = ROOT / "airi"
        if (airi_dir / "package.json").exists():
            self._log(f"[AIRI] Repo: {airi_dir} ✅")
        else:
            self._log(f"[AIRI] Repo: ❌ Não encontrado")
        
        # Scripts
        scripts_needed = ["atualizar_airi.ps1", "iniciar_tamagotchi.ps1", "configurar_tamagotchi.ps1"]
        for s in scripts_needed:
            path = SCRIPTS / s
            if path.exists():
                self._log(f"[AIRI] Script {s}: ✅")
            else:
                self._log(f"[AIRI] Script {s}: ❌ NÃO ENCONTRADO")
        
        # Voz config
        voz_config = ROOT / "voz_config.json"
        if voz_config.exists():
            try:
                j = json.loads(voz_config.read_text(encoding="utf-8"))
                self._log(f"[AIRI] voz_config.json: ✅ (engine={j.get('engine')}, voice={j.get('voice')})")
            except:
                self._log("[AIRI] voz_config.json: ⚠️ Erro ao ler")
        else:
            self._log("[AIRI] voz_config.json: não existe (será criado ao salvar voz)")
        
        # CDP
        if self._is_port_open(CDP_PORT):
            self._log(f"[AIRI] CDP (porta {CDP_PORT}): ✅ Disponível")
        else:
            self._log(f"[AIRI] CDP (porta {CDP_PORT}): ❌ Não disponível (Tamagotchi não está rodando?)")

        # Página de boot (agentai-boot.html) — deve existir no stage-web/public
        boot_ok = _airi.diag.boot_page()
        if boot_ok["ok"]:
            self._log("[AIRI] agentai-boot.html: ✅ presente e servido")
        else:
            self._log(f"[AIRI] agentai-boot.html: ⚠️ {boot_ok['detail']}")
            self._log("[AIRI]   (o Iniciar Waifu copia isso automaticamente)")

        # Binário do Electron (Tamagotchi)
        elec = _airi.diag.electron()
        if elec["ok"]:
            self._log("[AIRI] Electron (binário): ✅ pronto")
        else:
            self._log("[AIRI] Electron (binário): ⚠️ ausente (o iniciar_tamagotchi.ps1 baixa)")

    def _auto_configurar_providers(self):
        """Configura os providers/módulos do AIRI via CDP/localStorage.

        Usa o pacote lia.airi: monta o JavaScript (providers + speech +
        consciousness + vision), injeta pelo CDP do Electron, recarrega a
        página e loga o status de cada bloco. Também garante que o
        agentai-boot.html existe no stage-web/public.
        """
        def _configure():
            if not _airi.cdp.is_port_open(_airi.config.CDP_PORT):
                self.after(0, lambda: self._log(
                    "[CONFIG] AIRI nao esta rodando com CDP na porta %d.\n"
                    "         Inicie o Tamagotchi primeiro (botao Iniciar Waifu)." % _airi.config.CDP_PORT))
                return
            # Lê o config de voz (engine/voz/pitch/velocidade)
            voice_id, voice_engine, voice_pitch, voice_rate = self._ler_config_voz()
            speech_model = "edge-tts" if voice_engine != "sovits" else "sovits"
            voice_str = _airi.inject.build_voice_str(voice_engine, voice_id, voice_pitch, voice_rate)

            self.after(0, lambda: self._log(
                "[CONFIG] Engine: %s | Modelo: %s | Voz: %s" % (voice_engine, speech_model, voice_str)))

            # Garante a página de boot (o AIRI pode ter sido re-clonado)
            self.after(0, lambda: self._log("[CONFIG] Sincronizando agentai-boot.html..."))
            _airi.boot.sync_boot_page()

            # Injeta providers + speech + consciousness + vision
            self.after(0, lambda: self._log("[CONFIG] Injetando providers + speech + consciousness + vision..."))
            result = _airi.cdp.inject_all(
                active_model=speech_model,
                voice=voice_str,
                pitch=voice_pitch,
                rate=voice_rate,
            )
            inj = result.inject_value.strip()
            self.after(0, lambda i=inj or result.summary: self._log("[CONFIG] Injeção CDP: %s" % i))
            # Loga o que o AIRI leu de volta (prova de reconhecimento / depuração).
            v = result.verify or {}
            if v:
                self.after(0, lambda: self._log("[CONFIG] ▼ AIRI reconheceu (lido via CDP):"))
                for k in ("brain_base", "speech_base", "speech_provider", "speech_model",
                          "speech_voice", "cons_provider", "cons_model", "vis_provider", "vis_model"):
                    if k in v and v[k] is not None:
                        self.after(0, lambda kv=(k, v[k]): self._log("[CONFIG]   %s = %s" % kv))
            for line in result.output.splitlines():
                line = line.strip()
                if line:
                    self.after(0, lambda l=line: self._log("[CONFIG] %s" % l))
            if result.ok:
                self.after(0, lambda: self._log("[CONFIG] Chat: %s" % _airi.config.brain_url()))
                self.after(0, lambda: self._log("[CONFIG] Voz: %s (%s)" % (voice_str, _airi.config.speech_url())))
            else:
                self.after(0, lambda: self._log("[CONFIG] Falha. Tente: powershell scripts\configurar_tamagotchi.ps1"))
        threading.Thread(target=_configure, daemon=True).start()

    def _ler_config_voz(self):
        """Lê voz_config.json e devolve (voice, engine, pitch, rate).

        Mantém defaults seguros caso o arquivo não exista ou esteja corrompido.
        """
        voice_id = "pt-BR-ThalitaNeural"
        voice_engine = "edge"
        voice_pitch = 0
        voice_rate = 1.0
        voz_config_file = ROOT / "voz_config.json"
        if voz_config_file.exists():
            try:
                j = json.loads(voz_config_file.read_text(encoding="utf-8"))
                voice_id = j.get("voice", voice_id)
                voice_engine = j.get("engine", "edge")
                voice_pitch = int(j.get("pitch", 0))
                voice_rate = float(j.get("speed", 1.0))
            except Exception:
                pass
        return voice_id, voice_engine, voice_pitch, voice_rate

    def _run_script(self, script_name, args=None):
        if self.other_process:
            self._log("[SISTEMA] Já existe um processo rodando. Aguarde."); return
        script_path = SCRIPTS / script_name
        if not script_path.exists():
            self._log(f"[ERRO] Script não encontrado: {script_path}"); return
        self._log(f"[SISTEMA] Executando: {script_name}")
        def _exec():
            cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script_path)]
            if args: cmd.extend(args)
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, cwd=str(ROOT), creationflags=0x08000000)
                self.other_process = proc
                for line in proc.stdout:
                    line = line.rstrip()
                    if line: self.after(0, lambda l=line: self._log(l))
                proc.wait()
                self.after(0, lambda: self._log(f"[SISTEMA] Finalizado (código {proc.returncode})"))
                self.other_process = None
                self.after(2000, self._refresh_status)
            except Exception as e:
                self.after(0, lambda: self._log(f"[ERRO] {e}"))
                self.other_process = None
        threading.Thread(target=_exec, daemon=True).start()

# ============================================================
# Main
# ============================================================
def _parse_cli():
    """Interpreta argumentos de linha de comando (--debug, --dump)."""
    debug = "--debug" in sys.argv
    dump = "--dump" in sys.argv
    return debug, dump


if __name__ == "__main__":
    debug_mode, do_dump = _parse_cli()

    # Em modo debug, ligamos logs verbosos e não tentamos capturar stdout na GUI
    # (o logger do pacote lia/log já grava em arquivo); também geramos um dump de
    # contexto para depuração remota.
    if debug_mode:
        os.environ["LIA_GUI_CAPTURES_STDOUT"] = "1"
        _file_logger.debug("Modo DEBUG ativado")
        _file_logger.info(f"{APP_NAME} {APP_VERSION} iniciando (debug)")

    if not _check_single_instance():
        _bring_window_to_front()
        sys.exit(0)

    app = LiaApp()
    app._debug_mode = debug_mode
    app._debug_dump_requested = do_dump

    if debug_mode:
        _file_logger.info("Janela principal criada")

    def _maybe_dump():
        # Se --dump foi passado, gera o artefato logo após a UI estar pronta;
        # senão, só em modo debug grava o contexto em arquivo (não-UI).
        if getattr(app, "_debug_dump_requested", False):
            _file_logger.info("Gerando dump de depuração...")
            z = _dbg.write_dump(pad={"debug": True, "argv": sys.argv})
            _file_logger.info(f"Dump gerado: {z}")

    app.after(1200, _maybe_dump)
    app.mainloop()
