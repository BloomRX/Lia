# 🔍 Checkup do Sistema de Voz da Lia

> Relatório de auditoria do pipeline de treinamento/síntese de voz.
> Gerado a partir do código-fonte verificado do GPT-SoVITS, da arquitetura
> atual (`docs/ESTADO-DO-PROJETO.txt`, `app/lia_app.py`, `scripts/*`) e de
> benchmarking de modelos TTS open-source (2026).

---

## 1. Conclusão em uma frase

**Manter GPT-SoVITS para uma waifu que fala português é lutar contra a ferramenta**:
o modelo **não tem fonemização nativa para português** (só zh/ja/en), o que é a
raiz de praticamente todos os bugs que viemos caçando (`KeyError: ''`,
`ZeroDivisionError`, segmento "sem transcrição", áudio "enrolado"). O caminho
recomendado é **trocar por Qwen3-TTS** (Apache 2.0, português nativo, clone em 3s,
streaming) e usar **clone few-shot para o dia a dia + fine-tune no Colab para a
identidade máxima**.

---

## 2. O achado decisivo

Em `GPT_SoVITS/text/cleaner.py`:

```python
language_module_map = {"zh": chinese, "ja": japanese, "en": english}

def clean_text(text, language):
    if language not in language_module_map:
        language = "en"
        text = " "   # ← se o idioma não for zh/ja/en, o TEXTO É APAGADO
```

O GPT-SoVITS **só sabe fonemizar chinês, japonês e inglês**. Quando o ASR grava
`pt` no `.list`:

- O pipeline **apaga o texto** → phoneme vazio → é daí que nascem os "segmentos
  sem transcrição" que estamos removendo manualmente; ou
- Se você mapeia `pt→en`, ele **pronuncia português com fonética inglesa** →
  sotaque estrangeiro e vogais nasais erradas (`ão`, `õe`, `nh`, `lh`, o `R`
  de "gato/carro"). O `patch_sovits_pt.py` (v51) contorna isso, mas é um
  *workaround* que aproveita o ARPABET do inglês — não é suporte de verdade.

**Ou seja:** não é um bug pontual; é uma **limitação arquitetural** do GPT-SoVITS
para a língua da Lia.

---

## 3. O que a voz da Lia precisa (e o estado atual)

| Necessidade | GPT-SoVITS hoje | Importância |
|---|---|---|
| Português brasileiro nativo | ❌ (fonética inglesa) | 🔴 Crítico |
| Emoção/expressividade | 🟡 média | 🟠 Alta (personalidade) |
| Consistência da voz da Liz | 🟢 boa (treino dedicado) | 🟠 Alta |
| Baixa latência (conversa) | 🟢 boa | 🟠 Alta |
| Licença limpa | 🟢 MIT | 🟢 já ok |
| Rodar no SEU hardware (CPU) | 🟢 roda (lento) | 🟢 ok |

---

## 4. Hardware: o ponto que ninguém disse

Seu hardware: **Ryzen 5 5500 · RX 580 8GB · 16 GB RAM**.

- A **RX 580 (Polaris / gfx803) NÃO é suportada pelo ROCm** nas versões atuais do
  PyTorch. Na prática **você roda TTS/treino em CPU**. Por isso o SoVITS leva
  "85 min" e as etapas são lentas.
- **16 GB de RAM** é suficiente para *inferência* de modelos de voz 0.5B–1.7B,
  mas **muito apertado para *treinar/fine-tunar* um LLM de voz** (0.6B+) localmente.

**Consequência prática:** o **clone few-shot (Caminho A) é totalmente viável na sua
máquina**; o **fine-tune pesado (Caminho B) deve rodar no Colab** (que você já usa
para o cérebro da Lia) e baixar os pesos para o PC.

---

## 5. Comparativo de modelos (2026) — todos com PORTUGUÊS

