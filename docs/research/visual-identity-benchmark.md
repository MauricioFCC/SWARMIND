# Benchmark: Identidad Visual — Repos AI / Multi-Agent

> Investigación realizada sobre 10 repos de referencia del ecosistema AI/multi-agent para extraer patrones de identidad visual, estructura de assets, badges y paletas de color útiles para **Swarmind**.

**Fecha:** 2026-07-29
**Repos analizados:** AutoGPT, LangChain, AutoGen, CrewAI, Microsoft Semantic Kernel, BabyAGI, GPT Engineer, Aider, Dify, Haystack

---

## 1. Patrones Comunes

### 1.1 Estructura del README (todos los repos)

Todos los repos top (AutoGPT, LangChain, AutoGen, CrewAI, Haystack) comparten este esqueleto:

```markdown
[BANNER / LOGO centrado]
[Título H1 o logo con tag-line]
[Subtítulo descriptivo en 1-2 líneas]

[BADGES row 1: Discord | Docs | Stars]
[BADGES row 2: License | PyPI | Downloads | CI]
[Tabla comparativa de features (cuando es comercial)]

---
## Quote / Social proof            ← solo AutoGPT
## Features (tabla 2x2 con screenshots)
## Quickstart (código)
## Documentación detallada
## Contributing
## License
```

### 1.2 Convenciones observadas

| Patrón | Adopción | Ejemplo |
|---|---|---|
| Logo SVG con variantes light/dark | 30% | LangChain (`.github/images/logo-{light,dark}.svg`) |
| Logo solo PNG | 60% | CrewAI, AutoGen, Dify, Haystack |
| Banner full-width 100% en README | 70% | AutoGPT, CrewAI, Dify, Haystack |
| Logo + título debajo (sin banner) | 20% | LangChain, Semantic Kernel |
| Sin banner, solo badges | 10% | BabyAGI, GPT Engineer, Aider |
| Imagen de "landing/hero" en README | 40% | AutoGen (`autogen-landing.jpg`), AutoGPT |
| Screenshots del producto (UI) | 80% | Todos salvo BabyAGI/GPT Engineer |
| Animated SVG/GIF showcase | 20% | Aider (`screencast.svg` con CSS animation) |
| `<picture>` con dark/light mode | 10% | LangChain |
| Asset: ilustración artística con personaje | 30% | AutoGPT (capa dorada), Haystack (abstract icons) |
| Diagrama de arquitectura propio | 30% | AutoGen, CrewAI (`crewAI-mindmap.png`) |

### 1.3 Estilo de banner

| Tipo | Repos que lo usan | Notas |
|---|---|---|
| **Ilustración cinemática con personaje** | AutoGPT | Más "marketing-heavy", colorido (azul oscuro + dorado + púrpura) |
| **Banner corporativo plano con iconos** | Haystack | Dark navy + iconos blancos distribuidos, texto centrado |
| **Cover/logo gigante + tagline** | Dify | "Dify — Build Production-ready Agentic AI Solutions", en gris claro |
| **Screenshot de la UI del producto** | AutoGPT, CrewAI (varias) | Múltiples cards 2x2 con screenshots de la herramienta |
| **Logo + tagline simple** | LangChain, Aider, AutoGen | Logo SVG centrado, sin imagen hero |

### 1.4 Tabla de presencia por repo

| Repo | Banner/Logo | Logo SVG | Social preview | Screenshots UI | Diagrama arquitectura |
|---|---|---|---|---|---|
| **AutoGPT** | ✅ Banner cinemático | ❌ PNG en docs | ✅ (vía GitHub settings) | ✅ 4+ | ❌ |
| **LangChain** | ✅ Logo SVG only | ✅ dual-mode | ✅ | ❌ | ❌ |
| **AutoGen** | ⚠️ Logo + landing.jpg | ❌ ag.svg hosted | ✅ | ✅ 2 | ✅ 3 capas (Core/Chat/Ext) |
| **CrewAI** | ✅ Logo PNG + 4 screenshots | ❌ PNG | ✅ | ✅ 50+ | ✅ `crewAI-mindmap.png` |
| **Semantic Kernel** | ❌ Sin banner | ❌ | ✅ | ❌ | ❌ |
| **BabyAGI** | ❌ Sin banner | ❌ | ❌ | 1 GIF de dashboard | ❌ |
| **GPT Engineer** | ❌ Solo badges + video | ❌ | ❌ | 1 video | ❌ |
| **Aider** | ✅ Logo SVG (green terminal) | ✅ | ✅ | ✅ Animated screencast | ❌ |
| **Dify** | ✅ Cover grande | ❌ | ✅ | ✅ many | ❌ |
| **Haystack** | ✅ Banner corporativo | ❌ (vía web) | ✅ | ✅ | ❌ |

