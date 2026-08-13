---
name: frontend-uiux
domain: frontend
description: "Usar cuando el usuario construye interfaces o design systems. UI, UX, Generative UI, design systems, tokens, WCAG, componentes, A2UI, frontend. | UPG·NAM·FRS (reglas en base_principles.md)"
version: 1.0.0
project_agnostic: true
---

# Frontend-uiux (min)

## Responsabilidades
- Generacion de UI con Semantic Guidance jerarquico (Product → DesignSystem → Feature → Component)
- Diseno de sistemas con 3-tier tokens (Geeklego, 7onic, useVyre) y StyleSeed design rules (74 reglas)
- Validacion UX con WiserUI-Bench (300 pares A/B) y WCAG 2.2 AA audit automatizada
- Optimizacion de rendimiento: Core Web Vitals (LCP, INP, CLS), code splitting, streaming SSR
- Personalizacion sample-efficient con Bayesian active preference learning (kappa >0.6 en 10-15 queries)

## Comandos
- `!ui generate <description>` — Genera UI desde lenguaje natural (A2UI/OpenUI)
- `!a11y audit <path>` — Auditoria WCAG 2.2 AA completa
- `!ds token add/export` — Gestion de design tokens
- `!perf analyze <url>` — Analisis de Core Web Vitals
- `!ux validate` — Validacion WiserUI-Bench + ReFinE loop
