# ============================================================
#  Lia App - Painel da Waifu (Desktop)  v51
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
        self.title("🌸 Lia App")
        self.geometry("1000x650")
        self.minsize(900, 550)
        self.voice_process = None
        self.other_process = None
        self.sovits_process = None
        self._child_pids = []  # PIDs de processos filhos pra cleanup
        self._last_audio_path = None  # Remember last audio selection directory
        self._build_ui()
        self.after(500, verificar_primeira_vez)
        self.after(100, self._init_deps)
        self._refresh_status()
        self._refresh_training_status()
        
        # Cleanup ao fechar
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_deps(self):
        def _install():
            garantir_node_modules(lambda t: self.after(0, lambda: self._log(t)))
        threading.Thread(target=_install, daemon=True).start()

    def _build_ui(self):
        # ============================================================
        # TOP: Status bar (full width)
        # ============================================================
        status_bar = ctk.CTkFrame(self, corner_radius=0, height=60)
        status_bar.pack(fill="x", padx=0, pady=0)
        status_bar.pack_propagate(False)

        # Logo
        logo_frame = ctk.CTkFrame(status_bar, fg_color="transparent")
        logo_frame.pack(side="left", padx=16)
        ctk.CTkLabel(logo_frame, text="🌸 Lia App", font=("", 20, "bold")).pack(side="left")
        ctk.CTkLabel(logo_frame, text="v51", font=("", 10), text_color="gray").pack(side="left", padx=(4, 0))

        # Status cards in a row
        status_cards = ctk.CTkFrame(status_bar, fg_color="transparent")
        status_cards.pack(side="left", fill="x", expand=True, padx=20)
        self.st_voice = self._make_status_card(status_cards, "🎙️", "Voz", "...")
        self.st_aba = self._make_status_card(status_cards, "🌐", "Aba", "...")
        self.st_sovits = self._make_status_card(status_cards, "🎤", "SoVITS", "...")
        self.st_tama = self._make_status_card(status_cards, "🖥️", "Tamagotchi", "...")

        # ============================================================
        # MIDDLE: 3 columns
        # ============================================================
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        # LEFT: Actions (200px)
        left = ctk.CTkFrame(main, width=200, corner_radius=10)
        left.pack(side="left", fill="y", padx=(0, 4))
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="⚡ Ações", font=("", 13, "bold"), text_color="#4ade80").pack(anchor="w", padx=12, pady=(12, 8))
        self._make_button(left, "🚀 Iniciar Waifu", self._act_iniciar_waifu, "#4ade80")
        self._make_button(left, "▶ Iniciar voz", self._act_ligar_voz)
        self._make_button(left, "⏹ Parar voz", self._act_parar_voz)
        self._make_button(left, "🔗 Injetar URL", self._act_injetar_url)
        self._make_button(left, "⚙ Configurar", self._act_configurar)
        self._make_button(left, "🔍 Diagnosticar", self._act_diagnosticar)

        ctk.CTkFrame(left, height=1, fg_color="gray30").pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(left, text="🎤 SoVITS", font=("", 13, "bold"), text_color="#fbbf24").pack(anchor="w", padx=12, pady=(4, 8))
        self._make_button(left, "📦 Instalar Servidor", self._instalar_sovits_servidor, "#b45309")
        self._make_button(left, "▶ Rodar Servidor", self._run_sovits_local, "#15803d")
        self._make_button(left, "⏹ Parar Servidor", self._parar_sovits)
        self._make_button(left, "📤 Importar Modelo", self._importar_modelo_sovits, "#6d28d9")
        self._make_button(left, "🔥 Treinar Local", self._treinar_sovits_local, "#dc2626")

        self.sovits_status = ctk.CTkLabel(left, text="...", font=("", 9), text_color="gray", wraplength=170)
        self.sovits_status.pack(anchor="w", padx=12, pady=(4, 8))

        # Training status section
        ctk.CTkFrame(left, height=1, fg_color="gray30").pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(left, text="🔥 Models em treinamento", font=("", 11, "bold"), text_color="#f97316").pack(anchor="w", padx=12, pady=(4, 4))
        self.training_frame = ctk.CTkFrame(left, fg_color="transparent")
        self.training_frame.pack(fill="x", padx=10, pady=(0, 4))
        self.training_labels = {}  # model_name -> label widget
        self._no_training_label = ctk.CTkLabel(self.training_frame, text="Nenhum modelo treinando", font=("", 9), text_color="gray")
        self._no_training_label.pack(anchor="w", padx=2)
        # Barra de progresso ao vivo (lê training_live.json que o train_auto.py escreve)
        self.training_progress = ctk.CTkProgressBar(self.training_frame, width=180, height=12, progress_color="#f97316")
        self.training_progress.set(0)
        self.training_progress_label = ctk.CTkLabel(self.training_frame, text="", font=("", 9), text_color="#fbbf24", anchor="w", wraplength=170)
        self.training_progress_label.pack(anchor="w", padx=2, pady=(2, 0))

        # CENTER: Log
        center = ctk.CTkFrame(main, corner_radius=10)
        center.pack(side="left", fill="both", expand=True, padx=4)

        ctk.CTkLabel(center, text="📋 Log", font=("", 13, "bold"), text_color="gray").pack(anchor="w", padx=12, pady=(12, 4))
        self.log_text = ctk.CTkTextbox(center, font=("Consolas", 11), wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Status bar no fundo do log
        self.log_status_bar = ctk.CTkFrame(center, height=28, fg_color="transparent")
        self.log_status_bar.pack(fill="x", padx=8, pady=(0, 8))
        self.log_status_label = ctk.CTkLabel(self.log_status_bar, text="⏸ Pronto", font=("", 11), text_color="gray")
        self.log_status_label.pack(side="left")
        self.log_progress_label = ctk.CTkLabel(self.log_status_bar, text="", font=("", 10), text_color="gray")
        self.log_progress_label.pack(side="right")

        # RIGHT: Voice config (280px)
        right = ctk.CTkFrame(main, width=280, corner_radius=10)
        right.pack(side="right", fill="y", padx=(4, 0))
        right.pack_propagate(False)

        ctk.CTkLabel(right, text="🎙️ Configurar Voz", font=("", 13, "bold"), text_color="#818cf8").pack(anchor="w", padx=12, pady=(12, 8))

        # Engine selector (dropdown)
        engine_frame = ctk.CTkFrame(right, fg_color="transparent")
        engine_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(engine_frame, text="Engine:", font=("", 11, "bold")).pack(anchor="w")
        self.engine_var = ctk.StringVar(value="edge")
        self.engine_combo = ctk.CTkComboBox(engine_frame, values=["edge", "kokoro", "sovits"], 
                                            variable=self.engine_var, width=250,
                                            command=lambda _: self._update_voice_list())
        self.engine_combo.pack(pady=4)
        self.engine_combo.set("edge")

        # Kokoro install
        kokoro_frame = ctk.CTkFrame(right, fg_color="transparent")
        kokoro_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(kokoro_frame, text="🦉 Instalar Kokoro", command=self._instalar_kokoro, width=130, fg_color="#6b21a8", hover_color="#7c3aed", height=28).pack(side="left")
        self.kokoro_status = ctk.CTkLabel(kokoro_frame, text="", font=("", 9), text_color="gray")
        self.kokoro_status.pack(side="left", padx=6)

        # Voice selector
        ctk.CTkLabel(right, text="Voz:", font=("", 11, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        self.voice_combo = ctk.CTkComboBox(right, values=["pt-BR-ThalitaNeural"], width=250)
        self.voice_combo.pack(padx=12, pady=2)
        self.voice_combo.set("pt-BR-ThalitaNeural")

        # Pitch
        ctk.CTkLabel(right, text="Pitch:", font=("", 11, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        pitch_frame = ctk.CTkFrame(right, fg_color="transparent")
        pitch_frame.pack(fill="x", padx=12)
        self.pitch_slider = ctk.CTkSlider(pitch_frame, from_=-50, to=50, number_of_steps=100, width=180)
        self.pitch_slider.pack(side="left")
        self.pitch_slider.set(0)
        self.pitch_label = ctk.CTkLabel(pitch_frame, text="0", font=("", 11), width=30)
        self.pitch_label.pack(side="left", padx=4)
        self.pitch_slider.configure(command=lambda v: self.pitch_label.configure(text=str(int(v))))

        # Speed
        ctk.CTkLabel(right, text="Velocidade:", font=("", 11, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        speed_frame = ctk.CTkFrame(right, fg_color="transparent")
        speed_frame.pack(fill="x", padx=12)
        self.speed_slider = ctk.CTkSlider(speed_frame, from_=0.5, to=2.0, number_of_steps=30, width=180)
        self.speed_slider.pack(side="left")
        self.speed_slider.set(1.0)
        self.speed_label = ctk.CTkLabel(speed_frame, text="1.0", font=("", 11), width=30)
        self.speed_label.pack(side="left", padx=4)
        self.speed_slider.configure(command=lambda v: self.speed_label.configure(text=f"{v:.1f}"))

        # Buttons
        btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(16, 8))
        ctk.CTkButton(btn_frame, text="🔊 Testar voz", command=self._testar_voz, width=120, height=32).pack(side="left", padx=4)
        ctk.CTkButton(btn_frame, text="💾 Salvar", command=self._salvar_voz, width=80, height=32).pack(side="left", padx=4)

        self.voz_status = ctk.CTkLabel(right, text="...", font=("", 9), text_color="gray", wraplength=250)
        self.voz_status.pack(anchor="w", padx=12, pady=(4, 12))

    def _make_status_card(self, parent, icon, label, value):
        card = ctk.CTkFrame(parent, corner_radius=8, height=44, width=140)
        card.pack(side="left", padx=6, pady=8)
        card.pack_propagate(False)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=6, pady=4)
        ctk.CTkLabel(inner, text=icon, font=("", 14), width=24).pack(side="left")
        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(2, 0))
        ctk.CTkLabel(info, text=label, font=("", 8), text_color="gray", anchor="w").pack(fill="x")
        val_label = ctk.CTkLabel(info, text=value, font=("", 10, "bold"), anchor="w")
        val_label.pack(fill="x")
        card._val_label = val_label
        return card

    def _make_button(self, parent, text, command, color=None):
        kwargs = {"text": text, "font": ("", 11), "height": 30, "corner_radius": 6, "anchor": "w", "command": command}
        if color:
            kwargs["fg_color"] = color
            kwargs["hover_color"] = "#22c55e"
        btn = ctk.CTkButton(parent, **kwargs)
        btn.pack(fill="x", padx=10, pady=2)

    def _set_status(self, card, ok, text):
        color = "#4ade80" if ok else "#f87171"
        card._val_label.configure(text=text, text_color=color)

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
                self.after(0, lambda: self._set_status(self.st_voice, True, f"v{voice.get('version', '?')}"))
                self.after(0, lambda: self.voz_status.configure(text=f"Servidor de voz: rodando v{voice.get('version', '?')}", text_color="#4ade80"))
            else:
                self.after(0, lambda: self._set_status(self.st_voice, False, "Off"))
                self.after(0, lambda: self.voz_status.configure(text="Servidor de voz: parado", text_color="#f87171"))
            self.after(0, lambda: self._set_status(self.st_aba, aba["up"], "Online" if aba["up"] else "Off"))
            sovits_ok = self._is_port_open(SOVITS_PORT)
            if sovits_ok:
                self.after(0, lambda: self._set_status(self.st_sovits, True, "Rodando"))
                self.after(0, lambda: self.sovits_status.configure(text="SoVITS: rodando ✅", text_color="#4ade80"))
            else:
                sovits_dir = ROOT / "sovits-data"
                if (sovits_dir / "GPT-SoVITS" / "api_v2.py").exists():
                    self.after(0, lambda: self._set_status(self.st_sovits, False, "Instalado"))
                    self.after(0, lambda: self.sovits_status.configure(text="SoVITS: instalado (parado)", text_color="#fbbf24"))
                else:
                    self.after(0, lambda: self._set_status(self.st_sovits, False, "Não instalado"))
                    self.after(0, lambda: self.sovits_status.configure(text="SoVITS: não instalado", text_color="#f87171"))
            if tama["up"]:
                self.after(0, lambda: self._set_status(self.st_tama, True, "Pronto"))
            else:
                self.after(0, lambda: self._set_status(self.st_tama, False, "Não instalado"))
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
            self.sovits_status.configure(text="Nenhum treino ativo", text_color="gray")
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
        self._log("[SOVITS] Pipeline: Slice → ASR → Fix PT → Dataset → Treino")
        self._set_busy(f"Treinando '{nome}'...")

        output_dir = repo_dir / "logs" / nome
        output_dir.mkdir(parents=True, exist_ok=True)

        def _train():
            try:
                sovits_env = self._get_sovits_env()
                sovits_env["PYTHONUNBUFFERED"] = "1"
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
                for line in iter(proc.stdout.readline, b""):
                    line = line.decode("utf-8", errors="replace").rstrip()
                    if line:
                        self.after(0, lambda l=line: self._log(f"[SOVITS] {l}"))
                proc.wait()
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

    def _update_voice_list(self):
        engine = self.engine_var.get()
        if engine == "kokoro":
            self.voice_combo.configure(values=["af_heart","af_bella","af_nicole","af_sarah","af_sky","am_adam","am_michael","pf_dora","pm_santa","pm_alex","jf_alpha","jf_gongitsune","jm_kumo","zf_xiaobei","zm_yunxi"])
            self.voice_combo.set("pf_dora")
        elif engine == "sovits":
            sovits_models = self._listar_modelos_sovits()
            if sovits_models:
                self.voice_combo.configure(values=sovits_models)
                self.voice_combo.set(sovits_models[0])
            else:
                self.voice_combo.configure(values=["(nenhum modelo)"])
                self.voice_combo.set("(nenhum modelo)")
        else:
            self.voice_combo.configure(values=["pt-BR-ThalitaNeural","pt-BR-FranciscaNeural","pt-BR-GiovannaNeural","pt-BR-BrendaNeural","pt-BR-AntonioNeural","pt-BR-DonatoNeural","pt-BR-ValerioNeural","pt-BR-ManuelaNeural","pt-BR-NicolauNeural","ja-JP-NanamiNeural","ja-JP-AoiNeural","ja-JP-KeitaNeural","ja-JP-DaichiNeural","en-US-AriaNeural","en-US-JennyNeural","en-US-SaraNeural","en-US-GuyNeural","en-US-TonyNeural","es-MX-DaliaNeural","es-ES-ElviraNeural","fr-FR-DeniseNeural","ko-KR-SunHiNeural","zh-CN-XiaoxiaoNeural","zh-CN-YunxiNeural"])
            self.voice_combo.set("pt-BR-ThalitaNeural")

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

        def _start():
            try:
                if cfg_path and gpt_path and convert_script.exists():
                    try:
                        self.after(0, lambda: self._log(f"[SOVITS] 🔧 Ajustando pesos p/ float32 (fix CPU): {os.path.basename(gpt_path)} e {os.path.basename(sovits_path)}..."))
                        # O ckpt do GPT e o que costuma ter pesos fp16; passamos ELE primeiro
                        # (o script processa cada arquivo de forma independente — falha de um nao aborta o outro).
                        conv = subprocess.run(
                            [str(venv_python), str(convert_script), gpt_path, sovits_path],
                            capture_output=True, text=True, timeout=900, creationflags=0x08000000
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

    def _treinar_sovits_local(self):
        """Treinamento 100% automático via script train_auto.py."""
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

    # ============================================================
    # Other actions
    # ============================================================
    def _act_iniciar_waifu(self):
        escolha = ctk.CTkInputDialog(text="Onde abrir o Airi?\n\n1 = Aba do navegador\n2 = Tamagotchi (desktop)\n3 = As duas", title="🌸 Iniciar Waifu").get_input()
        if not escolha: return
        escolha = escolha.strip()
        if not self.voice_process: self._act_ligar_voz()
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
