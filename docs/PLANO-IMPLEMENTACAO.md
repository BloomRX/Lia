# Plano de Implementação — Lia

> **Objetivo:** implementar, de forma limpa e depurável, todas as features discutidas:
> integração AIRI, voz (3 engines), personalidade, VRM/Live2D, mecânicas extras (visão/
> discord/minecraft/etc.), medidor de desempenho e a **Opção A** (roupa/acessório/cabelo vivos).
> **Restrição forte:** **manter tudo gratuito** (sem serviços pagos; Claude Code é pago → NÃO usar).
> **Requisito transversal:** código limpo (sem monólito) e **meios de depurar** o processo.

---

## 0. Princípios inegociáveis

1. **Grátis de ponta a ponta.** AIRI é open-source e self-hosted. A voz é local
   (edge online grátis, kokoro offline, SoVITS local/Colab grátis). A "mente" é o Colab grátis.
   **Nada de Claude Code pago** para o produto. O trabalho de desenvolvimento aqui é feito por
   mim (agente) na Arena — você não paga por isso.
2. **Fonte de verdade = arquivos.** Toda config que a Lia injeta é **localStorage/CDP**
   (chaves `settings/...`). Manter os valores num arquivo `voz_config.json`/config e espelhar.
3. **Um módulo, uma responsabilidade.** Separar UI de lógica de negócio; separar AIRI, voz,
   soVITS, diagnóstico. Fim do monólito.
4. **Depurável por padrão.** Logs por categoria, dump de config, health-check de cada serviço,
   modo debug que captura tudo (inclusive o que o AIRI recebeu/retornou).
5. **Nunca quebrar o que funciona.** Refatorar por etapas com a app sempre rodando; cada fase
   termina com uma versão estável testável.

---

## 1. O que já existe (estado atual)

- `app/lia_app.py` — **monólito (3363 linhas)**. Classe `LiaApp(ctk.CTk)` de ~3000 linhas
  com: UI (drawers/voice/sovits/model selector/console), lógica de voz (liga/para/testa),
  soVITS (instalar/treinar/importar), AIRI (injeção CDP/localStorage, diagnóstico), gating
  (não inicializar quando treinando, etc.).
- `scripts/servidor_voz_airi.js` — TTS (edge/kokoro offline/sovits proxy) + `/cerebro/v1` proxy.
- `scripts/iniciar_tamagotchi.ps1`, `scripts/configurar_tamagotchi.ps1`, `scripts/atualizar_airi.ps1`,
  `scripts/agentai-boot.html`.
- AIRI clonado em `dest/airi` (via `app/installer.py`), `pnpm`.

**Problema central:** tudo numa função/arquivo só → difícil manter/debugar/estender.

---

## 2. Arquitetura alvo (refatoração limpa)

Dividir `lia_app.py` em **pacote `lia/`** com módulos de responsabilidade única. O entry point
`lia_app.py` vira um `main` fino; a `LiaApp` vira **orquestrador** que compõe os serviços.

```
app/
  lia_app.py                  <- entry point fino (só cria LiaApp e roda)
  lia/
    __init__.py
    config.py                 <- lê/grava config (voz_config.json, prefs, palette, idioma)
    paths.py                  <- caminhos (ROOT, SCRIPTS, sovits-data, kokoro-data, airi)
    log.py                    <- logger estruturado por categoria (voz|sovits|airi|console|sistema)
    debug.py                  <- modo debug (dump config, captura logs, exportar diagnóstico zip)
    app/
      windows.py              <- janela/identidade (borderless, icon, AppUserModelID, 3 tamanhos)
      ui.py                   <- composição da UI (header, rail, cards, drawers, console)
      drawers.py              <- drawers (voice/options/model/console) + hover/toggle
      language.py             <- i18n PT-BR/EN + girias (girias intactas)
    voz/
      engine.py               <- seleção de engine (edge|kokoro|sovits), config, instrumento
      servidor.py             <- start/stop do servidor_voz_airi.js (porta 9860)
      kokoro.py               <- instalar/status Kokoro (venv + onnx)
      sovits.py               <- servidor soVITS, treino, import/delete modelo, avatar
    airi/
      install.py              <- garante AIRI + pnpm (move do app/installer.py aqui)
      injeção.py               <- CDP/localStorage (providers, speech, consciousness, vision, modelo)
      boot.py                 <- atualiza e copia agentai-boot.html + abre URL
      tamagotchi.py           <- inicia stage-tamagotchi + injeta config
      diagnóstico.py          <- health-checks de airi/voz/subsistemas
    waifu/
      orquestrador.py         <- _iniciar_engines_da_waifu, gating, sequência de start/stop
      medidor.py              <- medidor de desempenho (FPS/mem/CPU, liga/desliga)
    persona/
      card.py                 <- Character Card v3 (nome, system_prompt, personality, greetings, tags)
      painel.py               <- UI do painel de personalidade no Lia
    modelo/
      vrm.py                  <- selecionar/importar .vrm, injetar no AIRI, Live2D por URL no start
      wardrobe.py             <- (Opção A) anexar roupa/acessório/cabelo + animação de vestir
    mecânicas/
      catalogo.py             <- lista de módulos AIRI (visão, discord, minecraft, x, web-search, ...)
      toggles.py              <- liga/desliga e aponta config de cada mecânica
  assets/ (icon, bg, modelos)
```

