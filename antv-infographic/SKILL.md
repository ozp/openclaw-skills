# AntV Infographic — Skill de Referência

## Visão Geral

**@antv/infographic** é um motor declarativo de infográficos da AntV (Ant Group).
Gera SVG de alta qualidade a partir de sintaxe estruturada, com ~200 templates,
sistema de temas, e suporte a streaming para IA.

- **Repo**: https://github.com/antvis/Infographic
- **Docs**: https://infographic.antv.vision
- **Galeria**: https://infographic.antv.vision/gallery
- **NPM**: `@antv/infographic` (instalado: v0.2.16)
- **Licença**: MIT

---

## 1. Instalação — NPM (✅ Feito)

```bash
npm install @antv/infographic
# Instalado em /home/ozp/node_modules/@antv/infographic
```

## 2. Instalação — Skills para Claude Code

### Opção A: Via Plugin Marketplace (Recomendado)

Dentro do Claude Code, executar:

```
/plugin marketplace add https://github.com/antvis/Infographic.git
/plugin install antv-infographic-skills@antv-infographic
```

### Opção B: Instalação Manual

```bash
set -e
VERSION=0.2.16  # Conferir última tag em https://github.com/antvis/Infographic/releases
BASE_URL=https://github.com/antvis/Infographic/releases/download
mkdir -p ~/.claude/skills

curl -L --fail -o /tmp/skills.zip "$BASE_URL/$VERSION/skills.zip"
unzip -q -o /tmp/skills.zip -d ~/.claude/skills
rm -f /tmp/skills.zip
```

### Skills Disponíveis após Instalação

| Skill | Função |
|-------|--------|
| `infographic-creator` | Cria arquivo HTML que renderiza um infográfico |
| `infographic-syntax-creator` | Gera sintaxe de infográfico a partir de descrições |
| `infographic-structure-creator` | Gera designs de estrutura customizados |
| `infographic-item-creator` | Gera designs de itens customizados |
| `infographic-template-updater` | Atualiza a biblioteca de templates (devs) |

---

## 3. Uso Básico — API TypeScript

```typescript
import { Infographic } from '@antv/infographic';

const infographic = new Infographic({
  container: '#container',
  width: 800,
  height: 600,
  template: 'list-row-simple-horizontal-arrow',
  data: {
    title: 'Título do Infográfico',
    desc: 'Descrição breve',
    items: [
      { label: 'Etapa 1', desc: 'Descrição', icon: 'company-021_v1_lineal' },
      { label: 'Etapa 2', desc: 'Descrição', icon: 'antenna-bars-5_v1_lineal' },
      { label: 'Etapa 3', desc: 'Descrição', icon: 'achievment-050_v1_lineal' },
    ]
  },
  theme: 'default',
  padding: 20
});

infographic.render();
```

### Exportação

```typescript
// PNG com alta resolução (DPI 3x)
const pngUrl = await infographic.toDataURL({ type: 'png', dpr: 3 });

// SVG vetorial com recursos embutidos
const svgUrl = await infographic.toDataURL({ type: 'svg', embedResources: true });
```

### Streaming (para output de IA)

```typescript
let buffer = '';
for (const chunk of chunks) {
  buffer += chunk;
  infographic.render(buffer);
}
```

### Templates Customizados

```typescript
import { registerTemplate, getTemplates } from '@antv/infographic';

registerTemplate('meu-template', {
  design: { structure: 'list-column', item: 'badge-card', title: 'text-3d' },
  width: 1200, height: 800,
  theme: 'gradient-blue',
  padding: { top: 40, right: 40, bottom: 40, left: 40 }
});
```

---

## 4. Caminhos para Impressão (PDF / Print-Ready)

### Caminho 1 — SVG Puro com Dimensões de Impressão

**Conceito**: Gerar SVG com viewBox em dimensões reais de impressão.
SVG é vetorial → escala infinitamente sem perda.

**Dimensões de referência (em pixels a 300 DPI)**:

