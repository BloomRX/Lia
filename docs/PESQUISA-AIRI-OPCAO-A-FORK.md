# Pesquisa — AIRI: Opção A (roupa viva) + Fork/Interatividade

> Rodada de pesquisa (data 01/09/2026). Objetivo: (1) validar tecnicamente a
> **Opção A** (trocar roupa/acessório/cabelo sem recarregar o VRM, com animação)
> — "ver se roda bem sem bug"; e (2) mapear o caso do vídeo do usuário: **pedir ao
> Claude Code para forkar o AIRI e adicionar mais interatividade**.

---

## PARTE 1 — Opção A: roupa/acessório/cabelo vivos

### 1.1 O que o AIRI expõe hoje (confirmado no código)
- Renderer VRM em `packages/stage-ui-three/` (`VRMModel.vue`, `composables/vrm/*`).
  Usa **`@pixiv/three-vrm`** + **`three-vrm-animation`**.
- Já há, em runtime:
  - `vrm.scene` (Object3D) → dá pra `scene.add`/`remove`.
  - `vrm.humanoid` → **bones** (`head`, `spine`, `chest`, `leftHand`...).
  - `vrm.expressionManager` → expressões (usado no `useVRMEmote`).
  - `createVRMAnimationClip` + mixer → animações VRMA (`idle_loop.vrma`).
- **NÃO existe** sistema de outfit/wardrobe/acessório nativo (busca no tree: nada).
- **NÃO existe** "spawn object na cena" / scene manipulation ainda (é **TODO** no
  roadmap v0.8+: "Pre-defined object models callout (place in scene)").

### 1.2 Como se faz "anexar roupa/acessório" a um bone no three.js (base técnica)
A técnica é **suportada** e madura no three.js:

- **Acessório rígido (óculos, chapéu, armas):** basta
  `bone.add(mesh)` (ex.: `vrm.humanoid.getNormalizedBoneNode('head').add(glasses)`).
  O acessório passa a seguir o bone automaticamente. Simples e sem bug conhecido.
- **Roupa que deforma (skinned):** o mesh de roupa é um `SkinnedMesh` que **tem
  a própria armature**. Para anexar à armature do corpo, fazer **skeleton swap**:
  `outfitMesh.skeleton = bodyMesh.skeleton` (ou `vrm.scene` armature). É o mesmo
  princípio do **VRCFury "Armature Link"** / **"SkinRewrite"** / **"Apply Accessories"**
  do mundo VRChat — que é exatamente o caso de uso "vestir/despir em runtime".

### 1.3 O trade-off crítico: o VRM do Vroid é um UNIQUE mesh
- O VRoid Studio exporta **corpo+roupa+cabelo+acessórios num só VRM** (um conjunto de
  meshes já skinned ao mesmo skeleton, mas **tudo junto**).
- Para a Opção A (trocar partes individualmente) a base precisa ter **partes separadas**:
  - **Corpo base** (nu, sem cabelo/acessório) como VRM principal.
  - **Cada look/item** como mesh independente (pode ser um VRM de acessório, um GLB,
    ou um sub-mesh nomeado) **com o mesmo esqueleto/bones** do corpo.
- Isso é a **parte "artística"/pipeline** (Blender/Unity) — não é um bug do AIRI.