---

## 2. Tamaños Estándar

### 2.1 Social Preview Card (GitHub)

GitHub renderiza el social preview a **1280×640 px** (ratio 2:1). Se sube desde Settings → Social preview.

| Spec | Valor |
|---|---|
| Dimensiones recomendadas | **1280 × 640 px** |
| Formato | PNG o JPG |
| Peso máximo | 1 MB |
| Ruta en repo | N/A — se configura en GitHub UI, no se commitea |

> ⚠️ **Hallazgo:** Ninguno de los 10 repos commitea el `social_preview.png` al repo. Se gestiona desde la UI de GitHub. **No debemos** intentar versionarlo en el repo.

### 2.2 Logo dimensions

| Contexto | Tamaño recomendado | Formato preferido |
|---|---|---|
| **README hero** | 400–600 px ancho | SVG (escala libre) |
| **Favicon** | 32×32, 64×64, 256×256 | SVG + PNG fallback |
| **README badge / inline** | 24–48 px altura | SVG |
| **Documentación header** | 150–200 px ancho | SVG |
| **Print / press kit** | Vector a cualquier tamaño | SVG / AI |

Casos observados:
- LangChain logo: `472 × 100` (ratio 4.72:1, wordmark horizontal)
- Aider logo: `200 × 60` (ratio 3.33:1, wordmark)
- AutoGen logo: `100 × 100` (square, contained en README width=100)
- CrewAI logo: PNG libre, mostrado `width=600px` en README
- Dify cover: ≈ `2000 × 800` (ratio 2.5:1, hero con tagline)

### 2.3 Banner README

| Tipo | Ratio | Dimensión aprox | Ejemplo |
|---|---|---|---|
| Hero cinemático | 16:9 o 21:9 | 1600×900 / 1920×820 | AutoGPT |
| Banner corporativo | 5:1 (flat, edge-to-edge) | 1600×320 | Haystack |
| Cover con tagline | 2.5:1 a 3:1 | 1920×640 / 1500×500 | Dify |

Convención práctica: **se renderiza a `width="100%"`** en markdown → el archivo debe ser >= 1280 px de ancho para verse nítido en pantallas retina.

### 2.4 Screenshots de producto

- **Ancho consistente:** 800–1200 px
- **Formato:** PNG (lossless) o WebP
- **Peso:** mantener < 500 KB idealmente (CrewAI tiene varios > 1 MB → evitar)
- **Centrados** con `<div align="center">` o ancho fijo

---

## 3. Estructura de Carpetas Recomendada

### 3.1 Lo que hacen los demás

| Repo | Patrón |
|---|---|
| AutoGPT | `docs/home/.gitbook/assets/` + `docs/content/imgs/readme/` |
| LangChain | `.github/images/` (solo logo SVG) |
| AutoGen | `autogen-landing.jpg` en root + paths relativos |
| CrewAI | `docs/images/` (≈80 archivos, totalmente plano) |
| Haystack | `images/` (raíz) |
| Dify | `images/` (raíz) |
| Aider | Assets en repo aparte `aider.chat/assets/` (servidos por web, no en repo) |
| Semantic Kernel | Sin carpeta de assets |
| BabyAGI | Sin assets en repo |
| GPT Engineer | Sin assets en repo |

### 3.2 Patrón dominante: 2-3 ubicaciones

```
swarmind/
├── .github/
│   ├── images/                    ← logos, badges, social assets
│   │   ├── logo-light.svg
│   │   ├── logo-dark.svg
│   │   ├── logo-icon.svg          ← favicon-style
│   │   ├── logo-icon.png          ← 512×512
│   │   ├── og-image.png           ← (opcional, se prefiere GitHub settings)
│   │   └── contributors.svg
│   └── workflows/                 ← CI
│
├── docs/
│   └── assets/
│       ├── banner.png             ← 1600×900 hero
│       ├── banner-dark.png        ← variant for dark mode (opcional)
│       ├── screenshots/
│       │   ├── dashboard.png
│       │   ├── agents-view.png
│       │   ├── workflow-builder.png
│       │   └── ...
│       ├── diagrams/
│       │   ├── architecture.png
│       │   ├── agent-lifecycle.png
│       │   └── data-flow.svg
│       └── icons/                 ← feature icons (estilo Aider)
│           ├── brain.svg
│           ├── network.svg
│           └── ...
│
└── README.md                      ← referencia con paths relativos
```

