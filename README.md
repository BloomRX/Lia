# Lia

**Lia** é uma waifu virtual com voz, treinamento de voz personalizado e integração com IA.

```
┌─────────────────────────── Colab ───────────────────────────┐
│  AgentAI.ipynb                                              │
│  Qwen3-4B 4-bit · Gradio · API OpenAI-compatible (:7861)    │
│  túnel cloudflared → URL salva no Drive (memory/api_url.txt)│
└──────────────────────┬──────────────────────────────────────┘
                       │ (PC lê a URL do Drive)
┌──────────────────────┴────────────── PC (Windows) ───────────┐
│  waifu.bat (painel)                                          │
│   ├─ servidor_voz_airi.js  (edge-tts, porta 9860)            │
│   ├─ Airi stage-web        (Vite, porta 5173)                │
│   └─ injeta Base URL + voz no navegador (agentai-boot.html)  │
│                                                              │
│  app/lia_app.py (interface principal)                        │
│   ├─ Instalar servidor (deps leves)                          │
│   ├─ Voz: Edge · Kokoro · Qwen3 · CosyVoice3 · SoVITS        │
│   └─ Clonar/treinar voz (substitui o GPT-SoVITS)             │
└──────────────────────────────────────────────────────────────┘
```

## Estrutura

```
Lia/
├── app/
│   ├── LiaAppInstaller.bat    ← Instalador rápido (PowerShell)
│   ├── installer.py           ← Script de instalação Python
│   └── lia_app.py             ← ⭐ App principal (interface + treinamento)
│
├── colab/
│   └── AgentAI.ipynb          ← Notebook do Colab (cérebro IA)
│
├── docs/
│   ├── ESTADO-DO-PROJETO.txt  ← Estado atual do projeto
│   ├── LEIA-ME.txt            ← Instruções rápidas
│   └── persona-lia.md         ← Definição da persona da Lia
│
├── scripts/
│   ├── train_auto.py          ← Pipeline de treinamento (SoVITS legado)
│   ├── servidor_voz_airi.js   ← Gateway de voz (Edge + Kokoro + Qwen3 + CosyVoice)
│   ├── voice_engines/         ← ⭐ Novos motores TTS (Qwen3/CosyVoice) + instaladores
│   │   ├── README.md          ← Arquitetura e uso dos novos motores
│   │   ├── _common.py         ← Framework do worker (JSON-lines com o Node)
│   │   ├── qwen3_worker.py    ← Worker Qwen3-TTS (clone + voz pré-definida)
│   │   ├── cosyvoice3_worker.py ← Worker CosyVoice 3 (beta)
│   │   ├── install_qwen3.py   ← Baixa/setup do Qwen3 (só o modelo escolhido)
│   │   └── install_cosyvoice3.py ← Setup do CosyVoice 3 (beta)
│   ├── iniciar_voz.ps1        ← Inicia servidor de voz
│   ├── iniciar_tamagotchi.ps1 ← Abre Airi desktop
│   ├── configurar_tamagotchi.ps1
│   ├── atualizar_airi.ps1     ← Re-ler URL do Drive
│   ├── testar_vozes.ps1       ← Testar vozes disponíveis
│   ├── waifu_painel.ps1       ← Painel da waifu
│   ├── diagnosticar_airi.ps1  ← Diagnóstico do sistema
│   └── agentai-boot.html      ← Boot page do Airi
│
├── instalar_alltalk.bat        ← Instala o AllTalk TTS v2 (CPU, portátil)
├── iniciar_alltalk.bat         ← Inicia o AllTalk TTS v2 (porta 7851)
├── waifu.bat                  ← ⭐ Launcher principal (menu)
├── .gitignore
└── README.md
```

> O **AllTalk TTS v2** (`erew123/alltalk_tts`) é clonado em `alltalk_tts\`
> (gitignored) e serve o **provedor de VOZ** do Airi via `http://127.0.0.1:7851/v1`
> (OpenAI-compatible), com pipeline **RVC** para a voz clonada.

## Como usar

### 1. Instalar (primeira vez)

```bash
# Opção A: Duplo clique em app/LiaAppInstaller.bat
# Opção B: PowerShell
powershell -ExecutionPolicy Bypass -File app/LiaAppInstaller.bat
```

### 2. Abrir o app

```bash
# Duplo clique em waifu.bat
# ou
python app/lia_app.py
```

### 3. Voz personalizada (Qwen3-TTS / CosyVoice 3)

O GPT-SoVITS está sendo **substituído** por motores com português nativo, licença
Apache 2.0 e clone em segundos. O fluxo (novo):

1. Abra o app (`waifu.bat`) e abra o **ajuste de voz** (🎙️)
2. Escolha a **engine**: `qwen3` (recomendado) ou `cosyvoice3`
3. Clique em **"🤖 Instalar Qwen3"** (baixa só o modelo escolhido, ex.: 0.6B)
4. **Clonar voz** (rápido, sem treino): forneça um áudio de referência de 5–15s
   → a Lia fala na hora, em português nativo.
5. **Treinar** (identidade máxima, opcional): o fine-tune roda no **Colab**
   (GPU gratuita) ou **local** (CPU lento); o app baixa os pesos.

> Para o **legado SoVITS**, o fluxo antigo (slice → ASR → BERT → SoVITS) continua
> disponível em `sovits-data/GPT-SoVITS/{nome}/`, mas está marcado para remoção.

### 4. Colab (cérebro IA)

1. Abra `colab/AgentAI.ipynb` no Google Colab
2. Runtime: **T4 GPU**
3. Execute as células na ordem
4. A URL do túnel é salva no Google Drive

## Servidor de voz

O servidor de voz (`scripts/servidor_voz_airi.js`) tem interface web em `http://localhost:9860/`:

