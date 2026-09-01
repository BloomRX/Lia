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
#       sv_model, vocoder, ...) para float32. Assim cobre qualquer modelo que
#       tenha vindo com pesos fp16.
#    2. No api_v2.py, imprimir o traceback completo quando o /tts falha, para
#       diagnosticar a origem exata caso ainda haja erro.
#
#  Idempotente (nao duplica). Backup .bak na 1a vez.
#
#  Uso:
#    python patch_sovits_float.py <TTS.py> <api_v2.py>
# ============================================================================
import sys
import re
import os
import shutil


def _bak(path):
    bak = path + ".bak"
    if not os.path.exists(bak):
        try:
            shutil.copy2(path, bak)
            print(f"[PATCH] backup -> {os.path.basename(bak)}")
        except Exception as e:
            print(f"[PATCH] aviso: falha no backup ({e})")


def _apply(text, anchor, insert_lines, label):
    """Insere `insert_lines` logo apos a linha que contem `anchor`. Se ja contem o conteúdo, pula."""
    # Se o conteudo do insert ja esta no texto, evita duplicar
    if any(line.strip() and line.strip() in text for line in insert_lines if line.strip()):
        print(f"[PATCH] {label}: ja presente (skip).")
        return text, False
    m = re.search(r"^(\s*).*" + re.escape(anchor) + r".*$", text, re.M)
    if not m:
        print(f"[PATCH] {label}: ANCTOR NAO ENCONTRADA => '{anchor}' (TTS.py de outra versao?)")
        return text, False
    ind = m.group(1)
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

    # 1) Forcar float32 em TODOS os modelos quando is_half=False (no fim do _init_models)
    anchor = "self.init_cnhuhbert_weights(self.configs.cnhuhbert_base_path)"
    insert = [
        "# patch: forca float32 em TODOS os modelos (inclusive SV/vocoder) quando is_half=False",
        "if not self.configs.is_half:",
        "    import torch as _torch_pt",
        "    for _k, _v in list(vars(self).items()):",
        "        if isinstance(_v, _torch_pt.nn.Module):",
        "            try:",
        "                setattr(self, _k, _v.float())",
        "            except Exception:",
        "                pass",
    ]
    text, c = _apply(text, anchor, insert, "float-todos-modelos")
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
    if "traceback.print_exc()" in text:
        print("[PATCH] api_v2: traceback ja presente (skip).")
        return True
    # Acha a linha `return JSONResponse(status_code=400, content={"message": "tts failed"...`
    m = re.search(r"^(\s*)return JSONResponse\(status_code=400, content=\{\"message\": \"tts failed\".*$", text, re.M)
    if not m:
        print("[PATCH] api_v2: ancor 'tts failed' nao encontrada (skip).")
        return True
    ind = m.group(1)
    ins = f"{ind}traceback.print_exc()\n"
    text = text[: m.start()] + ins + text[m.start():]
    # garante import traceback
    if "import traceback" not in text:
        text = text.replace("import threading", "import threading\nimport traceback", 1)
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
