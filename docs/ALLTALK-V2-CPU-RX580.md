# AllTalk TTS v2 — Instalação em CPU (RX 580, sem NVIDIA)

Guia **portátil** de instalação e configuração do **AllTalk TTS v2** para a sua
máquina (RX **580**, **sem CUDA / sem DirectML / sem ROCm**), rodando em **CPU**.

> **Este guia não usa caminho fixo.** Tudo é relativo à pasta do projeto
> (a raiz onde estão `waifu.bat` e `PullLia.bat`). Funciona em **qualquer**
> lugar: `C:\Lia`, `J:\Lia`, `D:\Projetos\Lia`, pendrive — basta clonar o repo.
>
> A pasta do projeto é chamada aqui de **`<REPO>`**.

---

## O que já está pronto no repo (integração com o Git)

Este guia é acompanhado por scripts **versionados** que resolvem tudo sozinhos,
sem caminho no código:

| Arquivo | O que faz |
|---|---|
| **`instalar_alltalk.bat`** (raiz) | Clona o AllTalk em `<REPO>\alltalk_tts` (se preciso), valida Python 3.9–3.11 via `py`, e **instala em modo CPU** (venv + torch CPU + requirements sem CUDA/DeepSpeed). |
| **`iniciar_alltalk.bat`** (raiz) | Inicia o AllTalk (porta 7851), preferindo o venv local. |
| **`scripts/alltalk_config.py`** | Utilitário: `--find-python`, `--check-python`, `--install-cpu`, `--patch-confignew`, `--endpoint`. |
| **`docs/ALLTALK-V2-CPU-RX580.md`** | Este guia. |

O AllTalk vira a subpasta **`<REPO>\alltalk_tts\`** (gitignored, como o `airi\`).

---

## Fatos verificados do AllTalk v2

- Engines disponíveis: **F5-TTS, Parler-TTS, Piper, Coqui VITS, Coqui XTTS**.
  → **NÃO existe engine Edge-TTS** no AllTalk v2.
- Endpoint **compatível com OpenAI**:
  **`POST http://127.0.0.1:7851/v1/audio/speech`**.
- Para usar uma voz sua no Airi, é preciso **mapear** as 6 vozes OpenAI
  (`alloy`, `echo`, `fable`, `nova`, `onyx`, `shimmer`) para uma voz/engine
  do AllTalk — feito na UI (aba **TTS Engine Settings** → engine → **OpenAI Voice
  Mappings**) ou via `PUT /api/openai-voicemap`.
- Tem pipeline **RVC** embutido (`.pth` + `.index`), com pitch e index-rate.
- DeepSpeed **precisa estar desligado**: `"deepspeed_activate": false`.

---

## Pré-requisitos (na sua máquina)

1. **Python 3.9 – 3.11** (3.12+ não é suportado). **Não precisa mexer no seu
   `python` global** — o instalador procura um 3.9–3.11 automaticamente:
   1. Baixe o **Python 3.11** de https://www.python.org/downloads/windows/.
   2. Instale marcando **"py launcher"** (e opcionalmente "Add Python to PATH").
      Isso instala **ao lado** do Python que você já tem (ex.: 3.14) — **não
      substitui** e **não quebra nada** (a Lia App precisa de 3.10+, então 3.11
      continua servindo).
   3. O `instalar_alltalk.bat` usa `py -3.11` sozinho; seu `python` do sistema
      (e tudo que depende dele) fica intacto.