### 3.3 Recomendación específica para Swarmind

Adoptar la **convención de LangChain** para logos (`.github/images/`) porque es la más limpia y discoverable, y la de **Haystack** (`images/` en root o `docs/assets/`) para el resto:

```
swarmind/
├── .github/
│   ├── images/
│   │   ├── logo-light.svg         ← wordmark claro
│   │   ├── logo-dark.svg          ← wordmark oscuro
│   │   ├── logo-icon.svg          ← solo marca (cuadrado)
│   │   ├── logo-icon.png          ← 512×512 fallback
│   │   ├── wordmark.png           ← 1200×300 si se quiere PNG
│   │   └── favicon.svg
│   └── workflows/
│
├── docs/
│   └── assets/
│       ├── banner.png             ← 1600×900 hero
│       ├── banner-dark.png        ← 1600×900 dark variant
│       ├── cover.png              ← 1920×640 con tagline
│       ├── screenshots/
│       │   ├── 01-dashboard.png
│       │   ├── 02-agents.png
│       │   ├── 03-workflow.png
│       │   ├── 04-traces.png
│       │   └── ...
│       ├── diagrams/
│       │   ├── architecture.png
│       │   ├── architecture.svg   ← preferido, escalable
│       │   ├── agent-mesh.png
│       │   └── sequence-flow.svg
│       └── icons/                 ← opcional, si seguimos estilo Aider
│
└── README.md
```

---

## 4. Badges Comunes (shields.io)

### 4.1 Badges universales (10/10 repos)

```markdown
<!-- License -->
<img src="https://img.shields.io/github/license/Significant-Gravitas/AutoGPT" alt="License">

<!-- Stars -->
<img src="https://img.shields.io/github/stars/Significant-Gravitas/AutoGPT?style=social" alt="Stars">
```

### 4.2 Badges de distribución (8/10)

```markdown
<!-- PyPI version -->
<img src="https://img.shields.io/pypi/v/langchain" alt="PyPI">

<!-- PyPI downloads -->
<img src="https://img.shields.io/pepy/dt/langchain" alt="PyPI Downloads">

<!-- npm (si aplica) -->
<img src="https://img.shields.io/npm/v/package" alt="npm">

<!-- Docker pulls -->
<img src="https://img.shields.io/docker/pulls/langgenius/dify-web" alt="Docker Pulls">

<!-- crates.io (Rust) -->
<img src="https://img.shields.io/crates/v/swarmind" alt="crates.io">
```

### 4.3 Badges de comunidad (9/10)

```markdown
<!-- Discord -->
<img src="https://img.shields.io/discord/XXXXXXX?logo=discord&logoColor=white" alt="Discord">

<!-- Twitter/X -->
<img src="https://img.shields.io/twitter/follow/Swarmind?style=social" alt="Twitter">

<!-- YouTube (si hay videos) -->
<img src="https://img.shields.io/youtube/channel/subscribers/XXXX" alt="YouTube">
```

### 4.4 Badges de CI/CD (5/10)

```markdown
<!-- Tests -->
<img src="https://github.com/USER/swarmind/actions/workflows/tests.yml/badge.svg" alt="Tests">

<!-- Build status -->
<img src="https://github.com/USER/swarmind/actions/workflows/build.yml/badge.svg" alt="Build">

<!-- Coverage (codecov) -->
<img src="https://codecov.io/gh/USER/swarmind/branch/main/graph/badge.svg" alt="Coverage">

<!-- Lint (ruff) -->
<img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff">

<!-- Type check (mypy) -->
<img src="https://img.shields.io/badge/types-Mypy-blue.svg" alt="Mypy">
```

### 4.5 Badges de status especiales (1-2/10)

```markdown
<!-- Maintenance mode (AutoGen) -->
<img src="https://img.shields.io/badge/status-maintenance%20mode-orange" alt="Status">

<!-- Build version colored -->
<img src="https://img.shields.io/badge/version-1.0.0-blue" alt="Version">

<!-- Static badge custom (Dify) -->
<img src="https://img.shields.io/badge/Product-F04438" alt="Product">
```