> **Regra de clean code:** `LiaApp` não sabe mais *como* iniciar o soVITS ou injetar no AIRI;
> ele chama `voz.sovits.start(...)` e `airi.injecao.configure(...)`. Cada módulo expõe
> funções pequenas e testáveis. Nada de classes de 3000 linhas.

### 2.1 Estratégia de refatoração segura (não quebrar nada)
1. **Extrair, não reescrever.** Mover funções existentes para módulos *sem mudar comportamento*.
2. **Fase 1 = só mover + conectar o `log` e `debug`.** App continua idêntico por fora.
3. Manter um **checklist de fumaça** (contas de passar): a app abre, voz liga, soVITS treina,
   waifu sobe, AIRI injeta, diagnóstico roda.
4. Cada fase → commit pequeno e testável.

---

## 3. Depuração (meios de debugar o processo)

### 3.1 Logger estruturado (por categoria)
- `log.py` cria um logger com **categoria**: `[VOZ]`, `[SOVITS]`, `[AIRI]`, `[CONSOLE]`,
  `[SISTEMA]`, `[WAIFU]`, `[MODELO]`, `[MEDIDOR]`.
- Cada log tem **timestamp + nível + categoria + mensagem**. Pode ser filtrado (o Lia já tem
  aba de console; manter + categorizar).
- **Pipe para arquivo** (`logs/lia-<data>.log`) sempre ativo — para debugar sem a tela.

### 3.2 Modo debug (`--debug` / toggle)
- Liga: logs de verbose, **dump de config** (json) em `logs/`, e **dump do que foi injetado no
  AIRI** (localStorage lido de volta após injetar, via CDP).
- Output: `logs/debug-<data>.zip` com config + logs + estado dos processos — útil pra reportar.

### 3.3 Health-checks por serviço (usar no painel de diagnóstico)
- `voz`: `GET http://127.0.0.1:9860/health` + `/v1/models` (edge/kokoro) → mostra version/engines.
- `sovits`: verifica processo/túnel Colab + `/cerebro/_status`.
- `airi`: `http://127.0.0.1:5173` (web) e `http://127.0.0.1:9222` (CDP tamagotchi).
- `waifu`: estado de cada engine (edge/kokoro/sovits) + túnel.
- Cada um mostra **verde/vermelho/amarelo** + botão "reparar".

### 3.4 Logs de injeção (o mais importante para AIRI)
- Ao injetar, registrar exatamente o **JSON que foi escrito** em cada chave
  (`settings/providers/configured`, `settings/speech/*`, `settings/consciousness/*`,
  `settings/vision/*`, `settings/stage/model`).
- Após injetar + recarregar, **ler de volta** via CDP e logar se o AIRI reconheceu
  (ex.: `providers['openai-compatible'].config.baseUrl`, `speech['active-provider']`, etc.).
- Isso é o que permite saber "por que não ativou o cérebro" etc.

---

## 4. Decisões "grátis" (substituir o que é pago)

| Recurso | Opção grátis (usar) | Opção PAGA (evitar) |
| --- | --- | --- |
| **Mente (LLM)** | Colab (Qwen3-4B, Gradio, API openai-compatível) | API paga |
| **Voz** | Edge (online grátis) / Kokoro (offline) / SoVITS (local ou Colab) | ElevenLabs etc. |
| **Visual** | AIRI open-source + VRM/Live2D (arquivos próprios) | — |
| **Input "vivo"** | `server-sdk` / **Channel Server** (grátis, parte do AIRI) — bridge de input simples (WebSocket) | **Claude Code (PAGO)** ❌ |
| **Desenvolvimento** | **Eu (agente Arena)** + AIRI open-source | Claude Code (PAGO) ❌ |
| **Ferramentas auxiliares** | npm/pnpm, venv, msedge-tts, kokoro-onnx, mineflayer (open-source) | — |

