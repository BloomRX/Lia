# Voz personalizada (clonada/treinada) para a Airi — guia prático

> PC de referência: Ryzen 5 5500 (6c/12t) · RX 580 8GB · 16GB RAM · objetivo: pt-BR, latência baixa
> Continuação de `colab-vs-alternativas-airi.md` e `hardware-detect.py`

---

## A lição que a comunidade já aprendeu por você

Um guia completo de IA local em RX 580 (projeto aivisionslab, 2026) testou as rotas de clonagem e concluiu:

| Rota | Naturalidade | Observação |
|---|---|---|
| TTS generativo puro (XTTS etc.) | 60–70% | prosódia "artificial", degrada em textos longos |
| **Voz neural de qualidade + conversão RVC** | **80–95%** | prosódia humana (ator real) + identidade clonada |

**A fórmula vencedora:** use uma voz neural pt-BR excelente (grátis) só para a *prosódia*, e um modelo **RVC treinado na voz-alvo** para converter a *identidade*. É o padrão da comunidade BR de voz/VTuber.

## ⚠️ Verdades sobre o SEU hardware (testadas e documentadas)

- **DirectML está morto para RVC**: `torch-directml` exige torch 2.4.1 e o Applio atual exige 2.7.1 — conflito irresolúvel. Esqueça a RX 580 no pipeline PyTorch.
- **RVC na CPU funciona bem para inferência**: ~30 min de processamento por 2h de áudio (RTF ~0,25) — para frases de chat de 3–5s, ~0,5–1,2s de conversão.
- **TREINAR na CPU é sofrimento**: ~6 min/época × 200 épocas ≈ **20h** num Xeon 24 threads (no seu Ryzen, mais). 
- **Conclusão: treine UMA VEZ no Colab grátis (T4, ~30–60 min), rode local para sempre.** É exatamente o único uso que o Colab tem de bom (tarefa finita, começo-meio-fim) — como no doc anterior.

## 🏗️ Pipeline recomendado (latência estimada por frase)

```
Texto da Akari (frases curtas, graças ao card tsundere 😉)
   │
   ├─ 1. Edge-TTS pt-BR (Francisca/Thalita)  → ~0,3s   [prosódia humana, grátis, sem chave]
   │
   ├─ 2. RVC local (CPU, modelo .pth da voz) → ~0,5–1,2s [identidade clonada]
   │
   └─ SOM = voz personalizada
```

**Total do estágio de voz: ~1–1,5s** (+ STT ~0,3s + cérebro ~0,3s ⇒ ~2s ponta a ponta).
Custo extra da personalização: ~1s vs. Kokoro/Piper "puro". É o preço honesto no seu hardware; numa NVIDIA futura, o RVC cai para <300ms.

## Como integrar no Airi (o mesmo truque de sempre)

O Airi aceita provedores **"OpenAI Compatible"** para fala e transcrição (Base URL customizada). Então basta um servidor local que exponha `POST /v1/audio/speech` e faça Edge-TTS→RVC internamente:

1. **AllTalk TTS v2** (erew123/alltalk_tts): servidor OpenAI-compatible que já une TTS + RVC opcional, com interface de vozes. Caminho mais pronto.
2. Alternativa: **Applio** tem modo API — um wrapper de ~50 linhas (FastAPI) chama Edge-TTS e depois o endpoint do Applio.
3. No Airi: **Settings → Providers → Speech → OpenAI Compatible** → Base URL `http://localhost:7851/v1` (ou a do seu wrapper) → selecionar em **Modules → Speech**.
4. Seu App de pré-config: health-check no endpoint de voz antes de abrir o Airi (mesma lógica do Groq).

## 🎓 Passo a passo do treino (uma vez só)

1. **Dataset**: 10–30 min de áudio limpo da voz-alvo (mono, sem música, sem eco). Fatie em clipes de 5–15s. RVC **não precisa de transcrição**.
   - Voz válida: a sua, de alguém com permissão explícita, ou material licenciado. (Clonar voz de terceiros sem consentimento = não.)
2. **Treino no Colab**: abra o notebook oficial do **Applio** (IAHispano/Applio), suba o dataset (zip), treine **~200–300 épocas** no T4 (30–60 min), baixe o `.pth` + `.index`.
3. **Inferência local**: instale o Applio em modo CPU (funciona bem) ou use o AllTalk com RVC integrado; carregue seu `.pth`.
4. **Ajuste fino**: `index rate` 0.5–0.75 (protege de artefatos), pitch 0 se voz do mesmo gênero, f0 method `rmvpe`.

## Rotas alternativas (comparação honesta)

