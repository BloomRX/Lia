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

---

*Obs.: esta seção é só anotação. Quando o usuário trouxer mais ideias, acrescentar abaixo e manter o status.*