> **Substituição do `airi-plugin-claude-code`:** o plugin só faz o *input* do Claude Code
> virar fala da waifu. Como **não vamos usar Claude Code**, o caminho grátis é um **bridge de
> input próprio** que envia texto pro Channel Server do AIRI (WebSocket, `server-sdk`) — sem
> depender de hook pago. A "interatividade" não exige Claude Code; exige apenas **uma fonte de
> input** (voz reconhecida, terminal, ou um script que manda texto). Isso é grátis.

---

## 5. Roadmap em fases

> Cada fase tem entregáveis claros, termina com a app rodando, e é commitada.

### FASE 1 — Fundação limpa + depuração (pré-requisito de tudo)
**Objetivo:** quebrar o monólito e ter logs/dump de debug. **Sem feature nova.**
- [ ] Criar pacote `lia/` e mover lógica (config, paths, log, debug) para módulos.
- [ ] `log.py` (categorias + arquivo) e `debug.py` (dump config + logs).
- [ ] `LiaApp` passa a compor módulos (sem mudar UI por fora).
- [ ] `--debug` e health-checks básicos no painel de diagnóstico.
- **Entregável:** app roda igual, porém modular e com logs/zip de debug.

### FASE 2 — Integração AIRI robusta (base) — ✅ CONCLUÍDA
**Objetivo:** garantir que a beta do AIRI receba a config certa e funcione sempre.
- [x] `app/lia/airi/inject.py`: setar também `settings/consciousness/active-provider` + `active-model`
  (`openai-compatible`/`agentai`) **e** `settings/vision/*` (provider+model) — default é `''` na beta.
- [x] Automatizar a cópia/criação do `agentai-boot.html` em `apps/stage-web/public/`
  (a cada atualização do AIRI, copiar automaticamente) — `app/lia/airi/boot.py` +
  `scripts/atualizar_airi.ps1`.
- [x] Ajustar `atualizar_airi.ps1` e `configurar_tamagotchi.ps1` para a beta
  (provider consistente, cérebro via URL FIXA do bridge, Electron binário no `iniciar_tamagotchi.ps1`).
- [x] Logs de injeção (ler de volta via CDP e conferir reconhecimento) — `app/lia/airi/cdp.py` + `diag.py`.
- [x] Reconfiguração limpa do "Iniciar Waifu": web (boot page + atualizar_airi.ps1) e
  Tamagotchi (CDP) agora usam o mesmo provider/cérebro/visão.
- **Entregável:** AIRI beta sempre com providers/voz/cérebro/visão ativos.

### FASE 3 — Voz (3 engines) + settings além de pitch/rate
**Objetivo:** config de voz completa e start correto por engine.
- [ ] `voz/engine.py`: seleção de engine e prefixo (`edge:`/`kokoro:`/`sovits:`).
- [ ] Start/stop por engine: edge entra direto, kokoro sobe worker ONNX, soVITS usa servidor/túnel.
- [ ] Painel de voz: expor voz (com preview), modelo, provider, SSML (quando suportado),
  além de pitch/rate. Mostrar o que é válido por engine.
- [ ] Manter os 3 motores; soVITS em painel separado (já existe — manter fora da tela principal).
- **Entregável:** controle total de voz, com comportamento correto por engine.

### FASE 4 — Personalidade (painel intuitivo, Character Card v3)
**Objetivo:** painel no Lia para editar a "personalidade" e injetar como card ativo.
- [ ] `persona/card.py`: modelo de Character Card v3 (nome, tagline, system_prompt, personality,
  greetings, scenario, tags, lorebook).
- [ ] `persona/painel.py`: UI intuitiva (campos organizados, pré-visualização).
- [ ] Injeção: escrever `airi-cards` + `airi-card-active-id` (localStorage) e, opcionalmente,
  `local:characters` (IndexedDB).
- [ ] Validar que o card ativo liga personalidade↔modelo↔voz.
- **Entregável:** no Lia App, editar e aplicar a personalidade da Lia.

