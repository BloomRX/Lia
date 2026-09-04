#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hardware-detect.py — o "entendedor de hardware" pro seu App de pré-config do Airi.

Detecta GPU/RAM do PC (Windows, Linux e macOS) e devolve um perfil JSON com:
  1. Cérebro na nuvem (Groq + fallback Cerebras) — igual em QUALQUER PC;
  2. Fallback local — só se o hardware justificar, com o backend certo
     (CUDA / Vulkan / Metal / CPU) e a classe de modelo certa pra VRAM;
  3. Avisos específicos (ex.: RX 580 não tem ROCm; iGPU não vale o esforço).

Sem dependências externas — só biblioteca padrão do Python 3.8+.

Uso:
    python3 hardware-detect.py           # relatório legível
    python3 hardware-detect.py --json    # JSON puro (pra injetar no seu App)

Porte a função classify() + decide() pra linguagem do seu App se quiser —
a lógica de decisão é toda delas.
"""

import argparse
import glob
import json
import platform
import re
import shutil
import subprocess
import sys

# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------

def run_cmd(cmd, timeout=10):
    """Roda um comando e devolve o stdout (ou '' se falhar/timeout)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def total_ram_gb():
    """RAM total do sistema em GB (aproximada)."""
    try:
        if platform.system() == "Linux":
            with open("/proc/meminfo", encoding="ascii") as f:
                m = re.search(r"MemTotal:\s+(\d+) kB", f.read())
            return round(int(m.group(1)) / 1024 / 1024) if m else None
        if platform.system() == "Darwin":
            out = run_cmd(["sysctl", "-n", "hw.memsize"])
            return round(int(out) / 1024 ** 3) if out else None
        if platform.system() == "Windows":
            out = run_cmd([
                "powershell", "-NoProfile", "-Command",
                "[math]::Round((Get-CimInstance Win32_ComputerSystem)"
                ".TotalPhysicalMemory/1GB)",
            ])
            return int(out) if out else None
    except (ValueError, TypeError, OSError):
        pass
    return None


def nvidia_smi_gpus():
    """VRAM exata das NVIDIA via nvidia-smi, se existir."""
    path = shutil.which("nvidia-smi")
    if not path:
        return []
    out = run_cmd([path, "--query-gpu=name,memory.total",
                   "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                gpus.append({"name": parts[0],
                             "vram_gb": round(int(parts[1]) / 1024)})
            except ValueError:
                gpus.append({"name": parts[0], "vram_gb": None})
    return gpus


# ----------------------------------------------------------------------------
# Detecção de GPUs por sistema
# ----------------------------------------------------------------------------

def gpus_windows():
    gpus = []
    out = run_cmd([
        "powershell", "-NoProfile", "-Command",
        "Get-CimInstance Win32_VideoController | "
        "Select-Object Name,AdapterRAM | ConvertTo-Json",
    ])
    if out:
        try:
            data = json.loads(out)
            if isinstance(data, dict):
                data = [data]
            for d in data:
                name = (d.get("Name") or "").strip()
                if name:
                    # AdapterRAM é 32-bit: satura em 4GB. Use só como pista;
                    # nvidia-smi abaixo corrige as NVIDIA com valor exato.
                    hint = round((d.get("AdapterRAM") or 0) / 1024 ** 3)
                    gpus.append({"name": name,
                                 "vram_gb": hint if hint else None})
        except json.JSONDecodeError:
            pass
    _merge_nvidia_smi(gpus)
    return gpus


def gpus_linux():
    gpus = []
    out = run_cmd(["lspci"])
    for line in out.splitlines():
        if re.search(r"VGA compatible controller|3D controller|Display "
                     r"controller (class)", line, re.I):
            name = line.split(":", 2)[-1].strip()
            name = re.sub(r"\[[0-9a-f]{4}:[0-9a-f]{4}\]", "", name)
            name = re.sub(r"\(rev [0-9a-f]+\)", "", name).strip()
            if name:
                gpus.append({"name": name, "vram_gb": None})
    # VRAM exata de GPUs AMD/Intel via sysfs (driver amdgpu/i915/xe)
    vrams = []
    for f in glob.glob("/sys/class/drm/card*/device/mem_info_vram_total"):
        try:
            with open(f, encoding="ascii") as fh:
                gb = round(int(fh.read().strip()) / 1024 ** 3)
            if gb:
                vrams.append(gb)
        except (OSError, ValueError):
            continue
    for i, gb in enumerate(vrams):
        if i < len(gpus) and gpus[i]["vram_gb"] is None:
            gpus[i]["vram_gb"] = gb
    _merge_nvidia_smi(gpus)
    return gpus


