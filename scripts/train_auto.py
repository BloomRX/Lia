#!/usr/bin/env python3
"""
Treinamento automático GPT-SoVITS
Uso: python train_auto.py --model NOME --audio-dir DIR --repo DIR --output DIR
"""
import os
import sys
import json
import argparse
import subprocess
import traceback
import time

# Script de extração de semantic tokens (v2Pro) — gera 6-name2semantic.tsv
# para o s1_train.py (GPT). Construído como o SoVITS para casar com o
# pretrained s2G v2Pro (o 3-get-semantic.py oficial injeta 'version' pelo
# tamanho e colide com 'version: v2Pro' do config).
semantic_code = '''import sys, os, torch, traceback
repo = sys.argv[1]
inp_text = sys.argv[2]
opt_dir = sys.argv[3]
pretrained_s2G = sys.argv[4]
s2config_path = sys.argv[5]

for p in [repo, os.path.join(repo, "GPT_SoVITS"), os.path.join(repo, "tools"), os.path.join(repo, "GPT_SoVITS", "module")]:
    if p not in sys.path:
        sys.path.insert(0, p)

import utils
from module.models import SynthesizerTrn
from tools.my_utils import clean_path

device = "cuda" if torch.cuda.is_available() else "cpu"
hps = utils.get_hparams_from_file(s2config_path)
vq_model = SynthesizerTrn(
    hps.data.filter_length // 2 + 1,
    hps.train.segment_size // hps.data.hop_length,
    n_speakers=hps.data.n_speakers,
    **hps.model,
)
vq_model.eval()
vq_model = vq_model.to(device)
print("loading", pretrained_s2G, flush=True)
vq_model.load_state_dict(torch.load(pretrained_s2G, map_location="cpu", weights_only=False)["weight"], strict=False)

hubert_dir = os.path.join(opt_dir, "4-cnhubert")
semantic_path = os.path.join(opt_dir, "6-name2semantic.tsv")

def name2go(wav_name, lines):
    hubert_path = os.path.join(hubert_dir, wav_name + ".pt")
    if not os.path.exists(hubert_path):
        return
    ssl_content = torch.load(hubert_path, map_location="cpu").to(device)
    with torch.no_grad():
        codes = vq_model.extract_latent(ssl_content)
    semantic = " ".join([str(i) for i in codes[0, 0, :].tolist()])
    lines.append("%s\\t%s" % (wav_name, semantic))

with open(inp_text, "r", encoding="utf8") as f:
    lines = f.read().strip("\\n").split("\\n")

out = []
for line in lines:
    try:
        wav_name, spk_name, language, text = line.split("|")
        wav_name = os.path.basename(clean_path(wav_name))
        name2go(wav_name, out)
    except Exception as e:
        print("skip:", repr(e), flush=True)

with open(semantic_path, "w", encoding="utf8") as f:
    f.write("\\n".join(out))
print("semantic done:", len(out), flush=True)
'''

def setup_paths(repo_dir):
    paths = [
        repo_dir,
        os.path.join(repo_dir, "GPT_SoVITS"),
        os.path.join(repo_dir, "GPT_SoVITS", "BigVGAN"),
        os.path.join(repo_dir, "tools"),
        os.path.join(repo_dir, "tools", "asr"),
        os.path.join(repo_dir, "tools", "uvr5"),
    ]
    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        import site
        for sp in site.getsitepackages():
            if "packages" in sp:
                pth = os.path.join(sp, "gpt_sovits_paths.pth")
                with open(pth, "w") as f:
                    f.write("\n".join(paths))
                break
    except:
        pass

def save_progress(output_dir, step):
    """Salva progresso para poder retomar depois."""
    progress_file = os.path.join(output_dir, ".training_progress.json")
    with open(progress_file, "w") as f:
        json.dump({"step": step, "timestamp": time.time()}, f)

def load_progress(output_dir):
    """Carrega progresso salvo."""
    progress_file = os.path.join(output_dir, ".training_progress.json")
    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r") as f:
                return json.load(f).get("step", 0)
        except:
            pass
    return 0

