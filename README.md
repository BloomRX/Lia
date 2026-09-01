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
│   ├─ Treinar voz local (GPT-SoVITS v2Pro)                   │
│   └─ Download do modelo treinado                             │
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
│   ├── train_auto.py          ← Pipeline de treinamento automatizado
│   ├── servidor_voz_airi.js   ← Servidor TTS (Edge + Kokoro offline)
│   ├── iniciar_voz.ps1        ← Inicia servidor de voz
│   ├── iniciar_tamagotchi.ps1 ← Abre Airi desktop
│   ├── configurar_tamagotchi.ps1
│   ├── atualizar_airi.ps1     ← Re-ler URL do Drive
│   ├── testar_vozes.ps1       ← Testar vozes disponíveis
│   ├── waifu_painel.ps1       ← Painel da waifu
│   ├── diagnosticar_airi.ps1  ← Diagnóstico do sistema
│   └── agentai-boot.html      ← Boot page do Airi
│
├── waifu.bat                  ← ⭐ Launcher principal (menu)
├── .gitignore
└── README.md
```

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

### 3. Treinar voz personalizada

1. Abra o app (`waifu.bat`)
2. Clique em **"🎤 Treinar Local"**
3. Selecione a pasta com áudios da voz
4. O treinamento é **100% automático** (slice → ASR → BERT → SoVITS)
5. Ao final, o modelo fica em `sovits-data/GPT-SoVITS/{nome}/`

### 4. Colab (cérebro IA)

1. Abra `colab/AgentAI.ipynb` no Google Colab
2. Runtime: **T4 GPU**
3. Execute as células na ordem
4. A URL do túnel é salva no Google Drive

## Servidor de voz

O servidor de voz (`scripts/servidor_voz_airi.js`) tem interface web em `http://localhost:9860/`:

- **Engine Edge** (online): vozes Microsoft, qualidade alta
- **Engine Kokoro** (offline): funciona sem internet, ~360 MB
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

- **Repo**: [github.com/BloomRX/Lia](https://github.com/BloomRX/Lia)
- **GPT-SoVITS**: [github.com/RVC-Boss/GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)
