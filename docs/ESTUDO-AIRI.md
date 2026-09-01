# Estudo do Project AIRI — e como a Lia se integra

> Análise da versão mais recente do **Project AIRI** (`github.com/moeru-ai/airi`, ramo
> `main` / tags `v0.12.0-beta.*`), assumindo que **sempre usaremos a versão mais
> recente, mesmo em beta**. Focado no que importa para a integração com a Lia.
> Última atualização: 01/09/2026 (último commit do AIRI no momento da análise).

---

## 1. O que é o Project AIRI

Projeto open-source (MIT) que recria conceitos inspirados na Neuro-sama: um
**"contêiner de almas" / waifu virtual** com voz, visão e habilidades (jogar
Minecraft/Factorio, live2d, etc.). É **self-hosted** — roda localmente (web ou
desktop) e você pluga seus próprios provedores de IA.

- Repo: `https://github.com/moeru-ai/airi` (moeru-ai / org `@proj-airi`)
- Star/fork grandes (48k+ stars, 4.8k forks) — projeto muito ativo (4.3k commits).
- O que a Lia usa dele: a **interface da waifu** (stage-web no navegador e
  stage-tamagotchi no desktop). A "mente" (cérebro) e a "voz" vêm de **fora**
  (Colab + servidor de voz da Lia), plugadas via **providers OpenAI-compatíveis**.

---

## 2. Arquitetura do monorepo (versão `main` / beta)

É um monorepo `pnpm` com workspaces. Estrutura top-level:

```
apps/
  stage-web          <- WEB da waifu (Vue 3 + Vite) — porta 5173 (Vite default)
  stage-tamagotchi   <- DESKTOP (Electron + electron-vite) — janela transparente na tela
  stage-pocket       <- versão mobile (pocket)
  component-calling  <- (framework de componentes, auxiliar)
  ui-server-auth     <- UI do serviço de auth (só p/ backend hosted)
server/
  apps/api           <- API de recursos (backend hosted)
  apps/auth          <- Better Auth + OIDC (backend hosted)
  packages/auth-shared, server-sdk-shared
  dev/caddy          <- roteamento local (só p/ backend)
  docker-compose.yaml<- stack local do backend (Postgres+Redis+API+Auth+Caddy)
packages/            <- bibliotecas compartilhadas (TS/Vue):
  stage-ui           <- UI compartilhada (botões, stores de providers, módulos de settings)
  stage-pages        <- páginas (inclui páginas de SETTINGS / providers)
  stage-shared       <- composables compartilhados (persistência, analytics)
  stage-layouts      <- layouts
  pipelines-audio    <- pipeline de áudio (TTS, streaming, prioridade, chunker)
  audio              <- utilidades de áudio (contexto, encoding)
  core-agent         <- mensagens do agente / renderização de provider
  core-character     <- (stub, ainda vazio — `export {}`)
  server-sdk / server-runtime / electron-* (eventa, screen-capture, vueuse)
  plugin-sdk         <- SDK de plugins (discord, minecraft, etc.)
```

**Quem usa `packages/stage-ui`**: o código de providers, módulos de settings e a
persistência moram em `packages/stage-ui`, e **tanto o web quanto o desktop**
(que só é uma casca Electron) usam esse pacote. Ou seja: a lógica de
"cérebro/voz" é **compartilhada** entre web e tamagotchi.

> 🇧🇷 Implicação para a Lia: o que funciona na web funciona igual no desktop e
> vice-versa, porque ambos consomem o mesmo `stage-ui`. A única diferença é a
> "casca" e alguns providers nativos (microfone, janela).

---

## 3. Portas, scripts e como rodar (dev)

### 3.1 Versões pinadas
- `.tool-versions`: `nodejs 26.7.0`, `pnpm 11.24.0`.
- `package.json` (root) → `"packageManager": "pnpm@11.24.0"`.
- ⚠️ A doc `docs/content/en/docs/contributing/index.md` ainda cita **Node 24.13.0**
  (defasada). **Use o `.tool-versions` como fonte de verdade** (Node via `mise`/`nvm`,
  Corepack para pnpm).
- `installer.py` da Lia clona `https://github.com/moeru-ai/airi.git` e roda
  `pnpm install`.