def run_step(cmd, cwd, env, step_name, timeout=3600, max_error_lines=5):
    print(f"\n{'='*50}")
    print(f"[{step_name}] ▶️ Iniciando...")
    sys.stdout.flush()
    
    start_time = time.time()
    error_count = 0
    last_error_type = ""
    in_traceback = False
    traceback_lines = []
    
    try:
        p = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=1, universal_newlines=True, encoding="utf-8", errors="replace",
            cwd=cwd, env=env,
        )
        
        for line in iter(p.stdout.readline, ""):
            line = line.rstrip()
            elapsed = int(time.time() - start_time)
            
            if "Traceback (most recent call last):" in line:
                in_traceback = True
                traceback_lines = [line]
                error_count += 1
                continue
            
            if in_traceback:
                traceback_lines.append(line)
                if line and not line.startswith(" ") and not line.startswith("  File"):
                    in_traceback = False
                    error_type = line.split(":")[0] if ":" in line else line
                    if error_type != last_error_type or error_count <= max_error_lines:
                        if error_type != last_error_type:
                            print(f"[{step_name}] [{elapsed}s] ⚠️ {error_type}")
                            last_error_type = error_type
                        for tb_line in traceback_lines[-3:]:
                            print(f"[{step_name}] [{elapsed}s]   {tb_line}")
                    elif error_count == max_error_lines + 1:
                        print(f"[{step_name}] [{elapsed}s]   ... (erros repetidos omitidos)")
                    traceback_lines = []
                    sys.stdout.flush()
                continue
            
            if line:
                print(f"[{step_name}] [{elapsed}s] {line}")
                sys.stdout.flush()
        
        p.wait(timeout=timeout)
        elapsed = int(time.time() - start_time)
        
        if error_count > 0:
            print(f"[{step_name}] ⚠️ {error_count} erro(s)")
        
        if p.returncode == 0:
            print(f"[{step_name}] ✅ ({elapsed}s)")
            return True
        else:
            print(f"[{step_name}] ❌ código {p.returncode} ({elapsed}s)")
            return False
            
    except subprocess.TimeoutExpired:
        p.kill()
        print(f"[{step_name}] ❌ Timeout")
        return False
    except Exception as e:
        print(f"[{step_name}] ❌ {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--audio-dir", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--lang", default="pt")
    parser.add_argument("--epochs-s2", type=int, default=8)
    parser.add_argument("--epochs-s1", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=1)
    args = parser.parse_args()

    repo = args.repo
    vpy = args.python
    model_name = args.model
    audio_dir = args.audio_dir
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    setup_paths(repo)

    # Environment
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["no_proxy"] = "localhost, 127.0.0.1, ::1"
    env["all_proxy"] = ""
    env["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    # ffmpeg setup
    venv_dir = os.path.dirname(os.path.dirname(vpy))
    ffmpeg_bin = os.path.join(venv_dir, "Lib", "site-packages", "imageio_ffmpeg", "binaries")
    if os.path.isdir(ffmpeg_bin):
        env["PATH"] = ffmpeg_bin + ";" + env.get("PATH", "")
        ffmpeg_exe = os.path.join(ffmpeg_bin, "ffmpeg.exe")
        if not os.path.exists(ffmpeg_exe):
            for f in os.listdir(ffmpeg_bin):
                if f.startswith("ffmpeg") and f.endswith(".exe"):
                    try:
                        import shutil
                        shutil.copy2(os.path.join(ffmpeg_bin, f), ffmpeg_exe)
                        print(f"  FFMPEG: {f} → ffmpeg.exe")
                    except:
                        pass
                    break
        venv_scripts = os.path.join(venv_dir, "Scripts")
        ffmpeg_in_scripts = os.path.join(venv_scripts, "ffmpeg.exe")
        if not os.path.exists(ffmpeg_in_scripts) and os.path.exists(ffmpeg_exe):
            try:
                import shutil
                shutil.copy2(ffmpeg_exe, ffmpeg_in_scripts)
            except:
                pass

    # NLTK data — force download to venv-local dir (avoids ~/nltk_data permission issues)
    nltk_data_dir = os.path.join(venv_dir, "nltk_data")
    os.makedirs(nltk_data_dir, exist_ok=True)
    env["NLTK_DATA"] = nltk_data_dir
    env["NLTK_ALLOW_PROXIED_URLOPEN"] = "1"

    # Detectar etapa inicial (retomar treino)
    saved_step = load_progress(output_dir)
    
    # Verificar se etapas já foram concluídas
    sliced_dir = os.path.join(output_dir, "slicer_opt")
    asr_output = os.path.join(output_dir, "asr_opt")
    hubert_dir = os.path.join(output_dir, "4-cnhubert")
    wav32_dir = os.path.join(output_dir, "5-wav32k")
    sv_dir = os.path.join(output_dir, "7-sv_cn")
    
    has_slices = len([f for f in os.listdir(sliced_dir) if f.endswith(".wav")]) > 10 if os.path.isdir(sliced_dir) else False
    has_asr = len([f for f in os.listdir(asr_output) if f.endswith(".list")]) > 0 if os.path.isdir(asr_output) else False
    has_hubert = os.path.isdir(hubert_dir) and len(os.listdir(hubert_dir)) > 10 if os.path.isdir(hubert_dir) else False
    has_wav32 = os.path.isdir(wav32_dir) and len(os.listdir(wav32_dir)) > 10 if os.path.isdir(wav32_dir) else False
    has_sv = os.path.isdir(sv_dir) and len([f for f in os.listdir(sv_dir) if f.endswith(".pt")]) > 10 if os.path.isdir(sv_dir) else False
    
    # Encontrar .list
    list_file = None
    if has_asr:
        for f in os.listdir(asr_output):
            if f.endswith(".list"):
                list_file = os.path.join(asr_output, f)
                break
    
    # Determinar por onde começar
    # heuristic = a etapa MAIS CEDO que podemos começar dado o que já existe
    # (evita refazer slice/ASR que já foram concluídos).
    if has_slices and has_asr:
        heuristic = 3  # Pular pra dataset (BERT + HuBERT)
    elif has_slices:
        heuristic = 1  # Pular pra ASR
    else:
        heuristic = 0  # Começar do zero
    # O progresso salvo (.training_progress.json) guarda a etapa MAIS AVANÇADA
    # já concluída (ex.: SoVITS terminou = 6). Retomamos do MAIOR dos dois, para
    # NÃO refazer etapas caras (ex.: 24 min de SoVITS) após um erro no GPT.
    # Obs.: a etapa 4 (Dataset) SEMPRE re-extrai HuBERT em float32 quando roda;
    # então começar além dela significa que ela já foi concluída com sucesso.
    start_step = max(saved_step, heuristic)
    if start_step == 6:
        print("   ℹ️ SoVITS já concluído — indo direto pro GPT")

    print("=" * 60)
    print(f"🔥 Treinamento GPT-SoVITS — {model_name}")
    print(f"   Retomando da etapa {start_step}/6")
    if has_slices: print(f"   ✅ Slice: OK")
    if has_asr: print(f"   ✅ ASR: OK")
    if has_hubert: print(f"   ✅ HuBERT: OK")
    if has_wav32: print(f"   ✅ Wav32k: OK")
    print("=" * 60)
    sys.stdout.flush()

    # ── ETAPA 0: Deps ──
    if start_step <= 0:
        print("\n[0/6] 📦 Dependências...")
        sys.stdout.flush()
        for pkg in ["faster-whisper", "funasr", "opencc", "nltk", "pytorch-lightning", "tensorboard", "torchmetrics<=1.5", "matplotlib", "librosa"]:
            mod = pkg.split("<")[0].split("=")[0].replace("-", "_")
            r = subprocess.run([vpy, "-c", f"import {mod}"], capture_output=True, creationflags=0x08000000)
            if r.returncode != 0:
                subprocess.run([vpy, "-m", "pip", "install", "--disable-pip-version-check", "--prefer-binary", pkg],
                               capture_output=True, creationflags=0x08000000)
        save_progress(output_dir, 1)

    # ── ETAPA 1: Slice ──
    if start_step <= 0:
        print("\n[1/6] 🔪 Slice...")
        sys.stdout.flush()
        if has_slices:
            n = len([f for f in os.listdir(sliced_dir) if f.endswith(".wav")])
            print(f"  ⏭️ Pulando — {n} segmentos")
        else:
            os.makedirs(sliced_dir, exist_ok=True)
            try:
                from slicer2 import Slicer
                from tools.my_utils import load_audio
                import numpy as np
                from scipy.io import wavfile

                audio_files = [os.path.join(audio_dir, f) for f in sorted(os.listdir(audio_dir))
                               if f.lower().endswith(('.wav', '.mp3', '.flac', '.ogg', '.m4a'))]
                if not audio_files:
                    print("❌ Nenhum áudio!"); sys.exit(1)
                print(f"  📁 {len(audio_files)} áudio(s)")

                slicer = Slicer(sr=32000, threshold=-40, min_length=400, min_interval=300, hop_size=10, max_sil_kept=500)
                total = 0
                for inp_path in audio_files:
                    name = os.path.basename(inp_path)
                    print(f"  🔪 {name}")
                    sys.stdout.flush()
                    try:
                        audio = load_audio(inp_path, 32000)
                        for chunk, start, end in slicer.slice(audio):
                            tmp_max = np.abs(chunk).max()
                            if tmp_max > 1: chunk /= tmp_max
                            if tmp_max > 0: chunk = (chunk / tmp_max * 0.225) + 0.75 * chunk
                            wavfile.write(os.path.join(sliced_dir, "%s_%010d_%010d.wav" % (name, start, end)),
                                          32000, (chunk * 32767).astype(np.int16))
                            total += 1
                    except Exception as e:
                        print(f"  ⚠️ {e}")
                print(f"  ✅ {total} segmentos")
                if total == 0: print("❌ Nenhum segmento!"); sys.exit(1)
            except Exception as e:
                print(f"❌ Slice: {e}"); sys.exit(1)
        save_progress(output_dir, 2)

    # ── ETAPA 2: ASR ──
    if start_step <= 1:
        print("\n[2/6] 🎤 ASR (Faster Whisper)...")
        sys.stdout.flush()
        if has_asr:
            print(f"  ⏭️ Pulando — ASR já feito")
        else:
            os.makedirs(asr_output, exist_ok=True)
            asr_script = os.path.join(repo, "tools", "asr", "fasterwhisper_asr.py")
            if not os.path.exists(asr_script):
                asr_script = os.path.join(repo, "tools", "asr", "funasr_asr.py")
            if not os.path.exists(asr_script):
                print("❌ Script ASR não encontrado!"); sys.exit(1)
            print("  ⏳ Primeira vez: baixa modelo ~3GB")
            asr_cmd = [vpy, asr_script, "-i", sliced_dir, "-o", asr_output, "-s", "large-v3", "-l", "auto", "-p", "float32"]
            if not run_step(asr_cmd, repo, env, "ASR", timeout=1800):
                print("❌ ASR falhou!"); sys.exit(1)
            
            # Encontrar .list gerado
            for f in os.listdir(asr_output):
                if f.endswith(".list"):
                    list_file = os.path.join(asr_output, f)
                    break
        save_progress(output_dir, 3)

    # ── ETAPA 3: Fix PT→EN ──
    if start_step <= 2:
        print("\n[3/6] 🌐 Idioma...")
        sys.stdout.flush()
        if not list_file and has_asr:
            for f in os.listdir(asr_output):
                if f.endswith(".list"):
                    list_file = os.path.join(asr_output, f)
                    break
        if list_file:
            with open(list_file, "r", encoding="utf-8") as f:
                content = f.read()
            if "|PT|" in content:
                content = content.replace("|PT|", "|EN|")
                with open(list_file, "w", encoding="utf-8") as f:
                    f.write(content)
                print("  ✅ PT→EN")
            else:
                print("  ✅ OK")
            subprocess.run([vpy, "-c",
                            "import nltk; nltk.download('averaged_perceptron_tagger', quiet=True); "
                            "nltk.download('averaged_perceptron_tagger_eng', quiet=True); "
                            "nltk.download('punkt', quiet=True); nltk.download('punkt_tab', quiet=True); "
                            "nltk.download('cmudict', quiet=True)"], env=env)
        save_progress(output_dir, 4)

    # ── ETAPA 4: Dataset ──
    if start_step <= 3:
        print("\n[4/6] 📊 Dataset...")
        sys.stdout.flush()
        bert_dir = os.path.join(repo, "GPT_SoVITS", "pretrained_models", "chinese-roberta-wwm-ext-large")
        hubert_model_dir = os.path.join(repo, "GPT_SoVITS", "pretrained_models", "chinese-hubert-base")

        if not list_file:
            for f in os.listdir(asr_output):
                if f.endswith(".list"):
                    list_file = os.path.join(asr_output, f)
                    break

        # Always ensure NLTK data is downloaded before BERT (idempotent)
        print("  📦 Verificando NLTK data...")
        sys.stdout.flush()
        nltk_script = os.path.join(repo, "TEMP", "download_nltk.py")
        os.makedirs(os.path.join(repo, "TEMP"), exist_ok=True)
        with open(nltk_script, "w", encoding="utf-8") as f:
            f.write(
                "import nltk, os, ssl\n"
                "# Allow proxied fetch (SSRF protection bypass for corporate proxies)\n"
                "os.environ['NLTK_ALLOW_PROXIED_URLOPEN'] = '1'\n"
                "try:\n"
                "    nltk.pathsec.ALLOW_PROXIED_FETCH = True\n"
                "except Exception:\n"
                "    pass\n"
                "try:\n"
                "    _create_unverified_https_context = ssl._create_unverified_context\n"
                "except AttributeError:\n"
                "    pass\n"
                "else:\n"
                "    ssl._create_default_https_context = _create_unverified_https_context\n"
                "data_dir = os.environ.get('NLTK_DATA', '')\n"
                "print(f'NLTK data dir: {data_dir}')\n"
                "for res in ['averaged_perceptron_tagger', 'averaged_perceptron_tagger_eng', 'punkt', 'punkt_tab', 'cmudict']:\n"
                "    try:\n"
                "        nltk.download(res, quiet=False)\n"
                "        print(f'  OK: {res}')\n"
                "    except Exception as e:\n"
                "        print(f'  FAIL: {res}: {e}')\n"
                "try:\n"
                "    from nltk.data import find\n"
                "    find('tokenizers/punkt')\n"
                "    print('NLTK verification: OK')\n"
                "except Exception as e:\n"
                "    print(f'NLTK verification: FAIL - {e}')\n"
                "print('NLTK download done')\n"
            )
        run_step([vpy, nltk_script], repo, env, "NLTK", timeout=120)

        # 4a: BERT — always re-run to ensure correct phoneme data
        # (previous runs may have produced corrupted output due to missing NLTK data)
        bert_output = os.path.join(output_dir, "2-name2text.txt")
        bert_output_part = os.path.join(output_dir, "2-name2text-0.txt")
        for old_bert in [bert_output, bert_output_part]:
            if os.path.exists(old_bert):
                os.remove(old_bert)
                print(f"  🗑️ Removido BERT antigo: {os.path.basename(old_bert)}")
        print("  4a: BERT...")
        sys.stdout.flush()
        env_1a = env.copy()
        env_1a.update({"inp_text": list_file or "", "inp_wav_dir": sliced_dir, "exp_name": model_name,
                        "opt_dir": output_dir, "bert_pretrained_dir": bert_dir,
                        "i_part": "0", "all_parts": "1", "_CUDA_VISIBLE_DEVICES": "0", "is_half": "False"})
        if not run_step([vpy, os.path.join(repo, "GPT_SoVITS", "prepare_datasets", "1-get-text.py")],
                        repo, env_1a, "BERT", timeout=1800):
            print("❌ BERT falhou!"); sys.exit(1)
        # BERT writes to 2-name2text-0.txt, but SoVITS expects 2-name2text.txt
        if os.path.exists(bert_output_part) and not os.path.exists(bert_output):
            os.rename(bert_output_part, bert_output)
            print(f"  📄 Renamed: 2-name2text-0.txt → 2-name2text.txt")
        elif os.path.exists(bert_output_part) and os.path.exists(bert_output):
            os.replace(bert_output_part, bert_output)
            print(f"  📄 Replaced: 2-name2text-0.txt → 2-name2text.txt")

        # 4b: HuBERT — ALWAYS clean and re-extract (corrupted half-precision features)
        hubert_out = os.path.join(output_dir, "4-cnhubert")
        if os.path.isdir(hubert_out):
            old_pt = [f for f in os.listdir(hubert_out) if f.endswith(".pt")]
            if old_pt:
                print(f"  🗑️ Limpando {len(old_pt)} features HuBERT antigas...")
                for f in old_pt:
                    os.remove(os.path.join(hubert_out, f))
                sys.stdout.flush()
        wav32_out = os.path.join(output_dir, "5-wav32k")
        if os.path.isdir(wav32_out):
            old_wav = [f for f in os.listdir(wav32_out) if f.endswith(".wav")]
            if old_wav:
                print(f"  🗑️ Limpando {len(old_wav)} wav32k antigos...")
                for f in old_wav:
                    os.remove(os.path.join(wav32_out, f))
                sys.stdout.flush()
        # Also clean SV embeddings since they depend on wav32k
        if os.path.isdir(sv_dir):
            old_sv = [f for f in os.listdir(sv_dir) if f.endswith(".pt")]
            if old_sv:
                print(f"  🗑️ Limpando {len(old_sv)} SV embeddings antigos...")
                for f in old_sv:
                    os.remove(os.path.join(sv_dir, f))
                sys.stdout.flush()

        print("  4b: HuBERT...")
        sys.stdout.flush()
        env_1b = env.copy()
        env_1b.update({"inp_text": list_file or "", "inp_wav_dir": sliced_dir, "exp_name": model_name,
                        "opt_dir": output_dir, "cnhubert_base_dir": hubert_model_dir,
                        "sv_path": os.path.join(repo, "GPT_SoVITS", "pretrained_models", "sv", "pretrained_eres2netv2w24s4ep4.ckpt"),
                        "i_part": "0", "all_parts": "1",
                        "_CUDA_VISIBLE_DEVICES": "", "CUDA_VISIBLE_DEVICES": "",
                        "is_half": "False"})
        # Create patched copy that forces float32 (original doesn't call .float() after get_model)
        hubert_script_orig = os.path.join(repo, "GPT_SoVITS", "prepare_datasets", "2-get-hubert-wav32k.py")
        hubert_script_patched = os.path.join(repo, "TEMP", "2-get-hubert-wav32k-patched.py")
        os.makedirs(os.path.join(repo, "TEMP"), exist_ok=True)
        try:
            with open(hubert_script_orig, "r", encoding="utf-8") as f:
                hubert_code = f.read()
            # Check for our specific patch marker (not the existing .float() in nan_fails block)
            patch_marker = "# Force float32 (patched by train_auto)"
            if patch_marker not in hubert_code:
                # Inject .float() right after get_model() call
                old_pattern = "model = cnhubert.get_model()\n# is_half=False"
                new_pattern = "model = cnhubert.get_model()\nmodel = model.float()  # Force float32 (patched by train_auto)\n# is_half=False"
                if old_pattern in hubert_code:
                    hubert_code = hubert_code.replace(old_pattern, new_pattern)
                    print("  🔧 Patched HuBERT script: added model.float() after get_model()")
                else:
                    # Fallback: try just the get_model line
                    old_pattern2 = "model = cnhubert.get_model()"
                    if old_pattern2 in hubert_code:
                        hubert_code = hubert_code.replace(
                            old_pattern2,
                            "model = cnhubert.get_model()\nmodel = model.float()  # Force float32 (patched by train_auto)",
                            1  # Only replace first occurrence
                        )
                        print("  🔧 Patched HuBERT script (fallback): added model.float()")
                    else:
                        print("  ⚠️ Could not find get_model() pattern in script")
            else:
                print("  ✅ HuBERT script already patched")
            with open(hubert_script_patched, "w", encoding="utf-8") as f:
                f.write(hubert_code)
        except Exception as e:
            print(f"  ⚠️ Patch failed ({e}), using original script")
            hubert_script_patched = hubert_script_orig
        if not run_step([vpy, hubert_script_patched],
                        repo, env_1b, "HuBERT", timeout=1800):
            print("❌ HuBERT falhou!"); sys.exit(1)
        save_progress(output_dir, 5)

        # 4c: Speaker Verification embeddings (v2Pro only) — 7-sv_cn/
        # Re-check after HuBERT cleaning (has_sv may be stale)
        sv_files_now = len([f for f in os.listdir(sv_dir) if f.endswith(".pt")]) if os.path.isdir(sv_dir) else 0
        if sv_files_now > 10:
            print(f"  4c: SV embeddings... ⏭️ Já feito ({sv_files_now} files)")
        else:
            print("  4c: SV embeddings (speaker verification)...")
            sys.stdout.flush()
            os.makedirs(sv_dir, exist_ok=True)
            sv_model_path = os.path.join(repo, "GPT_SoVITS", "pretrained_models", "sv", "pretrained_eres2netv2w24s4ep4.ckpt")
            if not os.path.exists(sv_model_path):
                print(f"  ⚠️ SV model não encontrado: {sv_model_path}")
                print("  ⚠️ Pulando extração SV — download o modelo primeiro!")
            else:
                sv_script = os.path.join(repo, "TEMP", "extract_sv.py")
                os.makedirs(os.path.join(repo, "TEMP"), exist_ok=True)
                sv_code = 'import sys, os, torch, numpy as np, librosa\n\nrepo = sys.argv[1]\nwav32_dir = sys.argv[2]\nsv_out_dir = sys.argv[3]\nsv_model_path = sys.argv[4]\n\nsys.path.insert(0, os.path.join(repo, "GPT_SoVITS", "eres2net"))\nfrom ERes2NetV2 import ERes2NetV2\nimport kaldi as Kaldi\n\ndevice = "cuda:0" if torch.cuda.is_available() else "cpu"\npretrained_state = torch.load(sv_model_path, map_location="cpu", weights_only=False)\nmodel = ERes2NetV2(baseWidth=24, scale=4, expansion=4)\nmodel.load_state_dict(pretrained_state)\nmodel.eval()\nmodel = model.to(device)\n\nwav_files = sorted([f for f in os.listdir(wav32_dir) if f.endswith(".wav")])\nprint(f"  Processing {len(wav_files)} files...")\nfor i, fname in enumerate(wav_files):\n    out_path = os.path.join(sv_out_dir, fname + ".pt")\n    if os.path.exists(out_path):\n        continue\n    wav_path = os.path.join(wav32_dir, fname)\n    wav_32k, sr = librosa.load(wav_path, sr=32000, mono=True)\n    wav_16k = librosa.resample(wav_32k, orig_sr=32000, target_sr=16000)\n    tensor_wav = torch.from_numpy(wav_16k).float().unsqueeze(0).to(device)\n    with torch.no_grad():\n        feat = torch.stack([Kaldi.fbank(wav0.unsqueeze(0), num_mel_bins=80, sample_frequency=16000, dither=0) for wav0 in tensor_wav])\n        sv_emb = model.forward3(feat).cpu()\n    torch.save(sv_emb, out_path)\n    if (i + 1) % 50 == 0 or i == len(wav_files) - 1:\n        print(f"  SV: {i+1}/{len(wav_files)}")\n        sys.stdout.flush()\n\nprint(f"  SV: Done - {len(wav_files)} embeddings")\n'
                with open(sv_script, "w", encoding="utf-8") as f:
                    f.write(sv_code)
                if not run_step([vpy, sv_script, repo, wav32_out, sv_dir, sv_model_path],
                                repo, env, "SV", timeout=1800):
                    print("❌ SV embeddings falhou!"); sys.exit(1)
        save_progress(output_dir, 5)

    # ── Config SoVITS (compartilhado entre o treino e a extração de semantic) ──
    # Sempre regenerado, para que o s1_train.py (GPT) tenha o config correto
    # mesmo ao retomar direto da etapa 6 (SoVITS já concluído).
    s2_config = {
        "train": {"log_interval": 100, "eval_interval": 500, "seed": 1234, "epochs": args.epochs_s2,
                  "learning_rate": 0.0001, "betas": [0.8, 0.99], "eps": 1e-09, "batch_size": args.batch_size,
                  "fp16_run": False, "lr_decay": 0.999875, "segment_size": 20480, "init_lr_ratio": 1,
                  "warmup_epochs": 0, "c_mel": 45, "c_kl": 1.0, "text_low_lr_rate": 0.4,
                  "pretrained_s2G": os.path.join(repo, "GPT_SoVITS", "pretrained_models", "v2Pro", "s2Gv2Pro.pth"),
                  "pretrained_s2D": os.path.join(repo, "GPT_SoVITS", "pretrained_models", "v2Pro", "s2Dv2Pro.pth"),
                  "if_save_latest": True, "if_save_every_weights": True, "save_every_epoch": 4,
                  "gpu_numbers": "0", "grad_ckpt": False, "lora_rank": 32},
        "data": {"exp_dir": output_dir,
                 "max_wav_value": 32768.0, "sampling_rate": 32000, "filter_length": 2048, "hop_length": 640,
                 "win_length": 2048, "n_mel_channels": 128, "mel_fmin": 0.0, "mel_fmax": None,
                 "add_blank": True, "n_speakers": 300, "cleaned_text": True},
        "model": {"inter_channels": 192, "hidden_channels": 192, "filter_channels": 768, "n_heads": 2,
                  "n_layers": 6, "kernel_size": 3, "p_dropout": 0.1, "resblock": "1",
                  "resblock_kernel_sizes": [3, 7, 11], "resblock_dilation_sizes": [[1,3,5],[1,3,5],[1,3,5]],
                  "upsample_rates": [10, 8, 2, 2, 2], "upsample_initial_channel": 512,
                  "upsample_kernel_sizes": [16, 16, 8, 2, 2], "n_layers_q": 3, "use_spectral_norm": False,
                  "gin_channels": 1024, "semantic_frame_rate": "25hz", "freeze_quantizer": True,
                  "version": "v2Pro"},
        "s2_ckpt_dir": output_dir, "save_weight_dir": os.path.join(repo, "SoVITS_weights_v2Pro"),
        "name": model_name, "version": "v2Pro", "content_module": "cnhubert",
    }
    temp_dir = os.path.join(repo, "TEMP")
    os.makedirs(temp_dir, exist_ok=True)
    s2_path = os.path.join(temp_dir, f"tmp_s2_{model_name}.json")
    # Force-delete old cached config to avoid stale version/data fields
    if os.path.exists(s2_path):
        try:
            os.remove(s2_path)
            print(f"  🗑️ Deleted old TEMP config: {s2_path}")
        except Exception as e:
            print(f"  ⚠️ Could not delete old config: {e}")
    with open(s2_path, "w", encoding="utf-8") as f:
        json.dump(s2_config, f, indent=2)
    print(f"  📄 Config written: {s2_path}")

    # ── Semantic tokens (GPT) — gera 6-name2semantic.tsv ──
    # O s1_train.py do GPT exige 6-name2semantic.tsv. O script oficial
    # 3-get-semantic.py injeta 'version' pelo tamanho do arquivo, o que colide
    # com o 'version: v2Pro' do config (erro TypeError). Então usamos um script
    # próprio que constrói o modelo EXATAMENTE como o SoVITS (v2Pro) e escreve
    # direto em 6-name2semantic.tsv. Em CPU isso leva alguns minutos; só roda
    # se o arquivo ainda não existir (idempotente, inclusive na retomada).
    semantic_path = os.path.join(output_dir, "6-name2semantic.tsv")
    if os.path.exists(semantic_path) and os.path.getsize(semantic_path) > 0:
        print(f"  📊 Semantic tokens: já existem ({os.path.basename(semantic_path)})")
    else:
        if not list_file:
            for f in os.listdir(asr_output):
                if f.endswith(".list"):
                    list_file = os.path.join(asr_output, f)
                    break
        if not has_hubert:
            print("  ⚠️ Semantic tokens: HuBERT não encontrado, pulando (GPT falhará sem 6-name2semantic.tsv)")
        elif not list_file:
            print("  ⚠️ Semantic tokens: .list não encontrado, pulando (GPT falhará sem 6-name2semantic.tsv)")
        else:
            if os.path.exists(semantic_path):
                os.remove(semantic_path)
            print("  📊 Semantic tokens (GPT)...")
            sys.stdout.flush()
            s2G_path = os.path.join(repo, "GPT_SoVITS", "pretrained_models", "v2Pro", "s2Gv2Pro.pth")
            semantic_script = os.path.join(repo, "TEMP", "extract_semantic.py")
            os.makedirs(os.path.dirname(semantic_script), exist_ok=True)
            with open(semantic_script, "w", encoding="utf-8") as f:
                f.write(semantic_code)
            if not run_step([vpy, semantic_script, repo, list_file, output_dir, s2G_path, s2_path],
                            repo, env, "Semantic", timeout=7200):
                print("❌ Semantic tokens falhou! (sem 6-name2semantic.tsv o GPT não inicia)")
            else:
                sz = os.path.getsize(semantic_path) if os.path.exists(semantic_path) else 0
                if sz > 0:
                    print(f"  📄 6-name2semantic.tsv gerado ({sz} bytes)")
                else:
                    print("  ⚠️ Semantic tokens: arquivo vazio/apagado, GPT pode falhar")

    # ── ETAPA 5: SoVITS ──
    if start_step <= 4:
        print(f"\n[5/6] 🧠 SoVITS ({args.epochs_s2} epochs)...")
        print("  ⏳ Pode levar horas em CPU...")
        sys.stdout.flush()
        # Ensure checkpoint directories exist (Windows os.rename needs target dir)
        os.makedirs(os.path.join(output_dir, "logs_s2_v2Pro"), exist_ok=True)
        os.makedirs(os.path.join(repo, "SoVITS_weights_v2Pro"), exist_ok=True)
        sys.stdout.flush()
        if not run_step([vpy, os.path.join(repo, "GPT_SoVITS", "s2_train.py"), "--config", s2_path],
                        repo, env, "SoVITS", timeout=7200):
            print("❌ SoVITS falhou!"); sys.exit(1)
        save_progress(output_dir, 6)

    # ── ETAPA 6: GPT ──
    print(f"\n[6/6] 🤖 GPT ({args.epochs_s1} epochs)...")
    print("  ⏳ Pode levar horas em CPU...")
    sys.stdout.flush()
    import yaml
    s1_config = {
        "train": {"seed": 1234, "epochs": args.epochs_s1, "batch_size": args.batch_size,
                  "save_every_n_epoch": 4, "precision": "32", "gradient_clip": 1.0,
                  "if_save_every_weights": True, "if_save_latest": True, "if_dpo": False,
                  "half_weights_save_dir": os.path.join(repo, "GPT_weights_v2Pro"), "exp_name": model_name},
        "optimizer": {"lr": 0.01, "lr_init": 0.00001, "lr_end": 0.0001, "warmup_steps": 2000, "decay_steps": 40000},
        "data": {"max_eval_sample": 8, "max_sec": 54, "num_workers": 1, "pad_val": 1024},
        "model": {"vocab_size": 1025, "phoneme_vocab_size": 732, "embedding_dim": 512, "hidden_dim": 512,
                  "head": 16, "linear_units": 2048, "n_layer": 24, "dropout": 0, "EOS": 1024, "random_bert": 0},
        "inference": {"top_k": 15},
        "pretrained_s1": os.path.join(repo, "GPT_SoVITS", "pretrained_models", "s1v3.ckpt"),
        "train_semantic_path": os.path.join(output_dir, "6-name2semantic.tsv"),
        "train_phoneme_path": os.path.join(output_dir, "2-name2text.txt"),
        "output_dir": os.path.join(output_dir, "logs_s1_v2Pro"),
    }
    temp_dir = os.path.join(repo, "TEMP")
    os.makedirs(temp_dir, exist_ok=True)
    s1_path = os.path.join(temp_dir, f"tmp_s1_{model_name}.yaml")
    # Ensure GPT checkpoint directories exist
    os.makedirs(os.path.join(output_dir, "logs_s1_v2Pro"), exist_ok=True)
    os.makedirs(os.path.join(repo, "GPT_weights_v2Pro"), exist_ok=True)
    with open(s1_path, "w", encoding="utf-8") as f:
        yaml.dump(s1_config, f, default_flow_style=False)
    env_s1 = env.copy()
    env_s1.update({"_CUDA_VISIBLE_DEVICES": "0", "hz": "25hz"})
    if not run_step([vpy, os.path.join(repo, "GPT_SoVITS", "s1_train.py"), "--config_file", s1_path],
                    repo, env_s1, "GPT", timeout=7200):
        print("❌ GPT falhou!"); sys.exit(1)

    # Limpar progresso ao finalizar
    progress_file = os.path.join(output_dir, ".training_progress.json")
    if os.path.exists(progress_file):
        os.remove(progress_file)

    print("\n" + "=" * 60)
    print(f"✅ '{model_name}' treinado!")
    print(f"   SoVITS: {repo}/SoVITS_weights_v2Pro/")
    print(f"   GPT: {repo}/GPT_weights_v2Pro/")
    print("=" * 60)

if __name__ == "__main__":
    main()