### 1.4 Licença / guideline do VRoid (IMPORTANTE — não ignorar)
- O maintainer do three-vrm (ke456-png) na discussão [#1220](https://github.com/pixiv/three-vrm/discussions/1220)
  apontou que o **VRoid Studio tem guideline**: não usar VRoid Studio para criar
  aplicação que **deforme meshes** e/ou crie modelos 3D **combinando meshes/texturas**.
- **Porém** ele considerou **aceitável** um módulo JavaScript que apenas **troca outfits
  entre VRMs existentes** (não deforma nem cria avatar). Ou seja: o caso da Opção A se
  enquadra como aceitável **desde que** a gente não distribua o VRoid como "ferramenta de
  criação de modelo", e sim como o AIRI já faz (trocar/combinar modelos prontos).

### 1.5 Riscos/bugs esperados na Opção A (o que "ver se roda sem bug" revela)
| Risco | Por quê | Mitigação |
| --- | --- | --- |
| **Skeleton swap dá mismatch de bones** | A roupa precisa ter bones com os MESMOS nomes do corpo; senão deforma errado | Preparar roupa com o mesmo rig; validar nomes (`getObjectsByProperty`) |
| **"Double up" de bones** | Se usar reparent manual, o mesh de roupa cria ossos duplicados | Preferir **SkinRewrite** (reaproveita a armature do corpo) em vez de reparent bone a bone |
| **Física de roupa (spring bone) some** | A física VRM não é transferida ao anexar mesh extra | Anexar o mesh e re-aplicar os springbones do item (ou aceitar sem física) |
| **Troca pop** (sem transição) | `visible=true/false` é abrupto | Usar animação/crossfade (Opção A) ou fade MToon (Opção B) |
| **Anchoring perde offset** | `bone.add()` preserva transform local; se o mesh de acessório tiver origem errada, "salta" | Setar transform do item no bone no Blender/Unity (origem 0,0,0) ou corrigir o offset ao anexar |
| **Memória/latência** | Carregar vários VRMs de look carrega meshes pesados | Carregar itens uma vez e manter em cache; ou usar GLB menores |

### 1.6 Conclusão pragmática ("roda bem?")
- **Sim, a parte de anexar a bone é robusta** (three.js + three-vrm suportam).
- **O esforço real está no pipeline de assets** (separar corpo/item no Vroid/Blender/Unity)
  e **na integração dentro do AIRI** (que precisa de um fork/patch no `stage-ui-three` com
  um "wardrobe" store + componente de anexo + animação de vestir).
- O AIRI **não oferece API** para isso ainda → ou **fork**, ou **plugin** (se o plugin SDK
  expuser a cena; hoje a cena three-vrm não é plugável). Provável **fork** no `stage-ui-three`.

---

## PARTE 2 — Fork com Claude Code para "adicionar interatividade" (o vídeo)

### 2.1 O que o AIRI já tem de "interatividade via Claude Code"
- **`plugins/airi-plugin-claude-code`** (v0.12.0-beta.5) — package
  `@proj-airi/airi-plugin-claude-code`, que depende de `@anthropic-ai/claude-code`.
- Função (lida do `src/cli.ts`): intercepta o hook do Claude Code
  **`UserPromptSubmit`** e, via `@proj-airi/server-sdk` (`Client` com nome
  `proj-airi:plugin-claude-code`), envia ao **Channel Server** do AIRI:
  `channelServer.send({ type: 'input:text', data: { text: hookEvent.prompt } })`.
- **Tradução:** quando você digita um prompt no Claude Code, ele **vira uma "fala"/input
  da waifu** no AIRI. É uma "interatividade" de **input** (não de cena).
- Instalação/uso: `pnpm -F @proj-airi/airi-plugin-claude-code dev` e configurar o hook
  do Claude Code (`airi-plugin-claude-code-cli send`). É um **CLI** que lê o evento do
  hook pelo **stdin** (por isso o nome "send").

### 2.2 Rotas para "adicionar interatividade" (além de voice/chat)
| Caminho | O que dá | Esforço | Observação |
| --- | --- | --- | --- |
| **Fork repo + patch** | Mudar o mínimo necessário p/ suas features (ex.: Opção A no `stage-ui-three`) | alto (mantém fork) | É o que o cara do vídeo fez (usou Claude Code p/ editar o código) |
| **Plugin (SDK)** | Adicionar tools/widgets/providers **sem forkar tudo** | médio | O plugin SDK tem Kits API / Tools API / Gamelet API / Widget UI. Ideal p/ coisas "de borda" (homeassistant, web-extension, chess) |
| **Input externo** | Conectar uma fonte de input (Claude Code, Discord, game, etc.) | baixo | `airi-plugin-*` + server-sdk / Channel Server |
| **Fork + plugin** | Forkar só o que não dá por plugin + plugin p/ o resto | médio-alto | Estratégia equilibrada (recomendada p/ a Lia) |

### 2.3 Referências do ecossistema de plugins (branch `main`)
- Plugins oficiais na pasta `plugins/`:
  - `airi-plugin-claude-code` (input → Channel Server)
  - `airi-plugin-homeassistant`
  - `airi-plugin-web-extension`
  - `airi-plugin-bilibili-laplace`
  - `airi-plugin-game-chess` (usa **Gamelet API** — widget interativo)
- SDK: `packages/plugin-sdk` (Kits API, Tools API, Gamelet API, Widget UI,
  `plugin.airi.json` manifest) e `packages/plugin-sdk-tamagotchi`.
- O roadmap v0.8 traz "Scene manipulation" (colocar objetos na cena) ainda **não feito**
  → é o que proporcionaria anexar itens ao avatar via tool, sem fork.

### 2.4 Sugestão de estratégia p/ Lia (para anotar, não implementar)
- **No curto prazo:** usar o **plugin** (`server-sdk` / Channel Server) para conectar a
  Lia a um input (ex.: a Lia "ouve" o que você digita no Claude Code ou comandos de voz).
- **No médio prazo (Opção A):** **fork controlado** do AIRI, restrito ao `stage-ui-three`
  (adicionar um store "wardrobe" + componente de anexo de itens + animação de vestir),
  alimentado por uma tool/plugin. **Não** forkar o monorepo inteiro.
- **Ferramenta de apoio:** usar **Claude Code** (como o vídeo) como assistente de edição
  do fork — é exatamente o caso do `airi-plugin-claude-code`.

---

### Fontes consultadas
- tree do repo `moeru-ai/airi` (`git/trees/main?recursive=1`) — localizado
  `plugins/airi-plugin-claude-code`, tool system (`stage-ui/src/tools/*`), trilhas de plugins.
- `packages/plugin-sdk`, `packages/plugin-sdk-tamagotchi`, `plugins/airi-plugin-*`.
- Discussão three-vrm [#1220](https://github.com/pixiv/three-vrm/discussions/1220)
  (trocar outfits entre VRMs; guideline do VRoid Studio aceita módulo que só troca outfits).
- SO/Reddit: anexar mesh a bone (`bone.add`), skeleton swap para roupa skinned,
  VRCFury Armature Link / SkinRewrite, Apply Accessories.
- Roadmap v0.8 (issue #312): "Scene manipulation / Pre-defined object models callout"
  ainda não implementado.
- Issue #255 (Plugin system) e #520 (estrutura/state/client) — contexto do plugin system.
