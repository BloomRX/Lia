# ============================================================
#  Lia App - Painel da Waifu (Desktop)  v55
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
ROOT = Path(__file__).parent.parent
SCRIPTS = ROOT / "scripts"
VOICE_SCRIPT = SCRIPTS / "servidor_voz_airi.js"
VOICE_PORT = 9860
AIRI_PORT = 5173
CDP_PORT = 9222
SOVITS_PORT = 9880
SOVITS_WEBUI_PORT = 9874
FLAG_FILE = ROOT / ".lia_app_configurado"


def _stem_model_name(stem):
    """Extrai o base name de um arquivo de peso (ex: 'lia_e8_s1920' ou 'lia-e20' -> 'lia')."""
    m = re.match(r"(.+?)[_-]e\d+", stem)
    return m.group(1) if m else stem


# ============================================================
# i18n (pt-BR / en) — termos "multilíngues" (Waifu, Online, Network,
# SoVITS, Engine, Tamagotchi, Kokoro) ficam iguais nos dois idiomas.
# ============================================================
LANGS = [("pt", "🇧🇷 Português"), ("en", "🇺🇸 English")]
LANG_KEYS = dict(LANGS)

L10N = {
    "pt": {
        "mode_idle": "IDENTE", "mode_training": "⛔ TREINANDO", "mode_waifu": "▲ WAIFU ATIVA",
        "status_voz": "Voz", "status_web": "Web", "status_sovits": "SoVITS", "status_tama": "Tamagotchi",
        "cta_start": "🚀 INICIAR WAIFU", "cta_training": "⛔ Treinando…",
        "menu_injetar": "🔗 Injetar URL", "menu_diag": "🔍 Diagnosticar", "menu_config": "⚙ Configurar",
        "menu_sovits": "🎤 Painel SoVITS", "menu_voice": "🎙️ Ajustar Voz",
        "stage_title": "Lia está aqui", "stage_hint": "Clique na Waifu para escolher o modelo",
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
        "palette": "🎨 Paleta:",
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
        "stage_title": "Lia is here", "stage_hint": "Click the Waifu to choose a model",
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
        "palette": "🎨 Palette:",
        "pronto": "Ready", "loading": "Loading", "off": "Off",
        "rodando": "Running", "instalado": "Installed", "nao_instalado": "Not installed",
        "aba": "Web", "online": "Online",
    },
}

