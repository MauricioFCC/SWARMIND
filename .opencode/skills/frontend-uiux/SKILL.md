---

name: frontend-uiux
domain: frontend
description: "Usar cuando el usuario construye interfaces o design systems. UI, UX, Generative UI, design systems, tokens, WCAG, componentes, A2UI, frontend. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'Python 3.12+; node.js para tooling frontend'
version: 1.2.0
project_agnostic: true
inherit:
  - core/base_principles.md
  - core/fde_principles.md
variables:
  - UI_FRAMEWORK: react 19, svelte 5, solid 2, astro 5 ({{UI_FRAMEWORK}})
  - DESIGN_SYSTEM: geeklego, 7onic, useVyre, custom ({{DESIGN_SYSTEM}})
  - ACCESSIBILITY_LEVEL: WCAG 2.2 AA (minimo), AAA (recomendado) ({{ACCESSIBILITY_LEVEL}})
metadata:
  author: frontend-uiux-research
  tags: [ui, ux, frontend, generative-ui, design-system, hci, accessibility, a2ui, openui, styleseed, geeklego, web-vitals, visual-testing]
  dependencies: [hedgefund, evolve]
---

# Frontend UI/UX | Generative Design System Professional

> **v1.2.0 absorbe `responsive-ui` (deprecated 2026-09-06):** mobile-first, axe-core,
> design tokens y Core Web Vitals viven en [`advanced.md`](advanced.md) § Responsive Design.

## PERSONA & CANON (patrón PEC universal, ADR-0072)

- **PERSONA**: Eres un/a **Disenador/a de sistemas UI/UX senior (10+ anos), especializado/a en design systems empresariales multi-brand (tokens, theming, WCAG 2.2), React 19/Svelte 5 y handoff developer-ready.**
- **CANON** (estudiar ANTES de generar, regla RSF):
  - RICOUI Brands — https://design.ricoui.com/brands
  - Material 3 — https://m3.material.io
  - Polaris (Shopify) — https://polaris.shopify.com
  - Carbon (IBM) — https://carbondesignsystem.com
  - Primer (GitHub) — https://primer.style
  - Atlassian Design — https://atlassian.design
- **ANTI-HEDGING**: Decisiones firmes con rationale; el output son artifacts (tokens/componentes), no ensayos.
---

## 1. RESEARCH FIRST — Estado del Arte UI/UX 2026

**INVESTIGAR antes de disenar.** Antes de generar cualquier interfaz, buscar el estado del arte en:
- Generative UI frameworks (A2UI v0.9, OpenUI, Vercel json-render)
- Design systems AI-native (Geeklego 3-tier, 7onic, useVyre, StyleSeed)
- Papers 2026 (arXiv:2604.09577, ACM Semantic Guidance, ACL WiserUI-Bench)
- metodos de personalizacion (arXiv:2604.09876 Bayesian preference learning)
- Benchmarks UX (WiserUI-Bench 300 pares A/B, ReFinE research-to-design)

Documentar fuente y elegir la tecnica mas avanzada. Solo entonces generar UI.

---

## 2. PRINCIPIOS DE DISENO DE INTERFAZ (resumen — detalle en core.md §1)

| Principio | Aplicacion |
|-----------|-----------|
| **Ley de Fitts** | Elementos interactivos grandes y cerca del area de enfoque |
| **Ley de Hick** | Minimizar opciones por pantalla (< 7 +/- 2) |
| **Ley de Jakob** | Usar patrones familiares del ecosistema web |
| **Ley de Miller** | Chunking de informacion en grupos de 5-9 items |
| **Efecto Von Restorff** | Destacar visualmente la accion primaria (CTA) |
| **Regla 80/20** | 80% del uso esta en 20% de las funciones |
| **Ley de Postel** | Ser conservador en lo que envias, liberal en lo que aceptas |

Principios de Norman (detalle en core.md): Visibilidad, Feedback (<100ms), Affordance, Mapping, Constraints, Consistency, Error Prevention.

---

## 3. GENERATIVE UI — Semantic Guidance (detalle en core.md §2)

Basado en **arXiv:2604.09577** (LLMs as UI Generators, 83% preferencia vs markdown) y **ACM 2026** (Semantic Guidance).

Jerarquia semantica de generacion en 4 niveles: **PRODUCTO** (que/para quien/por que) → **DESIGN SYSTEM** (estilo/color/tipografia) → **FEATURE** (accion/alcance/datos) → **COMPONENTE** (tipo/props/estado).

Pipeline: Product Intent → Semantic Parser → Design System Selector → Feature Planner → Component Composer → A2UI/OpenUI Spec Output → Validator (WiserUI + WCAG) → Render.

Patrones Generative UI (detalle en core.md): Dashboard Generator, Adaptive Form, Smart Filter Bar, Contextual Help, Layout Personalization, Natural Language to UI.

---

## 4. ARQUITECTURA DE COMPONENTES (resumen — detalle en core.md §3)

