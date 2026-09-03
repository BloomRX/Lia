# voice_engines — Novos motores de voz (substituem o GPT-SoVITS)

> Esta pasta concentra TUDO que é novo para a voz da Lia, de forma organizada,
> para nem você nem eu nos perdermos enquanto avançamos.
>
> **Objetivo:** trocar o GPT-SoVITS (que não tem português nativo) por motores
> modernos com **português nativo**, licença limpa (Apache 2.0), clone em
> poucos segundos e streaming. Cada motor roda como um *worker* Python
> independente que o servidor Node (`../servidor_voz_airi.js`) sobe **só quando
> usado** (economiza RAM e não trava o Edge/Kokoro).

---

## 1. Por que esta pasta?

O `servidor_voz_airi.js` é um **gateway multi-engine**: um único servidor Node na
porta **9860** que fala uma API compatível com OpenAI (`/v1/audio/speech`,
`/v1/models`, ...) e escolhe a engine por um **prefixo no nome da voz**:

```
edge:<voz>        → nuvem Microsoft (online)     [já existe]
kokoro:<voz>      → modelo offline (ONNX)        [já existe]
sovits:<voz>      → GPT-SoVITS (porta 9880)       [a ser removido]
qwen3:<id_voice>  → Qwen3-TTS   (novo)           [este pacote]
cosyvoice3:<id>   → CosyVoice 3 (novo)           [este pacote]
```

Cada motor novo é um **worker Python** em `voice_engines/`. O Node escuta o
worker via **JSON-lines no stdin/stdout** (mesmo protocolo do Kokoro) e só o
carrega na primeira vez que for usado.

---

## 2. Estrutura de arquivos

```
voice_engines/
├── README.md                 ← este arquivo (arquitetura + uso)
├── _common.py                ← framework do worker (loop stdio + salvar áudio)
├── qwen3_worker.py           ← worker Qwen3-TTS (clone + voz custom)
├── cosyvoice3_worker.py      ← worker CosyVoice 3 (beta)
├── install_qwen3.py          ← baixa/setup do Qwen3 (só o modelo escolhido)
└── install_cosyvoice3.py     ← baixa/setup do CosyVoice 3 (pesado, beta)

# Diretórios de dados (criados em runtime, gitignored, fora do repo):
#  <repo>/voice-data/
#  ├── qwen3/
#  │   ├── installed.json      ← marca qual variante do Qwen3 está pronta
#  │   ├── venv/               ← venv do worker Qwen3
#  │   └── voices/<nome>/
#  │       ├── config.json     ← variante + ref_audio + ref_text + idioma
#  │       └── ref.wav         ← áudio de referência (5–15s)
#  └── cosyvoice3/
#      ├── installed.json
#      ├── venv/
#      └── voices/<nome>/...
```

---

## 3. Como o worker conversa com o Node

Protocolo **JSON-lines** (mesmo do Kokoro), para os motores novos serem tratados
do mesmo jeito no servidor:

**Node → worker (stdin), um objeto por linha:**
```json
{ "id": "q1_1712", "text": "Olá, Lia!", "voice": "liz",
  "speed": 1.0, "ref_audio": "...", "ref_text": "...",
  "language": "Auto", "instruct": "", "out": "C:/tmp/q1_1712.wav" }
```

**worker → Node (stdout), um objeto por linha:**
```json
{ "event": "ready" }                                   // carregou modelo
{ "event": "warn", "msg": "..." }                      // aviso (não-fatal)
{ "event": "ok", "id": "q1_1712", "file": "..." }      // sucesso
{ "event": "error", "id": "q1_1712", "msg": "..." }    // erro
```

O worker **nunca usa GPU** por padrão: na sua máquina (RX 580 = AMD, sem ROCm)
tudo roda em **CPU**. Em `config.json` dá para trocar para `cuda` quando existir
GPU NVIDIA.

---

## 4. Qual modelo escolher (decisão de hardware)

| Variante | RAM/CPU no seu PC | Recomendado? |
|---|---|---|
| Qwen3-TTS **0.6B** (clone + voz custom) | leve (~2.5 GB) | ✅ **padrão** |
| Qwen3-TTS **1.7B** (clone + voz custom) | pesado (~6.8 GB fp32) | ⚠️ só se sobrar RAM |
| CosyVoice 3 **0.5B** | médio (~4 GB) | 🟡 opcional (beta) |

Regra: **baixar só o que for usar** (`install_qwen3.py --variant 0.6b`).

---

## 5. Como adicionar um motor novo (passo a passo)

1. Criar `voice_engines/<nome>_worker.py` que:
   - Chama `_common.py` com um `name`, uma função `load(model_dir)` e uma função
     `generate(req, model) -> caminho do wav`.
   - Imprime `{"event":"ready"}` ao terminar o load.
2. No `servidor_voz_airi.js`:
   - Detectar o motor (ex.: `detectQwen3()`) pela existência de
     `voice-data/<engine>/installed.json`.
   - `ensureWorker()` + `generate()` seguindo o padrão do Kokoro.
   - Adicionar o prefixo no dispatch de `/v1/audio/speech`.
   - Listar em `/v1/models` e `/health`.
3. Na interface (`app/lia_app.py`): adicionar o motor no `engine_combo` e em
   `_update_voice_list()`.

---

## 6. Comandos úteis

```bash
# Instalar só o Qwen3 0.6B (recomendado)
python scripts/voice_engines/install_qwen3.py --variant 0.6b

# Instalar o Qwen3 1.7B (mais pesado)
python scripts/voice_engines/install_qwen3.py --variant 1.7b

# Instalar o CosyVoice 3 (beta, mais passos manuais possíveis)
python scripts/voice_engines/install_cosyvoice3.py

# Testar o worker direto (sem o servidor): cria um wav de teste
python scripts/voice_engines/qwen3_worker.py --selftest
```

---

## 7. Status atual (Git)

- ✅ Fase 1a: estrutura + workers + instaladores (este pacote).
- ⏳ Fase 1b: ligação no `servidor_voz_airi.js` (dispatch + install/status).
- ⏳ Fase 1c: seletor no `app/lia_app.py` (engine qwen3/cosyvoice3).
- ⏳ Fase 2: remover GPT-SoVITS do código e das listas (depois de validar).