def gpus_macos():
    gpus = []
    out = run_cmd(["system_profiler", "SPDisplaysDataType"])
    for line in out.splitlines():
        if "Chipset Model" in line:
            name = line.split(":", 1)[-1].strip()
            if name:
                gpus.append({"name": name, "vram_gb": None})
    return gpus


def _merge_nvidia_smi(gpus):
    """Substitui a VRAM (e completa nomes) das NVIDIA com dados exatos."""
    for smi_gpu in nvidia_smi_gpus():
        for g in gpus:
            if "nvidia" in g["name"].lower():
                g["vram_gb"] = smi_gpu["vram_gb"]
                break
        else:
            gpus.append(smi_gpu)


# ----------------------------------------------------------------------------
# Classificação e decisão
# ----------------------------------------------------------------------------

def classify(name):
    n = name.lower()
    if "nvidia" in n or re.search(r"\b(gtx|rtx)\s*\d{3,4}", n):
        return "nvidia"
    if "apple" in n and re.search(r"\bm[1-4]\b", n):
        return "apple"
    if "radeon" in n or "amd" in n or re.search(r"\brx\s?\d{3,4}\b", n) \
            or "vega" in n:
        return "amd"
    if "intel" in n and re.search(r"\barc\b|iris|uhd|hd graphics", n):
        return "intel"
    return "desconhecido"


def amd_generation(name):
    n = name.lower()
    if "vega" in n or "radeon vii" in n:
        return "pre-rdna"
    m = re.search(r"\brx\s?(\d{3,4})\b", n)
    if not m:
        return None
    series = int(m.group(1))
    if series < 5000:
        return "pre-rdna"       # RX 470/480/570/580/590 (Polaris)
    if series < 7000:
        return "rdna1-2"        # RX 5000/6000
    return "rdna3"              # RX 7000


def is_igpu(name):
    n = name.lower()
    return bool(re.search(r"uhd|iris|hd graphics", n))


def model_class_for_vram(vram_gb):
    """Classe de modelo Q4_K_M que cabe confortavelmente na VRAM."""
    if vram_gb is None:
        return "7B-8B Q4 (confirmar VRAM no app)"
    if vram_gb <= 4:
        return "3B-4B Q4 (ex.: Qwen3 4B, Llama 3.2 3B)"
    if vram_gb <= 7:
        return "4B-7B Q4 (ex.: Qwen3 4B, Mistral 7B apertado)"
    if vram_gb <= 11:
        return "7B-8B Q4 (ex.: Llama 3.1 8B, Qwen3 8B)"
    if vram_gb <= 15:
        return "12B-14B Q4 (ex.: Qwen3 14B, Phi-4 14B)"
    return "24B-32B Q3/Q4 (ex.: Qwen3 32B)"