| Rota | Prós | Contras | Veredito no seu PC |
|---|---|---|---|
| **Edge-TTS + RVC (recomendada)** | 80–95% natural, latência ~1s, treino rápido no Colab | 2 peças (mas AllTalk une) | ✅ **principal** |
| XTTS v2 (zero-shot, 6s de referência) | sem treino nenhum | inferência CPU lenta (segundos/frase), licença não-comercial | teste rápido apenas |
| XTTS v2 **fine-tunada** | voz muito fiel, boa em pt-BR | mesmo problema de latência CPU | melhor p/ quem tem NVIDIA |
| F5-TTS fine-tune | comunidade aprova | pt-BR não-oficial, treino pesado | niche |
| Qwen3-TTS (clone 3s) | qualidade | você já viu: PyTorch → CPU → lento | ❌ |
| Piper treinado do zero | 40ms, rei da latência | precisa de horas de áudio; voz mais robótica | para "treino completo" extremo |
| ElevenLabs | topo de linha | clonagem só no plano pago | se um dia pagar |

## Orçamento final do pipeline de voz

| Estágio | Serviço | Latência | Custo |
|---|---|---|---|
| STT (ouvir) | Groq whisper-turbo | ~0,3s | grátis (2.000 req/dia) |
| Cérebro | Groq/Cerebras | ~0,3s 1º token | grátis |
| Prosódia | Edge-TTS pt-BR | ~0,3s | grátis |
| Identidade | RVC local (CPU) | ~0,5–1,2s | grátis |
| Treino da voz | Colab T4 (1x) | 30–60 min | grátis |

**Tudo grátis. Único custo real: uma tarde de preparação de dataset + um treino no Colab.**

---

## 🎬 Playbook: dataset de 13 minutos (o caso exato)

13 min é o *sweet spot* documentado do RVC. Não compre/ Grave mais nada — só siga:

### Etapa 1 — Preparar o dataset (1–2h, no seu PC)

1. **Se o áudio veio com música/efeitos** (anime, game, trailer): separe a voz primeiro com **UVR5** (Ultimate Vocal Remover — grátis, modelo `UVR-DeNoise` ou `bs_roformer`; roda na CPU do Ryzen). Fundo musical é o assassino nº 1 de treinos RVC.
2. **Padronize**: `ffmpeg -i entrada.mp3 -ac 1 -ar 44100 saida.wav` (mono, WAV, sem compressão).
3. **Fatie em clipes de 5–15s** — o *Dataset Toolbox* do próprio Applio faz slicing automático por silêncio (aba "Tools → Dataset Toolbox").
4. **Escute TUDO antes de treinar** (vale, são 13 min): corte clipes com ruído, risadas sobrepostas, respiração longa, voz gritada distorcida. 13 min limpos > 20 min sujos.
5. Compacte: `dataset_akari.zip`.

### Etapa 2 — Treinar no Colab (T4, ~30–45 min)

No notebook oficial do Applio (`github.com/IAHispano/Applio` → Colab):

| Parâmetro | Valor | Por quê |
|---|---|---|
| Sample rate do modelo | **48k (v2)** | preserva o brilho de voz feminina |
| Épocas | **200, teste; estenda até 300** | dataset curto: mais que isso arrisca overfit (voz "abafada"/artefatos) |
| Batch size | 8–12 | T4 tem 15GB usáveis |
| Precisão | fp16 (auto no T4) | — |
| Save cada | 25 épocas | permite voltar se a última ficou pior |
| Index | FAISS (auto) | melhora similaridade |

O Applio renderiza **samples de teste durante o treino** — escute os do checkpoint 100/150/200 e escolha o melhor (quase sempre é entre 150–250 com dataset desse tamanho). Baixe o **`.pth` + `.index`**.

### Etapa 3 — Inferência local (CPU do Ryzen, para sempre)

- Applio em modo CPU ou AllTalk TTS v2 (que já embute RVC no servidor OpenAI-compatible do Airi).
- Config de inferência inicial: **f0 method `rmvpe`** · **pitch 0** (mesmo gênero/tessitura da voz base) · **index rate 0.6–0.75** (protege de artefatos; se a identidade ficar fraca, sobe pra 0.85).
- Teste com as falas reais do card da Akari: "<|EMOTE_ANGRY|> Q-QUE?! Eu?! Organizar arquivos é abaixo da minha dignidade!"

### Etapa 4 — Fase 2 (opcional, quando valer a pena)

Peça pra dubladora gravar uma sessão de **frases tsundere emocionais** (raiva fingida, risada, "hmph", suspiros, frases curtas com ironia). Duas formas de usar:
- **Melhor prosódia futura**: com ~45–60 min totais, dá pra fine-tunar um modelo estilo F5-TTS com a voz dela *direto* (sem conversão) — prosódia própria em vez de Francisca.
- **Toques de produção**: os sons curtos ("hmph!", risadinha) viram samples disparáveis/cortes de áudio nas reações do Airi.

### Erros clássicos que destroem treinos de 13 min (evite)

1. Treinar com música de fundo ("mas dá pra ouvir ela bem!") — UVR5 resolve, não pule.
2. 500+ épocas em dataset curto por achar que "mais é melhor" → overfit.
3. Pitch ≠ 0 na conversão → timbre artificial de "anúncio de rádio".
4. Não ouvir os checkpoints → entregar a pior época do treino.
5. Esquecer que a voz base (Edge-TTS) define a entonação — se a frase do card estiver sem emoção, nenhuma conversão salva; a emoção nasce no texto/exemplos do card.