# Paletas de cor (tema) — aplicadas às superfícies principais do app.
PALETTES = {
    # Paleta padrão da Lia verdadeira: vinho (roupa), preto carvão (casaco),
    # branco (camisa), rosa-avermelhado (cabelo), magenta (olhos), violeta (detalhe).
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

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_NAME = "Lia"
APP_VERSION = "v55"

# Caminho das assets (imagens do app). A arte real da Lia fica em:
#   app/assets/splash.png  -> arte exibida/presença central (splash)
#   app/assets/icon.png    -> se não houver .ico, é convertida p/ ícone (title bar/taskbar)
#   app/assets/icon.ico    -> ícone nativo (barra de tarefas / gerenciador de tarefas)
#   sovits-data/<modelo>/avatar.png -> avatar associado a um modelo de voz em treino
ASSETS_DIR = ROOT / "app" / "assets"

# Resoluções fixas (pequeno / médio / grande) — evita desalinhamento no resize.
SIZES = {
    "Pequeno": "880x580",
    "Medio": "1120x740",
    "Grande": "1360x880",
}
SIZE_DEFAULT = "Medio"

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
        # ── Identidade do app (nome/ícone no Windows) ──
        self._set_app_identity()
        self.voice_process = None
        self.other_process = None
        self.sovits_process = None
        self._child_pids = []  # PIDs de processos filhos pra cleanup
        self._last_audio_path = None  # Remember last audio selection directory
        self._training_procs = {}  # model_name -> Popen de treino ativo (pra não deletar em uso)
        # ── Estado operacional (evita conflitos) ──
        #   idle      -> nada rodando, tudo liberado
        #   training  -> um treino ativo: recursos vão pro treino (bloqueia iniciar waifu/voz/servidores)
        #   waifu     -> Airi aberto (aba ou tamagotchi): não pode treinar, mas pode configurar túnel/opções
        self.mode = "idle"
        self._btn = {}  # key -> CTkButton (pra habilitar/desabilitar via gating)
        self._aba_up = False   # cache do status da aba (atualizado em background)
        self._tama_up = False  # cache do status do tamagotchi
        # ── Painel de voz (drawer OVERLAY flutuante) ──
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
        # Console: manter a seta conforme o estado
        if hasattr(self, "_console_state"):
            arrow = " ▴" if self._console_state == "collapsed" else " ▾"
            self._console_toggle.configure(text=self._t("console") + arrow)
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
            self._btn["waifu"].configure(fg_color=p["accent"], hover_color=p["accent"])

    def _set_palette(self, name):
        self.palette = name
        self._apply_palette(name)
        self._save_prefs()

    # ------------------------------------------------------------------
    # Painel de voz lateral (drawer vertical colapsável)
    # ------------------------------------------------------------------
    def _expand_voice(self):
        self.voice_drawer_open = True
        # Ajusta a altura do overlay à janela atual para nunca cortar o conteúdo
        try:
            h = min(600, max(360, self.winfo_height() - 92))
            self.voice_drawer_body.configure(height=h)
        except Exception:
            pass
        # Traz para frente e anima o deslocamento x (fora -> dentro)
        self.voice_drawer_body.lift()
        self._voice_anim_to(0)

    def _collapse_voice(self):
        self.voice_drawer_open = False
        self._voice_anim_to(self._VOICE_W)

    def _voice_anim_to(self, target):
        """Anima o `x` do overlay (place). target=0 => aberto; target=W => fora da tela."""
        if self._voice_anim_job:
            try:
                self.after_cancel(self._voice_anim_job)
            except Exception:
                self._voice_anim_job = None
        body = self.voice_drawer_body
        try:
            cur = int(body.place_info().get("x", self._VOICE_W))
        except Exception:
            cur = self._VOICE_W
        dist = target - cur
        if dist == 0:
            body.place_configure(relx=1.0, rely=0.0, x=target, y=64, anchor="ne")
            return
        steps = max(1, int(abs(dist) / 7))  # ~7px por passo => rápido
        step = dist / steps
        def _step(remaining):
            cur2 = int(body.place_info().get("x", self._VOICE_W))
            nx = cur2 + step
            if (step < 0 and nx < target) or (step > 0 and nx > target):
                nx = target
            body.place_configure(relx=1.0, rely=0.0, x=int(nx), y=64, anchor="ne")
            if abs(nx - target) < 1 or remaining <= 1:
                body.place_configure(relx=1.0, rely=0.0, x=int(target), y=64, anchor="ne")
                self._voice_anim_job = None
                return
            self._voice_anim_job = self.after(6, lambda: _step(remaining - 1))
        _step(steps)

    def _toggle_voice_drawer(self):
        if self.voice_drawer_open:
            self._voice_pinned = False
            self._collapse_voice()
        else:
            self._voice_pinned = True
            self._expand_voice()

    def _build_ui(self):
        # ============================================================
        # HEADER (status bar) — logo + idioma + paleta + LEDs + modo
        # ============================================================
        self._surfaces.clear()
        status_bar = ctk.CTkFrame(self, corner_radius=0, height=64, fg_color=PALETTES[self.palette]["head"])
        status_bar.pack(fill="x", padx=0, pady=0)
        status_bar.pack_propagate(False)
        self._surfaces.append((status_bar, "head"))

        logo_frame = ctk.CTkFrame(status_bar, fg_color="transparent")
        logo_frame.pack(side="left", padx=16)
        ctk.CTkLabel(logo_frame, text="🌸 " + APP_NAME, font=("", 22, "bold"), text_color="#f5f5f5").pack(side="left")
        ctk.CTkLabel(logo_frame, text=" " + APP_VERSION, font=("", 10), text_color="gray").pack(side="left", padx=(2, 0))

        # Seletor de idioma (bandeira)
        self.lang_combo = ctk.CTkComboBox(status_bar, values=list(LANG_KEYS.values()),
                                          width=130, font=("", 10), state="normal",
                                          command=self._on_lang_change)
        self.lang_combo.pack(side="left", padx=(8, 0))
        self.lang_combo.set(LANG_KEYS[self.lang])

        # Seletor de paleta
        self.palette_combo = ctk.CTkComboBox(status_bar, values=list(PALETTE_LABELS.values()),
                                             width=140, font=("", 10), state="normal",
                                             command=self._on_palette_change)
        self.palette_combo.pack(side="left", padx=(6, 0))
        self.palette_combo.set(PALETTE_LABELS.get(self.palette, self.palette))

        # Seletor de resolução (tamanho fixo)
        self.size_combo = ctk.CTkComboBox(status_bar, values=list(SIZES.keys()),
                                          width=96, font=("", 10), state="normal",
                                          command=self._on_size_change)
        self.size_combo.pack(side="left", padx=(6, 0))
        self.size_combo.set(self.size_key)

        # LED status cards
        status_cards = ctk.CTkFrame(status_bar, fg_color="transparent")
        status_cards.pack(side="left", fill="x", expand=True, padx=20)
        self.st_voice = self._make_status_card(status_cards, "🎙️", self._t("status_voz"), "off", key="status_voz")
        self.st_aba = self._make_status_card(status_cards, "🌐", self._t("status_web"), "off", key="status_web")
        self.st_sovits = self._make_status_card(status_cards, "🎤", self._t("status_sovits"), "off", key="status_sovits")
        self.st_tama = self._make_status_card(status_cards, "🖥️", self._t("status_tama"), "off", key="status_tama")
        for i, k in enumerate(["status_voz", "status_web", "status_sovits", "status_tama"]):
            pass  # labels já traduzidos no _make_status_card

        # Badge de modo operacional
        self.mode_badge = ctk.CTkLabel(status_bar, text=self._t("mode_idle"), font=("", 11, "bold"),
                                       text_color="#e5e7eb", corner_radius=10, fg_color=PALETTES[self.palette]["panel"])
        self.mode_badge.pack(side="right", padx=16)

        # ============================================================
        # MAIN — left controls | center stage+console | right voice drawer
        # ============================================================
        main = ctk.CTkFrame(self, fg_color=PALETTES[self.palette]["bg"])
        main.pack(fill="both", expand=True, padx=8, pady=8)
        self._surfaces.append((main, "bg"))

        # ---------- LEFT: control panel (launcher) ----------
        left = ctk.CTkFrame(main, width=300, corner_radius=12, fg_color=PALETTES[self.palette]["bg"])
        left.pack(side="left", fill="y", padx=(0, 6))
        left.pack_propagate(False)
        self._surfaces.append((left, "bg"))

        # Título do painel
        ctk.CTkLabel(left, text="LIA CONTROL", font=("", 13, "bold"), text_color=PALETTES[self.palette]["accent2"]).pack(anchor="w", padx=14, pady=(14, 4))

        # Opções secundárias (engrenagem) — ações de manutenção
        self._btn["options"] = ctk.CTkButton(
            left, text="⚙ ", command=self._toggle_options_menu, height=30, corner_radius=8,
            font=("", 11), fg_color="#1f2937", hover_color="#374151", anchor="w")
        self._btn["options"].pack(fill="x", padx=12, pady=4)
        self.options_menu = ctk.CTkToplevel(self)
        self.options_menu.title("⚙")
        self.options_menu.geometry("240x220")
        self.options_menu.withdraw()
        self.options_menu.attributes("-topmost", True)
        self.options_menu.configure(fg_color="#0f172a")
        self._make_button(self.options_menu, self._t("menu_injetar"), self._act_injetar_url, key="url", ikey="menu_injetar")
        self._make_button(self.options_menu, self._t("menu_diag"), self._act_diagnosticar, key="diag", ikey="menu_diag")
        self._make_button(self.options_menu, self._t("menu_config"), self._act_configurar, key="config", ikey="menu_config")
        self._make_button(self.options_menu, self._t("menu_voice"), self._toggle_voice_drawer, key="menu_voice", ikey="menu_voice")
        self._make_button(self.options_menu, self._t("menu_sovits"), self._show_sovits_panel, key="menu_sovits", ikey="menu_sovits")

        ctk.CTkFrame(left, height=1, fg_color=PALETTES[self.palette]["line"]).pack(fill="x", padx=12, pady=6)

        # Resumo de status da voz (compacto)
        self.voz_summary = ctk.CTkLabel(left, text="", font=("", 10), text_color="gray", anchor="w", wraplength=260, justify="left")
        self.voz_summary.pack(anchor="w", padx=14, pady=(2, 6))
        self.sovits_status = ctk.CTkLabel(left, text="SoVITS: ...", font=("", 10), text_color="gray", anchor="w", wraplength=260, justify="left")
        self.sovits_status.pack(anchor="w", padx=14, pady=(0, 6))

        ctk.CTkFrame(left, height=1, fg_color=PALETTES[self.palette]["line"]).pack(fill="x", padx=12, pady=6)

        # Especificações / dica
        self._stage_hint2_lbl = ctk.CTkLabel(left, text=self._t("stage_hint2"), font=("", 10), text_color="gray", anchor="w", wraplength=260, justify="left")
        self._stage_hint2_lbl.pack(anchor="w", padx=14, pady=4)

        # Empurra o botão principal para o rodapé (estilo launcher)
        ctk.CTkFrame(left, fg_color="transparent").pack(fill="both", expand=True)

        # ---------- BOTTOM-LEFT: INICIAR WAIFU ----------
        cta_row = ctk.CTkFrame(left, fg_color="transparent")
        cta_row.pack(fill="x", padx=10, pady=(6, 12))
        self._btn["waifu"] = ctk.CTkButton(
            cta_row, text=self._t("cta_start"), command=self._act_iniciar_waifu,
            font=("", 15, "bold"), height=48, corner_radius=8,
            fg_color=PALETTES[self.palette]["accent"], hover_color=PALETTES[self.palette]["accent"],
            text_color="#ffffff")
        self._btn["waifu"].pack(fill="x", expand=True)

        # ---------- CENTER: stage + console ----------
        center = ctk.CTkFrame(main, corner_radius=12, fg_color=PALETTES[self.palette]["bg"])
        center.pack(side="left", fill="both", expand=True, padx=6)
        self._surfaces.append((center, "bg"))

        # Palco (splash art da waifu) — clique abre o selecionador de modelo
        self.stage = ctk.CTkFrame(center, fg_color=PALETTES[self.palette]["panel"], corner_radius=12, cursor="hand2")
        self.stage.pack(fill="both", expand=True, padx=8, pady=8)
        self.stage.pack_propagate(False)
        self._surfaces.append((self.stage, "panel"))
        self.stage.bind("<Button-1>", lambda e: self._open_model_selector())

        splash = self._load_splash()
        if splash is not None:
            self._stage_label = ctk.CTkLabel(self.stage, image=splash, text="")
        else:
            self._stage_label = ctk.CTkLabel(self.stage, text="🌸", font=("", 90))
        self._stage_label.pack(expand=True)
        self._stage_label.bind("<Button-1>", lambda e: self._open_model_selector())

        self.stage_title = ctk.CTkLabel(self.stage, text=f"{self._personagem_atual}", font=("", 20, "bold"), text_color="#e5e7eb")
        self.stage_title.pack(expand=True)
        self.stage_title.bind("<Button-1>", lambda e: self._open_model_selector())
        self.stage_hint = ctk.CTkLabel(self.stage, text=self._t("stage_hint"), font=("", 11), text_color="gray")
        self.stage_hint.pack()
        self.stage_hint.bind("<Button-1>", lambda e: self._open_model_selector())

        # Console (log) recolhível / ocultável — fixo na base (não some)
        self.console_frame = ctk.CTkFrame(center, fg_color=PALETTES[self.palette]["console"], corner_radius=10)
        self._surfaces.append((self.console_frame, "console"))
        self.console_frame.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        self.console_frame.pack_propagate(False)
        self.console_frame.configure(height=160)
        console_header = ctk.CTkFrame(self.console_frame, fg_color="transparent", height=32)
        console_header.pack(fill="x", padx=8, pady=(6, 0))
        self._console_toggle = ctk.CTkButton(console_header, text=self._t("console") + " ▾", command=self._toggle_console,
                                             width=140, height=24, font=("", 10), fg_color="transparent",
                                             hover_color="#26262e", text_color="#9ca3af")
        self._console_toggle.pack(side="left")
        self.log_status_label = ctk.CTkLabel(console_header, text="⏸ " + self._t("pronto"), font=("", 10), text_color="#9ca3af")
        self.log_status_label.pack(side="left", padx=8)
        self._btn_clear_log = ctk.CTkButton(console_header, text=self._t("console_clear"), command=self._clear_log,
                                            width=30, height=24, font=("", 11), fg_color="transparent",
                                            hover_color="#26262e", text_color="#f87171")
        self._btn_clear_log.pack(side="right")
        self._btn_hide_log = ctk.CTkButton(console_header, text=self._t("console_hide"), command=self._hide_console,
                                           width=30, height=24, font=("", 11), fg_color="transparent",
                                           hover_color="#26262e", text_color="#9ca3af")
        self._btn_hide_log.pack(side="right", padx=(0, 4))
        self.log_progress_label = ctk.CTkLabel(console_header, text="", font=("", 10), text_color="#9ca3af")
        self.log_progress_label.pack(side="right", padx=(0, 6))

        self.log_text = ctk.CTkTextbox(self.console_frame, font=("Consolas", 10), wrap="word", height=6)
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self._console_state = "open"
        self._console_footer = ctk.CTkButton(center, text="▤", command=self._restore_console, width=34, height=24,
                                             font=("", 12), fg_color=PALETTES[self.palette]["console"],
                                             hover_color="#26262e", text_color="#9ca3af")

        # ---------- RIGHT: voice drawer (OVERLAY flutuante acima do fundo) ----------
        self._VOICE_W = 320
        # Indicador vertical discreto (gatilho) — flutuante, não mexe no layout
        self.voice_strip = ctk.CTkFrame(self, width=40, corner_radius=12, fg_color=PALETTES[self.palette]["panel"])
        self.voice_strip.place(relx=1.0, rely=0.40, x=-52, y=0, anchor="ne")
        self.voice_strip.configure(height=220)
        self.voice_strip.pack_propagate(False)
        self._surfaces.append((self.voice_strip, "panel"))
        mic = ctk.CTkLabel(self.voice_strip, text="🎙️", font=("", 16), cursor="hand2")
        mic.pack(anchor="center", pady=(34, 8))
        mic.bind("<Button-1>", lambda e: self._toggle_voice_drawer())
        self.voice_strip.bind("<Button-1>", lambda e: self._toggle_voice_drawer())
        for ch in "VOZ":
            ctk.CTkLabel(self.voice_strip, text=ch, font=("", 12, "bold"),
                         text_color=PALETTES[self.palette]["accent2"]).pack(anchor="center")
        self.voice_model_icon = ctk.CTkLabel(self.voice_strip, text="🎤", font=("", 12), text_color="gray")
        self.voice_model_icon.pack(anchor="center", pady=(10, 0))
        self.voice_strip.bind("<Enter>", lambda e: self._on_voice_enter())
        self.voice_strip.bind("<Leave>", lambda e: self.after(280, self._voice_maybe_collapse))

        # Corpo do drawer (configurações) — overlay colocado sobre a janela
        self.voice_drawer_body = ctk.CTkFrame(self, width=self._VOICE_W, corner_radius=14,
                                              fg_color=PALETTES[self.palette]["panel"])
        self.voice_drawer_body.pack_propagate(False)
        self._surfaces.append((self.voice_drawer_body, "panel"))
        self.voice_drawer_body.place(relx=1.0, rely=0.0, x=self._VOICE_W, y=64, anchor="ne")  # fora da tela
        self.voice_drawer_body.bind("<Enter>", lambda e: self._on_voice_enter())
        self.voice_drawer_body.bind("<Leave>", lambda e: self.after(280, self._voice_maybe_collapse))

        # Cabeçalho do body
        self._btn["drawer"] = ctk.CTkButton(self.voice_drawer_body, text="◂ Fechar", command=self._toggle_voice_drawer,
                                            width=300, height=28, font=("", 10), fg_color="transparent",
                                            hover_color="#26262e", text_color="#9ca3af")
        self._btn["drawer"].pack(fill="x", padx=10, pady=(10, 0))
        self._voice_title_lbl = ctk.CTkLabel(self.voice_drawer_body, text=self._t("voice_title"), font=("", 13, "bold"), text_color=PALETTES[self.palette]["accent2"])
        self._voice_title_lbl.pack(anchor="w", padx=14, pady=(2, 4))

        # Engine
        engine_frame = ctk.CTkFrame(self.voice_drawer_body, fg_color="transparent")
        engine_frame.pack(fill="x", padx=14, pady=4)
        self._engine_lbl = ctk.CTkLabel(engine_frame, text=self._t("voice_engine"), font=("", 11, "bold"))
        self._engine_lbl.pack(anchor="w")
        self.engine_var = ctk.StringVar(value="edge")
        self.engine_combo = ctk.CTkComboBox(engine_frame, values=["edge", "kokoro", "sovits"],
                                            variable=self.engine_var, width=286,
                                            command=lambda _: self._update_voice_list())
        self.engine_combo.pack(pady=4)
        self.engine_combo.set("edge")

        # Kokoro install (só kokoro)
        self.kokoro_frame = ctk.CTkFrame(self.voice_drawer_body, fg_color="transparent")
        self.kokoro_frame.pack(fill="x", padx=14, pady=4)
        self._kokoro_btn = ctk.CTkButton(self.kokoro_frame, text=self._t("voice_install_kokoro"), command=self._instalar_kokoro, width=130, fg_color="#6b21a8", hover_color="#7c3aed", height=28)
        self._kokoro_btn.pack(side="left")
        self.kokoro_status = ctk.CTkLabel(self.kokoro_frame, text="", font=("", 9), text_color="gray")
        self.kokoro_status.pack(side="left", padx=6)

        # Voz
        self._voice_lbl = ctk.CTkLabel(self.voice_drawer_body, text=self._t("voice_voice"), font=("", 11, "bold"))
        self._voice_lbl.pack(anchor="w", padx=14, pady=(8, 2))
        self.voice_combo = ctk.CTkComboBox(self.voice_drawer_body, values=["pt-BR-ThalitaNeural"], width=286)
        self.voice_combo.pack(padx=14, pady=2)
        self.voice_combo.set("pt-BR-ThalitaNeural")

        # Pitch (edge)
        self.pitch_frame = ctk.CTkFrame(self.voice_drawer_body, fg_color="transparent")
        self._pitch_lbl = ctk.CTkLabel(self.pitch_frame, text=self._t("voice_pitch"), font=("", 11, "bold"))
        self._pitch_lbl.pack(anchor="w", padx=14, pady=(8, 2))
        pitch_slider_row = ctk.CTkFrame(self.pitch_frame, fg_color="transparent")
        pitch_slider_row.pack(fill="x", padx=14)
        self.pitch_slider = ctk.CTkSlider(pitch_slider_row, from_=-50, to=50, number_of_steps=100, width=220)
        self.pitch_slider.pack(side="left")
        self.pitch_slider.set(0)
        self.pitch_label = ctk.CTkLabel(pitch_slider_row, text="0", font=("", 11), width=30)
        self.pitch_label.pack(side="left", padx=4)
        self.pitch_slider.configure(command=lambda v: self.pitch_label.configure(text=str(int(v))))

        # Velocidade
        self.speed_frame = ctk.CTkFrame(self.voice_drawer_body, fg_color="transparent")
        self._speed_lbl = ctk.CTkLabel(self.speed_frame, text=self._t("voice_speed"), font=("", 11, "bold"))
        self._speed_lbl.pack(anchor="w", padx=14, pady=(8, 2))
        speed_slider_row = ctk.CTkFrame(self.speed_frame, fg_color="transparent")
        speed_slider_row.pack(fill="x", padx=14)
        self.speed_slider = ctk.CTkSlider(speed_slider_row, from_=0.5, to=2.0, number_of_steps=30, width=220)
        self.speed_slider.pack(side="left")
        self.speed_slider.set(1.0)
        self.speed_label = ctk.CTkLabel(speed_slider_row, text="1.0", font=("", 11), width=30)
        self.speed_label.pack(side="left", padx=4)
        self.speed_slider.configure(command=lambda v: self.speed_label.configure(text=f"{v:.1f}"))

        # Iniciar / Parar voz (para testes / recuperação)
        srv_row = ctk.CTkFrame(self.voice_drawer_body, fg_color="transparent")
        srv_row.pack(fill="x", padx=14, pady=(12, 4))
        self._btn["voz_on"] = ctk.CTkButton(srv_row, text=self._t("voice_start"), command=self._act_ligar_voz, width=130, height=30)
        self._btn["voz_on"].pack(side="left", padx=2)
        self._btn["voz_off"] = ctk.CTkButton(srv_row, text=self._t("voice_stop"), command=self._act_parar_voz, width=130, height=30, fg_color="#7f1d1d", hover_color="#991b1b")
        self._btn["voz_off"].pack(side="left", padx=2)

        # Testar / Salvar
        btn_frame = ctk.CTkFrame(self.voice_drawer_body, fg_color="transparent")
        btn_frame.pack(fill="x", padx=14, pady=(8, 8))
        self._btn["test_voz"] = ctk.CTkButton(btn_frame, text=self._t("voice_test"), command=self._testar_voz, width=150, height=32)
        self._btn["test_voz"].pack(side="left", padx=4)
        self._btn["salvar"] = ctk.CTkButton(btn_frame, text=self._t("voice_save"), command=self._salvar_voz, width=90, height=32)
        self._btn["salvar"].pack(side="left", padx=4)

        self.voz_status = ctk.CTkLabel(self.voice_drawer_body, text="...", font=("", 9), text_color="gray", wraplength=240)
        self.voz_status.pack(anchor="w", padx=14, pady=(0, 10))

        # Estado inicial: drawer colapsado; controles da engine padrão prontos
        self._collapse_voice()
        self._update_voice_list()
        self._apply_palette(self.palette)

        # Registo i18n dos widgets criados inline (botões/labels traduzíveis)
        self._reg("cta_start", self._btn["waifu"])
        self._reg("stage_hint", self.stage_hint)
        self._reg("stage_hint2", getattr(self, "_stage_hint2_lbl", self.stage_hint))
        self._reg("voice_title", self._voice_title_lbl)
        self._reg("voice_engine", self._engine_lbl)
        self._reg("voice_voice", self._voice_lbl)
        self._reg("voice_pitch", self._pitch_lbl)
        self._reg("voice_speed", self._speed_lbl)
        self._reg("voice_install_kokoro", self._kokoro_btn)
        self._reg("voice_start", self._btn["voz_on"])
        self._reg("voice_stop", self._btn["voz_off"])
        self._reg("voice_test", self._btn["test_voz"])
        self._reg("voice_save", self._btn["salvar"])
        self._reg("console_clear", self._btn_clear_log)
        self._reg("console_hide", self._btn_hide_log)

    def _on_voice_enter(self):
        # Abre rápido quando o mouse encosta no indicador ou no painel
        self._expand_voice()

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
        # Considera 'dentro' se o ponteiro estiver sobre o painel OU o indicador
        return not (self._pointer_dentro(self.voice_drawer_body) or self._pointer_dentro(self.voice_strip))

    def _voice_maybe_collapse(self):
        if not self._voice_pinned and self.voice_drawer_open and self._voice_outside_now():
            self._collapse_voice()

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

    def _open_model_selector(self):
        win = ctk.CTkToplevel(self)
        win.title(self._t("model_title"))
        win.geometry("360x260")
        win.attributes("-topmost", True)
        win.grab_set()
        ctk.CTkLabel(win, text=self._t("model_title"), font=("", 15, "bold")).pack(pady=(18, 8))
        for nome in self._personagens:
            def _pick(n=nome):
                self._personagem_atual = n
                self.stage_title.configure(text=n)
                win.destroy()
                self._log(f"[MODEL] Personagem: {n}")
            ctk.CTkButton(win, text=nome, command=_pick, width=200, height=34,
                          fg_color=PALETTES[self.palette]["panel"], hover_color="#26262e").pack(pady=4)
        ctk.CTkLabel(win, text=self._t("model_placeholder"), font=("", 9), text_color="gray").pack(pady=(10, 8))

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
        except Exception:
            pass

    def _toggle_console(self):
        if self._console_state == "open":
            self._console_state = "collapsed"
            self.log_text.pack_forget()
            self.console_frame.configure(height=34)
            self._console_toggle.configure(text=self._t("console") + " ▴")
        else:
            self._console_state = "open"
            if not self.console_frame.winfo_ismapped():
                self.console_frame.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
            self.console_frame.configure(height=160)
            self.log_text.pack(fill="both", expand=True, padx=8, pady=(4, 8))
            self._console_toggle.configure(text=self._t("console") + " ▾")

    def _hide_console(self):
        self._console_state = "hidden"
        self.console_frame.pack_forget()
        self._console_footer.pack(side="bottom", anchor="e", padx=8, pady=(0, 8))

    def _restore_console(self, show_log=True):
        self._console_footer.pack_forget()
        self.console_frame.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        self._console_state = "open" if show_log else "collapsed"
        if show_log:
            self.console_frame.configure(height=160)
            self.log_text.pack(fill="both", expand=True, padx=8, pady=(4, 8))
            self._console_toggle.configure(text=self._t("console") + " ▾")
        else:
            self.console_frame.configure(height=34)
            self._console_toggle.configure(text=self._t("console") + " ▴")

    # ------------------------------------------------------------------
    # Menu de opções
    # ------------------------------------------------------------------
    def _toggle_options_menu(self):
        # Abre o menu como uma janelinha perto do botão ⚙
        btn = self._btn.get("options")
        if btn and btn.winfo_viewable():
            x = btn.winfo_rootx()
            y = btn.winfo_rooty() + btn.winfo_height() + 2
        else:
            x, y = self.winfo_rootx() + 16, self.winfo_rooty() + 70
        self.options_menu.geometry(f"240x220+{int(x)}+{int(y)}")
        if self.options_menu.state() == "withdrawn":
            self.options_menu.deiconify()
            self.options_menu.lift()
        else:
            self.options_menu.withdraw()

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
        card = ctk.CTkFrame(parent, corner_radius=8, height=44, width=150, fg_color=PALETTES[self.palette]["panel"])
        card.pack(side="left", padx=6, pady=8)
        card.pack_propagate(False)
        self._surfaces.append((card, "panel"))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=6, pady=4)
        ctk.CTkLabel(inner, text=icon, font=("", 15), width=26).pack(side="left")
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(2, 0))
        lbl = ctk.CTkLabel(info, text=label, font=("", 9, "bold"), text_color="gray", anchor="w")
        lbl.pack(fill="x")
        card._status_lbl = lbl
        # LED (círculo colorido) + valor
        val_row = ctk.CTkFrame(info, fg_color="transparent")
        val_row.pack(fill="x")
        led = ctk.CTkFrame(val_row, width=10, height=10, corner_radius=5, fg_color="#6b7280")
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
        self._aplicar_gating()

    def _aplicar_gating(self):
        """Habilita/desabilita botões conforme o modo, para não disputar recursos."""
        if not hasattr(self, "_btn"):
            return
        mode = self.mode
        b = self._btn

        def _enable(key):
            if key in b and b[key] is not None:
                b[key].configure(state="normal")
        def _disable(key):
            if key in b and b[key] is not None:
                b[key].configure(state="disabled")

        # Em treino: todo o esforço vai pro treino. Bloqueia iniciar waifu/voz/servidores
        # e operações de modelo. Libera parar/diagnosticar.
        if mode == "training":
            for k in ["waifu", "options", "voz_on", "url", "diag", "config", "menu_voice", "menu_sovits",
                      "sovits_inst", "sovits_on", "import", "train", "delete",
                      "test_voz", "salvar"]:
                _disable(k)
            for k in ["voz_off", "sovits_off"]:
                _enable(k)
            self._btn["waifu"].configure(text=self._t("cta_training"))
            return

        # Com a waifu aberta: não pode treinar. Pode configurar túnel/voz/servidores.
        if mode == "waifu":
            for k in ["train", "delete"]:
                _disable(k)
            for k in ["waifu", "options", "voz_on", "voz_off", "url", "diag", "config", "menu_voice", "menu_sovits",
                      "sovits_inst", "sovits_on", "sovits_off", "import",
                      "test_voz", "salvar"]:
                _enable(k)
            self._btn["waifu"].configure(text=self._t("cta_start"))
            return

        # idle
        for k in ["waifu", "options", "voz_on", "voz_off", "url", "diag", "config", "menu_voice", "menu_sovits",
                  "sovits_inst", "sovits_on", "sovits_off", "import", "train", "delete",
                  "test_voz", "salvar"]:
            _enable(k)
        self._btn["waifu"].configure(text=self._t("cta_start"))

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
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

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
        # Bloqueio: não inicia a waifu enquanto houver treino em andamento
        if self._modo_atual() == "training":
            self._log("[AÇÃO] ⛔ Não posso iniciar a waifu durante o treino. Aguarde terminar.")
            return
        escolha = ctk.CTkInputDialog(text="Onde abrir o Airi?\n\n1 = Aba do navegador\n2 = Tamagotchi (desktop)\n3 = As duas", title="🌸 Iniciar Waifu").get_input()
        if not escolha: return
        escolha = escolha.strip()
        # Sobe automaticamente o servidor da engine selecionada (bridge +, se sovits, o GPT-SoVITS)
        self._iniciar_engines_da_waifu()
        if escolha == "1" or escolha.lower() == "web":
            self._log("[AÇÃO] Iniciar Waifu (Web)")
            self._run_script("atualizar_airi.ps1")
        elif escolha == "2" or escolha.lower() == "tamagotchi":
            self._log("[AÇÃO] Iniciar Waifu (Tamagotchi)")
            self._run_script("iniciar_tamagotchi.ps1")
            def _auto_config():
                import time; time.sleep(30)
                self.after(0, lambda: self._log("[CONFIG] Auto-configurando providers..."))
                self._auto_configurar_providers()
            threading.Thread(target=_auto_config, daemon=True).start()
        elif escolha == "3" or escolha.lower() == "ambos":
            self._log("[AÇÃO] Iniciar Waifu (Web + Tamagotchi)")
            self._run_script("atualizar_airi.ps1")
            def _open_tama():
                import time; time.sleep(3)
                self._run_script("iniciar_tamagotchi.ps1")
                time.sleep(30)
                self.after(0, lambda: self._log("[CONFIG] Auto-configurando providers..."))
                self._auto_configurar_providers()
            threading.Thread(target=_open_tama, daemon=True).start()
        else:
            self._log("[INFO] Opção inválida. Use 1, 2 ou 3.")
        # Reavalia o modo: com a waifu aberta, bloqueia treino
        self.after(4000, self._atualizar_gating)

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

    def _auto_configurar_providers(self):
        def _configure():
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('127.0.0.1', CDP_PORT))
            sock.close()
            if result != 0:
                self.after(0, lambda: self._log("[CONFIG] AIRI nao esta rodando com CDP na porta %d.\n         Inicie o Tamagotchi primeiro (botao Iniciar Waifu)." % CDP_PORT)); return
            voice_id = "pt-BR-ThalitaNeural"; voice_pitch = 0; voice_rate = 1.0; voice_engine = "edge"
            voz_config_file = ROOT / "voz_config.json"
            if voz_config_file.exists():
                try:
                    j = json.loads(voz_config_file.read_text(encoding="utf-8"))
                    voice_id = j.get("voice", voice_id); voice_engine = j.get("engine", "edge")
                    voice_pitch = int(j.get("pitch", 0)); voice_rate = float(j.get("speed", 1.0))
                except: pass
            speech_model = "edge-tts"
            if voice_engine == "kokoro":
                voice_str = "kokoro:" + voice_id
                if voice_pitch != 0: voice_str += ":+%d" % voice_pitch if voice_pitch > 0 else ":%d" % voice_pitch
                if voice_rate != 1.0: voice_str += "@%.2f" % voice_rate
            elif voice_engine == "sovits":
                voice_str = "sovits:" + voice_id
                speech_model = "sovits"
            else:
                voice_str = voice_id
                if voice_pitch != 0: voice_str += ":+%d" % voice_pitch if voice_pitch > 0 else ":%d" % voice_pitch
                if voice_rate != 1.0: voice_str += "@%.2f" % voice_rate
            brain_url = "http://127.0.0.1:%d/cerebro/v1" % VOICE_PORT
            voice_base = "http://127.0.0.1:%d/v1/" % VOICE_PORT
            voice_str_esc = voice_str.replace("'", "\\'")
            speech_model_esc = speech_model.replace("'", "\\'")
            ps_script = r'''
$cdpPort = %d
$brainUrl = '%s'
$voiceBase = '%s'
$voiceStr = '%s'
$speechModel = '%s'
try {
    $targets = Invoke-RestMethod -Uri "http://127.0.0.1:${cdpPort}/json" -TimeoutSec 3
    $page = $targets | Where-Object { $_.type -eq 'page' -and $_.webSocketDebuggerUrl } | Select-Object -First 1
    if (-not $page) { Write-Host "ERRO: Nenhuma pagina encontrada"; exit 1 }
    $ws = New-Object System.Net.WebSockets.ClientWebSocket
    $ct = New-Object System.Threading.CancellationToken($false)
    $ws.ConnectAsync([Uri]$page.webSocketDebuggerUrl, $ct).Wait()
    $js = @"
(function() {
  try {
    var configured = {};
    var added = {};
    try { configured = JSON.parse(localStorage.getItem('settings/providers/configured') || '{}'); } catch(e) {}
    try { added = JSON.parse(localStorage.getItem('settings/providers/added') || '{}'); } catch(e) {}
    delete configured['openai-audio-speech'];
    delete added['openai-audio-speech'];
    configured['openai-compatible'] = { id: 'openai-compatible', definitionId: 'openai-compatible', config: { apiKey: 'local', baseUrl: '${brainUrl}/' }, status: 'configured', configuredBy: 'user' };
    added['openai-compatible'] = true;
    configured['openai-compatible-audio-speech'] = { id: 'openai-compatible-audio-speech', definitionId: 'openai-compatible-audio-speech', config: { apiKey: 'local', baseUrl: '${voiceBase}' }, status: 'configured', configuredBy: 'user' };
    added['openai-compatible-audio-speech'] = true;
    localStorage.setItem('settings/providers/configured', JSON.stringify(configured));
    localStorage.setItem('settings/providers/added', JSON.stringify(added));
    localStorage.removeItem('settings/speech/active-provider');
    localStorage.removeItem('settings/speech/active-model');
    localStorage.removeItem('settings/speech/voice');
    localStorage.removeItem('settings/speech/pitch');
    localStorage.removeItem('settings/speech/rate');
    localStorage.setItem('settings/speech/active-provider', 'openai-compatible-audio-speech');
    localStorage.setItem('settings/speech/active-model', '$speechModel');
    localStorage.setItem('settings/speech/voice', '$voiceStr');
    return 'OK';
  } catch(e) { return 'ERRO: ' + e.message; }
})();
"@
    $msg = @{ id = 1; method = 'Runtime.evaluate'; params = @{ expression = $js; returnByValue = $true } } | ConvertTo-Json -Depth 10
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)
    $ws.SendAsync([System.ArraySegment[byte]]::new($bytes), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    $buf = New-Object byte[] 65536
    $result = ""
    do {
        $r = $ws.ReceiveAsync([System.ArraySegment[byte]]::new($buf), $ct).Result
        $result += [System.Text.Encoding]::UTF8.GetString($buf, 0, $r.Count)
    } while (-not $r.EndOfMessage)
    Write-Host "INJECT: $result"
    $reload = @{ id = 2; method = 'Page.reload'; params = @{ ignoreCache = $false } } | ConvertTo-Json
    $bytes2 = [System.Text.Encoding]::UTF8.GetBytes($reload)
    $ws.SendAsync([System.ArraySegment[byte]]::new($bytes2), [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait()
    $r2 = $ws.ReceiveAsync([System.ArraySegment[byte]]::new($buf), $ct).Result
    $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $ct).Wait()
    Write-Host "OK: Providers + modulo speech configurados"
} catch {
    Write-Host "ERRO: $_"
}
''' % (CDP_PORT, brain_url, voice_base, voice_str_esc, speech_model_esc)
            self.after(0, lambda: self._log("[CONFIG] Injetando providers + modulo speech..."))
            self.after(0, lambda: self._log("[CONFIG] Engine: %s | Modelo: %s | Voz: %s" % (voice_engine, speech_model, voice_str)))
            try:
                proc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script], capture_output=True, text=True, timeout=30, creationflags=0x08000000)
                output = proc.stdout.strip()
                for line in output.split("\n"):
                    line = line.strip()
                    if line: self.after(0, lambda l=line: self._log("[CONFIG] %s" % l))
                if "OK:" in output:
                    self.after(0, lambda: self._log("[CONFIG] Chat: %s" % brain_url))
                    self.after(0, lambda: self._log("[CONFIG] Voz: %s (%s)" % (voice_str, voice_base)))
                else:
                    self.after(0, lambda: self._log("[CONFIG] Falha. Tente: powershell scripts\\configurar_tamagotchi.ps1"))
            except Exception as e:
                self.after(0, lambda: self._log("[CONFIG] Erro: %s" % str(e)))
        threading.Thread(target=_configure, daemon=True).start()

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
if __name__ == "__main__":
    if not _check_single_instance():
        _bring_window_to_front()
        sys.exit(0)
    app = LiaApp()
    app.mainloop()
