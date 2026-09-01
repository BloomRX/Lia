# ============================================================================
#  patch_sovits_float.py
#  Corrige o erro "Input type (torch.FloatTensor) and weight type
#  (torch.HalfTensor)" do GPT-SoVITS em CPU.
#
#  Causa: o treinamento salva parte dos pesos em meia precisao (float16).
#  Em CPU (is_half=False, inputs float32) isso gera o mismatch.
#
#  ESTRATEGIA (a mais robusta):
#    1. No TTS.py, ao final do _init_models, se is_half=False, castar TODOS os
#       modelos (qualquer atributo nn.Module: t2s, vits, bert, cnhuhbert,
#       sv_model, vocoder, ...) para float32. Cobre inclusive o modelo SV do
#       v2Pro, que os casts individuais nao alcancam.
#    2. No api_v2.py, imprimir o traceback completo quando o /tts falha.
#
#  Idempotencia por SENTINELA (linha unica), nao por linha comum, para evitar
#  falso positivo quando o TTS.py ja tem outra linha parecida.
#
#  Uso:
#    python patch_sovits_float.py <TTS.py> <api_v2.py>
# ============================================================================
import sys
import re
import os
import shutil


SENTINEL_ALL = "# LIA_FIX_FLOAT32_ALL"
SENTINEL_API = "# LIA_FIX_API_TRACEBACK"


def _bak(path):
    bak = path + ".bak"
    if not os.path.exists(bak):
        try:
            shutil.copy2(path, bak)
            print(f"[PATCH] backup -> {os.path.basename(bak)}")
        except Exception as e:
            print(f"[PATCH] aviso: falha no backup ({e})")


def _insert_after_anchor(text, anchor_regex, insert_lines, label, sentinel):
    """Insere `insert_lines` logo apos a linha que casa com anchor_regex.
    Se sentinel ja estiver no texto, pula (idempotente)."""
    if sentinel in text:
        print(f"[PATCH] {label}: ja aplicado (skip).")
        return text, False
    m = anchor_regex.search(text)
    if not m:
        print(f"[PATCH] {label}: ANCTOR NAO ENCONTRADA (versao diferente do arquivo?); nada alterado.")
        return text, False
    ind = m.group(1) if m.lastindex else "        "
    block = "\n".join((ind + line) if line.strip() else "" for line in insert_lines) + "\n"
    text = text[: m.end()] + "\n" + block + text[m.end():]
    print(f"[PATCH] {label}: aplicado.")
    return text, True


def patch_tts(path):
    if not os.path.exists(path):
        print(f"[PATCH] arquivo nao encontrado: {path}")
        return False
    _bak(path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    changed = False

    # 1) Cast de TODOS os modelos quando is_half=False (no fim do _init_models)
    anchor_re_all = re.compile(
        r"^(\s*)self\.init_cnhuhbert_weights\(self\.configs\.cnhuhbert_base_path\)[^\n]*\n", re.M
    )
    insert_all = [
        SENTINEL_ALL,
        "if not self.configs.is_half:",
        "    import torch as _torch_pt",
        "    for _k, _v in list(vars(self).items()):",
        "        if isinstance(_v, _torch_pt.nn.Module):",
        "            try:",
        "                setattr(self, _k, _v.float())",
        "            except Exception:",
        "                pass",
    ]
    text, c = _insert_after_anchor(text, anchor_re_all, insert_all, "float-todos-modelos", SENTINEL_ALL)
    changed = changed or c

    # 2) (reforco) cast .float() individual do VITS e T2S apos carregar
    for anchor_l, cast in [
        ("self.vits_model = vits_model", "self.vits_model = self.vits_model.float()"),
        ("self.t2s_model = t2s_model", "self.t2s_model = self.t2s_model.float()"),
    ]:
        if cast in text:
            continue
        m = re.search(r"^(\s*)" + re.escape(anchor_l) + r"[ \t]*\n", text, re.M)
        if not m:
            print(f"[PATCH] individual {anchor_l}: ancor nao encontrada (skip).")
            continue
        ind = m.group(1)
        ins = f"{ind}if not self.configs.is_half:\n{ind}    {cast}\n"
        text = text[: m.end()] + ins + text[m.end():]
        print(f"[PATCH] individual {anchor_l}: aplicado.")
        changed = True

    if changed:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    return True


def patch_api(path):
    if not os.path.exists(path):
        print(f"[PATCH] arquivo nao encontrado: {path}")
        return False
    _bak(path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if SENTINEL_API in text:
        print("[PATCH] api_v2: traceback ja aplicado (skip).")
        return True
    # Acha a linha do return do tts failed e insere traceback.print_exc() antes.
    m = re.search(r"^(\s*)return JSONResponse\([^\n]*\"tts failed\"[^\n]*$", text, re.M)
    if not m:
        print("[PATCH] api_v2: ancor 'tts failed' nao encontrada (skip).")
        return True
    ind = m.group(1)
    ins = f"{ind}{SENTINEL_API}\n{ind}traceback.print_exc()\n"
    text = text[: m.start()] + ins + text[m.start():]
    if "import traceback" not in text:
        # coloca import traceback depois do bloco de imports (apos import threading, se existir)
        if "import threading" in text:
            text = text.replace("import threading", "import threading\nimport traceback", 1)
        else:
            text = text.replace("import sys\n", "import sys\nimport traceback\n", 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("[PATCH] api_v2: traceback.print_exc() inserido no /tts.")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python patch_sovits_float.py <TTS.py> [api_v2.py]")
        sys.exit(1)
    ok = True
    ok = patch_tts(sys.argv[1]) and ok
    if len(sys.argv) >= 3:
        ok = patch_api(sys.argv[2]) and ok
    print("PATCH_OK" if ok else "PATCH_INCOMPLETO")
