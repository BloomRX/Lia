# ============================================================================
#  fix_sovits_fp32.py
#  Corrige o erro "Input type (torch.FloatTensor) and weight type
#  (torch.HalfTensor)" do GPT-SoVITS em CPU.
#
#  Causa: o GPT-SoVITS s1_train salva os pesos do GPT em meia precisao
#  (float16) no diretorio de "half_weights" (GPT_weights_v2Pro). Na
#  inferencia em CPU (is_half=False, inputs float32) isso gera o mismatch.
#
#  Este script converte todos os tensores float16 de cada checkpoint para
#  float32 e regrava o arquivo (com backup .bak). Idempotente e robusto:
#    * processa CADA arquivo de forma independente (falha de um nao aborta os demais)
#    * fallback no argumento weights_only do torch.load
#    * tenta converter tambem .ckpt (PyTorch Lightning) e .pth
#
#  Uso:
#    python fix_sovits_fp32.py <gpt.ckpt> [sovits.pth] [...]
#    (passe PRIMEIRO o ckpt do GPT, que e o que normalmente carrega pesos fp16)
# ============================================================================
import sys
import os
import shutil
import traceback
import torch


def _walk(d, path=""):
    """Retorna lista de (nome_campo, shape) de tensores float16."""
    found = []
    if isinstance(d, dict):
        for k, v in d.items():
            found += _walk(v, f"{path}.{k}" if path else str(k))
    elif isinstance(d, (list, tuple)):
        for i, v in enumerate(d):
            found += _walk(v, f"{path}[{i}]")
    elif isinstance(d, torch.Tensor):
        if d.dtype == torch.float16:
            found.append((path, tuple(d.shape)))
    return found


def _conv(o):
    """Converte recursivamente tensores float16 -> float32."""
    if isinstance(o, dict):
        return {k: _conv(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return type(o)(_conv(v) for v in o)
    if isinstance(o, torch.Tensor) and o.dtype == torch.float16:
        return o.float()
    return o


def _load_torch(path):
    """Tenta carregar um checkpoint de forma compatível com varias versoes."""
    attempts = [
        dict(map_location="cpu", weights_only=False),
        dict(map_location="cpu"),
        dict(),
    ]
    last = None
    for kw in attempts:
        try:
            return torch.load(path, **kw)
        except TypeError as e:
            last = e            # argumento nao suportado -> tenta proximo
        except Exception as e:
            last = e
            raise               # erro real -> nao tenta de novo com kwargs mais fracos
    if last is not None:
        raise last


def fix(path):
    if not path or not os.path.exists(path):
        print(f"  (arquivo não encontrado: {path})")
        return
    name = os.path.basename(path)
    dirn = os.path.dirname(path)
    marker = os.path.join(dirn, os.path.basename(path) + ".fp32ok")

    # Se ja convertido e o arquivo nao foi regravado desde entao, pula.
    if os.path.exists(marker) and os.path.getmtime(marker) >= os.path.getmtime(path):
        print(f"  {name}: já convertido (skip)")
        return

    print(f"  {name}: carregando...")
    try:
        ck = _load_torch(path)
    except Exception as e:
        print(f"  {name}: ⚠️ não consegui ler o arquivo ({type(e).__name__}: {e}) — pulando (tenta o próximo).")
        return

    fp16 = _walk(ck)
    if fp16:
        print(f"  {name}: {len(fp16)} tensores float16 encontrados (ex.: {fp16[0][0]} {fp16[0][1]})")
        bak = path + ".bak"
        if not os.path.exists(bak):
            try:
                shutil.copy2(path, bak)
                print(f"  {name}: backup -> {os.path.basename(bak)}")
            except Exception as e:
                print(f"  {name}: ⚠️ falha no backup ({e}) — continuando sem backup.")
        try:
            torch.save(_conv(ck), path)
            print(f"  {name}: ✅ convertido p/ float32 e salvo.")
        except Exception as e:
            print(f"  {name}: ⚠️ falha ao salvar ({e})")
            return
    else:
        print(f"  {name}: ✅ já está float32 (nada a fazer).")

    # marca como ok apenas depois de processar com sucesso
    try:
        with open(marker, "w", encoding="utf-8") as f:
            f.write("ok")
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python fix_sovits_fp32.py <gpt.ckpt> [sovits.pth] [...]")
        sys.exit(1)
    for a in sys.argv[1:]:
        fix(a)
    print("OK")
