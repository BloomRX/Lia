# Backlog / Ideias — Lia

> Documento de anotação rápida das ideias que o usuário vai trazendo.
> **NÃO implementar aqui** — apenas registrar o desejo e a viabilidade técnica,
> para depois detalhar/priorizar. A última item é a fonte para o próximo passo.

---

## 🎨 Troca natural de roupas, acessórios e cabelo (sem recarregar o modelo)

**Status:** 💡 ideia em estudo — **não implementar ainda**.

### O desejo (nas palavras do usuário)
- A Lia poder **trocar de roupa/acessórios** por comando, ou **por livre e espontânea vontade**.
- Ele sabe que "trocar `Modelo1.vrm` → `Modelo2.vrm`" **recarregaria** o modelo (o AIRI hoje
  troca via `settings/stage/model` — isso recarrega). Ele **não quer** isso.
- Quer algo **natural**: "ela fazendo uma animação de colocar óculos, roupa, etc." **sem sumir**.
- Conceito: **corpo base** sem roupa + sem cabelo (no start a Lia injeta a roupa 1 antes de
  aparecer). Ao dar o comando, ela veste/desveste no lugar, sem desmontar o avatar.
- **Cabelo** também poder trocar de corte.

### Resposta de viabilidade (técnica) — ✅ SIM, dá, mas não vem pronto

O AIRI carrega o VRM com **`@pixiv/three-vrm`** e tem **`three-vrm-animation`**:
`packages/stage-ui-three/src/composables/vrm/{loader,core,animation,expression,lip-sync,interaction}.ts`
e o `VRMModel.vue`. Isso dá acesso, em runtime, a:
- `vrm.scene` (Object3D) → dá pra **adicionar/remover itens** (`scene.add` / `remove`).
- `vrm.humanoid` → **bones** (`head`, `spine`, `chest`, `hands`) pra **ancorar** roupa/óculos/cabelo.
- `vrm.expressionManager` → expressões faciais (já usado no `useVRMEmote`).
- `createVRMAnimationClip` + mixer → **animações VRMA** (já há `idle_loop.vrma`).

**PORÉM** (limitações reais):
1. **O AIRI não tem** nenhum sistema de "outfit/wardrobe/acessório". Nada nativo.
2. O `.vrm` exportado do **Vroid** (padrão) vem como **um único mesh** (roupa+cabelo+acessórios
   na mesma malha/textura). Pra esse "trocar vivo", o **modelo precisa ser preparado com
   partes separadas** (ou modelos de acessório independentes).

### Abordagens possíveis (da mais "natural" para a mais simples)

| # | Abordagem | Natural? | Esforço | Comentário |
| --- | --- | --- | --- | --- |
| **A** | **Corpo base + "itens" anexados aos bones** (roupa/cabelo/óculos como meshes extras) + **animação de vestir/desvestir** (tween do item de fora → ponto do corpo) | ⭐⭐⭐⭐ | alto | A mais fiel. Cada item entra/sai com a própria animação. É o que ele descreve. |
| **B** | Mesmos itens anexados aos bones, mas **mostrar/ocultar** (`node.visible`) com um **FX de fade/crossfade** (opacity MToon) | ⭐⭐⭐ | médio | "Pop" em vez de animação completa de vestir. Mais simples e robusto. |
| **C** | Trocar o **VRM inteiro** mascarando o reload com uma **transição** (ex.: fade/efeito de "vestir") | ⭐⭐ | baixo | Ainda recarrega; menos natural. Só se A/B não derem. |

> **Recomendação do desenho:** mirar no **A** como objetivo, com **B** como plano B de
> menor risco (entregar "troca sem soma" primeiro e depois enriquecer a animação).

### Pré-requisitos / decisões a tomar (quando for implementar)
1. **Preparar o modelo da Lia** com partes separadas:
   - Corpo base (nu, sem cabelo), e cada "look" como **mesh separado** (ou VRM de acessório).
   - Pode ser feito no **Vroid** (exportar variações) ou no **Unity/Blender** e retirar os meshes.
2. **Definir o formato dos itens:** cada item = um arquivo (VRM/GLB) próprio OU sub-mesh
   referenciado por nome. Melhor `GLB`/mesh anexado a bone (mais leve que carregar um VRM inteiro por item).
3. **Mecanismo de acionamento:** comando de voz / texto (o AIRI já tem "tools"/skills —
   um skill "vestir/despir" chamaria a troca) e/ou comportamento "de livre vontade"
   (a Lia decide trocar sozinha a partir do context/user request — via system prompt/tool).
4. **Integração com o AIRI:** como o AIRI não tem isso, a via natural é um **cenário/plugin**
   (o AIRI tem SDK de plugin/cenário) ou um **patch interno** no `stage-ui-three`
   (adicionar um "wardrobe" store + componente de anexo de itens + animação de vestir).
5. **Nuance "livre e espontânea vontade":** a escolha de trocar sozinha é **comportamental**
   (LLM/tool), enquanto a troca em si é **a animação/vestido** (three-vrm). São duas camadas;
   a de decisão fica no cérebro (Colab→Airi), a de execução no avatar.

### Onde isso se encaixa no AIRI (referência rápida)
- Renderer 3D/avatar: `packages/stage-ui-three/src/` (`VRMModel.vue`, `composables/vrm/*`).
- Suporte a plugins/cenários (para anexar o "wardrobe" sem forkar tudo):
  `packages/plugin-sdk*`, `apps/stage-tamagotchi/src/main/services/airi/plugins/*`.
