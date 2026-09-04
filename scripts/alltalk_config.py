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

