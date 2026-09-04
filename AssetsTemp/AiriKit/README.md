# 🎀 Kit Airi — Lia Edition

Arquivos criados para o seu projeto de VTuber (Project Airi).
PC de referência: Ryzen 5 5500 · RX 580 8GB · 16GB RAM — mas tudo
funciona em qualquer PC, com detecção automática de hardware.

---

## 📄 O que tem dentro

### 1. `hardware-detect.py` — Perfilador de hardware + skills + voz
Script Python (sem dependências, roda em Windows/Linux/macOS) que:
- Detecta GPU (NVIDIA/AMD/Intel/Apple), VRAM e RAM do PC;
- Decide o backend local certo (CUDA / Vulkan / Metal / CPU);
- Monta o perfil de skills (busca, arte, visão, Minecraft, MCP...);
- Recomenda STT e TTS conforme o hardware (incluindo avisos tipo
  "Polaris não tem ROCm, use Vulkan" e "evite Qwen3-TTS local em AMD").

Como usar:
    python hardware-detect.py          # relatório legível
    python hardware-detect.py --json   # JSON para injetar no seu App

### 2. `airi-card-tsundere.json` — Card da Lia (Character Card V3)
Personagem tsundere completa em PT-BR, pronta para importar no Airi
(Settings → Airi Card → Import). Formato CCV3 compatível com
SillyTavern. Inclui system prompt com tags de emoção
(<|EMOTE_ANGRY|> etc.), exemplos de diálogo e saudações.

### 3. `colab-vs-alternativas-airi.md` — Por que abandonar o Colab
Documento de referência: os 9 problemas do Colab como "cérebro"
(timeouts, URL mutante, ToS...) e a migração para Groq (principal),
Cerebras (fallback) e LM Studio local (offline), mantendo seu App
de pré-configuração.

### 4. `voz-personalizada-airi.md` — Guia de voz clonada
Pipeline completo para a voz da dubladora (dataset de 13 min):
Edge-TTS (prosódia) + RVC treinado no Colab (identidade) + integração
OpenAI-Compatible no Airi. Inclui playbook do treino, parâmetros,
erros clássicos e a Fase 2 (fine-tune direto).

---

## 🚀 Setup rápido (resumo do plano completo)

| Papel | Serviço/ferramenta | Custo |
|---|---|---|
| Cérebro | Groq `llama-3.3-70b-versatile` | grátis |
| Fallback nuvem | Cerebras (1M tokens/dia) | grátis |
| Ouvidinho (STT) | Groq `whisper-large-v3-turbo` | grátis |
| Prosódia (TTS base) | Edge-TTS pt-BR | grátis |
| Voz clonada | RVC (Applio) na CPU, treino no Colab | grátis |
| Fallback local | LM Studio Vulkan + Qwen3 4B/8B | grátis |
| Memória longa | mem0 self-hosted (opcional) | grátis |
| Personalidade | `airi-card-tsundere.json` | — |
| Skills | Tavily (busca), Groq Vision, NIM/Cloudflare (imagem) | grátis |

Latência ponta a ponta alvo: ~1–2s até ela começar a falar.

---

## ⚠️ Lembretes

- Python 3.8+ para o `hardware-detect.py` (nada além disso é preciso).
- Permissão de uso da voz da dubladora por escrito — sempre.
- O card é editável: ajuste trejeitos, cenário e exemplos à vontade.