- Troca de modelo (recarrega): `settings/stage/model` (`packages/stage-ui/src/stores/settings/stage-model.ts`).

### 🔬 Aprofundamento da Opção A (rodada de pesquisa)

> Ver detalhes em [`PESQUISA-AIRI-OPCAO-A-FORK.md`](PESQUISA-AIRI-OPCAO-A-FORK.md).

**Como funciona tecnicamente (base do three.js).** "Anexar a bone" é recurso maduro:

- **Acessório rígido** (óculos, chapéu): `bone.add(mesh)` — ex.:
  `vrm.humanoid.getNormalizedBoneNode('head').add(glasses)`. Passa a seguir o bone
  automaticamente. Simples, sem bug conhecido.
- **Roupa deformável (skinned):** a roupa é um `SkinnedMesh` com a própria armature.
  Para usar a armature do corpo → **skeleton swap**: `outfitMesh.skeleton = bodyMesh.skeleton`.
  É o mesmo princípio do **VRCFury "Armature Link"** / **"SkinRewrite"** do mundo VRChat
  ("vestir/despir em runtime").

**O trade-off crítico (por que não vem pronto).** O **VRoid exporta corpo+roupa+cabelo
num único VRM** (meshes juntos no mesmo skeleton). Para a Opção A, a base precisa de
**partes separadas**:
- **Corpo base** (nu, sem cabelo/acessório) como VRM principal.
- **Cada look/item** como mesh independente (VRM de acessório / GLB / sub-mesh nomeado)
  **com os mesmos bones do corpo**.

**Bugs/riscos que "ver se roda bem" vai revelar** (resumido; tabela completa no doc):

| Risco | Mitigação |
| --- | --- |
| Skeleton swap mismatch de bones | Preparar roupa com o MESMO rig/nome de bones |
| "Double up" de bones (bone a bone) | Preferir **SkinRewrite** (reusa armature do corpo) |
| Física/spring bone da roupa some | Re-aplicar springbone do item ou aceitar sem física |
| Troca "pop" sem transição | Crossfade/fade MToon (Opção B) ou animação de vestir (Opção A) |
| Acessório "salta" (origem errada) | Setar origem 0,0,0 no Blender/Unity e corrigir offset ao anexar |
| Memória/latência (vários VRMs de look) | Cachear itens; usar GLB menores |

**Conclusão prática.** A parte de "anexar a bone" é **robusta** (three.js + three-vrm).
O esforço real está (1) no **pipeline de assets** (separar corpo/item no Vroid/Blender/Unity)
e (2) na **integração no AIRI**, que **não tem API** para isso → provável **fork/patch**
no `stage-ui-three` (store "wardrobe" + componente de anexo + animação de vestir), ou
plugin se o SDK expuser a cena (hoje a cena three-vrm não é plugável).

**Licença do VRoid (não ignorar).** O maintainer do three-vrm [#1220] indicou que o VRoid
Studio tem guideline que **proíbe** usar VRoid para criar app que **deforme meshes** e/ou
**crie modelos combinando meshes**. Porém considerou **aceitável** um módulo JS que apenas
**troca outfits entre VRMs existentes** (como o AIRI faz). → A Opção A se enquadra como
aceitável, desde que não distribua o Vroid como "ferramenta de criação de modelo".

---

## 🤖 Adicionar interatividade ao AIRI (via fork/Claude Code — o vídeo)

**Status:** 💡 em estudo — **não implementar ainda** (anotação da pesquisa).

### O que o AIRI já tem (confirmado no código)
- **`plugins/airi-plugin-claude-code`** (v0.12.0-beta.5). Fluxo: no hook
  **`UserPromptSubmit`** do Claude Code, conecta ao **Channel Server** do AIRI
  (`@proj-airi/server-sdk`) e envia `{ type: 'input:text', data: { text: prompt } }`.
  → **O que você digita no Claude Code vira "fala"/input da waifu** no AIRI.
- SDK de plugin: Kits API / **Tools API** / **Gamelet API** / Widget UI / manifest
  `plugin.airi.json`. Plugins oficiais: claude-code, homeassistant, web-extension,
  bilibili-laplace, game-chess.

### Rotas para "adicionar mais interatividade"
| Caminho | O que dá | Esforço | Obs. |
| --- | --- | --- | --- |
| **Fork + patch** | Mudar o que precisar (ex.: Opção A no `stage-ui-three`) | alto (mantém fork) | foi o do vídeo (Claude Code editando) |
| **Plugin SDK** | Tools/widgets/providers sem forkar tudo | médio | ideal p/ coisas de borda |
| **Input externo** | Conectar fonte de input (Claude Code/Discord/game) | baixo | `server-sdk` / Channel Server |
| **Fork + plugin** | Forkar só o que não dá por plugin | médio-alto | **recomendado p/ a Lia** |

### 📋 Papel do Claude Code no projeto (como no vídeo)
- **Assistente de edição do fork:** usar Claude Code para editar o código do AIRI
  (o `airi-plugin-claude-code` é a ponte; aqui na Arena eu já atuo como agente de código).
- Ideia: manter um **fork enxuto** da Lia (só o `stage-ui-three` + plugin), não o monorepo
  inteiro, e usar Claude Code para o dia a dia do fork.

---

*Obs.: esta seção é só anotação. Quando o usuário trouxer mais ideias, acrescentar abaixo e manter o status.*