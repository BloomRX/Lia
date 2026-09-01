# ============================================================
#  Lia App - Instalador com Interface
#  Clona o repo, instala dependencias, cria atalhos.
# ============================================================
import customtkinter as ctk
from tkinter import filedialog, messagebox
import subprocess
import threading
import os
import sys
from pathlib import Path

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

REPO_URL = "https://github.com/BloomRX/AIRI_Collab.git"
AIRI_URL = "https://github.com/moeru-ai/airi.git"

class InstallerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🌸 Lia App - Instalador")
        self.geometry("500x520")
        self.resizable(False, False)

        self.install_dir = Path(os.environ.get("USERPROFILE", "")) / "LiaApp"

        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 8))
        ctk.CTkLabel(header, text="🌸 Lia App", font=("", 28, "bold")).pack()
        ctk.CTkLabel(header, text="Instalador", font=("", 14), text_color="gray").pack()

        # Pasta
        folder_frame = ctk.CTkFrame(self, corner_radius=10)
        folder_frame.pack(fill="x", padx=24, pady=(16, 8))

        ctk.CTkLabel(folder_frame, text="📁 Pasta de instalação", font=("", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 4))

        path_row = ctk.CTkFrame(folder_frame, fg_color="transparent")
        path_row.pack(fill="x", padx=12, pady=(0, 10))

        self.path_entry = ctk.CTkEntry(path_row, font=("", 11))
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.path_entry.insert(0, str(self.install_dir))

        ctk.CTkButton(path_row, text="...", width=36, command=self._browse).pack(side="right")

        # Opções
        opt_frame = ctk.CTkFrame(self, corner_radius=10)
        opt_frame.pack(fill="x", padx=24, pady=8)

        ctk.CTkLabel(opt_frame, text="⚙️ Opções", font=("", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 4))

        self.chk_airi = ctk.CTkCheckBox(opt_frame, text="Baixar o Project AIRI (personagem)", font=("", 11))
        self.chk_airi.pack(anchor="w", padx=12, pady=4)
        self.chk_airi.select()

        self.chk_shortcuts = ctk.CTkCheckBox(opt_frame, text="Criar atalhos (Área de Trabalho + Menu Iniciar)", font=("", 11))
        self.chk_shortcuts.pack(anchor="w", padx=12, pady=(4, 10))
        self.chk_shortcuts.select()

        # Botão instalar
        self.btn_install = ctk.CTkButton(
            self, text="🚀 Instalar", font=("", 14, "bold"),
            height=44, corner_radius=10, command=self._start_install
        )
        self.btn_install.pack(fill="x", padx=24, pady=(16, 8))

        # Log
        log_frame = ctk.CTkFrame(self, corner_radius=10)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        ctk.CTkLabel(log_frame, text="📋 Log", font=("", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 4))

        self.log_text = ctk.CTkTextbox(log_frame, font=("Consolas", 10), wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=12, pady=(0, 10))

    def _browse(self):
        folder = filedialog.askdirectory(title="Escolha a pasta de instalação")
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)

    def _log(self, text):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def _start_install(self):
        self.btn_install.configure(state="disabled", text="Instalando...")
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        dest = Path(self.path_entry.get())
        do_airi = self.chk_airi.get()
        do_shortcuts = self.chk_shortcuts.get()

        # Verificar git
        try:
            subprocess.run(["git", "--version"], capture_output=True, check=True)
        except:
            self.after(0, lambda: self._log("[ERRO] Git não encontrado!"))
            self.after(0, lambda: self._log("Baixe em: https://git-scm.com/download/win"))
            self.after(0, lambda: self.btn_install.configure(state="normal", text="🚀 Instalar"))
            return

        # 1. Clonar repo
        self.after(0, lambda: self._log(f"[1/4] Clonando em {dest}..."))

        if (dest / ".git").exists():
            self.after(0, lambda: self._log("  Já existe! Atualizando..."))
            try:
                subprocess.run(["git", "pull"], cwd=str(dest), capture_output=True, check=True)
                self.after(0, lambda: self._log("  [OK] Atualizado!"))
            except Exception as e:
                self.after(0, lambda: self._log(f"  [ERRO] {e}"))
        else:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "clone", REPO_URL, str(dest)],
                    capture_output=True, check=True
                )
                self.after(0, lambda: self._log("  [OK] Clonado!"))
            except Exception as e:
                self.after(0, lambda: self._log(f"  [ERRO] {e}"))
                self.after(0, lambda: self.btn_install.configure(state="normal", text="🚀 Instalar"))
                return

        # 2. Instalar dependências Python
        self.after(0, lambda: self._log("[2/4] Instalando dependências..."))
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "customtkinter", "--quiet"],
                capture_output=True
            )
            self.after(0, lambda: self._log("  [OK] CustomTkinter instalado"))
        except Exception as e:
            self.after(0, lambda: self._log(f"  [AVISO] {e}"))

        # 3. Clonar AIRI
        if do_airi:
            airi_dir = dest / "airi"
            if (airi_dir / "package.json").exists():
                self.after(0, lambda: self._log("[3/4] AIRI já instalado"))
            else:
                self.after(0, lambda: self._log("[3/4] Clonando o Project AIRI..."))
                try:
                    subprocess.run(
                        ["git", "clone", AIRI_URL, str(airi_dir)],
                        capture_output=True, check=True
                    )
                    self.after(0, lambda: self._log("  [OK] AIRI clonado!"))
                    self.after(0, lambda: self._log("  Instalando dependências do AIRI (pnpm install)..."))
                    subprocess.run(["pnpm", "install"], cwd=str(airi_dir), capture_output=True)
                    self.after(0, lambda: self._log("  [OK] Dependências instaladas!"))
                except Exception as e:
                    self.after(0, lambda: self._log(f"  [ERRO] {e}"))
        else:
            self.after(0, lambda: self._log("[3/4] AIRI pulado (não selecionado)"))

        # 4. Atalhos
        if do_shortcuts:
            self.after(0, lambda: self._log("[4/4] Criando atalhos..."))
            bat_path = dest / "waifu.bat"
            desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
            start_menu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"

            for destino in [desktop, start_menu]:
                if not destino.exists():
                    continue
                lnk = destino / "Lia App.lnk"
                try:
                    cmd = f'''
                    $ws = New-Object -ComObject WScript.Shell
                    $sc = $ws.CreateShortcut("{lnk}")
                    $sc.TargetPath = "{bat_path}"
                    $sc.WorkingDirectory = "{dest}"
                    $sc.Description = "Lia App - Painel da Waifu"
                    $sc.Save()
                    '''
                    subprocess.run(
                        ["powershell", "-NoProfile", "-Command", cmd],
                        capture_output=True, creationflags=0x08000000
                    )
                except:
                    pass
            self.after(0, lambda: self._log("  [OK] Atalhos criados!"))
        else:
            self.after(0, lambda: self._log("[4/4] Atalhos pulados"))

        # Finalizar
        self.after(0, lambda: self._log(""))
        self.after(0, lambda: self._log("✅ Instalação concluída!"))
        self.after(0, lambda: self._log(f"Pasta: {dest}"))
        self.after(0, lambda: self._log("Abra o 'Lia App' na Área de Trabalho ou Menu Iniciar."))
        self.after(0, lambda: self.btn_install.configure(state="normal", text="🚀 Instalar"))
        self.after(0, lambda: messagebox.showinfo("Pronto!", "Instalação concluída!\n\nAbra o 'Lia App' na Área de Trabalho."))

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    app = InstallerApp()
    app.mainloop()
