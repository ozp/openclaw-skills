# openclaw-skills

Skills públicas compatíveis com o marketplace do [OpenClaw Mission Control](https://github.com/openclaw/openclaw-mission-control).

## Como usar no MC

### Registrar como Skill Pack

```bash
BASE=http://localhost:8001
TOKEN=<seu_token>

# 1. Registrar o pack
PACK_ID=$(curl -fsS -X POST "$BASE/api/v1/skills/packs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_url":"https://github.com/ozp/openclaw-skills","name":"ozp/openclaw-skills","branch":"main"}' | jq -r '.id')

# 2. Sincronizar (descobre e importa todas as skills)
curl -fsS -X POST "$BASE/api/v1/skills/packs/$PACK_ID/sync" \
  -H "Authorization: Bearer $TOKEN" | jq '{synced, created, updated}'

# 3. Instalar uma skill no gateway
SKILL_ID=$(curl -fsS "$BASE/api/v1/skills/marketplace?gateway_id=$GATEWAY_ID" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.[] | select(.name=="MC Operator") | .id')

curl -fsS -X POST "$BASE/api/v1/skills/marketplace/$SKILL_ID/install?gateway_id=$GATEWAY_ID" \
  -H "Authorization: Bearer $TOKEN"
```

## Skills disponíveis

| Skill | Categoria | Risco | Descrição |
|---|---|---|---|
| [mc-operator](./mc-operator/) | operations | low | Operar boards do Mission Control via API REST |
| [repo-ecosystem-evaluator](./repo-ecosystem-evaluator/) | analysis | low | Avaliar repositórios por qualidade arquitetural e fit de stack |
| [openclaw-agent-creator](./openclaw-agent-creator/) | infrastructure | medium | Criar e inicializar agentes OpenClaw com workspace completo |
| [openclaw-audit](./openclaw-audit/) | security | low | Auditar instalação OpenClaw: config, segurança, workspace |
| [serena-source-consultation](./serena-source-consultation/) | research | low | Consultar código-fonte e docs para verificar comportamento real |
| [skill-creator](./skill-creator/) | meta | low | Criar novas skills seguindo melhores práticas |
| [prompt-improver](./prompt-improver/) | productivity | low | Melhorar prompts aplicando técnicas de prompt engineering |
| [mineru](./mineru/) | document-processing | low | Parsear PDF/Word/PPT/imagens para Markdown via MinerU API |
| [skill-check](./skill-check/) | meta | low | Validar skills contra a especificação agentskills |
| [skills-discovery](./skills-discovery/) | meta | low | Buscar e instalar skills de agentes |
| [task-tracker-openclaw-skill](./task-tracker-openclaw-skill/) | productivity | low | Gestão de tarefas pessoais com daily standups e weekly reviews |

## Adicionando ao repositório

Para adicionar uma nova skill:

1. Crie um diretório com o nome da skill (ex: `minha-skill/`)
2. Adicione um `SKILL.md` com frontmatter YAML:
   ```yaml
   ---
   name: Minha Skill
   description: O que ela faz e quando usar.
   category: operations
   risk: low
   ---
   ```
3. Adicione a entrada em `skills_index.json`
4. Faça push e resincronize no MC: `POST /api/v1/skills/packs/{pack_id}/sync`