| Formato | mm | px (300dpi) |
|---------|-----|-------------|
| A4 | 210 × 297 | 2480 × 3508 |
| A3 | 297 × 420 | 3508 × 4961 |
| A2 | 420 × 594 | 4961 × 7016 |
| Poster 60×90 | 600 × 900 | 7087 × 10630 |

**Fluxo**:
1. Gerar infográfico com AntV Infographic (width/height em px de impressão)
2. Exportar SVG com `embedResources: true`
3. Abrir SVG no Inkscape → Salvar como PDF
4. Imprimir

**Vantagens**: Qualidade máxima, editável, sem dependência extra.
**Desvantagens**: Passo manual no Inkscape para PDF.

### Caminho 2 — SVG + ReportLab/svglib → PDF Direto (Python)

**Conceito**: Converter SVG programaticamente para PDF com dimensões exatas.

```python
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from reportlab.lib.pagesizes import A4, A3, landscape

# Converter SVG para objeto ReportLab
drawing = svg2rlg("infografico.svg")

# Escalar para caber na página
scale_x = A4[0] / drawing.width
scale_y = A4[1] / drawing.height
scale = min(scale_x, scale_y)
drawing.width *= scale
drawing.height *= scale
drawing.scale(scale, scale)

# Gerar PDF
renderPDF.drawToFile(drawing, "infografico_A4.pdf", fmt="PDF")
```

**Vantagens**: Automatizado, dimensões exatas, sem intervenção manual.
**Desvantagens**: svglib pode não suportar 100% dos features SVG avançados.

**Instalação**:
```bash
pip install svglib reportlab
```

### Caminho 3 — Puppeteer/Playwright → PDF (Node.js)

**Conceito**: Renderizar HTML com infográfico no browser headless e imprimir como PDF.

```javascript
const puppeteer = require('puppeteer');

const browser = await puppeteer.launch();
const page = await browser.newPage();

// Carregar HTML com o infográfico
await page.goto('file:///path/to/infografico.html', { waitUntil: 'networkidle0' });

// Gerar PDF com dimensões exatas
await page.pdf({
  path: 'infografico.pdf',
  width: '210mm',   // A4
  height: '297mm',
  printBackground: true,
  margin: { top: '0mm', right: '0mm', bottom: '0mm', left: '0mm' }
});

await browser.close();
```

**Para poster (60×90cm)**:
```javascript
await page.pdf({
  path: 'poster.pdf',
  width: '600mm',
  height: '900mm',
  printBackground: true,
  margin: { top: '0mm', right: '0mm', bottom: '0mm', left: '0mm' }
});
```

**Vantagens**: Fidelidade total (renderiza como browser), suporta CSS/fontes/gradientes.
**Desvantagens**: Precisa do Puppeteer/Playwright instalado.

**Instalação**:
```bash
npm install puppeteer
# ou
npx playwright install chromium
```

---

## 5. Comparação dos Caminhos

| Aspecto | SVG Puro (1) | svglib→PDF (2) | Puppeteer (3) |
|---------|-------------|----------------|---------------|
| Fidelidade visual | ★★★★★ | ★★★☆☆ | ★★★★★ |
| Automação | ★★☆☆☆ | ★★★★★ | ★★★★★ |
| Complexidade | Baixa | Média | Média |
| Suporte CSS/fontes | N/A (SVG nativo) | Limitado | Total |
| Dimensões exatas | Manual (Inkscape) | Programático | Programático |
| Recomendado para | Edição posterior | Scripts batch | Produção final |

---

## 6. Projetos Relacionados (Ecossistema)

- **baoyu-skills** (github.com/JimLiu/baoyu-skills): Skills para Claude Code com geração de infográficos via IA (requer API keys OpenAI/Google/DashScope). Diferente abordagem — gera imagens rasterizadas via IA generativa, não SVG programático.
- **AntV MCP Server Chart**: Servidor MCP para gerar gráficos via AntV (não infográficos).
- **Obsidian plugin**: Plugin para renderizar infográficos em Obsidian.
- **VSCode Extension**: Preview de infográficos em Markdown.

---

## Notas

- Versão instalada: 0.2.16 (março 2026)
- Localização: `/home/ozp/node_modules/@antv/infographic`
- Context7 library ID: `/antvis/infographic`