2. **Git para Windows** (https://git-scm.com/download/win).
3. **Espaço em disco**: ~6–10 GB para repo + modelos + vozes.
4. Nada de CUDA/ROCm — usamos **torch CPU** (o `requirements_other.txt` **não
   existe mais** no `main`; o `atsetup` na opção Standalone instalaria CUDA +
   DeepSpeed, o que não serve para a RX 580).

---

## Passo 1 — Instalar (um clique, portátil)

Na **raiz do projeto** (onde está `waifu.bat`), **dê dois cliques em**: **`instalar_alltalk.bat`**

O script faz sozinho:
1. Chama o launcher **`py`** direto para achar um **Python 3.9–3.11** (tenta
   `py -3.11`, depois `-3.10`, `-3.9`). **Não mexe no seu `python` do sistema.**
2. Clona `erew123/alltalk_tts` em `<REPO>\alltalk_tts` (se ainda não existir).
3. **Instala em modo CPU**: cria `<REPO>\alltalk_tts\venv`, instala **torch CPU**
   (sem `+cu121`), gera um `requirements_cpu.txt` **sem** as linhas `nvidia-*`,
   `torch`, `torchaudio` e `deepspeed`, e instala o restante. **Não usa o
   `atsetup.bat`** (que baixaria CUDA + DeepSpeed, rota NVIDIA).
4. Ajusta `confignew.json` (`deepspeed_activate: false`, `port_number: 7851`).

> **NÃO rode o `atsetup.bat` escolhendo "Standalone"** — essa opção instala
> `torch==2.2.2+cu121` + DeepSpeed (rota NVIDIA). Para a RX 580/CPU use
> **`instalar_alltalk.bat`**, que já faz o caminho CPU.

> Se o `.bat` disser que não achou o 3.11, rode **`py --list`** num terminal para
> conferir. Precisa de uma linha **`Python 3.11 (64-bit)`** (as linhas
> **`Astral/CPython...`** são do **uv**, não servem). Se não aparecer, instale o
> **3.11** de https://www.python.org/downloads/windows/ marcando **"py launcher"**.

> **Caminho manual** (se preferir não usar o `.bat`, ou se ele falhar):
> ```powershell
> cd J:\Lia                      # ← a pasta do seu projeto (onde está o waifu.bat)
> if (-not (Test-Path alltalk_tts)) { git clone https://github.com/erew123/alltalk_tts.git }
> py -3.11 scripts\alltalk_config.py --install-cpu
> ```
> (O `--install-cpu` cria o venv, instala torch CPU e o requirements sem CUDA.)

---

## Passo 2 — Conferir `confignew.json`

Abra `<REPO>\alltalk_tts\confignew.json` e confirme (o `.bat` já faz isso):

```json
"deepspeed_activate": false,
"port_number": "7851",
```

- `deepspeed_activate: false` → **obrigatório** sem NVIDIA (senão erro
  `RuntimeError: Found no NVIDIA driver`).
- `port_number: "7851"` → porta padrão. Se ocupada (erro "port 7851 already in
  use"), troque para `7602`/outra e use essa no endpoint do Airi.
- Salve e feche. (Cuidado para não quebrar o JSON.)

---

## Passo 3 — Iniciar

Na raiz do projeto, **dê dois cliques em**: **`iniciar_alltalk.bat`**

(Se o `.bat` não achar o venv, rode manualmente em `J:\Lia\alltalk_tts`:
```powershell
venv\Scripts\python script.py
```
A UI Gradio abre em **http://127.0.0.1:7851**.)

---

## Passo 4 — Base Pt-BR (testar primeiro)

Na UI, aba **Generate TTS**:
1. **"Swap TTS Engine"** → escolha **Piper** (mais rápido em CPU).
2. Em **TTS Engine Settings** → **Models/Voices Download** → baixe um modelo
   **pt-BR** do Piper (ex.: um `pt_BR-...` medium). O Piper tem vozes fixas por
   arquivo; é o candidato a **base rápida**.
3. Gere uma frase de teste em pt-BR (sem RVC ainda) para validar a base na CPU.

> Depois, se quiser qualidade, experimente **XTTS** (clonagem) — mas em CPU é
> **bem mais lenta**. O plano é testar **Piper primeiro** por ser rápido.

---

## Passo 5 — RVC (seu `.pth` + `.index`)

1. Coloque seu **`.pth`** (e o **`.index`**) no diretório de modelos RVC do
   AllTalk (wiki: https://github.com/erew123/alltalk_tts/wiki/RVC-(Retrieval-based-Voice-Conversion)
   para a pasta exata da sua versão).
2. Na UI, ative o pipeline **RVC**, selecione o **`.pth`** e o **`.index`**.
3. Ajuste conforme seu treino do Colab:
   - **pitch = 0**
   - **index rate ≈ 0.7**
4. Gere de novo com **Piper pt-BR + RVC** e compare.

---

## Passo 6 — Endpoint para o Airi (OpenAI-compatible)

O AllTalk v2 expõe um endpoint compatível com OpenAI:

```
Base URL : http://127.0.0.1:7851/v1
Endpoint : POST http://127.0.0.1:7851/v1/audio/speech
```

(Se mudou a porta, use a nova, ex.: `http://127.0.0.1:7852/v1`.)

**Importante — mapear a voz:** o Airi enviará `voice: "alloy"` (uma das 6 vozes
OpenAI). No AllTalk, mapeie essas vozes para a sua voz Piper+RVC:
- **UI**: aba **TTS Engine Settings** → engine escolhida → **OpenAI Voice Mappings**.
- **API**: `PUT /api/openai-voicemap` com
  `{"alloy":"sua_voz","nova":"sua_voz", ...}`.

É esse endpoint que você cola no **provedor de VOZ** do Airi (o cérebro continua
na nuvem Groq/Cerebras):

```
http://127.0.0.1:7851/v1
```

---

## Passo 7 — Teste (30 min) e decisão

Sequência de teste sugerida:
1. **Piper pt-BR** só (base) — velocidade e naturalidade em CPU.
2. **Piper pt-BR + RVC** (seu `.pth`/`.index`) — identidade de voz + estabilidade.
3. Se o AllTalk não tiver uma base boa **ou** o Piper+RVC não ficar bom →
   **migramos para o wrapper próprio**: FastAPI (~50 linhas) expondo
   `/v1/audio/speech`, fazendo **Edge-TTS → RVC** (Edge→Applio).

**Resumo da decisão:**
- Piper pt-BR + RVC bom → usar `http://127.0.0.1:7851/v1` direto no Airi.
- Não bom / precisa de voz Edge → wrapper próprio (Edge → Applio/RVC).

---

## Problemas comuns

| Sintoma | Causa / solução |
|---|---|
| `RuntimeError: Found no NVIDIA driver` | DeepSpeed ativo. `confignew.json` → `"deepspeed_activate": false`. |
| `port 7851 already in use` | Troque `"port_number"` e use essa no endpoint. |
| `PyTorch version mismatch with DeepSpeed` | Não instale DeepSpeed em CPU; mantenha `deepspeed_activate: false`. |
| Voz do Airi não muda / sempre "alloy" | Mapeie no **OpenAI Voice Mappings** (Passo 6). |
| Lento na geração | Normal em CPU com XTTS; use **Piper** para base rápida + RVC. |
| `MKL_THREADING_LAYER` warning | `set MKL_THREADING_LAYER=GNU` antes de iniciar (opcional). |