### 3.2 Scripts do root (`package.json`)
| Comando | O que faz |
| --- | --- |
| `pnpm dev` | `pnpm -r -F @proj-airi/stage-web dev` → web na 5173 |
| `pnpm dev:web` | idem, explícito |
| `pnpm dev:web:https` | web com mkcert (https) |
| `pnpm dev:tamagotchi` | Electron do desktop (stage-tamagotchi) |
| `pnpm dev:tamagotchi:xwayland` | idem p/ plataformas X11 |
| `pnpm dev:server-auth` | sobe UI de auth (só hosted) |
| `pnpm dev:backend` | `docker compose -f server/docker-compose.yaml up --build` (só hosted) |
| `pnpm dev:server` | server-runtime |
| `pnpm build:web` / `build:tamagotchi` | builds |
| `postinstall` | `pnpm exec simple-git-hooks && pnpm run build:packages` |

O **stage-web NÃO define porta no `vite.config.ts`** (usa default **5173**). É a
porta que a Lia usa (`AIRI_PORT = 5173`).

### 3.3 stage-tamagotchi (desktop) — atenção ao Electron
O `package.json` do tamagotchi tem script `dev`:
```
"dev": "install-electron && electron-vite dev"
```
> Motivo: o **Electron 42 removeu o script `postinstall`** que baixava o binário.
> Agora o binário é baixado quando o bin entry roda pela 1ª vez, mas
> `electron-vite` lê direto `node_modules/electron/path.txt` — então uma instalação
> limpa quebra com *"Error: Electron uninstall"*. O script `install-electron`
> resolves isso (roda o mesmo código do antigo `postinstall`, retornando cedo se o
> binário já existe).

O script da Lia `scripts/iniciar_tamagotchi.ps1` **já trata isso** (procura o
pacote, roda o `install.js` se `path.txt` não existir). É um dos pontos que
continuam válidos mesmo na beta.

---

## 4. Providers: o coração da integração

O AIRI é agnóstico de IA: você conecta **providers** para várias "tarefas"
(`tasks`): `chat`, `text-to-speech`, `transcription`, `vision`, `artistry`, etc.

### 4.1 Onde são definidos
`packages/stage-ui/src/libs/providers/providers/<nome>/index.ts` → cada provider
usa `defineProvider({ id, tasks, createProvider(config), ... })` e é registrado no
`registry.ts`. Os `.vue` de configuração ficam em
`packages/stage-pages/src/pages/settings/providers/<tarefa>/`.

Providers de **speech** (`text-to-speech`) presentes na beta:
`aivis-speech`, `alibaba-cloud-model-studio`, `app-local-audio-speech`,
`browser-local-audio-speech`, `comet-api-speech`, `deepgram-tts`, `elevenlabs`,
`google-gemini-audio-speech`, `index-tts-vllm`, `kokoro-local`, `microsoft-speech`,
`mimo-audio-speech`, `official-provider-speech`, `official-provider-speech-streaming`,
`openai-audio-speech`, **`openai-compatible-audio-speech`**, `openrouter-audio-speech`,
`player2-speech`, `voicevox`, `volcengine`.

Providers de **chat/consciência**: `openai-compatible` (é o que a Lia usa),
`official`, `ollama`, `lm-studio`, `amazon-bedrock`, `azure-ai-foundry`,
`cloudflare-workers-ai`, e dezenas de outros.

### 4.2 O provider que a Lia usa

**Voz** → `openai-compatible-audio-speech`
```ts
// packages/stage-ui/src/libs/providers/providers/openai-audio/index.ts
export const providerOpenAICompatibleAudioSpeech = defineProvider<OpenAICompatibleAudioConfig>({
  id: 'openai-compatible-audio-speech',
  tasks: ['text-to-speech'],
  createProvider: createAudioProvider,   // createOpenAI(apiKey, normalize(baseUrl))
})
```
- `createAudioProvider` **normaliza** o `baseUrl` com `/` no fim
  (se já termina em `/`, mantém; senão acrescenta).
- O `model` default da UI é `tts-1`, mas a Lia seta **`edge-tts`** (o servidor
  local ignora o model e usa o **prefixo do voice** para escolher edge/kokoro/sovits).
- O `baseUrl` que a Lia injeta: `http://127.0.0.1:9860/v1` → vira `.../v1/`.

**Cérebro** → `openai-compatible`
```ts
providerOpenAICompatible = defineProvider({ id: 'openai-compatible', tasks: ['chat'], ... })
```