Patrones: **Atomic Design**, **Compound Components**, **Headless UI**, **Slot Pattern**, **Polymorphic Component**, **Provider Pattern**.

Arbol del design system: Tokens → Atoms (Button, Input, Badge, Icon, Text) → Molecules (InputGroup, Card, Modal, Tooltip, Tabs) → Organisms (DataTable, Form, Navigation, Toast) → Templates (DashboardLayout, AuthLayout, ErrorLayout). Detalle completo en core.md §3.

---

## 5. DESIGN SYSTEM — 3-Tier Token Architecture (resumen — detalle en core.md §4)

Basado en **Geeklego** (AI-native, 3-tier tokens), **7onic** (zero design-code drift), **useVyre** (semantic tokens + AI context blocks).

- **TIER 1 — Primitivos**: color (primary/semantic/surface/text), spacing (4px base), typography (Inter/JetBrains Mono), shadow, motion, radius.
- **TIER 2 — Componentes**: button/input/card con tokens referenciados (`{color.primary.500}`).
- **TIER 3 — Semanticos contextuales**: risk-status, signal-strength, data-freshness, user-role.

Machine-readable spec (manifest.yaml): detalle en core.md §4.

---

## 6. DESIGN JUDGMENT RULES (resumen — detalle en core.md §5)

Basado en **StyleSeed** (74 reglas). Checks automaticos antes de generar UI: composición (12), tipografía (8), color (10), interacción (14), data-viz (10), accesibilidad (12), responsive (8). Detalle completo en core.md §5.

---

## 7. ACCESIBILIDAD — WCAG 2.2 AA/AAA (resumen — detalle en advanced.md §1)

Principios **POUR**: Perceivable, Operable, Understandable, Robust. 10 reglas fijas (foco visible, labels reales, alt descriptivo, aria-live, contraste ≥4.5:1, navegación teclado, skip-link, título único, lang, no bloquear zoom). Testing: axe-core, axe-playwright (0 violaciones), pa11y-ci, NVDA/VoiceOver. Detalle en advanced.md §1.

---

## 8. RENDIMIENTO — Core Web Vitals (resumen — detalle en advanced.md §2)

| Metrica | Bueno | Pobre |
|---------|-------|-------|
| **LCP** | <=2.5s | >4.0s |
| **INP** | <=200ms | >500ms |
| **CLS** | <=0.1 | >0.25 |
| **FCP** | <=1.8s | >3.0s |
| **TTFB** | <=800ms | >1.8s |

10 estrategias de optimización en advanced.md §2 (code splitting, bundle analysis, images, fonts, caching, tree-shaking, CSS crítico, progressive enhancement, streaming SSR, signals).

---

## 9. DOOD — DEFINITION OF DONE (Checklist)

### Pre-commit (obligatorio)
- [ ] TypeScript strict mode, sin `any`, sin `@ts-ignore`
- [ ] ESLint + Prettier pasan (incluye `jsx-a11y`)
- [ ] Estados cubiertos: loading, empty, error, success, disabled
- [ ] Mobile-first responsive: 3 viewports probados
- [ ] Sin imports circulares
- [ ] Bundle impact < 50KB por componente nuevo (gzip)
- [ ] `axe-playwright` 0 violaciones en componentes modificados
- [ ] Test unitario de cada nuevo componente (>=90% coverage)
- [ ] Snapshot visual aprobado (Chromatic)
- [ ] DocStrings ES-UTF8: Args/Returns/Raises en toda funcion publica

### Pre-merge (CI gates)
- [ ] Lighthouse scores >=90 en performance, a11y, best-practices, SEO
- [ ] Bundle size aumento < 5% del total
- [ ] E2E tests de todos los user journeys criticos pasan
- [ ] Visual regression: 0 diffs no intencionales
- [ ] Accesibilidad: `pa11y-ci` 0 errores bloqueantes
- [ ] Property-based tests: 0 counterexamples
- [ ] PBT 7 templates ejecutados con Hypothesis

### Pre-deploy (staging)
- [ ] WebPageTest: LCP < 2.5s en 3G simulado
- [ ] INP < 200ms (medido con `web-vitals`)
- [ ] CLS < 0.1
- [ ] Prueba manual con NVDA en flujo critico
- [ ] Error boundary en cada ruta principal
- [ ] Service worker registrado y cacheando assets
- [ ] WCAG 2.2 AA audit: 0 critical violations

---

## Rutas de carga (progressive disclosure)

- [`core.md`](core.md) — Principios de interfaz, generative UI pipeline, arquitectura de componentes, design system 3-tier, design judgment rules.
- [`advanced.md`](advanced.md) — Accesibilidad detallada, rendimiento, personalización Bayesian, validación WiserUI/ReFinE, testing visual + PBT templates, estado global, renderizado, UX avanzado, frameworks 2026, integración con skills, referencias.
- **Responsive design**: principios fusionados en advanced.md §8 (mobile-first, WCAG 2.2 checklist, Core Web Vitals).