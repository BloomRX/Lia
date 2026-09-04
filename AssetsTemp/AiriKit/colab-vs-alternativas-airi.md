# Por que Colab é um péssimo "cérebro" pro Airi (e como fazer melhor)

> Documento de referência para o projeto Airi — PC: Ryzen 5 5500 · RX 580 8GB · 16GB RAM
> Situação atual: App próprio de pré-configuração do Airi (voz funcionando) + LLM hospedado no Google Colab exposto via túnel.

---

## TL;DR

O Colab foi desenhado para **notebooks interativos de data science** — pessoas escrevendo código e olhando gráficos por algumas horas. Um companheiro virtual tipo Airi precisa do oposto: um **serviço de inferência que fica de pé 24/7, com URL fixa e resposta rápida**. Forçar o Colab nesse papel gera 9 problemas estruturais que nenhuma gambiarra resolve. A saída: trocar o endpoint no seu App de **`https://xxxx.ngrok.io`** para **Groq** (nuvem grátis, principal) e/ou **LM Studio local** (sua RX 580, fallback offline). Mesmo formato OpenAI-compatible, zero mudança de arquitetura no seu App.

---

## 1. Os limites reais do Colab grátis (2026)

| Limite | Valor | Consequência pro Airi |
|---|---|---|
| Timeout por inatividade | **~90 min** | VM é recolhida → Airi perde o cérebro no meio do dia |
| Teto absoluto da sessão | **~12h** | Nem mantendo a aba aberta; reinicia todo dia |
| Cota semanal de GPU | **15–30h dinâmicas** | Acabou a cota → só CPU → modelo de 8B vira engasgado |
| Disponibilidade de GPU | **Não garantida** | Em horário de pico você recebe CPU mesmo pedindo GPU |
| Execução em background | **Não existe no grátis** (é Pro+) | Precisa manter a célula rodando numa aba aberta pra sempre |
| Disco/RAM da VM | **Efêmeros** | Cada disconnect apaga modelo carregado, contexto, tudo |

Fontes: documentação/FAQ do Google e análises de 2026 (aicreditmart.com, thundercompute.com, spheron.network). O próprio Google diz, no FAQ, que quem precisa de acesso garantido/contínuo deve usar outro produto — ou seja, **não é o produto para esse caso de uso**.

## 2. As 9 dores no SEU fluxo específico (Colab + túnel + Airi)

1. **Ela "apaga" sozinha.** 90 min sem tráfego (ou você longe do PC) = runtime morto. VTuber é exatamente o caso de uso *idle → de repente uso*.
2. **Teto de 12h** = todo dia tem um "momento da morte" agendado, mesmo com uso constante.
3. **A URL do túnel muda a cada sessão.** ngrok/cloudflared grátis gera endereço novo a cada restart → seu App (ou você) precisa reconfigurar o Airi **toda vez**. Seu App de pré-config disfarça a dor; não a elimina.
4. **Cold start brutal.** Depois de cada disconnect: reconnect → rodar célula → baixar/carregar modelo (2–5 min, se não precisou baixar de novo do zero). Enquanto isso, a Lia está em coma.
5. **Cota de GPU imprevisível.** Você é prioridade *baixa* no free tier; pagantes passam na frente. Numa semana de uso intenso, você entra em cooldown e cai pra CPU — onde inferência vira tortura.
6. **Latência em dobro.** O caminho é: seu PC → túnel (ngrok) → VM do Colab (geralmente nos EUA) → modelo → volta. São 300–800ms *só de rede* antes do modelo começar a gerar — somados ao STT+TTS da voz, a conversa fica arrastada.
7. **Zona cinzenta de ToS.** Os termos do Colab são para computação interativa de notebook; servir aplicativo/API persistente via túnel é o tipo de uso que o Google restringe (fizeram isso com Stable Diffusion WebUI em 2023). Risco de perda de cota ou restrição da conta.
8. **Endpoint aberto na internet.** O túnel expõe seu servidor de inferência sem autenticação robusta — qualquer um com a URL queima a SUA cota de GPU.
9. **Zero memória entre sessões.** Toda RAM da VM some no disconnect — contexto de conversa, cache do modelo, tudo. Conecta com o problema anterior: você quer justamente uma Airi *com* memória.

## 3. Comparação direta das alternativas

