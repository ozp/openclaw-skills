# Awesome OpenClaw Agents — Biblioteca de Referência

Repositório público com 162 templates de agentes OpenClaw prontos para produção, organizados em 19 categorias. Use como base de inspiração, naming, estrutura de SOUL.md e definição de responsabilidades ao criar novos agentes.

**Repo:** https://github.com/mergisi/awesome-openclaw-agents
**Índice completo (JSON):** `agents.json` na raiz

---

## Como consultar antes de criar um agente

Antes de criar um novo agente do zero, verifique se existe um template adequado como ponto de partida:

```bash
# Listar todos os agentes com nome, categoria e papel
gh api repos/mergisi/awesome-openclaw-agents/contents/agents.json \
  --jq '.content' | base64 -d | \
  jq -r '.[] | "\(.category)/\(.id) — \(.name) (\(.role))"' | sort

# Buscar por categoria (ex: development)
gh api repos/mergisi/awesome-openclaw-agents/contents/agents.json \
  --jq '.content' | base64 -d | \
  jq -r '.[] | select(.category=="development") | "\(.id) — \(.name): \(.role)"'

# Ler o SOUL.md de um agente específico
gh api 'repos/mergisi/awesome-openclaw-agents/contents/agents/development/code-reviewer/SOUL.md' \
  --jq '.content' | base64 -d
```

Ou via URL raw no GitHub:
```
https://raw.githubusercontent.com/mergisi/awesome-openclaw-agents/main/agents/<category>/<agent-id>/SOUL.md
```

---

## Categorias e Agentes Disponíveis

| Categoria | Exemplos de Agentes |
|---|---|
| `automation` | Negotiation Agent, Job Applicant, Morning Briefing, Overnight Coder, Discord Business, Flight Scraper |
| `business` | Lead Gen, ERP Admin |
| `compliance` | (ver repo) |
| `creative` | Ad Copywriter, Storyboard Writer, Proofreader, Audio Producer, Short-Form Video, Music Producer |
| `customer-success` | (ver repo) |
| `data` | Anomaly Detector, Survey Analyzer, Data Entry, Transcription |
| `development` | Code Reviewer, API Documentation, API Tester, Bug Hunter, Changelog, Docs Writer, GitHub PR Reviewer, GitHub Issue Triager, QA Tester, Script Builder, Schema Designer, Test Writer, Migration Helper |
| `devops` | (ver repo) |
| `ecommerce` | Dropshipping Researcher, Price Monitor |
| `education` | Curriculum Designer, Essay Grader, Flashcard Generator |
| `finance` | Copy Trader |
| `freelance` | Upwork Proposal |
| `healthcare` | (ver repo) |
| `hr` | Resume Optimizer |
| `legal` | (ver repo) |
| `marketing` | Email Sequence, Content Repurposer, Book Writer, News Curator, LinkedIn Content, X/Twitter Growth, YouTube SEO, TikTok Creator, Instagram Reels, Localization, Telemarketer |
| `personal` | Travel Planner, Journal Prompter |
| `productivity` | Meeting Transcriber, Notion Organizer |
| `real-estate` | Property Video, Commercial RE |
| `saas` | Product Scrum |
| `security` | (ver repo) |
| `voice` | (ver repo) |

**Configs para Ollama:** `configs/ollama/` — Coding Assistant (Gemma4), Content Writer (Qwen3), Research Analyst (DeepSeek V3), Project Manager (Gemma4:26b), Customer Support.

---

## Estrutura Padrão de um Template

Cada agente tem:
```
agents/<category>/<agent-id>/
  README.md    # Visão geral e casos de uso
  SOUL.md      # Configuração completa do agente (identidade, responsabilidades, comportamentos)
```

O `SOUL.md` segue esta estrutura-padrão (ex: Code Reviewer):
```markdown
# <Nome> - <Papel>

You are <Nome>, an AI <papel> powered by OpenClaw.

## Core Identity
- **Role:** ...
- **Personality:** ...
- **Communication:** ...

## Responsibilities
1. <Responsabilidade 1>
   - Sub-item...

## Behavioral Guidelines
### Do:
### Don't:

## Severity Levels / Output Format / Example Interactions
```

---

## Quando Usar como Inspiração

- **Nomear o agente**: Lens (reviewer), Beats (music), Clipper (video), Viso (ad creator) — nomes expressivos, não genéricos
- **Definir responsabilidades**: Use a lista de responsabilidades de um template similar como checklist
- **Definir Do/Don't**: Adapte as diretrizes comportamentais à personalidade desejada
- **Definir níveis de output**: Severity levels (crítico/aviso/sugestão) são um bom padrão para agentes de revisão
- **Scope creep**: Verifique o que o template exclui explicitamente para definir limites do agente

---

## Uso no Fluxo de Criação de Agentes

1. Identificar a categoria do agente desejado (development, automation, productivity, etc.)
2. Buscar templates relevantes: `gh api ... | jq '.[] | select(.category=="...")'`
3. Ler 1-2 SOUL.md da categoria como referência de estrutura e vocabulário
4. Adaptar para o contexto OpenClaw/MC: adicionar seções de board, tasks, memory se relevante
5. Manter a identidade nomeada e personalidade expressiva do template como base
