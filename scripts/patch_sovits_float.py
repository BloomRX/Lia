# ============================================================================
#  patch_sovits_float.py
#  Corrige o erro "Input type (torch.FloatTensor) and weight type
#  (torch.HalfTensor)" do GPT-SoVITS em CPU.
#
#  Causa: o treinamento salva os pesos em meia precisao (float16). Na
#  inferencia em CPU (is_half=False, inputs float32), isso gera o mismatch.
#
#  Este script faz um patch cirurgico no TTS.py do GPT-SoVITS: logo depois de
#  carregar os pesos, ele forca o modelo do VITS e do T2S (GPT) para float32
#  quando is_half=False. Assim, independente do dtype salvo no checkpoint,
#  o modelo roda em fp32.
#
#  Idempotente: se a linha de cast ja existir, nao duplica. Cria backup .bak
#  na primeira vez. Funciona mesmo que o .pth nao possa ser lido por torch.load.
#
#  Uso:
#    python patch_sovits_float.py <caminho_do_TTS.py>
# ============================================================================
import sys
import re
import os
import shutil


PAIRS = [
    # (anchor_line, cast_line) — forca .float() do VITS (SoVITS)
    ("self.vits_model = vits_model", "self.vits_model = self.vits_model.float()"),
    # (anchor_line, cast_line) — forca .float() do T2S (GPT)
    ("self.t2s_model = t2s_model", "self.t2s_model = self.t2s_model.float()"),
]


def patch(path):
    if not os.path.exists(path):
        print(f"[PATCH] arquivo nao encontrado: {path}")
        return False

    with open(path, encoding="utf-8") as f:
        text = f.read()

    # backup so na primeira vez
    bak = path + ".bak"
    if not os.path.exists(bak):
        try:
            shutil.copy2(path, bak)
            print(f"[PATCH] backup -> {os.path.basename(bak)}")
        except Exception as e:
            print(f"[PATCH] aviso: falha no backup ({e}) — seguindo sem backup.")

    applied = []
    for anchor, castline in PAIRS:
        if castline in text:
            continue  # ja patched
        m = re.search(r"^(\s*)" + re.escape(anchor) + r"[ \t]*\n", text, re.M)
        if not m:
            print(f"[PATCH] ancor nao encontrada (TTS.py de outra versao?): {anchor}")
            continue
        ind = m.group(1)
        ins = f"{ind}if not self.configs.is_half:\n{ind}    {castline}\n"
        text = text[: m.end()] + ins + text[m.end():]
        applied.append(castline)

    if not applied:
        print("[PATCH] nada a fazer (ja patched ou ancoras ausentes).")
        return True

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[PATCH] TTS.py patched: +{len(applied)} cast .float()")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python patch_sovits_float.py <caminho_do_TTS.py>")
        sys.exit(1)
    ok = True
    for a in sys.argv[1:]:
        if not patch(a):
            ok = False
    print("PATCH_OK" if ok else "PATCH_INCOMPLETO")
