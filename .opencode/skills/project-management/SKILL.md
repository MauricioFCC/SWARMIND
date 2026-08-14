---




name: project-management
domain: management
description: "Usar cuando el usuario gestiona proyectos o metodologias. Scrum, Kanban, planificacion, seguimiento, riesgos, estimaciones, stakeholders. | UPG·NAM·FRS (reglas en base_principles.md)"
license: MIT
compatibility: 'Python 3.12+'
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
