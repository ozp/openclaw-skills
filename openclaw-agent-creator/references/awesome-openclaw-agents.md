# Awesome OpenClaw Agents — Biblioteca de Referência

Repositório público com 199 templates de agentes OpenClaw prontos para produção, organizados em 25 categorias. Use como base de inspiração, naming, estrutura de SOUL.md e definição de responsabilidades ao criar novos agentes.

**Repo:** https://github.com/mergisi/awesome-openclaw-agents
**Mirror local:** `/home/ozp/code/mirror/awesome-openclaw-agents` (usar preferencialmente — sem depender de rede)
**Índice completo (JSON):** `agents.json` na raiz — estrutura: `{ "total": 199, "agents": [...] }`

---

## Como consultar antes de criar um agente

**Preferencial — mirror local (sem rede):**
```bash
MIRROR=/home/ozp/code/mirror/awesome-openclaw-agents

# Listar todos os agentes com categoria e papel
jq -r '.agents[] | "\(.category)/\(.id) — \(.name) (\(.role))"' $MIRROR/agents.json | sort

# Buscar por categoria (ex: development)
jq -r '.agents[] | select(.category=="development") | "\(.id) — \(.name): \(.role)"' $MIRROR/agents.json

# Ler o SOUL.md de um agente específico
cat $MIRROR/agents/development/code-reviewer/SOUL.md

# Buscar por palavra-chave no nome ou role
jq -r '.agents[] | select((.name+.role) | ascii_downcase | contains("review")) | "\(.category)/\(.id) — \(.name)"' $MIRROR/agents.json
```

**Alternativa — via GitHub API (estrutura correta: `.agents[]`, não `.[]`):**
```bash
gh api repos/mergisi/awesome-openclaw-agents/contents/agents.json \
  --jq '.content' | base64 -d | \
  jq -r '.agents[] | "\(.category)/\(.id) — \(.name) (\(.role))"' | sort
```

Ou via URL raw:
```
https://raw.githubusercontent.com/mergisi/awesome-openclaw-agents/main/agents/<category>/<agent-id>/SOUL.md
```

---

## Categorias e Agentes Disponíveis (25 categorias, 199 agentes)

| Categoria | Total | Exemplos |
|---|---|---|
| `automation` | 6 | negotiation-agent, job-applicant, morning-briefing, flight-scraper |
| `business` | 14 | churn-predictor, competitor-pricing, customer-support, invoice-tracker |
| `compliance` | 4 | gdpr-auditor, soc2-preparer, ai-policy-writer, risk-assessor |
| `creative` | 13 | brand-designer, copywriter, podcast-producer, thumbnail-designer |
| `customer-success` | 2 | nps-followup, onboarding-guide |
| `data` | 9 | dashboard-builder, data-cleaner, etl-pipeline, report-generator |
| `development` | 18 | api-tester, bug-hunter, changelog, code-reviewer, dependency-scanner, docs-writer, migration-helper, pr-merger, test-writer, schema-designer |
| `devops` | 10 | cost-optimizer, deploy-guardian, incident-responder, infra-monitor |
| `ecommerce` | 7 | abandoned-cart, inventory-tracker, pricing-optimizer, product-lister |
| `education` | 8 | language-tutor, quiz-maker, research-assistant, study-planner |
| `finance` | 10 | expense-tracker, invoice-manager, revenue-analyst, tax-preparer |
| `freelance` | 4 | client-manager, proposal-writer, time-tracker, upwork-proposal |
| `healthcare` | 7 | meal-planner, wellness-coach, workout-tracker, symptom-triage |
| `hr` | 8 | onboarding, performance-reviewer, recruiter, resume-screener |
| `legal` | 6 | compliance-checker, contract-reviewer, policy-writer, patent-analyzer |
| `marketing` | 26 | ab-test-analyzer, brand-monitor, cold-outreach, competitor-watch, echo, influencer-finder, newsletter, reddit-scout |
| `moltbook` | 3 | moltbook-community-manager, moltbook-scout, moltbook-growth-agent |
| `ollama` | 5 | ollama-coding-assistant, ollama-content-writer, ollama-research-analyst, ollama-project-manager |
| `personal` | 7 | daily-planner, family-coordinator, fitness-coach, home-automation |
| `productivity` | 9 | daily-standup, focus-timer, habit-tracker, inbox-zero |
| `real-estate` | 5 | lead-qualifier, listing-scout, market-analyzer, property-video |
| `saas` | 6 | churn-prevention, feature-request, onboarding-flow, release-notes |
| `security` | 6 | access-auditor, incident-logger, phishing-detector, security-hardener |
| `supply-chain` | 3 | route-optimizer, inventory-forecaster, vendor-evaluator |
| `voice` | 3 | phone-receptionist, voicemail-transcriber, interview-bot |

---

## Estrutura Padrão de um Template

Cada agente tem:
```
agents/<category>/<agent-id>/
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

- **Nomear o agente**: Lens (reviewer), Beats (music), Clipper (video) — nomes expressivos, não genéricos
- **Definir responsabilidades**: Use a lista de responsabilidades de um template similar como checklist
- **Definir Do/Don't**: Adapte as diretrizes comportamentais à personalidade desejada
- **Definir níveis de output**: Severity levels (crítico/aviso/sugestão) são um bom padrão para agentes de revisão
- **Scope creep**: Verifique o que o template exclui explicitamente para definir limites do agente

---

## Uso no Fluxo de Criação de Agentes

1. Identificar a categoria do agente desejado (development, automation, productivity, etc.)
2. Buscar templates no mirror local: `jq -r '.agents[] | select(.category=="...")' $MIRROR/agents.json`
3. Ler 1-2 SOUL.md da categoria como referência: `cat $MIRROR/agents/<category>/<id>/SOUL.md`
4. Adaptar para o contexto OpenClaw/MC: adicionar seções de board, tasks, memory se relevante
5. Manter a identidade nomeada e personalidade expressiva do template como base
