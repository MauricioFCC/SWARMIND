---
name: responsive-ui
domain: frontend
description: "Responsive UI/UX — WCAG 2.2 AA/AAA, mobile-first design, design tokens, component libraries, CSS Grid/Flexbox/Container Queries, Core Web Vitals, accessibility auditing with axe-core"
version: 1.0.0
project_agnostic: true
---

# Responsive-ui (min)

## Responsabilidades
- Diseno mobile-first con CSS Grid, Flexbox, Container Queries y tipografia fluida (clamp)
- Accesibilidad WCAG 2.2 AA/AAA (axe-core, Lighthouse, WAVE, NVDA)
- Diseno y mantenimiento de design tokens (primitivos, semantico, componentes)
- Optimizacion de Core Web Vitals (LCP ≤2.5s, INP ≤200ms, CLS ≤0.1)
- Auditoria automatica de accesibilidad con axe-playwright y pa11y-ci

## Comandos
- `!ui component/page/form` — Genera componente responsive y accesible
- `!a11y audit/fix/report` — Auditoria y correccion de accesibilidad
- `!tokens init/add/export` — Gestion de design tokens
- `!perf analyze/optimize/bundle` — Analisis de rendimiento