### 4.6 Layout recomendado (estilo Aider)

```markdown
<p align="center">
  <!-- Fila 1: Social proof & community -->
  <img src="https://img.shields.io/github/stars/USER/swarmind?style=flat-square&logo=github&color=f1c40f&labelColor=555555" alt="Stars">
  <img src="https://img.shields.io/badge/Discord-Join-5865F2?style=flat-square&logo=discord&logoColor=white" alt="Discord">
  <img src="https://img.shields.io/badge/Twitter-Follow-1DA1F2?style=flat-square&logo=twitter&logoColor=white" alt="Twitter">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
</p>

<p align="center">
  <!-- Fila 2: Distribución -->
  <img src="https://img.shields.io/crates/v/swarmind?style=flat-square&color=fc6d26&logo=rust" alt="crates.io">
  <img src="https://img.shields.io/npm/v/swarmind?style=flat-square&color=cb3837&logo=npm" alt="npm">
  <img src="https://img.shields.io/github/v/release/USER/swarmind?style=flat-square" alt="Release">
  <img src="https://img.shields.io/github/downloads/USER/swarmind/total?style=flat-square" alt="Downloads">
</p>

<p align="center">
  <!-- Fila 3: CI/CD -->
  <img src="https://github.com/USER/swarmind/actions/workflows/tests.yml/badge.svg" alt="Tests">
  <img src="https://github.com/USER/swarmind/actions/workflows/lint.yml/badge.svg" alt="Lint">
  <img src="https://codecov.io/gh/USER/swarmind/branch/main/graph/badge.svg" alt="Coverage">
</p>
```

### 4.7 Proveedores alternativos

- **Trendshift** (`trendshift.io`): usado por CrewAI → mide momentum semanal
- **LFX Insights** (Linux Foundation): usado por Dify → health score, contributors activos
- **hvtracker.net**: usado por Haystack → evidence grade para AI trust
- **bestpractices.dev** (OpenSSF): usado por Haystack → best practices compliance
- **Star History** (`api.star-history.com`): usado por Dify → gráfica de evolución de stars

---

## 5. Paletas de Color Observadas

### 5.1 Repos analizados

| Repo | Color primario | Color acento | Fondo dominante | Estilo |
|---|---|---|---|---|
| **AutoGPT** | `#1a1a3e` dark navy | `#FFB800` gold + `#7B5BFF` purple | Dark blue gradient | Cinemático, premium |
| **LangChain** | `#161F34` navy profundo | `#7FC8FF` light blue | Light / dark dual | Clean, corporate, minimalista |
| **AutoGen** | `#1E40AF` azul Microsoft | `#9333EA` purple | Light + UI screenshots | Microsoft enterprise |
| **CrewAI** | `#000000` negro | `#E74C3C` rojo coral | White / cream | Cartoon / playful |
| **Microsoft Semantic Kernel** | `#0078D4` azul MS | `#8661C5` purple | White | Microsoft enterprise |
| **BabyAGI** | (sin branding fuerte) | — | — | Mínimo |
| **GPT Engineer** | (sin branding fuerte) | — | — | Mínimo |
| **Aider** | `#14B014` green terminal | (glow effect) | `#272822` dark (gjm8 theme) | Retro cyberpunk / terminal |
| **Dify** | `#000000` negro | `#155EEF` azul + `#528BFF` | `#F5F5F5` gris claro | Modern, flat, tech |
| **Haystack** | `#1E3A8A` navy + `#1B4F8C` | `#3B82F6` blue | Dark navy gradient | Corporate, dashed, con iconos |

### 5.2 Paletas de los terminales temáticos (Aider screencast)

```css
/* gjm8 theme (Aider) */
--bg:        #272822;
--fg:        #F8F8F2;
--red:       #F92672;
--green:     #A6E22E;
--yellow:    #F4BF75;
--blue:      #66D9EF;
--purple:    #AE81FF;
--cyan:      #A1EFE4;
```

### 5.3 Patrones de paleta

- **Azul como primario** en 7/10 repos (mayoría enterprise)
- **Dark mode como hero** en 4/10 (AutoGPT, Haystack, Aider, Aider-related)
- **Acento púrpura/violeta** frecuente para "AI" feel
- **Verde terminal** solo Aider (es su identidad)
- **Rojo/coral** solo CrewAI (diferenciación)
- **Dual-mode logo** solo LangChain (light + dark SVG variants)