def decide(gpus, ram_gb, os_name):
    """Cria o perfil de configuração a partir do hardware detectado."""
    profile = {
        "cloud_primary": {   # independe de hardware — vale pra todo PC
            "provider": "Groq",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama-3.3-70b-versatile",
        },
        "cloud_fallback": {
            "provider": "Cerebras",
            "base_url": "https://api.cerebras.ai/v1",
            "model": "qwen-3-235b-a22b-instruct",
        },
        "local_fallback": {"recommended": False, "backend": "cpu",
                           "runtime": None, "model_class": None,
                           "base_url": "http://localhost:1234/v1"},
        "voice": {},           # STT local (Whisper)
        "notes": [],
    }

    # --- escolhe a "melhor GPU" do PC (dGPU > iGPU) --------------------------
    ranked = sorted(gpus, key=lambda g: (is_igpu(g["name"]),
                                         classify(g["name"]) == "desconhecido"))
    best = ranked[0] if ranked else None
    vendor = classify(best["name"]) if best else "none"
    vram = best.get("vram_gb") if best else None

    if vendor == "nvidia":
        lf = profile["local_fallback"]
        lf.update(recommended=True, backend="cuda",
                  runtime="LM Studio (usa CUDA sozinho) ou Ollama",
                  model_class=model_class_for_vram(vram))
        profile["voice"] = {"stt": "faster-whisper device=cuda",
                            "nota": "GPU NVIDIA acelera STT e TTS local"}
        profile["notes"].append(
            "NVIDIA detectada: caminho mais fácil — CUDA é suportado "
            "por tudo (LM Studio, Ollama, Whisper).")

    elif vendor == "apple":
        lf = profile["local_fallback"]
        budget = round((ram_gb or 8) * 0.7)
        lf.update(recommended=True, backend="metal",
                  runtime="LM Studio ou Ollama (Metal nativo)",
                  model_class=model_class_for_vram(
                      8 if budget >= 11 else 4 if budget >= 5 else 2))
        profile["voice"] = {"stt": "whisper.cpp Metal ou CPU",
                            "nota": "RAM unificada acelera STT"}
        profile["notes"].append(
            "Apple Silicon: usar RAM unificada como orçamento de modelo "
            f"(~{budget} GB úteis de {ram_gb} GB).")

    elif vendor == "amd":
        lf = profile["local_fallback"]
        lf.update(recommended=True, backend="vulkan",
                  runtime="LM Studio com runtime Vulkan (ou koboldcpp Vulkan)",
                  model_class=model_class_for_vram(vram))
        profile["voice"] = {"stt": "faster-whisper int8 na CPU (leve o bastante)"}
        gen = amd_generation(best["name"])
        if gen == "pre-rdna":
            profile["notes"].append(
                "AMD Polaris/VEGA (ex.: RX 580): SEM ROCm e SEM aceleração "
                "no Ollama — Vulkan via LM Studio/koboldcpp é o único caminho. "
                "~17-22 tok/s em 7-8B Q4, ~35 tok/s em 4B.")
        elif gen in ("rdna1-2", "rdna3"):
            profile["notes"].append(
                "AMD RDNA: no Windows use Vulkan (sem dor); no Linux o ROCm "
                "existe mas é parcial por modelo — Vulkan continua o seguro.")
        else:
            profile["notes"].append(
                "AMD detectada: usar backend Vulkan por padrão.")

    elif vendor == "intel":
        lf = profile["local_fallback"]
        if is_igpu(best["name"]):
            lf.update(backend="cpu",
                      model_class="apenas 1B-3B (iGPU não vale o esforço)")
            profile["notes"].append(
                "Só iGPU Intel: melhor pular o fallback local e confiar na "
                "nuvem; se quiser offline, modelos 1B-3B na CPU.")
        else:
            lf.update(recommended=True, backend="vulkan",
                      runtime="LM Studio (Vulkan) ou IPEX-LLM (SYCL)",
                      model_class=model_class_for_vram(vram))
            profile["notes"].append(
                "Intel Arc: Vulkan funciona bem; SYCL/IPEX-LLM extrai um "
                "pouco mais de desempenho.")
        profile["voice"] = {"stt": "faster-whisper int8 na CPU"}

    else:
        lf = profile["local_fallback"]
        lf.update(backend="cpu",
                  model_class="1B-3B Q4 se RAM >= 8GB; senão, só nuvem")
        profile["voice"] = {"stt": "faster-whisper int8 na CPU"}
        profile["notes"].append(
            "Sem GPU utilizável: modo CPU — mantenha o local como opção "
            "mínima ou desabilite; a nuvem (Groq) segura tudo.")

    # --- Voz: STT + TTS conforme o hardware ---------------------------------
    profile["voice"] = dict(profile["voice"] or {})  # normaliza
    profile["voice"]["stt_nuvem"] = (
        "Groq whisper-large-v3-turbo (grátis: 20 req/min, 2.000/dia, "
        "28.800s de áudio/dia, latência < 300ms)")
    if lf["backend"] == "cuda":
        profile["voice"]["tts"] = ("Kokoro-82M via Kokoro-FastAPI (OpenAI-"
                                   "compatible) — GPU NVIDIA sobra; ou Qwen3-TTS")
    elif lf["backend"] == "metal":
        profile["voice"]["tts"] = "Kokoro-82M (ONNX/Metal, tempo real)"
    else:
        profile["voice"]["tts"] = (
            "Piper (RTF ~0.03, ~40ms p/ 1ª palavra, <1GB RAM, tem pt-BR) ou "
            "Kokoro-82M via Kokoro-FastAPI (melhor qualidade, roda em CPU em "
            "tempo real). EVITE Qwen3-TTS local: é PyTorch, não acelera em "
            "AMD/Intel — vira segundos por frase na CPU")
    profile["voice"]["tts_nuvem"] = (
        "Edge-TTS (grátis, sem chave, streaming ~instantâneo, vozes pt-BR "
        "da Microsoft; serviço não-oficial) — bom plano B")

    # --- Skills: o que cada uma exige neste hardware -------------------------
    # Regra de ouro: skills dependem de TOOL CALLING. Modelos locais pequenos
    # (4B-8B) chamam ferramentas mal; o cérebro da nuvem (70B+) é quem faz
    # skills funcionar. O fallback local é só pra conversa offline.
    lf = profile["local_fallback"]
    profile["skills"] = {
        "_aviso_geral": (
            "Skills (busca, arte, arquivos, Minecraft...) exigem tool calling: "
            "use o cérebro da nuvem. Modelos locais pequenos quebram tool calls."
            if lf["recommended"] else
            "Skills dependem de tool calling — mais um motivo pro cérebro na nuvem."),
        "web_search": {
            "provider": "Tavily",
            "custo": "grátis (~1.000 buscas/mês)",
            "como": "Settings → Modules → Web Search (colar TAVILY_API_KEY)",
        },
        "artistry_imagem": artistry_reco(vendor, vram),
        "vision": {
            "provider": "Groq (llama-4-scout/maverick, multimodal) ou Gemini 2.5 Flash grátis",
            "como": "Settings → Providers → Vision + ativar Vision Capture em Modules → Vision",
        },
        "minecraft": minecraft_reco(ram_gb),
        "factorio": {"possivel": bool(ram_gb and ram_gb >= 16),
                     "nota": "mesma receita do Minecraft: servidor local + agente; cérebro remoto"},
        "arquivos_mcp": {
            "provider": "MCP filesystem server (grátis, local)",
            "como": "Settings → Modules → MCP Server; ferramentas de arquivo rodam na CPU",
            "risco": "dar acesso a arquivos = permitir apagar coisas; comece com pastas dedicadas",
        },
        "discord_telegram": {"custo": "grátis", "nota": "roda como bot local, sem custo"},
    }

    if ram_gb and ram_gb < 16 and profile["local_fallback"]["recommended"]:
        profile["notes"].append(
            f"RAM total ({ram_gb}GB) modesta: prefira modelos de até 8B no "
            "fallback local para não competir com o Airi/TTS por memória.")
    return profile


