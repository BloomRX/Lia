# -*- coding: utf-8 -*-
"""
alltalk_config.py — utilitários de configuração do AllTalk TTS v2.

Objetivo: NÃO depender de caminho fixo. O AllTalk é clonado como subpasta do
repositório (alltalk_tts/), então resolvemos tudo a partir da localização
deste arquivo. Funciona de qualquer lugar (C:\\Lia, J:\\Lia, D:\\Projetos\\Lia,
pendrive...) após clonar o repo.

Modos:
  --check-python      valida que o Python é 3.9–3.11 (exigido pelo AllTalk v2).
  --patch-confignew   ajusta confignew.json (deepspeed_activate=false,
                      port_number=7851), se o arquivo existir.
  --endpoint          imprime o endpoint OpenAI-compatible para o Airi.
"""

import json
import os
import sys


def repo_root():
    """<repo>/scripts/alltalk_config.py  ->  <repo>"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def alltalk_dir(root=None):
    root = root or repo_root()
    return os.path.join(root, "alltalk_tts")


def check_python():
    v = sys.version_info
    ok = v.major == 3 and (9 <= v.minor <= 11)
    print("[%s] Python %d.%d.%d" % ("OK" if ok else "ERRO", v.major, v.minor, v.micro))
    if not ok:
        print("  -> AllTalk v2 exige Python 3.9-3.11 (3.12+ NÃO suportado).")
        print("  -> Instale 3.10 ou 3.11 e marque 'Add Python to PATH'.")
        return 1
    print("  -> OK para o AllTalk v2.")
    return 0


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
    # Se o .bat exportar ALLTALK_DIR para a subpasta alltalk_tts, usamos o
    # pai (repositorio) como root; caso contrario derivamos deste arquivo.
    env_dir = os.environ.get("ALLTALK_DIR")
    if env_dir:
        root = os.path.dirname(os.path.abspath(env_dir))
    code = 0
    for arg in argv:
        if arg == "--check-python":
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