| Modelo | Licença | Clone | Treino | Emoção | Streaming | Vram/RAM | Ponto forte |
|---|---|---|---|---|---|---|---|
| **Qwen3-TTS-0.6B** | Apache 2.0 | 3s | ✅ Base | ✅ instrução | ✅ | ~1.8GB | **melhor conj. geral + licença limpa + roda na CPU** |
| Qwen3-TTS-1.7B | Apache 2.0 | 3s | ✅ | ✅ | ✅ | ~3.9GB | mais qualidade, mais pesado |
| CosyVoice 3 (0.5B) | Apache 2.0 | 5s | ✅ | ✅ (melhor) | ✅ | ~4GB | **melhor similaridade + emoção** |
| XTTS-v2 (Coqui) | CPML (não-com.) | 6s | ✅ | limitada | ✅ | ~5GB | maduro, multilingue |
| IndexTTS-2 | Apache 2.0 | — | — | ✅ | lento | ~5GB | só zh/en — **não serve** |
| F5-TTS | CC‑BY‑NC (não-com.) | 5s | ✅ | limitada | ❌ | ~3GB | qualidade (mas **não-comercial**) |
| **GPT-SoVITS (atual)** | MIT | 5s | ✅ | média | ✅ | ~6GB | **sem PT — não serve** |

Benchmarks (speaker similarity / WER / qualidade), fontes: DataRoot Labs, IndexTTS,
CosyVoice 3, Qwen3-TTS (Alibaba), avaliações da comunidade.

---

## 6. Recomendação (Caminho A + B, como você pediu)

### 🥇 Qwen3-TTS-0.6B = motor principal da voz
- **Caminho A (clone few-shot, dia a dia):** solta um áudio de referência limpo de
  **5–15s** da voz desejada → a Lia fala na hora, em PT nativo, com emoção por
  instrução e streaming. **Sem treino, sem dor de cabeça.** Roda na sua CPU.
- **Caminho B (fine-tune, identidade máxima):** você **fine-tuna o Qwen3-TTS-Base
  no Colab (GPU gratuita)** com o dataset da voz e baixa os pesos pro PC. Ideal
  para a voz de um personagem fixo (a Liz).

### Por que não CosyVoice 3 como principal
É o campeão de *similaridade/emoção*, mas é mais pesado de rodar em CPU e o
ecossistema de fine-tune é mais chato. **Deixe como opcional** (posso plugar
também). F5-TTS e IndexTTS-2 ficam **fora** (licença não-comercial / sem PT).

### O que a troca elimina
- ✅ A limitação de português (causa dos bugs).
- ✅ O `patch_sovits_pt.py` (não é mais necessário).
- ✅ O pipeline SoVITS+GPT (6 etapas, horas em CPU) para o caso comum.
- ✅ Os arquivos `6-name2semantic.tsv`, `2-name2text.txt`, BERT/HuBERT/SV, etc.

---

## 7. Plano de migração proposto

1. **Adicionar Qwen3-TTS como nova engine** no app (novo servidor local
   `scripts/servidor_voz_qwen3.py`), ao lado de Edge/Kokoro, e como **voz custom**
   (substitui o papel do SoVITS na lista de modelos).
2. **Caminho A** — ao "Treinar" ou "Clonar", o app pede o áudio de referência e
   **gera o modelo clonado** imediatamente (sem SoVITS).
3. **Caminho B** — gerar um script/notebook `colab` que faz o fine-tune do
   Qwen3-TTS-Base com TensorBoard, e o app faz **download dos pesos**.
4. **Remover GPT-SoVITS** do código (opções de UI, `train_auto.py`, servidor 9880,
   patches) quando a nova engine estiver validada. **Não apagar a pasta** do disco
   do usuário de imediato (é o fallback) — ou apagar depois, com um script seguro.

---

## 8. Melhorias que valem para qualquer backend

1. **Qualidade do dataset > quantidade:** referência limpa, um só locutor, mesmo
   microfone/sala, nível normalizado, **5–15 s** para clone; **10–60+ min** variando
   emoção para fine-tune.
2. **Corte por voz (VAD)** em vez de só por tempo → evita "transcrição vazia".
3. **Teste A/B cego em PT-BR** antes de fixar: frases com os sons difíceis —
   *"João não dá a mão ao irmão"*, *"O menino é pequeno"*, *"Ela mora rua acima"*,
   *"O trabalho é maravilhoso"*.
4. **Pós-processamento:** compressão leve + rolloff de agudos reduz o "artificial".
5. **Aviso de voz sintética + watermark** (Chatterbox já tem) por segurança ética/legal.