def artistry_reco(vendor, vram):
    """Recomendação de geração de imagem conforme a GPU."""
    if vendor == "nvidia" and (vram or 0) >= 8:
        return {"recomendado": "nuvem grátis como padrão; ComfyUI local opcional",
                "local": f"ComfyUI cabe bem ({vram}GB VRAM, SD1.5/SDXL rápidos)",
                "nota": "imagem local usa PyTorch/CUDA — só NVIDIA tem caminho fácil"}
    if vendor == "amd":
        return {"recomendado": "provedor de imagem na nuvem",
                "local": "evitar: ComfyUI/PyTorch não usa Vulkan; em Polaris cai pra CPU "
                         "(minutos por imagem)",
                "nota": "créditos grátis (NVIDIA NIM, Cloudflare Workers AI ~10K neurons/dia c/ FLUX)"}
    if vendor == "apple":
        return {"recomendado": "nuvem como padrão",
                "local": "ComfyUI via MPS funciona razoável p/ SD1.5 em M1-M3",
                "nota": "-"}
    return {"recomendado": "provedor de imagem na nuvem",
            "local": "inviável local (sem GPU utilizável)",
            "nota": "-"}


def minecraft_reco(ram_gb):
    """Veredito de Minecraft conforme a RAM (servidor + agente rodam local)."""
    if ram_gb is None:
        return {"possivel": None, "nota": "RAM desconhecida — exigir >= 8GB livres p/ MC"}
    if ram_gb >= 16:
        return {"possivel": True,
                "nota": f"{ram_gb}GB RAM: servidor MC (2-4GB) + agente + Airi cabem; "
                        "feche navegador pesado enquanto jogar"}
    if ram_gb >= 8:
        return {"possivel": True,
                "nota": f"{ram_gb}GB RAM: dá, mas com servidor MC enxuto (2GB) e nada "
                        "de outro pesado aberto"}
    return {"possivel": False,
            "nota": f"{ram_gb}GB RAM: curto pra servidor + Airi juntos; use um servidor "
                    "remoto barato ou pule Minecraft"}


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def collect():
    os_name = platform.system()
    gpus = {"Windows": gpus_windows, "Linux": gpus_linux,
            "Darwin": gpus_macos}[os_name]()
    for g in gpus:
        g.setdefault("vendor", classify(g["name"]))
    return {
        "os": f"{os_name} {platform.release()}",
        "machine": platform.machine(),
        "ram_gb": total_ram_gb(),
        "gpus": gpus,
    }