| Critério | Colab + túnel | **Groq (nuvem grátis)** | **LM Studio local (RX 580, Vulkan)** |
|---|---|---|---|
| Latência de rede | 300–800ms (túnel+EUA) | **~50–150ms** | ~0ms (localhost) |
| Velocidade de geração | ~20–30 tok/s (T4, quando tem) | **300+ tok/s (LPU)** | ~20–35 tok/s (7B/4B Q4) |
| Uptime | 12h máx, 90min idle | **24/7, sem disconnect** | 24/7 enquanto o PC ligar |
| URL | **Muda toda sessão** | Fixa (api.groq.com) | **Fixa (localhost:1234)** |
| "Inteligência" do modelo | 8B–13B | **70B (Llama 3.3)** | 4B–8B |
| Manutenção | Alta (reconectar, rodar célula, reconfigurar) | **Zero** | Baixa (servidor sempre ligado) |
| Custo | R$ 0 (com risco de cota) | R$ 0 (30 req/min, ~1k+/dia) | R$ 0 (ilimitado) |
| Funciona offline? | Não | Não | **Sim** |
| Risco de ban/ToS | Zona cinzenta | Nenhum | Nenhum |

## 4. Como fazer melhor — mantendo seu App de pré-config

A boa notícia: seu App já resolve a parte chata (configurar o Airi antes de abrir). O Colab e as alternativas abaixo falam o **mesmo idioma** (API OpenAI-compatible). Você só troca o endpoint que o App injeta.

### Opção A — Groq como cérebro principal (recomendado)

1. Crie a chave grátis em **console.groq.com/keys** (sem cartão).
2. No seu App, troque a config injetada no Airi (provedor *OpenAI Compatible*):
   - **Base URL:** `https://api.groq.com/openai/v1`
   - **Model:** `llama-3.3-70b-versatile`
   - **API Key:** `gsk_...`
3. Pronto. Fim do item 1 ao 9 da lista de dores.

**Fallback:** configure um segundo provedor com **Cerebras** (`https://api.cerebras.ai/v1`, Qwen3-235B ou Llama 70B, 1M tokens/dia grátis). Quando o Groq estourar os limites diários, o Airi continua viva.

### Opção B — LM Studio local como fallback offline (RX 580)

1. Instale o **LM Studio** (usa Vulkan — única via real na Polaris; nada de Ollama/ROCm).
2. Baixe **Qwen3 4B Q4_K_M** (~35 tok/s na RX 580) ou **Llama 3.1 8B Q4_K_M** (~20 tok/s).
3. Ligue o servidor local do LM Studio: `http://localhost:1234/v1`.
4. Configure como segundo provedor no App/Airi.

Bônus: `localhost` **nunca muda** — a URL que o seu App injeta hoje para o túnel vira uma URL que vive pra sempre. E é seu plano B quando a internet cair.

### Opção C — Híbrido (o melhor dos dois mundos)

No Airi: **Consciousness = Groq 70B** (esperta e rápida no dia a dia) + segundo provedor local configurado (troca manual ou automática quando a cota bate). Seu App pode testar a conectividade do Groq antes de abrir o Airi e injetar a config correspondente — a mesma lógica que ele já usa hoje para o túnel, sem o ponto único de falha.

## 5. Onde o Colab AINDA faz sentido

Não jogue fora — só use pro que ele foi feito:

- **Testar modelos** antes de baixar pra RX 580 (vale a pena pro barramento de VRAM);
- Fine-tune/LoRA pontual de um modelo pequeno;
- Transcrição em lote (Whisper) de áudios longos;
- Qualquer tarefa **finita**, com começo, meio e fim — não um serviço residente.

## 6. Checklist de migração do seu App

- [ ] Criar chave no Groq (e no Cerebras, para fallback)
- [ ] Substituir no App: `BaseURL` do túnel → `https://api.groq.com/openai/v1` + campo de chave
- [ ] Adicionar segundo perfil de provedor apontando para `http://localhost:1234/v1` (LM Studio)
- [ ] Ajustar o campo `Model` para `llama-3.3-70b-versatile` (Groq) e `qwen3-4b` (local)
- [ ] Aproveitar que o App roda antes do Airi: fazer um *ping* no provedor e só abrir o Airi se estiver respondendo (hoje isso mascara o Colab morto; amanhã vira health-check de verdade)
- [ ] Aposentar o notebook do túnel (ou mantê-lo só para experimentos)