### 4.3 Como a voz é gerada (endpoint)
`packages/stage-ui/src/stores/modules/speech.ts`:
```ts
const response = await generateSpeech({
  ...provider.speech(model, requestProviderConfig),
  input,
  voice,
})
```
Para um provider OpenAI-compatível, isso chama **`POST {baseUrl}/audio/speech`** com
`{ model, input, voice, ... }`. O servidor da Lia (`scripts/servidor_voz_airi.js`)
expõe exatamente isso:

| Endpoint do servidor da Lia | Uso pelo Airi |
| --- | --- |
| `POST /v1/audio/speech` | Gera o áudio (edge/kokoro/sovits) — **é o que o Airi chama** |
| `GET /v1/models` | Lista `edge-tts` / `kokoro` (validação ao salvar provider) |
| `GET /v1/audio/voices` / `/all` | Lista vozes |
| `POST /v1/chat/completions` | Resposta fake — validação do cérebro |
| `/cerebro/v1` | **Proxy** para o túnel do Colab (URL fixa p/ o Airi) |
| `/cerebro/_status` | Status do túnel configurado |
| `/health`, `/` | Health check / interface |

### 4.4 Voice: como pitch/rate são passados
O Airi guarda `pitch`/`rate` em `settings/speech/*` e, para o provider
`openai-compatible-audio-speech`, envia o `voice` como está (a Lia usa sufixos
`:+30@1.1` no nome da voz para pitch/velocidade — e o servidor interpreta).
Também há suporte a `extraBody` para campos extras, e SSML para alguns providers.
Para a Lia, o **modelo** (`edge-tts`/`sovits`) e o **prefixo do voice**
(`kokoro:`, `sovits:`) são o mecanismo de troca de engine.

---

## 5. Persistência (localStorage) — o que a Lia injeta

O AIRI (mesmo na beta) guarda os providers e o estado de voz/cérebro em
`localStorage` via Pinia (`useLocalStorage` / `useLocalStorageManualReset`). As
chaves são **as mesmas** que a Lia já injeta hoje:

| Chave | Tipo | Default | Quem usa |
| --- | --- | --- | --- |
| `settings/providers/configured` | `Record<id, Provider>` | `{}` | providers configurados |
| `settings/providers/added` | `Record<id, boolean>` | `{}` | providers "adicionados" |
| `settings/speech/active-provider` | string | `speech-noop` | provider de voz ativo |
| `settings/speech/active-model` | string | `''` | modelo de voz ativo |
| `settings/speech/voice` | string | `''` | voz ativa |
| `settings/speech/pitch` | number | `0` | pitch |
| `settings/speech/rate` | number | `1` | velocidade |
| `settings/speech/ssml-enabled` | boolean | `false` | SSML |
| `settings/consciousness/active-provider` | string | `''` | cérebro ativo |
| `settings/consciousness/active-model` | string | `''` | modelo do cérebro |
| `settings/consciousness/active-custom-model` | string | `''` | modelo custom |

> A injeção da Lia (em `app/lia_app.py` → `_auto_configurar_providers`, e no
> `scripts/configurar_tamagotchi.ps1` / `scripts/agentai-boot.html`) já escreve
> `settings/providers/configured` e `settings/speech/*`. **Os IDs continuam válidos**
> na beta (`openai-compatible`, `openai-compatible-audio-speech`).
>
> ⚠️ **Observação (lacuna):** a injeção atual da Lia NÃO seta
> `settings/consciousness/active-provider` / `active-model`. Na beta o cérebro
> default é `''` (vazio). Se o Airi não auto-selecionar o provider de chat
> configurado, o `openai-compatible` fica "adicionado" mas não "ativo". Isso é um
> ponto a **testar/ajustar** ao migrar para a beta (ver §7).

---

## 6. Backend (hosted) — opcional

O AIRI beta agora tem um **backend opcional** (`server/`). Ele NÃO é necessário
para o uso local da cia (web/desktop + Colab + servidor de voz).

- Sobe com `pnpm dev:backend` (usa `server/docker-compose.yaml`).
- Stack: **Postgres (vchord, porta 5435 host), Redis (6379), API (`@proj-airi/api-server`), Auth (`@proj-airi/auth-server`), Caddy** expondo só `http://localhost:6112`.
- Finalidade: deploy **hosted** (Railway) com login (Better Auth), sync de
  configurações via API, etc.
