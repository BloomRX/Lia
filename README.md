# AIRI_Collab

Setup do projeto **Waifu**: o **AgentAI** (cérebro, roda no Google Colab com
Qwen3-4B em 4-bit) + **Project AIRI** (a waifu/avatar no PC) + **voz local**
(vozes Microsoft Edge via Node, grátis).

```
┌─────────────────────────── Colab ───────────────────────────┐
│  SETUP (1x) → START (todo dia)                              │
│  Qwen3-4B 4-bit · Gradio · API OpenAI-compatible (:7861)    │
│  túnel cloudflared → URL salva no Drive (memory/api_url.txt)│
└──────────────────────┬──────────────────────────────────────┘
                       │ (PC lê a URL do Drive)
┌──────────────────────┴────────────── PC (Windows) ───────────┐
│  waifu.bat (painel)                                          │
│   ├─ servidor_voz_airi.js  (edge-tts, porta 9860)            │
│   ├─ Airi stage-web        (Vite, porta 5173)                │
│   └─ injeta Base URL + voz no navegador (agentai-boot.html)  │
└──────────────────────────────────────────────────────────────┘
```

## Arquivos

| Arquivo | O que é |
|---|---|
| `SetupCollab.py` | ⭐ Célula SETUP do Colab — roda **1 vez** (Drive, pastas, deps, modelo, templates). **Copie este arquivo inteiro** |
| `StartCollab.py` | ⭐ Célula START do Colab — roda **todo dia** (modelo + agente + API + túnel). **Copie este arquivo inteiro** |
| `SetupCollab.md` / `StartCollab.md` | Documentação das células (explicações + o mesmo código em bloco ```` ```python ````) |
| `waifu.bat` | ⭐ **Painel da Waifu** — menu com status ao vivo e ações que ligam o que falta sozinhas |
| `iniciar_tudo.bat` | (antigo nome do launcher — só encaminha pro `waifu.bat`) |
| `iniciar_tamagotchi.ps1` | Abre o Airi **desktop** (janelinha transparente na tela, do fonte) |
| `iniciar_voz.ps1` | Só o servidor de voz |
| `atualizar_airi.ps1` | Só re-ler URL do Drive e injetar no Airi |
| `servidor_voz_airi.js` | Ponte TTS compatível com OpenAI, porta 9860 — **duas engines**: 🌐 Edge (online) e 🦉 Kokoro (offline, botão na interface instala tudo sozinho). Interface web: `http://localhost:9860/` |

## 🎛️ Voz da waifu (interface)

O servidor de voz agora tem uma página de configuração: com ele rodando
(`iniciar_tudo.bat` opção 2, ou `http://localhost:9860/` direto), dá pra:

1. **Escolher a voz** entre as recomendadas (Thalita 🌸, Brenda, Francisca,
   Antônio, Donato, Nanami 🇯🇵, Aoi 🇯🇵, Aria 🇺🇸) ou carregar o **catálogo
   completo do Edge** (400+ vozes, com busca);
2. **Ajustar pitch** (slider + presets "Fofinha +15" / "Super fofa +30" 🌸) e
   **velocidade**, testando na hora com "▶️ Ouvir teste";
3. **Copiar a configuração** pronta (ex.: `pt-BR-ThalitaNeural:+30@1.05`) e
   colar no Airi (*Settings → Providers → Speech → Voice*) ou no
   `atualizar_airi.ps1 -Voice "..."`.

A seleção fica salva no navegador (localStorage). Sem digitar nada no dedo. ✨

### 🦉 Voz offline (Kokoro) — opcional

No topo da interface há um seletor de **Engine**. A engine **Kokoro** funciona
sem internet (os modelos ficam no PC). Se ela aparecer como "não instalada",
basta clicar em **🦉 Instalar Kokoro** na própria interface: o servidor cria o
ambiente Python, instala as dependências e baixa os modelos (~360 MB) **uma
única vez**, guardando tudo em `kokoro-data/` ao lado do servidor. Requisito:
ter o **Python** instalado (`winget install Python.Python.3.12`). As vozes
offline são `kokoro:pf_dora`, `kokoro:pm_santa` e `kokoro:pm_alex`.

> Os `.md` substituem os antigos `.pdf` (que perdiam indentação, `\n` de
> strings, `\s` de regex e emojis). O código em `StartCollab.md`/`.py` está na
> **v2**, com correções de OOM — ver seção abaixo.
> **Não cole o `.md` inteiro no Colab** — só o bloco de código (ou use o `.py`).

## Como rodar

1. **Colab (1x):** abra o [`SetupCollab.py`](SetupCollab.py) no GitHub → botão **Raw** → Ctrl+A, Ctrl+C → cole numa célula (runtime **T4 GPU**) e rode.
2. **Colab (todo dia):** idem com o [`StartCollab.py`](StartCollab.py). Espere o `🌐 TÚNEL ATIVO`.
3. **PC:** rode `waifu.bat` → opção **1** (o menu mostra o status de cada peça antes).

## Verificar memória (anti-OOM)

No final do START, a linha de carga do modelo **precisa** mostrar:

```
✅ Modelo carregado.
   4-bit: True | VRAM em uso: ~2.8–3.2 GB
```

E o health check da API também reporta:

```
curl https://<túnel>/health   →  {"status":"ok","model_4bit":true,"vram_gb":3.1,...}
```

## Troubleshooting

| Sintoma | Causa | Solução |
|---|---|---|
| `Erro interno: CUDA out of memory` no Airi | Cell START antiga (pré-v2) e/ou runtime sujo com VRAM presa | **Desconectar e apagar runtime** no Colab, colar a cell do `StartCollab.md` v2 e rodar de novo |
| `4-bit: False` ou OOM já na carga | bitsandbytes quebrado/ausente | Rode o SETUP (reinstala deps), reinicie o runtime e rode o START |
| `⚠️ VRAM já ocupada sem modelo carregado` | Resto de execução anterior na mesma sessão | Reiniciar o runtime (a própria cell avisa) |
| Airi responde mas não salva memória/tarefas | Cell antiga com regex `<tool_call>` quebrado (bug do PDF) | Usar a cell do `StartCollab.md` v2 (regex corrigido) |
| URL do túnel não funciona | Sessão do Colab trocou | Rode o START de novo e depois `iniciar_tudo.bat` opção 3 |
