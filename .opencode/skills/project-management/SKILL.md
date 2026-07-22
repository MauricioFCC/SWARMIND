---
name: project-management
domain: management
description: "Gestion de proyectos: metodologias agiles (Scrum, Kanban), planificacion, seguimiento, riesgos, estimaciones, y comunicacion con stakeholders."
version: 1.0.0
project_agnostic: true
inherit:
  - core/base_principles.md
variables:
  - METHODOLOGY: scrum, kanban, waterfall, hybrid ({{METHODOLOGY}})
  - FRAMEWORK: pmp, prince2, agile, safe ({{FRAMEWORK}})
---
# Project Management — Gestion de Proyectos

## Descripcion
Skill de gestion de proyectos con metodologias agiles y tradicionales.

## Responsabilidades
1. Planificacion y desglose de trabajo (WBS)
2. Gestion de riesgos y mitigacion
3. Seguimiento de avances y reporting
4. Estimacion de tiempos y recursos
5. Comunicacion con stakeholders

## Comandos
- `!pm plan <objetivo>` — Plan de proyecto
- `!pm risk <contexto>` — Matriz de riesgos
- `!pm retrospective` — Facilitar retrospectiva
- `!pm estimate <tarea>` — Estimacion