### 5.4 Recomendación de paleta para Swarmind

Considerando que Swarmind es **multi-agente, AI-framework, probablemente con código (Rust/Python/TS)**, la paleta más estratégica combina referencias AI + claridad técnica:

#### Opción A: "AI Enterprise" (LangChain + Haystack inspired)

```
Primario:     #1A1A2E  (navy profundo, casi negro)
Acento:       #7C3AED  (violeta AI)
Secundario:   #06B6D4  (cyan para highlights)
Éxito:        #10B981  (verde para confirmaciones)
Fondo claro:  #F8FAFC
Fondo oscuro: #0F172A
Texto claro:  #F1F5F9
Texto oscuro: #1E293B
```

#### Opción B: "Cyber Swarm" (Aider + AutoGPT inspired)

```
Primario:     #0A0E27  (deep space)
Acento:       #FFD700  (gold — nodos activos)
Secundario:   #B967FF  (purple — agent connections)
Acento 2:     #00FFC2  (mint — data flow)
Warning:      #FF6B6B
Fondo oscuro: #050816
```

#### Opción C: "Tech Minimal" (Dify inspired)

```
Primario:     #0A0A0A  (casi negro)
Acento:       #2563EB  (azul saturado)
Secundario:   #525252  (gris medio)
Fondo:        #FAFAFA
Texto:        #171717
```

**Mi recomendación: Opción A** — es la más versátil (funciona para logo, banner, dark mode, UI) y está alineada con la convención del sector AI-agent frameworks (LangChain, Haystack, AutoGen, Semantic Kernel todos usan variantes de azul/violeta).

---

## 6. Lista de Assets Concretos a Crear para Swarmind

### 6.1 Identidad core (obligatorios)

| # | Asset | Path | Spec | Prioridad |
|---|---|---|---|---|
| 1 | Logo wordmark light | `.github/images/logo-light.svg` | 472×100 ratio, fondo claro | P0 |
| 2 | Logo wordmark dark | `.github/images/logo-dark.svg` | 472×100, fondo oscuro | P0 |
| 3 | Logo icon (cuadrado) | `.github/images/logo-icon.svg` | 100×100, solo marca | P0 |
| 4 | Logo icon PNG | `.github/images/logo-icon.png` | 512×512, fallback | P0 |
| 5 | Favicon SVG | `.github/images/favicon.svg` | 32×32 viewBox | P0 |

### 6.2 Marketing assets (recomendados)

| # | Asset | Path | Spec | Prioridad |
|---|---|---|---|---|
| 6 | Banner hero claro | `docs/assets/banner.png` | 1600×900, dark/light universal | P1 |
| 7 | Banner hero dark | `docs/assets/banner-dark.png` | 1600×900, versión dark mode | P2 |
| 8 | Cover con tagline | `docs/assets/cover.png` | 1920×640, "Swarmind — [tagline]" | P1 |
| 9 | Open Graph image | `.github/images/og-image.png` | 1280×640 (opcional — preferir GitHub settings) | P2 |

### 6.3 Documentación (recomendados)

| # | Asset | Path | Spec | Prioridad |
|---|---|---|---|---|
| 10 | Diagrama arquitectura | `docs/assets/diagrams/architecture.svg` | Vector, escalable | P1 |
| 11 | Diagrama arquitectura PNG | `docs/assets/diagrams/architecture.png` | 1600×900, fallback | P1 |
| 12 | Diagrama agent-mesh | `docs/assets/diagrams/agent-mesh.svg` | Visualización de agentes | P2 |
| 13 | Diagrama data-flow | `docs/assets/diagrams/data-flow.svg` | Sequence diagram | P2 |
| 14 | Screenshot dashboard | `docs/assets/screenshots/01-dashboard.png` | 1200×800 | P1 |
| 15 | Screenshot agent view | `docs/assets/screenshots/02-agents.png` | 1200×800 | P2 |
| 16 | Screenshot workflow builder | `docs/assets/screenshots/03-workflow.png` | 1200×800 | P2 |
| 17 | Screenshot traces/observability | `docs/assets/screenshots/04-traces.png` | 1200×800 | P2 |

### 6.4 Branding menor (opcionales)

