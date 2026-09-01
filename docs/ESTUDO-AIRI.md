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