- O `store` de providers ainda persiste em `localStorage` como **fonte de verdade
  local**; o backend é um "snapshot remoto" mesclado depois de um request
  (`createProvidersQueryOptions`). Ou seja: **a injeção via localStorage continua
  funcionando mesmo com backend presente**.

---

## 7. Versionamento / releases (o modelo que vamos seguir)

| Versão | Tipo | Data |
| --- | --- | --- |
| **v0.12.0-beta.5** | prerelease | 2026-08-29 |
| v0.12.0-beta.4 / beta.3 / beta.1 | prerelease | 2026-08-24..27 |
| **v0.11.3** | **estável** | 2026-07-18 |
| v0.11.0 | estável | 2026-07-08 |
| v0.10.2 | estável | 2026-05-07 |

Regra combinada: **usar sempre a mais recente (`main` / `v0.12.0-beta.x`)**, mesmo
sendo beta. O `main` do repo é o que o `installer.py` clona por padrão (ramo default
`main`), então hoje isso já acontece.

### 7.1 O que muda da `v0.11.3` para a `v0.12.0-beta` (relevante p/ Lia)
1. **Backend/API + Auth** novos (`server/`) — opcional, não bloqueia o uso local.
2. **Electron 42** removeu o `postinstall` do binário → tamagotchi precisa do
   `install-electron` (a Lia já trata em `iniciar_tamagotchi.ps1`).
3. **Stores Pinia** com `useLocalStorageManualReset` — as **chaves de localStorage
   continuam as mesmas**, então a injeção por CDP da Lia segue válida.
4. **Módulo `memory-long-term`** ainda é `<WIP />` (não implementado).
5. **`packages/core-character`** é stub (`export {}`) — a "personalidade" não é um
   conceito de código; é definida no config/UI do agente (system prompt no módulo de
   consciência + "persona" fornecida pelo usuário).
6. **Providers de voz novos** (aivis, index-tts, player2, etc.) — a Lia não precisa
   deles; continua no `openai-compatible-audio-speech`.

---

## 8. Integração atual com a Lia (fluxo real)

### 8.1 O que a Lia sobe e injeta
- **Cérebro (chat)**: Colab (Qwen3-4B 4-bit, Gradio, API OpenAI-compatível),
  túnel cloudflared → URL salva no Drive. O PC lê a URL e injeta no Airi.
- **Voz**: `scripts/servidor_voz_airi.js` na porta **9860** (edge/kokoro/sovits,
  com `/cerebro/v1` proxy para o túnel).
- **Interface**: stage-web (**5173**) no navegador e/ou stage-tamagotchi (Electron)
  no desktop.

### 8.2 Fluxo ao apertar "INICIAR WAIFU" (`_act_iniciar_waifu`)
1. Sobe automaticamente o servidor da engine escolhida (`_iniciar_engines_da_waifu`).
2. Opção 1 (web) → roda `scripts/atualizar_airi.ps1`.
   Opção 2 (tamagotchi) → roda `scripts/iniciar_tamagotchi.ps1` e, após 30s,
   `_auto_configurar_providers()` via CDP (porta **9222**).
   Opção 3 (ambos) → faz os dois.
3. `_auto_configurar_providers` conecta no CDP (`http://127.0.0.1:9222/json`),
   injeta `localStorage` e recarrega a página.