def print_human(info, profile):
    print("=" * 62)
    print("PERFIL DE HARDWARE — config recomendada pro Airi")
    print("=" * 62)
    print(f"Sistema : {info['os']} ({info['machine']})")
    print(f"RAM     : {info['ram_gb']} GB")
    print("GPUs    :")
    if not info["gpus"]:
        print("  (nenhuma detectada — modo CPU)")
    for g in info["gpus"]:
        vram = f", {g['vram_gb']}GB VRAM" if g.get("vram_gb") else ""
        print(f"  - {g['name']} [{g['vendor']}]{vram}")
    print("-" * 62)
    cp = profile["cloud_primary"]
    print(f"CÉREBRO (todos os PCs): {cp['provider']} — {cp['model']}")
    print(f"  base_url: {cp['base_url']}")
    cf = profile["cloud_fallback"]
    print(f"FALLBACK NUVEM        : {cf['provider']} — {cf['model']}")
    lf = profile["local_fallback"]
    print("-" * 62)
    if lf["recommended"]:
        print(f"FALLBACK LOCAL        : SIM — backend {lf['backend']}")
        print(f"  runtime : {lf['runtime']}")
        print(f"  modelo  : {lf['model_class']}")
        print(f"  base_url: {lf['base_url']}")
    else:
        print("FALLBACK LOCAL        : NÃO recomendado neste hardware")
        print(f"  (backend possível: {lf['backend']} — {lf['model_class']})")
    if profile["voice"]:
        print(f"VOZ (STT local)       : {profile['voice'].get('stt', '-')}")
    if profile.get("skills"):
        print("-" * 62)
        print("SKILLS (todas com cérebro na nuvem):")
        for name, s in profile["skills"].items():
            if name.startswith("_"):
                print(f"  ⚠ {s}")
                continue
            possivel = s.get("possivel", None)
            flag = {True: "✔", False: "✘", None: "•"}[possivel] \
                if possivel is not None else "•"
            provider = s.get("provider") or s.get("recomendado", "")
            print(f"  {flag} {name}: {provider}")
            for k in ("como", "nota", "local", "custo", "risco"):
                if s.get(k) and s[k] != "-":
                    print(f"      {k}: {s[k]}")
    if profile["notes"]:
        print("-" * 62)
        print("NOTAS:")
        for n in profile["notes"]:
            print(f"  • {n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true",
                    help="saída em JSON (para injetar no App)")
    args = ap.parse_args()

    info = collect()
    profile = decide(info["gpus"], info["ram_gb"], info["os"])
    if args.json:
        print(json.dumps({"hardware": info, "profile": profile},
                         ensure_ascii=False, indent=2))
    else:
        print_human(info, profile)


if __name__ == "__main__":
    main()