### FASE 5 — VRM (Vroid → Lia → AIRI) + Live2D (só injeção no start)
**Objetivo:** fluxo de modelo de avatar, VRM definitivo + Live2D como opção.
- [ ] `modelo/vrm.py`: selecionar/importar `.vrm` do Vroid.
- [ ] Caminho A (import UI) → durável; setar `settings/stage/model`.
- [ ] Caminho Live2D (só injeção no start): injetar um display model URL + `settings/stage/model`
  (sem recarregar/IndexedDB).
- [ ] Registro de logs do modelo escolhido + preview.
- **Entregável:** trocar o avatar da Lia (VRM/Live2D) de forma confiável.

### FASE 6 — Mecânicas extras + medidor de desempenho
**Objetivo:** ativar as "mecânicas a mais" do AIRI e medir o desempenho.
- [ ] `mecânicas/catalogo.py` + `toggles.py`: ligar flags dos módulos
  (visão/captura de tela, discord, minecraft, x, web-search, hearing, artistry, mcp, beat-sync).
- [ ] Cada mecânica: apontar config (token discord, servidor MC, etc.) e registrar "o que precisa rodar".
- [ ] `waifu/medidor.py`: medidor de desempenho (FPS, frame, longtask, memória) — reusar/portar o
  conceito do PerformanceOverlay do AIRI; toggle + mostrar junto às mecânicas ativas.
- [ ] Captura de tela ("ver a tela"): confirmar que só funciona no Electron (desktop), com aviso no web.
- **Entregável:** ativar mecânicas pelo Lia App e ver FPS/memória.

### FASE 7 — Opção A: roupa/acessório/cabelo vivos (a mais pesada)
**Objetivo:** trocar o visual da Lia sem recarregar o modelo, com animação de vestir/desvestir.
- [ ] Pipeline de assets: preparar **corpo base** (nu, sem cabelo) + **looks** como meshes separados
  (mesmos bones). (Parte artística — Vroid/Blender/Unity — documentar passo a passo.)
- [ ] Fork/patch no `stage-ui-three` do AIRI: adicionar **wardrobe store** + componente de anexo de
  itens a bones (`bone.add` p/ rígido; **skeleton swap** p/ roupa skinned) + animação de vestir
  (tween) e/ou fade (plano B).
- [ ] Tool/plugin que a Lia chama para "vestir/despir" (decisão no cérebro → execução no avatar).
- [ ] Tratar riscos (mismatch de bones, double-up, física, offset, memória) — ver
  `PESQUISA-AIRI-OPCAO-A-FORK.md`.
- [ ] Licença VRoid: respeitar (trocar outfits entre VRMs prontos; NÃO criar/deformar modelo).
- **Entregável:** a Lia veste/desveste e muda o cabelo com animação, sem recarregar.

---

## 6. Ordem recomendada & prioridade

- **Fase 1 primeiro** (limpeza + debug) — é o que permite tudo o resto sem perder o código.
- **Fases 2 e 3** são a espinha dorsal atual (não perder o que já funciona com a beta).
- **Fases 4, 5, 6** são valor rápido (personalidade, VRM, mecânicas, medidor).
- **Fase 7 (Opção A)** é a de maior risco/esforço — fazer por último, após a base sólida.

> **Ordem sugerida de investimento:** 1 → 2 → 3 → 4/5 → 6 → 7.

---

## 7. Riscos & mitigação

| Risco | Mitigação |
| --- | --- |
| Refatoração quebra algo | Extrair sem mudar comportamento; checklist de fumaça; commits pequenos |
| AIRI beta muda chaves | Logs de injeção + ler de volta via CDP; já documentado que keys são estáveis |
| Voz por engine difere | Comportamento por engine documentado e testado em cada uma |
| Opção A caro/instável | Plano B (fade) como fallback; pipeline de assets separado do código |
| Licença VRoid | Não criar/deformar modelo; só trocar outfits prontos |
| Custos pagos | Nenhum serviço pago; Colab/voz local/AIRI open-source; sem Claude Code |

---

## 8. Próximos passos imediatos

Aprovar este plano. Ao aprovar, começo pela **Fase 1**:
1. Criar `lia/` + `log.py` + `debug.py`.
2. Extrair `config.py`/`paths.py` do monólito.
3. Instalar `--debug` e logs categorizados.
4. Manter a app rodando igual.

> Diga "pode ir" para eu começar a Fase 1, ou ajuste prioridades.