### 8.3 `scripts/atualizar_airi.ps1`
- Lê a URL do túnel do Drive (com cache local `ultima_url.txt`).
- Health-check no túnel (e detecta sessões antigas que causam OOM).
- Garante o stage-web rodando (`pnpm --filter @proj-airi/stage-web dev`).
- Abre `http://localhost:5173/agentai-boot.html?url=<tunel>/v1/&model=agentai&voice=<voz>&voiceBase=http://localhost:9860/v1`.
- **`agentai-boot.html` é um arquivo da Lia** (em `scripts/`) que NÃO existe no repo
  do AIRI — ele precisa ser copiado para `$AiriDir\apps\stage-web\public\`. O script
  detecta se está lá; senão, avisa e abre o app direto (config na mão).

> ⚠️ **Ponto frágil de migração:** `agentai-boot.html` é um arquivo externo ao AIRI.
> A cada atualização do AIRI, ele precisa ser recopiado para `apps/stage-web/public/`.
> Esse é um candidato a **automatizar** (ex.: o Lia copiar o boot para a pasta do
> AIRI automaticamente ao subir).

---

## 9. Mapa de arquivos-chave (para consulta rápida)

| Arquivo (no AIRI) | Por que importa |
| --- | --- |
| `apps/stage-web/src/App.vue` | Root da interface web |
| `packages/stage-ui/src/stores/providers/config.ts` | Store de providers (localStorage) |
| `packages/stage-ui/src/stores/modules/speech.ts` | Store de voz (g. `generateSpeech`) |
| `packages/stage-ui/src/stores/modules/consciousness.ts` | Store do cérebro (modelos) |
| `packages/stage-ui/src/libs/providers/providers/openai-audio/index.ts` | `openai-compatible-audio-speech` |
| `packages/stage-ui/src/libs/providers/providers/openai-compatible/index.ts` | `openai-compatible` (chat) |
| `packages/stage-ui/src/libs/providers/providers/registry.ts` | Registro de providers |
| `packages/stage-pages/src/pages/settings/modules/speech.vue` | UI de settings de voz |
| `packages/stage-pages/src/pages/settings/modules/consciousness.vue` | UI do cérebro |
| `packages/pipelines-audio/src/speech-pipeline.ts` | Pipeline de TTS |
| `apps/stage-tamagotchi/package.json` | Scripts/Electron do desktop |
| `apps/stage-web/package.json` + `vite.config.ts` | Dev do web + porta default 5173 |
| `.tool-versions` | Node 26.7.0 / pnpm 11.24.0 |
| `server/docker-compose.yaml` | Backend opcional (hosted) |

---

## 10. Verificações recomendadas ao migrar a Lia para a beta do AIRI

1. **Cérebro ativo**: garantir que `settings/consciousness/active-provider`
   (`openai-compatible`) e `active-model` (`agentai`) sejam setados na injeção; na
   beta o default é `''`. Adicionar à injeção da Lia se o Airi não auto-selecionar.
2. **`agentai-boot.html`**: automatizar a cópia para `apps/stage-web/public/` (ou
   referenciar um boot mais robusto).
3. **Electron/tamagotchi**: já tratado no `iniciar_tamagotchi.ps1` (install-electron).
   Confirmar que o caminho `apps/stage-tamagotchi/node_modules/electron` continua
   sendo o lokus do binário na beta.
4. **Node/pnpm**: usar `nodejs 26.7.0` + `pnpm 11.24.0` (`.tool-versions`), não a
   versão defasada da doc (24.13.0).
5. **Chaves de voz**: `settings/speech/*` e provider
   `openai-compatible-audio-speech` continuam válidos — nenhuma mudança necessária
   no ID do provider para a voz.
6. **Backend novo**: não é necessário para o uso local; ignorar o `server/` da Lia.
7. **Persona**: definir a "personalidade" da Lia (system prompt / agente) na UI do
   AIRI (Settings → Consciousness), pois `core-character` ainda é stub.

---

## 11. Integração ampliada — além de voz/cérebro

> Seção criada a partir de uma rodada de pesquisa adicional no `main` (beta).
> O AIRI é muito mais que providers de chat e TTS: tem **avatares (VRM/Live2D/Spine/MMD/Tachie/Godot)**,
> **módulos/skills** (visão, audição, web-search, arte, jogos, mensagens, MCP, beat-sync),
> um **sistema de personagens (Character Card v3)** e até um **medidor de desempenho**.
> Abaixo, o mapa concreto com as chaves de persistência, o storage usado (localStorage vs IndexedDB)
> e o modo de injeção pela Lia.

### 11.0 Regra de ouro: localStorage vs IndexedDB (define o que dá pra injetar por CDP)

| Persistência | Backend | O que guarda | Dá pra injetar por CDP/localStorage? |
| --- | --- | --- | --- |
| **localStorage** | `useLocalStorageManualReset` | providers, voz, cérebro, visão, discord, airi-cards | ✅ Sim (setItem direto) |
| **IndexedDB (unstorage)** | `indexedDbDriver({ base: 'airi-local' })` | `local:characters` (personagens/cards completos), display models (arquivos VRM/Live2D) | ⚠️ Sim, mas precisa escrever no esquema do unstorage (mais complexo) |
| **localStorage** | `useLocalStorage` | `settings/stage/model`, `airi-cards`, `settings/stage-ui-three/*` | ✅ Sim |

> **Conclusão prática:** providers/voz/cérebro/visão/cards ativos são **localStorage** →
> a injeção atual da Lia (por CDP) funciona. Modelos (VRM/Live2D como arquivo) e o
> catálogo de personagens (com prompts) são **IndexedDB** → injeção mais trabalhosa.

### 11.1 O modelo de LLM setado. — "o modelo que deixaremos setado no Lia"

O cérebro da Lia é plugado no provider `openai-compatible`. O modelo fica em:

| Chave (localStorage) | Valor (Lia) |
| --- | --- |
| `settings/consciousness/active-provider` | `openai-compatible` |
| `settings/consciousness/active-model` | `agentai` (nome do modelo no Colab) |
| `settings/consciousness/active-custom-model` | (custom, se precisar) |
| `settings/consciousness/reasoning` | `'true'`/`'false'` (modo raciocínio) |

- O boot page passa o modelo via query `&model=agentai`.
- **Atenção:** no `main` o default de `active-provider`/`active-model` é `''`. A Lia
  **precisa setar** esses dois (além dos providers) para o cérebro ficar de fato ativo.

### 11.2 Settings de voz — além de pitch/speed

O módulo de voz (store `packages/stage-ui/src/stores/modules/speech.ts` + página
`.../settings/modules/speech.vue`) expõe mais campos além de pitch/rate:

| Campo | Chave | O que faz |
| --- | --- | --- |
| **Provider** | `settings/speech/active-provider` | escolhe o motor TTS |
| **Model** | `settings/speech/active-model` | escolhe o modelo TTS (ex.: `edge-tts`) |
| **Voz** | `settings/speech/voice` | voz ativa (`VoiceInfo`) — com preview |
| **Pitch** | `settings/speech/pitch` | tom |
| **Rate** | `settings/speech/rate` | velocidade |
| **SSML** | `settings/speech/ssml-enabled` | liga texto-SSML cru (p/ providers que suportam) |
| **Streaming** | (provider oficial streaming) | TTS de baixa latência (opcional) |

- A UI tem `FieldRange` (sliders), `FieldCheckbox`, `FieldInput`, e um seletor de vozes
  com **preview** (`VoiceCardManySelect`), busca de modelo e seletor de provider.
- **Limite real por engine (Lia):** o que além de pitch/rate funciona depende do motor:
  - **Edge** = pitch + rate (msedge-tts online).
  - **Kokoro** = speed (via `kokoro:` prefix) — pitch não é suportado nativamente.
  - **SoVITS** = usa áudio de referência + modelo clonado (não usa pitch/rate no mesmo
    sentido; é outra infraestrutura).
- Para o provider `openai-compatible-audio-speech`, o **modelo** e o **prefixo do voice**
  (`edge:`/`kokoro:`/`sovits:`) continuam sendo o mecanismo da Lia de trocar de motor.

### 11.3 Start por engine — Edge | Kokoro | SoVITS

O start **é diferente** e a Lia já reflete isso:

| Engine | Início | Infra | Latência |
| --- | --- | --- | --- |
| **Edge** | entra direto no `servidor_voz_airi.js` (msedge-tts) | online (Microsoft) | baixa |
| **Kokoro** | precisa de **modelo + venv** (`kokoro-data/`); primeiro pedido sobe um **worker Python persistente** e carrega o ONNX na RAM (~1x) | offline | 1º request alto, depois baixo |
| **SoVITS** | precisa de um **servidor SoVITS separado** (botão "Instalar/Rodar" no painel) ou do **túnel do Colab**; usa modelo de clone + áudio de referência | local ou Colab/túnel | alta |

- `servidor_voz_airi.js` (v3.6) gerencia **Edge + Kokoro** internamente e **proxy** o
  SoVITS para outro servidor/túnel. O SoVITS tem painel próprio na Lia (janela separada).

### 11.4 Painel de personalidade da Lia (painel intuitivo)

O AIRI tem um **sistema de personagens** real (não é stub como `core-character`):

- **Formato:** **Character Card v3** (`packages/ccc/src/codec/characterCardV3.ts`) —
  os mesmos card de `silver/char.ai` (name, description, personality, system_prompt,
  first_mes, scenario, character_book/lorebook, etc.).
- **Tipos** (`packages/stage-ui/src/types/character.ts`):
  - `prompts`: `[{ type: 'system'|'personality'|'greetings', content, language }]` ← **a personalidade**
  - `avatarModels`: `[{ name, type: 'vrm'|'live2d'|'spine', config: { vrm:{urls[]}, live2d:{urls[]} } }]`
  - `capabilities`: `[{ type:'llm'|'tts'|'vlm'|'asr', config: { apiKey, apiBaseUrl, model, temperature, voiceId, speed, pitch, ssml } }]`
- **Persistência do catálogo:** `local:characters` em **IndexedDB** (unstorage, montado em `airi-local`).
- **Card ativo (o que liga personalidade↔modelo↔voz):** store `airi-card`:
  - `airi-cards` (Map de `AiriCard`) e `airi-card-active-id` (default `'default'`) — **localStorage**.
  - O `AiriCard` agrega os **modules**: `consciousness.model`, `speech.model`/`voice_id`,
    `vision.model`, `artistry.model`, `displayModelId`, etc.
  - `updateActiveCardDisplayModel(displayModelId)` / `updateActiveCardSpeech(provider|model|voice_id)`.

> **Caminho para o painel de personalidade da Lia:** o Lia App edita o conteúdo de um
> Character Card v3 (nome, tagline, system_prompt, personality, greetings, tags, lorebook)
> e o injeta como card ativo (`airi-cards` + `airi-card-active-id` em localStorage), com o
> `speech` e o `consciousness` apontando para os providers da Lia. O `local:characters`
> (IndexedDB) é o registro completo; dá para injetar via IndexedDB no CDP.
> (Desejável: o painel da Lia mostrar os mesmos campos de um Character Card v3.)

### 11.5 Mecânicas/skills do AIRI (ativáveis)

O grid de módulos (Settings → Modules) lista: **consciousness, speech, hearing, vision,
web-search, artistry, memory-short-term, memory-long-term, messaging-discord, x,
gaming-minecraft, gaming-factorio, mcp-server, beat-sync**. Cada um tem sua própria
página e store; o `configured` indica se está pronto.

| Módulo | Rota | Chave principal | Como funciona / observação |
| --- | --- | --- | --- |
| **Visão** ("ver a tela") | `/settings/modules/vision` | `settings/vision/active-provider`/`active-model`/`active-custom-model`, `settings/vision/ollama-thinking-enabled` | usa um **VLM** (via `openai-compatible` p/ visão); no **desktop/tamagotchi** há **captura de tela** (`use-vision-screen-capture` + `electron-screen-capture`) |
| **Discord** | `/settings/modules/messaging-discord` | `settings/discord/enabled`, `settings/discord/token` | bot (integração `integrations/discord-bot`) |
| **Minecraft** | `/settings/modules/gaming-minecraft` | via `@proj-airi/server-sdk` (channel server/WebSocket) | precisa rodar o bot mineflayer (`integrations/minecraft`) e conectar a um servidor MC |
| **Factorio** | `/settings/modules/gaming-factorio` | store `gaming-factorio` | servidor separado |
| **X (Twitter)** | `/settings/modules/x` | store `twitter` | integração |
| **Web-search** | `/settings/modules/web-search` | store `web-search` | busca na web |
| **Hearing** | `/settings/modules/hearing` | store `hearing` | mic/ASR + transcrição |
| **Artistry** | `/settings/modules/artistry` | store `artistry` | widget/imagens geradas |
| **MCP** | `/settings/modules/mcp` | MCP servers | ferramentas externas via MCP |
| **Beat-sync** | `/settings/modules/beat-sync` | `settings/stage-ui-three/...` (rig de músicas) | dança/reações a música |
| **Memória** | `memory-short-term` / `memory-long-term` | — | curto termo ativo; **longo termo ainda é `<WIP />`** |

> Para a Lia ativar "Jogar Minecraft / Discord / ver a tela", o Lia App só **liga o flag
> do módulo e aponta a configuração**; a infraestrutura (bot mineflayer, token do Discord,
> captura de tela do Electron) precisa estar rodando/habilitada.

### 11.6 Medidor de desempenho

O AIRI **já tem um overlay de performance** (DevTools):
- `apps/stage-web/src/components/Devtools/PerformanceOverlay.vue` + store `stores/devtools-lag`.
- Métricas: **FPS, frame duration, long task, memória** (buffer/histograma, média/p95,
  gravação 60s, export CSV). É arrastável e fixa no canto.

> Para a Lia, dá para **reusar/ativar** esse overlay (ou reimplementar um medidor
> pequeno no Lia App) e mostrar FPS/uso de memória junto com as mecânicas ativas.
> Além disso há `renderScale` e `multisampling` (`settings/stage-ui-three/...`) que são
> ajustes de qualidade/performance.

### 11.7 Fluxo VRM: Vroid → Lia → AIRI (e Live2D só como injeção)

#### Como o AIRI trabalha com avatares
- Renders suportados (stage-model): `live2d`, `vrm`, `spine`, `tachie`, `mmd`, `godot` (e `disabled`).
- O **modelo ativo** é um **display model** (`DisplayModel`), que pode ser `type:'file'` (importado) ou `type:'url'` (preset).
- **Seleção/persistência:**
  - `settings/stage/model` = **id do display model** (default `preset-live2d-1`).
  - Renderer é inferido do formato (`vrm` → renderer `vrm`, etc.).
  - Pose/viewport em `settings/stage-ui-three/*`: `modelOffset`, `modelRotationY`, `cameraFOV`,
    `cameraDistance`, `trackingMode` (`camera`/`mouse`/`none`), luzes, `renderScale`, `multisampling`.
- **Importação de um `.vrm`:** pela UI (Settings → Model → botão **VRM**) → `useFileDialog({accept:'.vrm'})`
  → `addDisplayModel(DisplayModelFormat.VRM, file)` → **IndexedDB** (localforage, chave `display-model-<nanoid>`)
  e gera um thumbnail. Depois `handleModelPick` seta `settings/stage/model` e `updateActiveCardDisplayModel`.
- **Presets embutidos:** `AvatarSample_A/B.vrm`, `Hiyori` (Live2D).

#### Opções para o fluxo "Vroid → VRM → Lia → AIRI"

| Abordagem | Como | Durabilidade | Comentário |
| --- | --- | --- | --- |
| **A. Importação via UI (1x, manual)** | Usuário abre Settings→Model→VRM e seleciona o `.vrm` exportado do Vroid | ✅ persistente (IndexedDB) | Simples, mas manual a cada troca de VRM |
| **B. Injeção via CDP (arquivo → IndexedDB)** | Lia lê o `.vrm`, injeta os bytes no IndexedDB do Airi e seta `settings/stage/model` | ✅ persistente | Mais robusto, porém precisa mapear o esquema do unstorage (`airi-local`) |
| **C. Modelo por URL (protótipo/Live2D)** | Adicionar um display model `type:'url'` apontando para `http://localhost:9860/static/lia.vrm` (Lia serve o arquivo com CORS) e setar `settings/stage/model` | ⚠️ só em memória (Airi não persiste URL models) | Bom p/ Live2D por injeção no start (que é o caso "não usar por ora") |

> **Recomendação inicial:** usar **A (importar o VRM do Vroid 1x na UI)** para o VRM
> definitivo, já que é durável e simples. O **C** serve bem para o caso de **Live2D por
> injeção no start** (modificar o Model no boot) — a Lia injeta um display model URL +
> `settings/stage/model`, sem precisar de arquivo no IndexedDB. O **B** é o objetivo a
> médio prazo (automatizar 100%).
>
> O renderer/preview já funciona para Live2D e VRM no `stage-ui-three`; o fluxo
> "Vroid !=> VRM" é só gerar o `.vrm` no Vroid (export) e entregar ao AIRI.

### 11.8 Observações de migração (novas, desta rodada)

1. **Card ativo / personalidade:** para injetar a personalidade da Lia, usar o card ativo
   (`airi-cards` + `airi-card-active-id` em localStorage) e, se necessário, o catálogo
   `local:characters` (IndexedDB).
2. **Cérebro/visão ativos:** preencher `settings/consciousness/*` E `settings/vision/*`
   (provider+model), senão ficam desativados na beta.
3. **Captura de tela ("ver a tela")** só funciona no **desktop/Electron** (electron-screen-capture);
   na web exigiria `getDisplayMedia` (permissão do navegador).
4. **Minecraft/Discord/Factorio/X** são integrações separadas (pastas `integrations/*`) —
   precisam rodar como serviços, não são "só config".
5. **Persona não é stub:** `core-character` é stub, mas o sistema de **Character Card v3**
   é o caminho correto (não confundir).