- **Engine Edge** (online): vozes Microsoft, qualidade alta
- **Engine Kokoro** (offline): funciona sem internet, ~360 MB
- **Engine Qwen3-TTS**: português nativo, clone em 3s, Apache 2.0 (novo — recom.).
- **Engine CosyVoice 3**: máxima similaridade/emoção (novo, beta/opcional)
- **Ajustes**: pitch, velocidade, teste em tempo real
- **Vozes recomendadas**: Thalita 🌸, Brenda, Francisca, Nanami 🇯🇵

## Requisitos

- **Windows 10/11**
- **Python 3.10+** (`winget install Python.Python.3.12`)
- **Node.js 18+** (para servidor de voz)
- **Git** (para clonar GPT-SoVITS)
- **Google Colab** com T4 (para o cérebro IA)

## Troubleshooting

| Sintoma | Solução |
|---|---|
| App não abre | Verifique Python: `python --version` |
| Servidor de voz offline | Rode `scripts/iniciar_voz.ps1` |
| Treinamento falha no slice | Verifique FFmpeg: `ffmpeg -version` |
| CUDA out of memory | Feche outros apps GPU, reinicie |
| URL do túnel não funciona | Rode START no Colab novamente |

## Links

> **IMPORTANTE — manter atualizado.** Esta seção lista os recursos **externos** que a Lia
> usa. Sempre que adicionarmos/cambiarmos uma dependência externa (biblioteca, serviço,
> modelo, repo), atualize os itens abaixo e marque `✅` quando a observação for verificada.

### Projeto principal (waifu)

| Recurso | Uso na Lia | Link |
|---|---|---|
| **Project AIRI** (`moeru-ai/airi`) | Interface/motor da waifu (stage-web + tamagotchi) — usamos sempre a versão **mais recente (main/beta)**. Renderer VRM/Live2D, providers de voz/cérebro, plugins | [github.com/moeru-ai/airi](https://github.com/moeru-ai/airi) |

### Inteligência (LLM / ASR / TTS)

| Recurso | Uso | Link |
|---|---|---|
| **Qwen3-4B (via Colab)** `colab/AgentAI.ipynb` | Cérebro da Lia (chat, Gradio, API openai-compatible) | [Qwen](https://huggingface.co/Qwen) |
| **Qwen3-TTS** (pip `qwen-tts`) | Voz clonada + treino (PT nativo, Apache 2.0, clone 3s) — **novo motor recomendado** | [huggingface.co/Qwen/Qwen3-TTS](https://huggingface.co/Qwen/Qwen3-TTS) |
| **CosyVoice 3** (Alibaba) | Voz clonada (max. similaridade/emoção, Apache 2.0) — novo, beta | [github.com/FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) |
| **GPT-SoVITS** (`RVC-Boss/GPT-SoVITS`) | Voz clonada (treino local v2Pro) — **legado, em remoção** | [github.com/RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) |
| **kokoro-onnx** | Voz offline (Kokoro TTS v1.0, via venv + ONNX) | [thewh1teagle/kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) |
| **msedge-tts** (npm) | Voz online (Microsoft Edge Neural) | [msedge-tts](https://www.npmjs.com/package/msedge-tts) |
| **AllTalk TTS v2** (`erew123/alltalk_tts`) | **Provedor de VOZ do Airi** — OpenAI-compatible (`http://127.0.0.1:7851/v1`), engine Piper/XTTS + **RVC** para a voz clonada | [github.com/erew123/alltalk_tts](https://github.com/erew123/alltalk_tts) |

### Bibliotecas / ferramentas base (aplicadas pela Lia)

| Recurso | Uso | Link |
|---|---|---|
| **node / pnpm** | Rodam o AIRI (web/tamagotchi) e o servidor de voz | [nodejs.org](https://nodejs.org) · [pnpm.io](https://pnpm.io) |
| **customtkinter** | UI do Lia App (Python) | [github.com/TomSchimansky/CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| **pygame** | Reprodução de áudio para testar voz | [pygame.org](https://www.pygame.org) |
| **ffmpeg** | Processamento de áudio (SoVITS) | [ffmpeg.org](https://ffmpeg.org) |
| **cloudflared (túnel)** | Expõe o servidor do Colab para a Lia | [cloudflare](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) |

### Referência técnica (docs do AIRI que a Lia segue)

| Recurso | Por que importa | Link |
|---|---|---|
| **AIRI providers (voz/cérebro)** | `openai-compatible` (chat) e `openai-compatible-audio-speech` (TTS) — a Lia injeta via localStorage/CDP | [docs AIRI](https://moeru-ai-airi.mintlify.app/) |
| **AIRI Character Card v3** | Formato de personalidade (system/personality/greetings) — painel de personalidade da Lia | [spec CCv3](https://github.com/moeru-ai/airi/tree/main/packages/ccc) |
| **three-vrm / three-vrm-animation** | Renderer de avatar VRM (anexar acessórios/roupa — Opção A) | [github.com/pixiv/three-vrm](https://github.com/pixiv/three-vrm) |

### Documentos do projeto (neste repo)

- [`docs/ESTUDO-AIRI.md`](docs/ESTUDO-AIRI.md) — Estudo do AIRI + integração Lia.
- [`docs/PLANO-IMPLEMENTACAO.md`](docs/PLANO-IMPLEMENTACAO.md) — Plano de implementação em fases (refatoração etc.).
- [`docs/PESQUISA-AIRI-OPCAO-A-FORK.md`](docs/PESQUISA-AIRI-OPCAO-A-FORK.md) — Pesquisa Opção A + fork/interatividade.
- [`docs/IDEIAS-LIA.md`](docs/IDEIAS-LIA.md) — Backlog/ideias da Lia.
