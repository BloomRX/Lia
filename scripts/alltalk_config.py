# -*- coding: utf-8 -*-
"""
alltalk_config.py — utilitários de configuração do AllTalk TTS v2.

Objetivo: NÃO depender de caminho fixo. O AllTalk é clonado como subpasta do
repositório (alltalk_tts/), então resolvemos tudo a partir da localização
deste arquivo. Funciona de qualquer lugar (C:\\Lia, J:\\Lia, D:\\Projetos\\Lia,
pendrive...) após clonar o repo.

Modos:
  --find-python     imprime o caminho de um Python 3.9–3.11 (se houver) e sai.
  --check-python    valida (e reporta) que o Python corrente é 3.9–3.11.
  --install-cpu     cria venv + instala torch CPU + requirements (sem CUDA/DeepSpeed).
  --patch-confignew ajusta confignew.json (deepspeed_activate=false,
                    port_number=7851), se o arquivo existir.
  --endpoint        imprime o endpoint OpenAI-compatible para o Airi.
"""

import json
import os
import shutil
import subprocess
import sys


def repo_root():
    """<repo>/scripts/alltalk_config.py  ->  <repo>"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def alltalk_dir(root=None):
    root = root or repo_root()
    return os.path.join(root, "alltalk_tts")


def _is_valid(v):
    return v.major == 3 and (9 <= v.minor <= 11)


def check_python():
    v = sys.version_info
    ok = _is_valid(v)
    print("[%s] Python %d.%d.%d" % ("OK" if ok else "ERRO", v.major, v.minor, v.micro))
    if not ok:
        print("  -> AllTalk v2 exige Python 3.9-3.11 (3.12+ NÃO suportado).")
        print("  -> Instale 3.10 ou 3.11 e marque 'Add Python to PATH'.")
        print("  -> Dica: para NAO mexer no python global, use o launcher:")
        print("        py -3.11 -c \"print('ok')\"")
        return 1
    print("  -> OK para o AllTalk v2.")
    return 0


def find_python():
    """Devolve o caminho de um Python 3.9–3.11, ou None.

    Prioridade:
      1. O interpretador atual (o `python` do PATH), SE já for 3.9–3.11;
      2. O launcher `py -3.11` / `py -3.10` / `py -3.9` (versões lado a lado).
    Isso permite instalar o 3.11 ao lado do 3.14 sem mudar o `python` global.
    """
    # 1) Interpretador atual já serve?
    cur = sys.executable
    if cur and _is_valid(sys.version_info):
        return cur

    # 2) Launcher `py` (Windows Python Launcher).
    for ver in ("3.11", "3.10", "3.9"):
        try:
            out = subprocess.check_output(
                ["py", "-" + ver, "-c", "import sys;print(sys.executable)"],
                stderr=subprocess.DEVNULL, text=True,
            ).strip()
            if out:
                return out
        except Exception:
            continue

    # 3) Procurar pelo nome `python`/`python3.x` no PATH.
    for name in ("python", "python3", "python3.11", "python3.10", "python3.9"):
        exe = shutil.which(name)
        if not exe:
            continue
        try:
            v = subprocess.check_output(
                [exe, "-c", "import sys;print('%%d.%%d' %% sys.version_info[:2])"],
                stderr=subprocess.DEVNULL, text=True,
            ).strip()
            major, _, minor = v.partition(".")
            if int(major) == 3 and 9 <= int(minor) <= 11:
                return exe
        except Exception:
            continue

    return None


def find_python_cmd():
    exe = find_python()
    if exe:
        print(exe)
        return 0
    print("", end="")  # nada no stdout
    print("[ERRO] Nenhum Python 3.9-3.11 encontrado.", file=sys.stderr)
    print("       Instale 3.10 ou 3.11 (marcando 'py launcher' e 'Add to PATH').", file=sys.stderr)
    return 1


def patch_confignew(root=None):
    root = root or repo_root()
    ddir = alltalk_dir(root)
    p = os.path.join(ddir, "confignew.json")
    if not os.path.exists(p):
        print("[AVISO] confignew.json ainda não existe em: %s" % p)
        print("        Ele é criado no PRIMEIRO run do AllTalk. Rode o AllTalk")
        print("        1x e depois re-execute este script (ou edite manualmente).")
        return 1
    try:
        with open(p, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print("[ERRO] Não consegui ler confignew.json: %s" % e)
        return 1
    cfg["deepspeed_activate"] = False
    cfg["port_number"] = "7851"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print("[OK] confignew.json ajustado:")
    print("        deepspeed_activate = false")
    print("        port_number        = 7851")
    print("      Arquivo: %s" % p)
    return 0


def endpoint(root=None):
    print("http://127.0.0.1:7851/v1")


# ---------------------------------------------------------------------
# Instalação CPU (RX 580 / sem NVIDIA) — SEM CUDA, SEM DeepSpeed
# ---------------------------------------------------------------------
def _run(cmd, env=None, cwd=None):
    """Roda um comando e devolve (returncode, stdout+stderr)."""
    print("  $ %s" % " ".join(str(c) for c in cmd))
    p = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
    tail = "\n".join((p.stdout or "").splitlines()[-8:])
    if tail:
        print("      " + tail.replace("\n", "\n      "))
    if p.returncode != 0:
        print("  [ERRO] retornou %d. Abortando." % p.returncode)
    return p.returncode


def install_cpu(root=None):
    """Instala o AllTalk em modo CPU (sem CUDA/DeepSpeed).

    Passos:
      1. Criar venv em <alltalk_tts>/venv usando o Python 3.9-3.11.
      2. Instalar torch + torchaudio na versao CPU (nao +cu121).
      3. Gerar um requirements SEM as linhas nvidia-*/torch/torchaudio e
         instalar o restante (Piper, XTTS, RVC, grading, etc).
      4. Ajustar confignew.json.
    """
    root = root or repo_root()
    ddir = alltalk_dir(root)
    print("==> AllTalk em: %s" % ddir)
    if not os.path.isdir(ddir):
        print("[ERRO] Nao achei alltalk_tts em: %s" % ddir)
        print("       Rode: git clone https://github.com/erew123/alltalk_tts.git (em %s)" % root)
        return 1

    # 0) Python 3.9-3.11
    py = find_python()
    if not py:
        print("[ERRO] Nenhum Python 3.9-3.11 encontrado. Instale 3.10/3.11.")
        return 1
    print("==> Python usado: %s" % py)

    # 1) venv
    venv = os.path.join(ddir, "venv")
    venv_py = os.path.join(venv, "Scripts", "python.exe") if os.name == "nt" else os.path.join(venv, "bin", "python")
    if not os.path.exists(venv_py):
        print("==> Criando venv em %s ..." % venv)
        r = _run([py, "-m", "venv", venv], cwd=ddir)
        if r != 0:
            return r
    else:
        print("==> venv ja existe em %s" % venv)

    # 2) pip atualizado
    print("==> Atualizando pip/wheel ...")
    r = _run([venv_py, "-m", "pip", "install", "--upgrade", "pip", "wheel"], cwd=ddir)
    if r != 0:
        return r

    # 3) torch CPU (SEM +cu121). O index do PyTorch garante a build de CPU.
    print("==> Instalando torch/torchaudio CPU (nao +cu121) ...")
    r = _run([venv_py, "-m", "pip", "install", "--index-url",
              "https://download.pytorch.org/whl/cpu", "torch", "torchaudio"], cwd=ddir)
    if r != 0:
        return r
    r = _run([venv_py, "-c", "import torch;print('torch',torch.__version__,'| cuda?',torch.cuda.is_available())"], cwd=ddir)
    if r != 0:
        return r

    # 4) requirements SEM as linhas de CUDA/torch (ja instalado) e SEM deepspeed.
    req_src = os.path.join(ddir, "system", "requirements", "requirements_standalone.txt")
    req_out = os.path.join(ddir, "system", "requirements", "requirements_cpu.txt")
    if not os.path.exists(req_src):
        # fallback: procura na raiz
        req_src = os.path.join(ddir, "requirements_standalone.txt")
    if not os.path.exists(req_src):
        print("[AVISO] Nao achei requirements_standalone.txt. Pulei.")
        req_out = None
    else:
        print("==> Gerando requirements_cpu.txt (sem nvidia-*/torch/deepspeed) ...")
        skip_prefixes = ("nvidia-", "torch", "torchaudio", "deepspeed")
        with open(req_src, encoding="utf-8") as f:
            lines = f.readlines()
        kept = [l for l in lines if l.strip() and not l.strip().lower().startswith(skip_prefixes)]
        with open(req_out, "w", encoding="utf-8") as f:
            f.writelines(kept)
        print("    -> %s" % req_out)
        print("==> Instalando demais requirements (Piper/XTTS/RVC/gradio...) ...")
        r = _run([venv_py, "-m", "pip", "install", "-r", req_out], cwd=ddir)
        if r != 0:
            return r

    # 5) patch confignew.json
    print("==> Ajustando confignew.json ...")
    patch_confignew(root)

    print()
    print("============================================================")
    print("  Instalacao CPU concluida!")
    print("  Para iniciar:  cd %s" % ddir)
    print("                 venv\\Scripts\\python script.py")
    print("  (ou rode:      iniciar_alltalk.bat / start_alltalk.bat)")
    print("============================================================")
    return 0


def main():
    argv = sys.argv[1:] or ["--endpoint"]
    root = None
    env_dir = os.environ.get("ALLTALK_DIR")
    if env_dir:
        root = os.path.dirname(os.path.abspath(env_dir))
    code = 0
    for arg in argv:
        if arg == "--find-python":
            code |= find_python_cmd()
        elif arg == "--check-python":
            code |= check_python()
        elif arg == "--install-cpu":
            code |= install_cpu(root)
        elif arg == "--patch-confignew":
            code |= patch_confignew(root)
        elif arg == "--endpoint":
            endpoint(root)
        else:
            print("modo desconhecido: %s" % arg)
            code |= 1
    sys.exit(code)


if __name__ == "__main__":
    main()

