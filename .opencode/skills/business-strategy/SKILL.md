---

name: business-strategy
domain: business
description: "Analisis estrategico de negocios, modelos de negocio, analisis DOFA/SWOT, Porter, canvas, planes de negocio, ROI, KPIs de negocio, OKRs, y toma de decisiones estrategicas. UPG: usar ultima version estable (pyproject.toml/uv.lock al dia)"
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - ANALISIS_TYPE: dofa-swot, porter, pestel, canvas, OKR ({{ANALISIS_TYPE}})
  - INDUSTRY: tecnologia, salud, retail, finanzas, educacion ({{INDUSTRY}})
---
# Business Strategy — Analisis Estrategico de Negocios

## Descripcion
Skill para analisis estrategico, modelos de negocio y toma de decisiones empresariales. Complementa el enfoque tecnico con vision de negocio.

## Responsabilidades
1. Analisis DOFA (SWOT)/PESTEL/Porter de entornos de negocio
2. Diseno de modelos de negocio (Canvas, Lean Canvas)
3. Definicion de OKRs y KPIs de negocio
4. Analisis de ROI y viabilidad economica
5. Planificacion estrategica a corto/medio/largo plazo

## Comandos
- `!biz dofa <contexto>` — Analisis DOFA
- `!biz canvas <modelo>` — Generar Business Model Canvas
- `!biz okr <objetivo>` — Definir OKRs
- `!biz roi <inversion>` — Calcular ROI
- `!biz strategy <situacion>` — Plan estrategico

## Referencias
- Porter Five Forces
- Business Model Generation (Osterwalder)
- OKR (Doerr)
- Lean Startup (Ries)