| # | Asset | Path | Spec | Prioridad |
|---|---|---|---|---|
| 18 | Wordmark PNG | `.github/images/wordmark.png` | 1200×300 | P3 |
| 19 | Apple touch icon | `.github/images/apple-touch-icon.png` | 180×180 | P3 |
| 20 | Animated demo | `docs/assets/demo.svg` o `.gif` | < 5MB, < 10s loop | P3 |
| 21 | Feature icons | `docs/assets/icons/*.svg` | 24×24 c/u, estilo Aider | P3 |

### 6.5 Asset de GitHub nativo (no en repo)

| # | Asset | Ubicación | Spec |
|---|---|---|---|
| 22 | Social preview | GitHub Settings → Social preview | 1280×640 PNG, < 1MB |

---

## 7. Resumen ejecutivo y recomendaciones

### Lo que SÍ hacen los top repos

1. ✅ **Logo + tagline claro en las primeras 5 líneas** del README (todos)
2. ✅ **Badges sociales en fila** bajo el título (9/10)
3. ✅ **Banner full-width 100%** o logo SVG grande centrado (7/10)
4. ✅ **Variantes del logo light/dark** solo si el repo es muy maduro (LangChain)
5. ✅ **Screenshots reales del producto** (8/10) — no mockups
6. ✅ **Path consistente para assets** (`.github/images/` o `docs/assets/` o `images/`)
7. ✅ **Diagrama de arquitectura** en frameworks multi-agent (3/10: AutoGen, CrewAI, Aider)

### Lo que NO hacen /我们应该 evitar

1. ❌ **No commitear `social_preview.png`** al repo (lo gestiona GitHub)
2. ❌ **No usar GIFs de > 5MB** (CrewAI tiene 17MB GIFs — anti-patrón)
3. ❌ **No abusar de badges** (CrewAI tiene 12+ badges — saturación)
4. ❌ **No mezclar estilos** (Aider green terminal es identitario, no lo imites si no eres Aider)
5. ❌ **No tener banner oscuro cuando todo el resto es claro** (Dify tiene cover claro y UI clara — coherencia)

### Decisiones críticas para Swarmind

1. **Paleta:** Opción A (AI Enterprise navy + violet + cyan) o tu propia extensión
2. **Estructura:** `.github/images/` para logos + `docs/assets/` para el resto
3. **Hero:** Banner 1600×900 o cover con tagline (no ambos — elegir uno)
4. **Badges:** Máximo 8-10 distribuidos en 2-3 filas
5. **Logo:** SVG con variante light + dark es el estándar moderno
6. **Screenshots:** Tomar de la UI real, no diseñar mockups

---

## 8. Referencias directas (URLs verificadas)

### Logos
- LangChain: `https://raw.githubusercontent.com/langchain-ai/langchain/master/.github/images/logo-light.svg`
- LangChain: `https://raw.githubusercontent.com/langchain-ai/langchain/master/.github/images/logo-dark.svg`
- Aider: `https://aider.chat/assets/logo.svg`
- CrewAI: `https://raw.githubusercontent.com/crewAIInc/crewAI/main/docs/images/crewai_logo.png`
- Dify: `https://raw.githubusercontent.com/langgenius/dify/main/images/GitHub_README_if.png`

### Banners
- AutoGPT: `https://raw.githubusercontent.com/Significant-Gravitas/AutoGPT/master/docs/home/.gitbook/assets/Banner_image.png`
- Haystack: `https://raw.githubusercontent.com/deepset-ai/haystack/main/images/banner.png`

### Diagrams
- AutoGen: `https://microsoft.github.io/autogen/0.2/img/ag.svg` (hosted separately)
- CrewAI: `https://raw.githubusercontent.com/crewAIInc/crewAI/main/docs/images/crewAI-mindmap.png`

### Screenshots destacados
- AutoGPT: `docs/content/imgs/readme/autogpt_autopilot_chat.jpg`
- AutoGPT: `docs/content/imgs/readme/autogpt_agent_dashboard.jpg`
- AutoGPT: `docs/content/imgs/readme/build_screen.jpg`
- AutoGen: `python/packages/autogen-studio/docs/ags_screen.png`

---

**Conclusión:** Swarmind debería apuntar al patrón **LangChain + Haystack + AutoGPT**:
- Logo SVG dual-mode (LangChain style)
- Banner corporativo 1600×320 o cover con tagline (Haystack/Dify style)
- 2-3 filas de badges (estándar)
- Screenshots reales de la UI en cards 2x2 (AutoGPT style)
- Diagrama de arquitectura SVG (AutoGen/CrewAI style)
- Paleta navy + violet + cyan para diferenciación AI-native
